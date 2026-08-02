# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MONK HIL V2 — a hardware-in-the-loop (HIL) simulator for a fin-less, TVC-only (thrust-vector-controlled)
model rocket. It runs a real 6DOF rigid-body physics simulation, generates synthetic noisy sensor data
(IMU + barometer), streams it over UART to a real flight computer ("MONK board"), reads back actuator
(servo) commands, and visualizes the flight live in a browser dashboard. If no flight computer is
connected, an offline PD controller takes over so the sim still flies.

The rocket has **no fins** — Cp sits ahead of CG, so it is aerodynamically unstable by design and depends
entirely on active TVC to stay upright. This is a deliberate physical property of the vehicle, not a bug
in the sim.

## Running it

```
cd hil_rocket
python main.py
```

This starts a FastAPI server (uvicorn) on a background thread at `http://127.0.0.1:8000` and opens it in
a browser, while the main thread runs the 200 Hz physics loop. There is no separate frontend build step —
`server/frontend/*.html` are served directly as static files (vanilla JS + Three.js via CDN, no bundler).

There is no requirements.txt; dependencies are whatever's installed into `.venv` (numpy, scipy, fastapi,
uvicorn, pydantic, trimesh, pyserial, matplotlib, python-dotenv, pyyaml, python-multipart). `pyrightconfig.json`
points at `.venv` for type checking.

There is no test runner configured (no pytest installed, no test suite). `hil_rocket/test_aero.py` is a
manual smoke-test script (run with `python test_aero.py` from inside `hil_rocket/`) that exercises the
aero + motor pipeline and prints results — it has no assertions and is not run in CI.

## Architecture

### Two loops, one shared state

`main.py` is the entry point. It starts the FastAPI app (`server/app.py`) in a daemon thread and runs
`sim_loop()` on the main thread at `SIM_HZ = 200`. The two sides never call each other directly — they
communicate only through the single shared `sim_state` singleton (`server/state.py`), an `RLock`-protected
object with a `snapshot()` method for thread-safe reads. `SimRunner.tick()` (in `main.py`) is what
actually advances physics each frame; `broadcast_loop()` in `app.py` pushes `sim_state.snapshot()` to all
connected WebSocket clients at 20 Hz. `sim_state.record_history()` buffers ~20 Hz snapshots for the
flight-scrubber/replay UI (`GET /history`).

Flow per tick (`SimRunner.tick` in `main.py`):
1. Read current attitude → compute tilt from vertical.
2. If UART hardware is connected and sending actuator commands, use those; otherwise fall back to
   `OfflinePDController` (`simulator/tvc.py`).
3. Slew the commanded angles through `TVCActuator` (rate-limited, models real servo response).
4. Step `RocketPhysics` (RK4 integration) forward by `dt`.
5. Sample synthetic IMU/baro readings from the new true state.
6. Send a sensor packet over UART (no-op if offline).
7. Push everything into `sim_state`.

### Physics core (`simulator/`)

- `physics.py` — `RocketPhysics`: full 6DOF RK4 integration, quaternion attitude (`[w,x,y,z]`, body Z =
  nose/thrust axis), Barrowman-style destabilizing normal-force torque, TVC thrust-vector torque, ground
  collision. Coordinate convention: world frame X=east, Y=north, Z=up; body frame Z=nose. Motor thrust
  and mass-loss-over-burn are both driven by the `Motor`/`ThrustCurve` object.
- `motors.py` — `Motor`/`ThrustCurve` model plus a built-in Estes motor database (`ESTES_DB`), a RASP
  `.eng` file parser (`parse_eng_file`), and a custom-motor builder (`build_custom_motor`). `get_motor()`
  always has a safe fallback path in `main.py._resolve_motor` (defaults to `F15-0`).
- `tvc.py` — `TVCActuator` (rate-limited servo model) and `OfflinePDController` (gain-scheduled PD law,
  gains scale with dynamic pressure). Read the module docstring before touching gains: the sign
  conventions were empirically validated against the physics sim, not hand-derived, and the controller has
  **zero authority after motor burnout by design** (TVC torque ∝ thrust; thrust=0 at burnout means no
  torque regardless of commanded angle) — the vehicle tumbling post-burnout is correct physics, not a bug.
- `sensors.py` — `IMUSensor`/`BarometerSensor`: noise + slow bias-walk models tuned to resemble a real
  MPU-6050 + MS5611, matching what the physical MONK board would see.

### Aero pipeline (`aero/`)

Triggered by `POST /aero/analyze` in `server/app.py`, reading `uploads/stl/assembly.stl` (a single
full-rocket assembly STL exported from CAD: centerline on Z, tail at Z=0, nose in +Z, mm units).

1. `mesh_import.load_assembly()` — auto-detects STL units, slices the mesh into a radius-vs-Z profile
   (500 slices, windowed-max + smoothing to bridge small gaps between mated CAD parts).
2. `barrowman.run_barrowman()` — re-derives nosecone/body/fin geometry from that profile (nose shape
   classified by curve fit, fins detected by radius spikes above body radius) and runs the classic
   Barrowman equations for Cp location, CNα, and a Cd0 estimate.

Results are cached into `sim_state` (`cp_location`, `cd_curve`, `rocket_profile`, etc.) so the flight
dashboard can read them via `GET /aero` without re-running the analysis.

**Note:** the wind-tunnel visualization page and its ring-source flow-field solver (`aero/flow_field.py`)
have been removed. Only the Barrowman pipeline (Cp/Cd/geometry) remains — it still feeds the launch
screen's aero readout and the stability-margin display on the flight dashboard.

**Note:** `aero/mass_props.py` (`compute_mass_props`) expects a multi-component assembly API
(`assembly.components`, a `ComponentMesh` type) that no longer exists on `RocketAssembly` in the current
single-assembly `mesh_import.py`, and nothing in the app imports it. Treat it as stale/disconnected from
the current pipeline rather than a working code path.

### Comms (`comms/`)

`uart.py`'s `UARTManager` runs serial I/O on a background thread (a receive loop parsing incoming lines,
non-blocking sends) so the 200 Hz sim loop never stalls on serial I/O. If no COM port is given, or the
port fails to open, it transparently runs in "offline" mode — `main.py` and `tvc.py`'s offline PD
controller pick up attitude control in that case. `packet.py` defines the wire protocol: `$S,...` sensor
packets sim→board, `$A,...` actuator packets board→sim.

### Server (`server/`)

- `app.py` — all HTTP/WebSocket routes. Key endpoints: `POST /launch` (arms the sim with rocket/motor
  params from the launch screen), `POST /aero/analyze` + `GET /aero`, `POST /upload/stl/assembly` and
  `POST /upload/eng` (in `upload.py`), `POST /pause` / `POST /resume`, `GET /history` (flight scrubber),
  and `/ws` (WebSocket telemetry stream).
- `state.py` — `sim_state`, the single shared `SimState` singleton described above.
- `ws_manager.py` — tracks connected WebSocket clients and broadcasts JSON snapshots, silently dropping
  dead connections.
- `upload.py` — STL/`.eng` file upload endpoints; files are saved to fixed paths (`uploads/stl/assembly.stl`,
  `uploads/eng/custom.eng`), overwriting any previous upload.
- `frontend/` — two static HTML pages, no build step: `launch.html` (rocket/motor/COM-port config) and
  `flight.html` (live mission-control-style flight dashboard: chase-cam 3D viewer, telemetry panels,
  charts, event timeline — Three.js via CDN, 1 Three.js unit = 1 real metre).

### Note on `config.py`

`hil_rocket/config.py` (`CONFIG` dict) is not imported anywhere in the current codebase — launch
parameters instead flow through `LaunchParams` (pydantic model in `server/app.py`) and `sim_state.launch_params`.
Don't assume changes to `config.py` affect a running simulation.

## Working in this codebase

- All modules import using paths relative to `hil_rocket/` as the root (e.g. `from simulator.physics import
  ...`, `from aero.mesh_import import ...`) — run scripts from inside `hil_rocket/`, not the repo root.
- Distances/angles in physics and aero code follow the conventions stated at the top of each module's
  docstring (nose-first vs. tail-first Z, degrees vs. radians) — check the local convention before wiring
  new values through, since it differs between `physics.py` (body Z=nose, world Z=up) and
  `mesh_import.py`/`barrowman.py` (profile Z: tail=0 in the raw STL, but Barrowman internally flips to
  nose-first).
- Several modules (`tvc.py`, `physics.py`) have long docstrings explaining *why* a particular
  simplification or numerical approach was chosen, including known limitations that were deliberately
  left as-is (e.g. no TVC authority after burnout, accelerometer approximated along body +Z at low AoA).
  Read those before "fixing" what looks like an oversight.
