"""
physics.py
6DOF rigid-body rocket physics: RK4 integration, quaternion attitude
propagation, aerodynamic drag + destabilizing normal-force torque (this
rocket has no fins — Cp sits ahead of CG, so it is aerodynamically
UNSTABLE and relies on active TVC to stay upright, same as the real
hardware), TVC thrust-vector force/torque coupling, ground collision.

Coordinate conventions:
  World frame: X=east, Y=north, Z=up. Z=0 is the pad/ground.
  Body frame:  Z=nose (thrust axis), X/Y perpendicular to the body axis.
  Quaternion:  [w, x, y, z], rotates body-frame vectors into world frame.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

G = 9.80665       # m/s^2
RHO0 = 1.225      # kg/m^3, sea-level air density (simple constant-density model)


# ── Quaternion helpers ────────────────────────────────────────────────────────

def quat_normalize(q: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(q)
    return q / n if n > 1e-12 else np.array([1.0, 0.0, 0.0, 0.0])


def quat_to_rotmat(q: np.ndarray) -> np.ndarray:
    """Rotation matrix that maps BODY-frame vectors to WORLD frame."""
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z),   2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z),   2*(y*z-w*x)],
        [2*(x*z-w*y),     2*(y*z+w*x), 1-2*(x*x+y*y)],
    ])


def quat_derivative(q: np.ndarray, omega_body: np.ndarray) -> np.ndarray:
    """dq/dt = 0.5 * Omega(omega) * q  (standard quaternion kinematics)."""
    w, x, y, z = q
    wx, wy, wz = omega_body
    return 0.5 * np.array([
        -wx*x - wy*y - wz*z,
         wx*w + wz*y - wy*z,
         wy*w - wz*x + wx*z,
         wz*w + wy*x - wx*y,
    ])


def quat_to_euler(q: np.ndarray) -> np.ndarray:
    """Returns [pitch, roll, yaw] in degrees (body Z-axis = thrust/nose direction)."""
    w, x, y, z = q
    # Pitch: rotation about body X, roll: about body Z (thrust axis), yaw: about body Y
    # Using a Z(nose)-referenced convention: recover the nose direction in world frame
    R = quat_to_rotmat(q)
    nose_world = R @ np.array([0, 0, 1.0])   # where body +Z points, in world frame

    pitch = np.degrees(np.arctan2(nose_world[0], nose_world[2]))   # tilt toward east
    roll_axis_ref = R @ np.array([1.0, 0, 0])
    roll = np.degrees(np.arctan2(roll_axis_ref[1], roll_axis_ref[0]))
    yaw  = np.degrees(np.arctan2(nose_world[1], nose_world[2]))    # tilt toward north

    return np.array([pitch, roll, yaw])


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class RocketState:
    t:        float = 0.0
    pos:      np.ndarray = field(default_factory=lambda: np.zeros(3))
    vel:      np.ndarray = field(default_factory=lambda: np.zeros(3))
    quat:     np.ndarray = field(default_factory=lambda: np.array([1.0,0,0,0]))
    omega:    np.ndarray = field(default_factory=lambda: np.zeros(3))   # body-frame rad/s
    mass:     float = 0.5
    landed:   bool = False

    def flatten(self) -> np.ndarray:
        return np.concatenate([self.pos, self.vel, self.quat, self.omega])

    @staticmethod
    def unflatten(y: np.ndarray, t: float, mass: float, landed: bool) -> "RocketState":
        return RocketState(
            t=t, pos=y[0:3], vel=y[3:6],
            quat=quat_normalize(y[6:10]), omega=y[10:13],
            mass=mass, landed=landed,
        )


@dataclass
class RocketConfig:
    dry_mass:        float   # kg, structure mass (excl. propellant)
    moment_arm:      float   # m, CG to TVC gimbal pivot distance
    cd:              float   # drag coefficient
    ref_area:        float   # m^2, reference cross-sectional area
    cp_from_cg:      float   # m, Cp distance ahead of CG (positive = ahead, destabilizing)
    cn_alpha:        float   # per-radian normal force coefficient slope
    inertia_pitch:   float   # kg*m^2, transverse moment of inertia (pitch/yaw axis)
    inertia_roll:    float   # kg*m^2, roll (long axis) moment of inertia
    tvc_max_deg:     float = 12.0   # max gimbal deflection


class RocketPhysics:
    """
    Integrates full 6DOF rigid-body state forward using RK4, given a motor
    thrust curve and TVC servo commands each step.
    """

    def __init__(self, config: RocketConfig, motor, propellant_mass: float = 0.0):
        self.cfg = config
        self.motor = motor
        self.propellant_mass_initial = propellant_mass
        self.state = RocketState(mass=config.dry_mass + propellant_mass)
        self.ignition_time: Optional[float] = None
        self.burn_time = motor.burn_time_s if motor else 0.0

        # Latest commanded TVC angles (degrees), updated externally each tick
        self.tvc_pitch_cmd = 0.0
        self.tvc_yaw_cmd   = 0.0
        self.has_launched  = False   # true once genuinely airborne — prevents a


        # Cached aero outputs for telemetry (dynamic pressure, drag, AoA, etc.)
        self.last_dynamic_pressure = 0.0
        self.last_drag_force       = 0.0
        self.last_aoa_deg          = 0.0
        self.last_mach             = 0.0
        self.last_g_load           = 1.0
        self.last_thrust            = 0.0
        self.speed_of_sound = 343.0   # m/s, constant (no altitude lapse for simplicity)

    def ignite(self, t: float):
        self.ignition_time = t

    def set_tvc_command(self, pitch_deg: float, yaw_deg: float):
        m = self.cfg.tvc_max_deg
        self.tvc_pitch_cmd = float(np.clip(pitch_deg, -m, m))
        self.tvc_yaw_cmd   = float(np.clip(yaw_deg,   -m, m))

    def current_thrust(self, t: float) -> float:
        if self.ignition_time is None or self.motor is None:
            return 0.0
        t_burn = t - self.ignition_time
        if t_burn < 0 or t_burn > self.burn_time:
            return 0.0
        return self.motor.curve.thrust_at(t_burn)

    def current_mass(self, t: float) -> float:
        """Linear propellant burn approximation over the burn duration."""
        if self.ignition_time is None or self.propellant_mass_initial <= 0:
            return self.cfg.dry_mass
        t_burn = t - self.ignition_time
        if t_burn <= 0:
            return self.cfg.dry_mass + self.propellant_mass_initial
        if t_burn >= self.burn_time:
            return self.cfg.dry_mass
        frac_remaining = 1.0 - (t_burn / self.burn_time)
        return self.cfg.dry_mass + self.propellant_mass_initial * frac_remaining

    def _derivatives(self, t: float, y: np.ndarray) -> np.ndarray:
        pos   = y[0:3]
        vel   = y[3:6]
        quat  = quat_normalize(y[6:10])
        omega = y[10:13]

        mass = self.current_mass(t)
        thrust_mag = self.current_thrust(t)

        R = quat_to_rotmat(quat)               # body -> world
        nose_world = R @ np.array([0, 0, 1.0])

        # ── TVC-deflected thrust vector (in body frame, then rotate to world) ──
        pitch_rad = np.radians(self.tvc_pitch_cmd)
        yaw_rad   = np.radians(self.tvc_yaw_cmd)
        thrust_body = thrust_mag * np.array([
            np.sin(yaw_rad),
            np.sin(pitch_rad),
            np.cos(pitch_rad) * np.cos(yaw_rad),
        ])
        thrust_world = R @ thrust_body

        # ── Aerodynamics ─────────────────────────────────────────────────────
        speed = float(np.linalg.norm(vel))
        drag_force_world = np.zeros(3)
        aero_torque_body = np.zeros(3)
        aoa_deg = 0.0
        q_dyn = 0.0

        if speed > 0.05:
            q_dyn = 0.5 * RHO0 * speed**2

            # Drag opposes velocity direction
            drag_mag = q_dyn * self.cfg.cd * self.cfg.ref_area
            drag_force_world = -drag_mag * (vel / speed)

            # Angle of attack: angle between velocity and nose direction
            vel_dir = vel / speed
            cos_aoa = float(np.clip(np.dot(vel_dir, nose_world), -1.0, 1.0))
            aoa_rad = np.arccos(cos_aoa)
            aoa_deg = np.degrees(aoa_rad)

            if aoa_rad > 1e-6:
                # Normal force from Barrowman CNalpha, acting at Cp (ahead of CG
                # since this rocket has no fins) — this is a DESTABILIZING
                # torque (increases AoA further), which is why active TVC
                # control is required to keep the vehicle upright.
                normal_force_mag = self.cfg.cn_alpha * aoa_rad * q_dyn * self.cfg.ref_area

                # Torque arm: Cp is cfg.cp_from_cg ahead of CG along the body +Z axis
                # Body-frame velocity direction determines the plane of the moment
                vel_body = R.T @ vel_dir
                # Crossflow component of vel_body (perpendicular to body axis)
                crossflow_body = vel_body - vel_body[2]*np.array([0,0,1])
                cf_norm = np.linalg.norm(crossflow_body)
                if cf_norm > 1e-9:
                    crossflow_dir = crossflow_body / cf_norm
                    # Normal force acts opposite to crossflow direction, at Cp location
                    force_body = -normal_force_mag * crossflow_dir
                    arm_body = np.array([0, 0, self.cfg.cp_from_cg])
                    aero_torque_body = np.cross(arm_body, force_body)

        # ── TVC torque (thrust offset from CG by moment_arm) ────────────────
        tvc_torque_body = np.zeros(3)
        if thrust_mag > 1e-6:
            arm_body = np.array([0, 0, -self.cfg.moment_arm])   # gimbal is behind CG
            tvc_torque_body = np.cross(arm_body, thrust_body)

        # ── Sum forces (world frame) ─────────────────────────────────────────
        gravity_world = np.array([0, 0, -G * mass])
        total_force = thrust_world + drag_force_world + gravity_world

        accel = total_force / mass

        # ── Sum torques (body frame) → angular acceleration ──────────────────
        total_torque = tvc_torque_body + aero_torque_body
        I = np.array([self.cfg.inertia_pitch, self.cfg.inertia_pitch, self.cfg.inertia_roll])
        # Euler's equations (simplified, ignoring gyroscopic cross-coupling
        # for the pitch/yaw axes since inertia_pitch is equal on both):
        omega_dot = total_torque / I - np.cross(omega, I*omega) / I

        quat_dot = quat_derivative(quat, omega)

        # Cache telemetry values (computed at this evaluation; RK4 calls this
        # 4x per step, so these reflect the LAST stage — acceptable for display)
        self.last_dynamic_pressure = q_dyn
        self.last_drag_force       = float(np.linalg.norm(drag_force_world))
        self.last_aoa_deg          = aoa_deg
        self.last_mach             = speed / self.speed_of_sound
        self.last_g_load           = float(np.linalg.norm(total_force - gravity_world) / (mass*G)) if mass>0 else 1.0
        self.last_thrust           = thrust_mag

        return np.concatenate([vel, accel, quat_dot, omega_dot])

    def step(self, dt: float):
        """Advance the physics state by dt using RK4 integration."""
        if self.state.landed:
            return

        t = self.state.t
        y = self.state.flatten()

        k1 = self._derivatives(t, y)
        k2 = self._derivatives(t + dt/2, y + dt/2*k1)
        k3 = self._derivatives(t + dt/2, y + dt/2*k2)
        k4 = self._derivatives(t + dt,   y + dt*k3)

        y_new = y + (dt/6)*(k1 + 2*k2 + 2*k3 + k4)
        mass_new = self.current_mass(t + dt)

        # Track genuine liftoff (small threshold clears pad/rail friction and
        # RK4 numerical noise during the thrust ramp-up at ignition, when
        # gravity briefly exceeds thrust and z can dip slightly below its
        # start value before climbing — that dip must never be mistaken for
        # a landing).
        if not self.has_launched and y_new[2] > 0.02:
            self.has_launched = True

        landed = self.state.landed
        if self.has_launched and y_new[2] <= 0.0:
            # Ground collision: clamp to z=0, zero velocity, mark landed
            y_new[2] = 0.0
            y_new[3:6] = 0.0
            y_new[10:13] = 0.0
            landed = True

        self.state = RocketState.unflatten(y_new, t + dt, mass_new, landed)

    def get_phase(self) -> str:
        if self.ignition_time is None:
            return "IDLE"
        if self.state.landed:
            return "LANDED"
        t_burn = self.state.t - self.ignition_time
        if t_burn <= self.burn_time:
            return "BOOST"
        if self.state.vel[2] > 0:
            return "COAST"
        return "DESCENT"
