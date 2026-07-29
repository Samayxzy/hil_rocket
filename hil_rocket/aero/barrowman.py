"""
barrowman.py  (V2 — profile-based geometry extraction)
Extracts nosecone, body, and fin geometry from the rocket radius profile
produced by mesh_import, then runs the Barrowman equations.

All distances from NOSE TIP (positive toward tail). All units metres/SI.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from aero.mesh_import import RocketAssembly

logger = logging.getLogger(__name__)


# ── Geometry structs ──────────────────────────────────────────────────────────

@dataclass
class NoseconeGeometry:
    length:    float   # m
    base_dia:  float   # m
    shape:     str     # "ogive" | "conical" | "elliptical"


@dataclass
class BodyGeometry:
    length:    float
    diameter:  float


@dataclass
class FinGeometry:
    count:      int
    root_chord: float
    tip_chord:  float
    span:       float    # semispan from body surface
    sweep:      float    # axial leading-edge sweep
    position:   float    # distance from nose to fin root LE


@dataclass
class BarrowmanResult:
    cp_from_nose:      float
    cp_from_tail:      float
    cn_alpha_total:    float
    cn_alpha_nose:     float
    cn_alpha_fins:     float
    cd0:               float
    cd_curve:          List[dict]
    nose_length:       float
    body_diameter:     float
    body_length:       float
    fin_count:         int
    fin_span:          float
    stability_margin_calibers: float = 0.0

    def compute_stability(self, cg_from_nose: float, body_diameter: float):
        self.stability_margin_calibers = (
            (self.cp_from_nose - cg_from_nose) / body_diameter
        )
        logger.info(
            f"Cp={self.cp_from_nose*1000:.1f}mm  Cg={cg_from_nose*1000:.1f}mm  "
            f"Margin={self.stability_margin_calibers:.2f} cal"
        )

    def summary(self) -> dict:
        return {
            "cp_from_nose_m":       round(self.cp_from_nose, 4),
            "cp_from_tail_m":       round(self.cp_from_tail, 4),
            "cn_alpha":             round(self.cn_alpha_total, 3),
            "cd0":                  round(self.cd0, 4),
            "stability_margin_cal": round(self.stability_margin_calibers, 3),
            "nose_length_m":        round(self.nose_length, 4),
            "body_diameter_m":      round(self.body_diameter, 4),
            "body_length_m":        round(self.body_length, 4),
            "fin_count":            self.fin_count,
            "fin_span_m":           round(self.fin_span, 4),
        }


# ── Geometry extraction from radius profile ───────────────────────────────────

def _extract_geometry(
    assembly: RocketAssembly,
) -> Tuple[NoseconeGeometry, BodyGeometry, Optional[FinGeometry]]:
    """
    Analyse the radius profile to identify nosecone, body, and fin regions.

    Profile convention: Z=0 is tail, Z=total_length is nose tip.
    We flip it to work nose-first (standard Barrowman orientation).
    """
    z    = assembly.profile_z
    r    = assembly.profile_r
    L    = assembly.total_length
    r_body = assembly.body_diameter / 2

    # Flip so index 0 = nose tip, index -1 = tail
    z_nf = L - z[::-1]
    r_nf = r[::-1]

    # ── Nosecone: region where radius grows from ~0 to body radius ────────────
    # Find the first index where r exceeds 95% of body radius
    nose_end_idx = 0
    for i, ri in enumerate(r_nf):
        if ri >= 0.95 * r_body:
            nose_end_idx = i
            break

    if nose_end_idx == 0:
        nose_end_idx = len(r_nf) // 6   # fallback: first 1/6 of rocket

    nose_length = float(z_nf[nose_end_idx])
    if nose_length < 1e-4:
        nose_length = L * 0.2   # sane fallback

    # Classify nosecone shape from profile curve
    nose_shape = _classify_nose_shape(z_nf[:nose_end_idx+1], r_nf[:nose_end_idx+1], r_body)

    nose = NoseconeGeometry(
        length   = nose_length,
        base_dia = assembly.body_diameter,
        shape    = nose_shape,
    )

    # ── Fins: region where radius spikes significantly above body radius ───────
    fin_threshold = r_body * 1.15   # 15% above body = fin
    fin_mask      = r_nf > fin_threshold

    fin_geom = None
    if fin_mask.any():
        # Find fin axial extent (in nose-first coords)
        fin_indices = np.where(fin_mask)[0]
        fin_z_start = float(z_nf[fin_indices[0]])
        fin_z_end   = float(z_nf[fin_indices[-1]])

        fin_span     = float(r_nf[fin_mask].max()) - r_body
        fin_chord    = fin_z_end - fin_z_start
        fin_pos      = fin_z_start
        fin_count    = _estimate_fin_count_from_profile(r_nf[fin_indices])

        fin_geom = FinGeometry(
            count      = fin_count,
            root_chord = fin_chord,
            tip_chord  = fin_chord * 0.5,   # assume ~50% taper
            span       = fin_span,
            sweep      = fin_chord * 0.3,   # assume 30% LE sweep
            position   = fin_pos,
        )
        logger.info(
            f"Fins detected: n={fin_count}  chord={fin_chord*1000:.1f}mm  "
            f"span={fin_span*1000:.1f}mm  pos={fin_pos*1000:.1f}mm from nose"
        )
    else:
        logger.info("No fin protrusion detected in profile")

    # ── Body: section between nosecone and fins ───────────────────────────────
    if fin_geom is not None:
        body_length = max(0.01, fin_geom.position - nose_length)
    else:
        body_length = max(0.01, L - nose_length)

    body = BodyGeometry(
        length   = body_length,
        diameter = assembly.body_diameter,
    )

    logger.info(
        f"Geometry: nose={nose_length*1000:.1f}mm ({nose_shape})  "
        f"body={body_length*1000:.1f}mm  dia={assembly.body_diameter*1000:.1f}mm"
    )

    return nose, body, fin_geom


def _classify_nose_shape(z: np.ndarray, r: np.ndarray, r_body: float) -> str:
    """
    Fit the nosecone radius profile to determine shape.
    Compares normalised profile against ogive, conical, elliptical curves.
    """
    if len(z) < 3 or z[-1] < 1e-6:
        return "ogive"

    z_norm = z / z[-1]
    r_norm = r / r_body

    r_ogive    = np.sqrt(1 - (1 - z_norm)**2)      # ogive approximation
    r_conical  = z_norm
    r_ellipse  = np.sqrt(1 - (1 - z_norm)**2)

    err_ogive   = np.mean((r_norm - r_ogive)**2)
    err_conical = np.mean((r_norm - r_conical)**2)

    if err_conical < err_ogive * 0.8:
        return "conical"
    elif err_ogive < err_conical * 0.8:
        return "ogive"
    else:
        return "ogive"   # default to ogive for model rockets


def _estimate_fin_count_from_profile(r_fin_vals: np.ndarray) -> int:
    """
    Estimate fin count from radius variation in the fin region.
    Fins create periodic spikes in the radius profile as the mesh rotates.
    """
    # Look at local variance — more fins = smoother averaged profile
    # Without full 3D info we default to 4 for most model rockets,
    # but check if profile has strong periodic variation suggesting 3.
    std = float(np.std(r_fin_vals))
    mean = float(np.mean(r_fin_vals))

    if mean > 0 and std / mean > 0.3:
        return 3   # high variance suggests fewer, more distinct fins
    return 4       # default


# ── Barrowman equations ───────────────────────────────────────────────────────

def _cn_xcp_nosecone(nose: NoseconeGeometry) -> Tuple[float, float]:
    """CNα = 2 for all shapes. Xcp depends on shape (from nose tip)."""
    shape = nose.shape.lower()
    if shape == "conical":
        xcp = nose.length * 2/3
    elif shape == "elliptical":
        xcp = nose.length / 3
    elif shape == "parabolic":
        xcp = nose.length * 0.5
    else:   # ogive (default)
        xcp = nose.length * 0.466
    return 2.0, xcp


def _cn_xcp_fins(fins: FinGeometry, body_dia: float) -> Tuple[float, float]:
    """
    Barrowman fin CNα and Xcp (measured from nose tip).
    Trapezoidal planform equations from Barrowman 1967.
    """
    n  = fins.count
    s  = fins.span
    r  = body_dia / 2
    Cr = fins.root_chord
    Ct = fins.tip_chord
    ls = fins.sweep

    lm   = ls + (Cr - Ct) / 2   # midchord sweep
    diam = body_dia

    interference = 1 + r / (s + r)
    lm_norm      = 2 * lm / (Cr + Ct) if (Cr + Ct) > 0 else 0
    denom        = 1 + np.sqrt(1 + lm_norm**2)
    cn_fins      = interference * (4 * n * (s / diam)**2) / denom

    xcp_local = (
        lm / 3 * (Cr + 2*Ct) / (Cr + Ct)
        + 1/6 * (Cr + Ct - Cr*Ct / max(Cr+Ct, 1e-6))
    ) if (Cr + Ct) > 0 else Cr / 2

    xcp_from_nose = fins.position + xcp_local

    logger.debug(f"Fins: CNα={cn_fins:.3f}  Xcp={xcp_from_nose*1000:.1f}mm from nose")
    return cn_fins, xcp_from_nose


def _cd0_estimate(nose: NoseconeGeometry, body: BodyGeometry,
                  fins: Optional[FinGeometry], dia: float) -> float:
    """Simplified Hoerner drag model."""
    ref_area = np.pi * (dia/2)**2
    if ref_area < 1e-9:
        return 0.5

    # Nose pressure drag
    fin_ratio = nose.length / max(nose.base_dia, 1e-4)
    cd = 0.1 / (fin_ratio**0.3 + 0.01)

    # Body skin friction (turbulent)
    wetted = np.pi * dia * body.length
    cd    += 0.0027 * (wetted / ref_area)

    # Fin drag
    if fins is not None:
        fin_area = fins.count * (fins.root_chord + fins.tip_chord) * fins.span / 2
        cd      += 0.008 * (fin_area / ref_area)

    # Base drag
    cd += 0.025

    return max(round(cd, 4), 0.05)


def _cd_curve(cd0: float) -> List[dict]:
    """Cd vs AoA from -20° to +20° using Cd = Cd0 + k·sin²(α)."""
    k    = 1.2
    aoas = np.linspace(-20, 20, 81)
    return [
        {"aoa_deg": round(float(a), 1),
         "cd":      round(cd0 + k * np.sin(np.radians(a))**2, 4)}
        for a in aoas
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def run_barrowman(assembly: RocketAssembly) -> BarrowmanResult:
    """
    Run the full Barrowman analysis on a loaded RocketAssembly.
    Returns BarrowmanResult with Cp, CNα, Cd0, and Cd curve.

    Call result.compute_stability(cg_from_nose, diameter) once mass props
    are available to get the stability margin in calibers.
    """
    if assembly.profile_z is None or assembly.total_length < 1e-4:
        raise ValueError("Assembly has no valid geometry — check the STL file")

    nose, body, fins = _extract_geometry(assembly)

    ref_dia = body.diameter
    if ref_dia < 1e-4:
        raise ValueError("Body diameter near zero — check STL")

    cn_nose, xcp_nose = _cn_xcp_nosecone(nose)

    cn_fins, xcp_fins = (0.0, assembly.total_length * 0.8)
    if fins is not None:
        cn_fins, xcp_fins = _cn_xcp_fins(fins, ref_dia)

    cn_total = cn_nose + cn_fins
    if cn_total < 1e-6:
        raise ValueError("Total CNα near zero — Barrowman cannot compute Cp")

    xcp = (cn_nose * xcp_nose + cn_fins * xcp_fins) / cn_total
    cd0 = _cd0_estimate(nose, body, fins, ref_dia)

    result = BarrowmanResult(
        cp_from_nose   = xcp,
        cp_from_tail   = assembly.total_length - xcp,
        cn_alpha_total = cn_total,
        cn_alpha_nose  = cn_nose,
        cn_alpha_fins  = cn_fins,
        cd0            = cd0,
        cd_curve       = _cd_curve(cd0),
        nose_length    = nose.length,
        body_diameter  = ref_dia,
        body_length    = body.length,
        fin_count      = fins.count if fins else 0,
        fin_span       = fins.span  if fins else 0.0,
    )

    logger.info(
        f"Barrowman: Cp={xcp*1000:.1f}mm from nose  "
        f"CNα={cn_total:.3f}  Cd0={cd0:.4f}"
    )
    return result
