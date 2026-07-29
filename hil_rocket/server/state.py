import threading
import time

class SimState:
    """
    Central shared state between the sim loop (main.py) and the FastAPI server.
    All fields are written by the sim and read by the WebSocket broadcaster.
    Access is protected by a single RLock so partial reads don't occur.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # ── Flight metadata ──────────────────────────────────────────────────
        self.flight_phase   = "IDLE"       # IDLE / BOOST / COAST / DESCENT / LANDED
        self.mission_clock  = 0.0          # T+ seconds (does not advance while paused)
        self.loop_hz        = 0.0          # actual sim loop rate
        self.paused         = False
        self.launched       = False

        # ── True state (simulation truth) ────────────────────────────────────
        self.pos            = [0.0, 0.0, 0.0]   # x east, y north, z up (m)
        self.vel            = [0.0, 0.0, 0.0]   # m/s
        self.accel          = [0.0, 0.0, 0.0]   # m/s²
        self.attitude_q     = [1.0, 0.0, 0.0, 0.0]  # quaternion w,x,y,z
        self.euler          = [0.0, 0.0, 0.0]   # pitch, roll, yaw (deg)
        self.angular_rate   = [0.0, 0.0, 0.0]   # rad/s

        # ── Derived dynamics ─────────────────────────────────────────────────
        self.speed          = 0.0   # |vel| m/s
        self.mach           = 0.0
        self.g_load         = 1.0
        self.dynamic_pressure = 0.0  # Pa
        self.drag_force     = 0.0    # N
        self.aoa            = 0.0    # angle of attack (deg)

        # ── Motor ────────────────────────────────────────────────────────────
        self.thrust         = 0.0   # N
        self.burn_remaining = 0.0   # s
        self.motor_name     = "F15-0"

        # ── Sensor data (noisy, as sent to hardware) ─────────────────────────
        self.imu_accel      = [0.0, 0.0, 0.0]   # m/s² with noise
        self.imu_gyro       = [0.0, 0.0, 0.0]   # rad/s with noise
        self.baro_alt       = 0.0   # m estimated
        self.baro_true_alt  = 0.0   # m true
        self.baro_error     = 0.0   # m delta

        # ── UART / comms ─────────────────────────────────────────────────────
        self.uart_packets_sent    = 0
        self.uart_packet_rate     = 0.0   # Hz
        self.uart_last_packet     = ""
        self.hw_connected         = False

        # ── Hardware telemetry (from flight computer) ─────────────────────────
        self.hw_imu_accel         = [0.0, 0.0, 0.0]
        self.hw_imu_gyro          = [0.0, 0.0, 0.0]
        self.hw_attitude          = [0.0, 0.0, 0.0]   # pitch, roll, yaw (deg)
        self.hw_servo_pitch       = 0.0   # deg
        self.hw_servo_yaw         = 0.0   # deg
        self.hw_pid_error         = [0.0, 0.0]
        self.hw_link_quality      = 0.0   # 0–1

        # ── Aero / rocket geometry (populated from STL pipeline) ──────────────
        self.cp_location          = 0.0   # m from nose
        self.cg_location          = 0.0   # m from nose
        self.stability_margin     = 0.0   # calibers
        self.cd_curve             = []    # list of {aoa, cd} for wind tunnel
        self.rocket_length        = 0.0   # m
        self.rocket_diameter      = 0.0   # m
        self.rocket_profile       = []    # list of {z, r} — actual STL silhouette (tail=0 -> nose)
        self.flow_field_data      = None  # solved ring-source data (see aero/flow_field.py)
        self.stl_uploaded         = False
        self.stl_paths            = {}    # {"nosecone": path, "body": path, ...}

        # ── Flight history for scrubber ───────────────────────────────────────
        self._history             = []    # list of snapshots
        self._history_lock        = threading.Lock()
        self._last_history_t      = 0.0

        # ── Launch parameters (set from launch screen) ────────────────────────
        self.launch_params        = {}

    # ── Thread-safe snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serialisable dict of all current state."""
        with self._lock:
            return {
                "phase":            self.flight_phase,
                "t":                round(self.mission_clock, 2),
                "hz":               round(self.loop_hz, 1),
                "paused":           self.paused,
                "launched":         self.launched,

                "pos":              self.pos,
                "vel":              self.vel,
                "accel":            self.accel,
                "attitude_q":       self.attitude_q,
                "euler":            self.euler,
                "angular_rate":     self.angular_rate,

                "speed":            round(self.speed, 3),
                "mach":             round(self.mach, 4),
                "g_load":           round(self.g_load, 3),
                "dynamic_pressure": round(self.dynamic_pressure, 2),
                "drag_force":       round(self.drag_force, 3),
                "aoa":              round(self.aoa, 3),

                "thrust":           round(self.thrust, 2),
                "burn_remaining":   round(self.burn_remaining, 3),
                "motor_name":       self.motor_name,

                "imu_accel":        self.imu_accel,
                "imu_gyro":         self.imu_gyro,
                "baro_alt":         round(self.baro_alt, 2),
                "baro_true_alt":    round(self.baro_true_alt, 2),
                "baro_error":       round(self.baro_error, 3),

                "uart_packets_sent": self.uart_packets_sent,
                "uart_packet_rate":  round(self.uart_packet_rate, 1),
                "uart_last_packet":  self.uart_last_packet,
                "hw_connected":      self.hw_connected,

                "hw_imu_accel":     self.hw_imu_accel,
                "hw_imu_gyro":      self.hw_imu_gyro,
                "hw_attitude":      self.hw_attitude,
                "hw_servo_pitch":   round(self.hw_servo_pitch, 2),
                "hw_servo_yaw":     round(self.hw_servo_yaw, 2),
                "hw_pid_error":     self.hw_pid_error,
                "hw_link_quality":  round(self.hw_link_quality, 3),

                "cp_location":      round(self.cp_location, 4),
                "cg_location":      round(self.cg_location, 4),
                "stability_margin": round(self.stability_margin, 3),
                "rocket_length":    round(self.rocket_length, 4),
                "rocket_diameter":  round(self.rocket_diameter, 4),
                "stl_uploaded":     self.stl_uploaded,
            }

    def update(self, **kwargs):
        """Update one or more fields atomically."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)

    # ── History buffer ────────────────────────────────────────────────────────

    def record_history(self):
        """Call once per sim tick. Stores a snapshot at ~20 Hz."""
        now = self.mission_clock
        if now - self._last_history_t < 0.05:
            return
        self._last_history_t = now
        snap = self.snapshot()
        with self._history_lock:
            self._history.append(snap)

    def get_history(self) -> list:
        with self._history_lock:
            return list(self._history)

    def clear_history(self):
        with self._history_lock:
            self._history.clear()
            self._last_history_t = 0.0


# Single shared instance imported everywhere
sim_state = SimState()
