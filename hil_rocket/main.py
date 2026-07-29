"""
main.py
MONK HIL V2 entry point.

Boots the FastAPI server in a background thread and runs the real 6DOF
physics sim loop on the main thread. Reads launch parameters from
sim_state (set by the /launch endpoint) to configure the rocket, motor,
and TVC controller, then integrates physics forward each tick, updating
sim_state so the WebSocket broadcaster can stream it to the dashboard.
"""

import time
import threading
import webbrowser
import uvicorn
import logging
import numpy as np
from typing import Optional

from server.app import app
from server.state import sim_state

from simulator.physics import RocketPhysics, RocketConfig, quat_to_rotmat, quat_to_euler
from simulator.motors import get_motor, build_custom_motor
from simulator.sensors import IMUSensor, BarometerSensor
from simulator.tvc import TVCActuator, TVCActuatorConfig, OfflinePDController, PDGains
from comms.uart import UARTManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

SIM_HZ   = 200        # physics integration rate (RK4 needs a reasonably fine step)
HOST     = "127.0.0.1"
PORT     = 8000
G        = 9.80665


def _resolve_motor(motor_params: Optional[dict]):
    """
    Always returns a valid Motor — falls back to F15-0 if the requested
    motor name isn't found. F15-0 is a hardcoded entry in the Estes DB
    (simulator/motors.py) so this fallback can never itself return None.
    """
    fallback = get_motor("F15-0")
    assert fallback is not None, "F15-0 missing from ESTES_DB — check simulator/motors.py"

    if not motor_params:
        return fallback
    if motor_params.get("type") == "estes":
        m = get_motor(motor_params.get("name", "F15-0"))
        return m if m is not None else fallback
    tc = motor_params.get("thrust_curve")
    return build_custom_motor(
        name=motor_params.get("name", "Custom"),
        avg_thrust_n=float(motor_params.get("avg_thrust", 15.0)),
        burn_time_s=float(motor_params.get("burn_time", 3.0)),
        total_impulse_ns=motor_params.get("impulse"),
        thrust_curve=tc,
    )


def _build_rocket_config(params: dict, aero: Optional[dict]) -> RocketConfig:
    """
    Build RocketConfig from launch-screen params + Barrowman aero results.
    Falls back to sane defaults if aero analysis wasn't run (no STL).
    """
    mass = float(params.get("mass", 0.5))
    moment_arm = float(params.get("moment_arm", 0.15))
    cd = float(params.get("cd", 0.45))

    if aero and aero.get("rocket_diameter"):
        diameter = aero["rocket_diameter"]
        ref_area = np.pi * (diameter/2)**2
        # Cp-CG margin: Barrowman gives Cp from nose; approximate CG at
        # ~55% of body length from nose for a typical TVC-heavy layout
        # (battery/motor mass concentrated toward the tail) if not
        # otherwise specified — this is a simplification flagged for the
        # user, not a precise mass-property computation.
        cp_from_nose = aero.get("cp_from_nose", aero["rocket_length"]*0.15)
        cg_from_nose = aero["rocket_length"] * 0.55
        cp_from_cg = cg_from_nose - cp_from_nose   # positive = Cp ahead of CG (destabilizing)
        cn_alpha = aero.get("cn_alpha", 2.0)
    else:
        ref_area = np.pi * (0.0765/2)**2   # ~76.5mm default diameter
        cp_from_cg = 0.08
        cn_alpha = 2.0

    return RocketConfig(
        dry_mass=mass,
        moment_arm=moment_arm,
        cd=cd,
        ref_area=ref_area,
        cp_from_cg=max(cp_from_cg, 0.01),
        cn_alpha=cn_alpha,
        inertia_pitch=0.25,   # reasonable default for a ~0.5-1kg slender rocket
        inertia_roll=0.01,
        tvc_max_deg=10.0,
    )


class SimRunner:
    """Owns the live physics/sensor/comms objects for the current flight."""

    def __init__(self):
        self.phys: Optional[RocketPhysics] = None
        self.imu = IMUSensor()
        self.baro = BarometerSensor()
        self.tvc_actuator = TVCActuator(TVCActuatorConfig())
        self.controller = OfflinePDController(PDGains())
        self.uart: Optional[UARTManager] = None
        self.mission_start_t = None
        self.armed = False

    def arm(self):
        """Called once when /launch fires — build physics from sim_state params."""
        params = sim_state.launch_params
        motor = _resolve_motor(params.get("motor", {}))
        config = _build_rocket_config(params, params.get("aero"))

        prop_mass_kg = motor.prop_mass_g / 1000.0
        self.phys = RocketPhysics(config, motor, propellant_mass=prop_mass_kg)
        self.phys.ignite(0.0)

        com_port = params.get("com_port", "").strip()
        self.uart = UARTManager(port=com_port if com_port else None)

        self.mission_start_t = time.perf_counter()
        self.armed = True
        logger.info(
            f"Armed: motor={motor.name}  mass={config.dry_mass}kg  "
            f"cp_from_cg={config.cp_from_cg:.3f}m  hw={'ON' if self.uart.connected else 'OFFLINE'}"
        )

    def tick(self, dt: float):
        if not self.armed or self.phys is None:
            return

        phys = self.phys
        R = quat_to_rotmat(phys.state.quat)
        nose_world = R @ np.array([0, 0, 1.0])
        tilt_x = float(np.degrees(np.arctan2(nose_world[0], nose_world[2])))
        tilt_y = float(np.degrees(np.arctan2(nose_world[1], nose_world[2])))

        # ── Attitude control: hardware-in-the-loop if connected, else offline PD ──
        hw_connected = self.uart.connected and self.uart.link_quality() > 0
        actuator_cmd = self.uart.get_latest_actuator_command() if self.uart.connected else None

        if actuator_cmd is not None:
            pitch_cmd, yaw_cmd = actuator_cmd.servo_pitch_deg, actuator_cmd.servo_yaw_deg
        else:
            pitch_cmd, yaw_cmd = self.controller.compute(
                tilt_x, tilt_y, phys.state.omega, phys.last_dynamic_pressure
            )

        actual_pitch, actual_yaw = self.tvc_actuator.update(pitch_cmd, yaw_cmd, dt)
        phys.set_tvc_command(actual_pitch, actual_yaw)

        # ── Integrate physics ────────────────────────────────────────────────
        phys.step(dt)

        # ── Sensors (true body-frame specific force + gyro rate) ─────────────
        R_new = quat_to_rotmat(phys.state.quat)

        # Accelerometer reads specific force (thrust+drag, NOT gravity — an
        # accelerometer in free-fall reads zero). Approximated along the
        # body +Z axis, which is exact at zero AoA and a reasonable
        # simplification for synthetic sensor telemetry at the small AoA
        # this rocket's controller is designed to maintain.
        mass_now = phys.current_mass(phys.state.t)
        thrust_specific = phys.last_thrust / max(mass_now, 1e-6)
        drag_specific   = phys.last_drag_force / max(mass_now, 1e-6)
        specific_force_body = np.array([0.0, 0.0, thrust_specific - drag_specific])

        noisy_accel, noisy_gyro = self.imu.sample(specific_force_body, phys.state.omega, dt)
        noisy_baro_alt = self.baro.sample(phys.state.pos[2], dt)

        # ── Send synthetic sensor packet to HW (or offline no-op) ────────────
        self.uart.send_sensor_packet(
            noisy_accel[0], noisy_accel[1], noisy_accel[2],
            noisy_gyro[0], noisy_gyro[1], noisy_gyro[2],
            noisy_baro_alt,
        )

        # ── Push everything into sim_state for the dashboard ──────────────────
        euler = quat_to_euler(phys.state.quat)
        burn_remaining = max(0.0, phys.burn_time - phys.state.t) if phys.ignition_time is not None else 0.0

        sim_state.update(
            flight_phase       = phys.get_phase(),
            mission_clock      = phys.state.t,
            pos                = phys.state.pos.tolist(),
            vel                = phys.state.vel.tolist(),
            attitude_q         = phys.state.quat.tolist(),
            euler              = euler.tolist(),
            angular_rate       = phys.state.omega.tolist(),
            speed              = float(np.linalg.norm(phys.state.vel)),
            mach               = phys.last_mach,
            g_load             = phys.last_g_load,
            dynamic_pressure   = phys.last_dynamic_pressure,
            drag_force         = phys.last_drag_force,
            aoa                = phys.last_aoa_deg,
            thrust             = phys.last_thrust,
            burn_remaining     = burn_remaining,
            imu_accel          = noisy_accel.tolist(),
            imu_gyro           = noisy_gyro.tolist(),
            baro_alt           = noisy_baro_alt,
            baro_true_alt      = phys.state.pos[2],
            baro_error         = noisy_baro_alt - phys.state.pos[2],
            uart_packets_sent  = self.uart.packets_sent,
            uart_packet_rate   = self.uart.packets_sent / max(phys.state.t, 0.01),
            uart_last_packet   = self.uart.last_packet_sent[:60],
            hw_connected       = hw_connected,
            hw_servo_pitch     = actual_pitch,
            hw_servo_yaw       = actual_yaw,
            hw_link_quality    = self.uart.link_quality(),
        )

        if phys.state.landed and not sim_state.paused:
            sim_state.update(flight_phase="LANDED")


runner = SimRunner()


def sim_loop():
    """Main physics loop — ticks at SIM_HZ, integrates real 6DOF dynamics."""
    dt = 1.0 / SIM_HZ
    last_hz_update = time.perf_counter()
    tick_count = 0
    was_launched = False

    logger.info(f"Sim loop started at {SIM_HZ} Hz")

    while True:
        loop_start = time.perf_counter()

        while sim_state.paused:
            time.sleep(0.02)
            last_hz_update = time.perf_counter()   # don't count paused time toward Hz

        if not sim_state.launched:
            time.sleep(0.02)
            continue

        if not was_launched:
            runner.arm()
            was_launched = True

        sim_state.record_history()
        runner.tick(dt)

        tick_count += 1
        now = time.perf_counter()
        if now - last_hz_update >= 1.0:
            sim_state.update(loop_hz=tick_count / (now - last_hz_update))
            tick_count = 0
            last_hz_update = now

        elapsed = time.perf_counter() - loop_start
        sleep_for = dt - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)


def run_server():
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  MONK HIL V2")
    logger.info("=" * 60)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logger.info(f"Server running at http://{HOST}:{PORT}")

    time.sleep(1.2)
    webbrowser.open(f"http://{HOST}:{PORT}")

    try:
        sim_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
        if runner.uart:
            runner.uart.close()
