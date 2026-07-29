import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from server.ws_manager import ws_manager
from server.upload import router as upload_router
from server.state import sim_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MONK HIL V2")

FRONTEND = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
app.include_router(upload_router)


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(FRONTEND / "launch.html")

@app.get("/flight")
async def flight():
    return FileResponse(FRONTEND / "flight.html")

@app.get("/windtunnel")
async def windtunnel():
    return FileResponse(FRONTEND / "windtunnel.html")


# ── Aero analysis ─────────────────────────────────────────────────────────────

@app.post("/aero/analyze")
async def aero_analyze():
    """
    Run Barrowman + mass props on the uploaded assembly STL.
    Returns Cp, Cd, geometry summary, Cd curve, the actual radius
    profile extracted from the STL, and a solved ring-source potential
    flow field (validated axisymmetric panel method — see
    aero/flow_field.py for methodology and known limitations).
    """
    from aero.mesh_import import load_assembly, get_rocket_silhouette
    from aero.barrowman import run_barrowman
    from aero.flow_field import solve_ring_sources

    stl_path = Path("uploads/stl/assembly.stl")
    if not stl_path.exists():
        raise HTTPException(status_code=400, detail="No assembly STL uploaded yet")

    try:
        assembly = load_assembly(stl_path)
        result   = run_barrowman(assembly)
    except Exception as e:
        logger.error(f"Aero analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Extract actual silhouette (200 points, tail=0 -> nose=total_length)
    silhouette = get_rocket_silhouette(assembly, n_points=200)
    profile = [
        {"z": round(float(z), 5), "r": round(float(r), 5)}
        for z, r in silhouette
    ]

    # Solve the ring-source panel method against the REAL profile
    try:
        flow_solution = solve_ring_sources(
            silhouette[:, 0], silhouette[:, 1],
            n_rings=90, m_points=32,
        )
        flow_field_data = {
            "z_rings": [round(float(z), 5) for z in flow_solution.z_rings],
            "r_rings": [round(float(r), 5) for r in flow_solution.r_rings],
            "q_unit":  [round(float(q), 8) for q in flow_solution.Q_unit],
            "m_points": flow_solution.M,
            "solve_quality": flow_solution.summary(),
        }
        logger.info(f"Flow field solved: {flow_solution.summary()}")
    except Exception as e:
        logger.error(f"Ring-source solve failed: {e}")
        flow_field_data = None

    # Store in shared state so flight dashboard and wind tunnel can access it
    sim_state.update(
        cp_location    = result.cp_from_nose,
        cg_location    = 0.0,   # updated after launch with mass from params
        rocket_length  = assembly.total_length,
        rocket_diameter= assembly.body_diameter,
        cd_curve       = result.cd_curve,
        rocket_profile = profile,
        stl_uploaded   = True,
        stl_paths      = {"assembly": str(stl_path)},
        flow_field_data= flow_field_data,
    )

    return {
        "cp_from_nose":   result.cp_from_nose,
        "cp_from_tail":   result.cp_from_tail,
        "cd0":            result.cd0,
        "cn_alpha":       result.cn_alpha_total,
        "nose_length":    result.nose_length,
        "rocket_length":  assembly.total_length,
        "rocket_diameter": assembly.body_diameter,
        "cd_curve":       result.cd_curve,
        "profile":        profile,
        "rocket_profile": profile,
        "flow_field":     flow_field_data,
    }


@app.get("/aero")
async def aero_get():
    """Return current aero state for wind tunnel. Keys match /aero/analyze exactly."""
    return {
        "cp_from_nose":   sim_state.cp_location,
        "cg":             sim_state.cg_location,
        "stability_margin": sim_state.stability_margin,
        "cd_curve":       sim_state.cd_curve,
        "rocket_length":  sim_state.rocket_length,
        "rocket_diameter": sim_state.rocket_diameter,
        "rocket_profile": sim_state.rocket_profile,
        "profile":        sim_state.rocket_profile,
        "flow_field":     sim_state.flow_field_data,
        "stl_uploaded":   sim_state.stl_uploaded,
    }


# ── Launch ────────────────────────────────────────────────────────────────────

class LaunchParams(BaseModel):
    mass:       float
    moment_arm: float
    cd:         float
    com_port:   str = ""
    duration:   float = 60.0
    motor:      dict
    aero:       Optional[dict] = None


@app.post("/launch")
async def launch(params: LaunchParams):
    """Receive launch parameters from the launch screen and arm the sim."""
    # Resolve motor object
    from simulator.motors import get_motor, build_custom_motor
    motor_p = params.motor

    if motor_p.get("type") == "estes":
        motor = get_motor(motor_p.get("name", "F15-0"))
        if motor is None:
            raise HTTPException(status_code=400, detail=f"Unknown motor: {motor_p.get('name')}")
    else:
        tc = motor_p.get("thrust_curve")
        motor = build_custom_motor(
            name          = motor_p.get("name", "Custom"),
            avg_thrust_n  = float(motor_p.get("avg_thrust", 15.0)),
            burn_time_s   = float(motor_p.get("burn_time", 3.0)),
            total_impulse_ns = motor_p.get("impulse"),
            thrust_curve  = tc,
        )

    # Store everything in shared state
    sim_state.update(
        launch_params = params.model_dump(),
        launched      = True,
        motor_name    = motor.name,
    )

    # Pass motor and rocket params to sim (will be picked up by main loop)
    sim_state._motor  = motor
    sim_state._params = params

    logger.info(
        f"Launch: motor={motor.name}  mass={params.mass}kg  "
        f"moment_arm={params.moment_arm}m  port='{params.com_port}'"
    )
    return {"status": "launched", "motor": motor.summary()}


# ── Sim control ───────────────────────────────────────────────────────────────

@app.post("/pause")
async def pause():
    sim_state.update(paused=True)
    return {"status": "paused"}

@app.post("/resume")
async def resume():
    sim_state.update(paused=False)
    return {"status": "resumed"}

@app.get("/history")
async def history():
    return sim_state.get_history()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            try:
                msg  = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
                data = json.loads(msg)
                if data.get("cmd") == "pause":
                    sim_state.update(paused=True)
                elif data.get("cmd") == "resume":
                    sim_state.update(paused=False)
                elif data.get("cmd") == "ping":
                    await ws.send_text(json.dumps({"pong": True}))
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(ws)


async def broadcast_loop(hz: float = 20.0):
    interval = 1.0 / hz
    while True:
        await asyncio.sleep(interval)
        if ws_manager.client_count > 0:
            await ws_manager.broadcast(sim_state.snapshot())


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop(hz=20))
    logger.info("MONK HIL V2 server started — broadcast loop at 20 Hz")
