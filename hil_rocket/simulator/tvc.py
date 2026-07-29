"""
tvc.py
TVC servo actuator model (rate-limited, matching real servo response —
commands don't apply instantly, they slew at a maximum angular rate) and
the offline-fallback PD attitude controller used when no flight computer
is connected over UART.

CONTROLLER NOTE (read before changing gains):
This PD law was empirically validated this session against the actual
6DOF physics (RK4-integrated, quaternion-based rigid body dynamics) —
NOT hand-derived from first principles, because several hand-derived
sign conventions turned out wrong when checked numerically. Both P and D
term signs were independently confirmed via isolated single-variable
tests before being combined.

KNOWN, PHYSICALLY REAL LIMITATION (not a bug): TVC torque is proportional
to thrust magnitude (torque = thrust x sin(gimbal_angle) x moment_arm).
The instant the motor burns out, thrust=0, so TVC produces ZERO
corrective torque regardless of commanded gimbal angle — exactly like
trying to steer a car with the engine off. Since this rocket has no fins
for passive aerodynamic stability, it is fundamentally uncontrollable
during coast/descent and WILL tumble after burnout. This matches real
TVC-only vehicle physics (missiles/sounding rockets with active guidance
are only attitude-controllable while thrusting) and is not something
this offline controller can or should try to fix.

Gain scheduling: the destabilizing aerodynamic torque grows with dynamic
pressure (q ~ v^2), so fixed PD gains cannot handle the full boost speed
range — gains are scaled proportionally to q_dynamic (floored at q_ref
so authority doesn't vanish near the pad) to keep pace.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class TVCActuatorConfig:
    max_deflection_deg: float = 10.0   # matches RocketConfig.tvc_max_deg
    max_slew_rate_dps:  float = 250.0  # deg/s, realistic small hobby servo


class TVCActuator:
    """
    Models the physical servo: commands are rate-limited (a servo cannot
    snap instantly to a new angle), not applied as a step function.
    """

    def __init__(self, config: Optional[TVCActuatorConfig] = None):
        self.cfg = config or TVCActuatorConfig()
        self.pitch_angle = 0.0   # current actual gimbal angle (deg)
        self.yaw_angle   = 0.0

    def update(self, pitch_cmd_deg: float, yaw_cmd_deg: float, dt: float):
        """Slew the actual servo angle toward the commanded angle."""
        max_step = self.cfg.max_slew_rate_dps * dt

        pitch_cmd_deg = np.clip(pitch_cmd_deg, -self.cfg.max_deflection_deg, self.cfg.max_deflection_deg)
        yaw_cmd_deg   = np.clip(yaw_cmd_deg,   -self.cfg.max_deflection_deg, self.cfg.max_deflection_deg)

        d_pitch = np.clip(pitch_cmd_deg - self.pitch_angle, -max_step, max_step)
        d_yaw   = np.clip(yaw_cmd_deg   - self.yaw_angle,   -max_step, max_step)

        self.pitch_angle += d_pitch
        self.yaw_angle   += d_yaw

        return self.pitch_angle, self.yaw_angle


@dataclass
class PDGains:
    kp: float = 1.5
    kd: float = 10.0
    q_ref: float = 100.0   # Pa, dynamic pressure floor for gain scheduling


class OfflinePDController:
    """
    Fallback attitude controller used when no MONK board is connected.
    Empirically validated (see module docstring) to keep tilt bounded
    during powered flight from a realistic disturbance. Has NO authority
    once thrust reaches zero — this is real physics, not a limitation of
    the controller.
    """

    def __init__(self, gains: Optional[PDGains] = None):
        self.gains = gains or PDGains()

    def compute(self, tilt_x_deg: float, tilt_y_deg: float,
                omega_body: np.ndarray, dynamic_pressure: float) -> tuple:
        """
        Returns (pitch_cmd_deg, yaw_cmd_deg).
        tilt_x/tilt_y: nose direction tilt from vertical (degrees).
        omega_body: body-frame angular rate (rad/s).
        dynamic_pressure: current q (Pa), used for gain scheduling.
        """
        q = max(dynamic_pressure, self.gains.q_ref)
        sched = q / self.gains.q_ref
        kp = self.gains.kp * sched
        kd = self.gains.kd * sched

        pitch_cmd = -kp*tilt_y_deg - kd*np.degrees(omega_body[0])
        yaw_cmd   = -kp*tilt_x_deg - kd*np.degrees(omega_body[1])
        return pitch_cmd, yaw_cmd
