"""
motors.py
Motor database and thrust curve management.

Supports:
  - Built-in Estes motor database (13mm through 29mm)
  - Custom motor entry (avg thrust, burn time, total impulse)
  - RASP .eng file import for detailed thrust curves
"""

import logging
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Motor data structures ─────────────────────────────────────────────────────

@dataclass
class ThrustCurve:
    times:   list
    thrusts: list

    def thrust_at(self, t: float) -> float:
        if t < 0 or t > self.times[-1]:
            return 0.0
        return float(np.interp(t, self.times, self.thrusts))

    @property
    def burn_time(self) -> float:
        return float(self.times[-1])

    @property
    def total_impulse(self) -> float:
        return float(np.trapezoid(self.thrusts, self.times))

    @property
    def avg_thrust(self) -> float:
        bt = self.burn_time
        return self.total_impulse / bt if bt > 0 else 0.0

    @property
    def max_thrust(self) -> float:
        return float(max(self.thrusts))


@dataclass
class Motor:
    name:             str
    manufacturer:     str
    diameter_mm:      float
    length_mm:        float
    total_mass_g:     float
    prop_mass_g:      float
    avg_thrust_n:     float
    max_thrust_n:     float
    burn_time_s:      float
    total_impulse_ns: float
    impulse_class:    str
    curve:            ThrustCurve

    def summary(self) -> dict:
        return {
            "name":             self.name,
            "manufacturer":     self.manufacturer,
            "diameter_mm":      self.diameter_mm,
            "avg_thrust_n":     round(self.avg_thrust_n, 2),
            "max_thrust_n":     round(self.max_thrust_n, 2),
            "burn_time_s":      round(self.burn_time_s, 2),
            "total_impulse_ns": round(self.total_impulse_ns, 2),
            "impulse_class":    self.impulse_class,
            "prop_mass_g":      round(self.prop_mass_g, 1),
        }


# ── Thrust curve helpers ──────────────────────────────────────────────────────

def _flat_curve(avg_thrust: float, burn_time: float) -> ThrustCurve:
    ramp    = min(0.05, burn_time * 0.05)
    times   = [0.0, ramp, burn_time - ramp, burn_time]
    thrusts = [0.0, avg_thrust, avg_thrust, 0.0]
    return ThrustCurve(times=times, thrusts=thrusts)


def _estes_curve(avg: float, peak: float, burn: float) -> ThrustCurve:
    t_peak  = burn * 0.08
    t_mid   = burn * 0.85
    times   = [0.0, t_peak, t_mid,      burn * 0.97, burn]
    thrusts = [0.0, peak,   avg,         avg * 0.6,   0.0]
    return ThrustCurve(times=times, thrusts=thrusts)


# ── Estes motor database ──────────────────────────────────────────────────────
# name, diam_mm, len_mm, total_mass_g, prop_mass_g,
# avg_thrust_N, max_thrust_N, burn_time_s, total_impulse_Ns, class

_ESTES_RAW = [
    ("1/2A3-2T", 13,  45,  7.0,  1.6,  1.9,  5.3, 0.82,  1.56, "1/2A"),
    ("A8-3",     13,  45, 16.2,  3.1,  8.0, 14.1, 0.50,  2.50, "A"),
    ("A8-5",     13,  45, 16.2,  3.1,  8.0, 14.1, 0.50,  2.50, "A"),
    ("B4-2",     18,  70, 18.0,  4.4,  4.2,  8.8, 1.03,  4.38, "B"),
    ("B4-4",     18,  70, 18.0,  4.4,  4.2,  8.8, 1.03,  4.38, "B"),
    ("B6-2",     18,  70, 19.2,  4.8,  5.0,  9.7, 0.90,  5.00, "B"),
    ("B6-4",     18,  70, 19.2,  4.8,  5.0,  9.7, 0.90,  5.00, "B"),
    ("B6-6",     18,  70, 19.2,  4.8,  5.0,  9.7, 0.90,  5.00, "B"),
    ("C5-3",     18,  70, 24.0,  7.9, 10.8, 19.4, 0.90, 10.00, "C"),
    ("C5-5",     18,  70, 24.0,  7.9, 10.8, 19.4, 0.90, 10.00, "C"),
    ("C6-3",     18,  70, 24.0,  8.0, 10.0, 14.1, 1.70, 10.00, "C"),
    ("C6-5",     18,  70, 24.0,  8.0, 10.0, 14.1, 1.70, 10.00, "C"),
    ("C6-7",     18,  70, 24.0,  8.0, 10.0, 14.1, 1.70, 10.00, "C"),
    ("D12-3",    18,  70, 40.6, 13.9, 12.2, 29.7, 1.60, 16.85, "D"),
    ("D12-5",    18,  70, 40.6, 13.9, 12.2, 29.7, 1.60, 16.85, "D"),
    ("D12-7",    18,  70, 40.6, 13.9, 12.2, 29.7, 1.60, 16.85, "D"),
    ("E9-4",     24,  95, 49.0, 17.0, 14.0, 19.4, 3.00, 28.00, "E"),
    ("E9-6",     24,  95, 49.0, 17.0, 14.0, 19.4, 3.00, 28.00, "E"),
    ("E9-8",     24,  95, 49.0, 17.0, 14.0, 19.4, 3.00, 28.00, "E"),
    ("E12-4",    24,  95, 49.0, 17.0, 12.0, 19.0, 2.90, 28.05, "E"),
    ("E12-6",    24,  95, 49.0, 17.0, 12.0, 19.0, 2.90, 28.05, "E"),
    ("F15-0",    24, 114, 60.0, 23.0, 15.4, 19.5, 3.60, 29.70, "F"),
    ("F15-4",    24, 114, 60.0, 23.0, 15.4, 19.5, 3.60, 29.70, "F"),
    ("F15-6",    24, 114, 60.0, 23.0, 15.4, 19.5, 3.60, 29.70, "F"),
    ("G40-4",    29, 124,113.0, 46.0, 40.0, 68.0, 1.70, 40.00, "G"),
    ("G40-7",    29, 124,113.0, 46.0, 40.0, 68.0, 1.70, 40.00, "G"),
    ("G80-4",    29, 124,113.0, 46.0, 80.0,107.0, 0.90, 40.00, "G"),
    ("G80-7",    29, 124,113.0, 46.0, 80.0,107.0, 0.90, 40.00, "G"),
]


def _build_estes_db() -> dict:
    db = {}
    for row in _ESTES_RAW:
        name, diam, length, total_mass, prop_mass, avg_t, max_t, burn, impulse, cls = row
        db[name] = Motor(
            name=name, manufacturer="Estes",
            diameter_mm=diam, length_mm=length,
            total_mass_g=total_mass, prop_mass_g=prop_mass,
            avg_thrust_n=avg_t, max_thrust_n=max_t,
            burn_time_s=burn, total_impulse_ns=impulse,
            impulse_class=cls, curve=_estes_curve(avg_t, max_t, burn),
        )
    return db


ESTES_DB: dict = _build_estes_db()


# ── RASP .eng parser ──────────────────────────────────────────────────────────

def parse_eng_file(path: str) -> Motor:
    """
    Parse a RASP .eng thrust curve file.
    Header: name diam(mm) len(mm) delays prop_mass(kg) total_mass(kg) manufacturer
    Data lines: time(s) thrust(N)
    """
    lines        = Path(path).read_text().splitlines()
    header       = None
    curve_points = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        parts = line.split()
        if header is None:
            header = parts
        else:
            try:
                curve_points.append((float(parts[0]), float(parts[1])))
            except (ValueError, IndexError):
                continue

    if header is None or len(curve_points) < 2:
        raise ValueError(f"Invalid or empty .eng file: {path}")

    name         = header[0]
    diam_mm      = float(header[1])
    len_mm       = float(header[2])
    prop_mass_g  = float(header[4]) * 1000
    total_mass_g = float(header[5]) * 1000
    manufacturer = header[6] if len(header) > 6 else "Custom"

    times   = [p[0] for p in curve_points]
    thrusts = [p[1] for p in curve_points]

    if times[0] > 0:
        times.insert(0, 0.0); thrusts.insert(0, 0.0)
    if thrusts[-1] > 0.1:
        times.append(times[-1] + 0.01); thrusts.append(0.0)

    curve     = ThrustCurve(times=times, thrusts=thrusts)
    impulse   = curve.total_impulse
    imp_class = _impulse_class(impulse)

    logger.info(f"Parsed .eng: {name}  avg={curve.avg_thrust:.1f}N  burn={curve.burn_time:.2f}s")
    return Motor(
        name=name, manufacturer=manufacturer,
        diameter_mm=diam_mm, length_mm=len_mm,
        total_mass_g=total_mass_g, prop_mass_g=prop_mass_g,
        avg_thrust_n=curve.avg_thrust, max_thrust_n=curve.max_thrust,
        burn_time_s=curve.burn_time, total_impulse_ns=impulse,
        impulse_class=imp_class, curve=curve,
    )


def _impulse_class(impulse_ns: float) -> str:
    thresholds = [
        (0.3125, "1/8A"), (0.625, "1/4A"), (1.25, "1/2A"),
        (2.5, "A"), (5.0, "B"), (10.0, "C"), (20.0, "D"),
        (40.0, "E"), (80.0, "F"), (160.0, "G"), (320.0, "H"),
        (640.0, "I"), (1280.0, "J"), (2560.0, "K"), (5120.0, "L"),
    ]
    for limit, cls in thresholds:
        if impulse_ns <= limit:
            return cls
    return "M+"


# ── Custom motor builder ──────────────────────────────────────────────────────

def build_custom_motor(
    name:             str,
    avg_thrust_n:     float,
    burn_time_s:      float,
    total_impulse_ns: Optional[float] = None,
    max_thrust_n:     Optional[float] = None,
    prop_mass_g:      float = 0.0,
    total_mass_g:     float = 0.0,
    diameter_mm:      float = 24.0,
    length_mm:        float = 100.0,
    thrust_curve:     Optional[list] = None,
) -> Motor:
    """
    Build a Motor from user-supplied parameters.
    thrust_curve: optional list of [t, F] pairs for a custom thrust profile.
    """
    if thrust_curve and len(thrust_curve) >= 2:
        times   = [p[0] for p in thrust_curve]
        thrusts = [p[1] for p in thrust_curve]
        if times[0] > 0:
            times.insert(0, 0.0); thrusts.insert(0, 0.0)
        if thrusts[-1] > 0.1:
            times.append(times[-1] + 0.01); thrusts.append(0.0)
        curve = ThrustCurve(times=times, thrusts=thrusts)
    else:
        curve = _flat_curve(avg_thrust_n, burn_time_s)

    impulse   = total_impulse_ns if total_impulse_ns is not None else curve.total_impulse
    max_t     = max_thrust_n     if max_thrust_n     is not None else curve.max_thrust
    imp_class = _impulse_class(impulse)

    logger.info(f"Custom motor '{name}': avg={avg_thrust_n:.1f}N  burn={burn_time_s:.2f}s  class={imp_class}")
    return Motor(
        name=name, manufacturer="Custom",
        diameter_mm=diameter_mm, length_mm=length_mm,
        total_mass_g=total_mass_g, prop_mass_g=prop_mass_g,
        avg_thrust_n=avg_thrust_n, max_thrust_n=max_t,
        burn_time_s=burn_time_s, total_impulse_ns=impulse,
        impulse_class=imp_class, curve=curve,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_motor(name: str) -> Optional[Motor]:
    return ESTES_DB.get(name)

def list_motors() -> list:
    return [m.summary() for m in ESTES_DB.values()]

def motors_by_class() -> dict:
    groups: dict = {}
    for m in ESTES_DB.values():
        groups.setdefault(m.impulse_class, []).append(m.summary())
    return groups
