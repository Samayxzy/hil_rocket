"""
mesh_import.py  (V2 — single assembly STL)
Loads one full rocket assembly STL exported from Inventor with:
  - Rocket centreline on the Z-axis (X=0, Y=0)
  - Tail base at Z=0
  - Nose pointing in +Z direction
  - Units: mm

Normalises to metres and builds a radius profile for Barrowman and
the wind tunnel flow field.
"""

import logging
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False
    logging.warning("trimesh not installed — run: pip install trimesh")

logger = logging.getLogger(__name__)

UPLOAD_DIR    = Path("uploads/stl")
ASSEMBLY_FILE = UPLOAD_DIR / "assembly.stl"

_MIN_ROCKET_M = 0.05
_MAX_ROCKET_M = 4.00


@dataclass
class RocketAssembly:
    mesh:           object
    total_length:   float = 0.0
    max_diameter:   float = 0.0
    body_diameter:  float = 0.0
    unit_scale:     float = 1.0
    stl_path:       str   = ""
    profile_z:      Optional[np.ndarray] = None
    profile_r:      Optional[np.ndarray] = None


def _detect_scale(raw_length: float) -> float:
    for unit, scale in [("mm", 1e-3), ("cm", 1e-2), ("inches", 1/25.4), ("m", 1.0)]:
        if _MIN_ROCKET_M <= raw_length * scale <= _MAX_ROCKET_M:
            logger.info(f"STL units detected as {unit}  (scale={scale})")
            return scale
    logger.warning(f"Could not detect STL units (raw={raw_length:.2f}). Assuming mm.")
    return 1e-3


def load_assembly(path: Optional[Path] = None) -> RocketAssembly:
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed — run: pip install trimesh")

    stl_path = path or ASSEMBLY_FILE
    if not stl_path.exists():
        raise FileNotFoundError(
            f"Assembly STL not found: {stl_path}\n"
            "Export your Inventor assembly as uploads/stl/assembly.stl with:\n"
            "  - Centreline on Z-axis, tail at Z=0, nose in +Z, units=mm"
        )

    logger.info(f"Loading: {stl_path}")
    mesh = trimesh.load_mesh(str(stl_path))
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("STL produced an empty or invalid mesh")

    # ── Scale to metres ───────────────────────────────────────────────────────
    bounds     = mesh.bounds
    extents    = bounds[1] - bounds[0]
    raw_length = float(extents[2])   # Z is rocket axis by Inventor convention

    scale = _detect_scale(raw_length)
    if scale != 1.0:
        mesh.apply_scale(scale)
        bounds = mesh.bounds

    total_length = float(bounds[1, 2] - bounds[0, 2])

    # ── Build radius profile ──────────────────────────────────────────────────
    n_slices = 500
    z_vals   = np.linspace(bounds[0, 2], bounds[1, 2], n_slices)
    r_raw    = np.zeros(n_slices)

    for i, z in enumerate(z_vals):
        try:
            section = mesh.section(
                plane_origin=[0, 0, z],
                plane_normal=[0, 0, 1],
            )
            if section is not None and len(section.vertices) > 0:
                pts      = section.vertices
                r_raw[i] = np.sqrt(pts[:, 0]**2 + pts[:, 1]**2).max()
        except Exception:
            pass

    # Normalise Z so tail = 0
    z_vals = z_vals - bounds[0, 2]

    # Windowed maximum: exact single-height slices can hit r=0 if there's
    # even a tiny gap between mated CAD components (e.g. body tube vs. a
    # separately-modelled TVC gimbal assembly with mating tolerance) —
    # this bridges such gaps by taking the widest radius found within a
    # small neighbourhood of each height, rather than one exact slice.
    window_frac   = 0.015   # ~1.5% of total length
    window_slices = max(3, int(window_frac * n_slices))
    if window_slices % 2 == 0:
        window_slices += 1
    half_w = window_slices // 2

    r_windowed = np.zeros(n_slices)
    for i in range(n_slices):
        lo = max(0, i - half_w)
        hi = min(n_slices, i + half_w + 1)
        r_windowed[i] = r_raw[lo:hi].max()

    # Light final smoothing to remove residual mesh-triangulation jitter
    kernel   = np.ones(5) / 5
    r_smooth = np.convolve(r_windowed, kernel, mode='same')
    r_smooth[[0,1,2,-3,-2,-1]] = r_windowed[[0,1,2,-3,-2,-1]]

    # ── Body diameter: mode of radius histogram ───────────────────────────────
    # Most slices hit the body tube; nosecone taper and fin spikes are outliers.
    nonzero_r = r_smooth[r_smooth > 1e-4]
    if len(nonzero_r) == 0:
        raise ValueError("Radius profile is all-zero — check STL Z orientation.")

    hist, bin_edges = np.histogram(nonzero_r, bins=60)
    bin_width = bin_edges[1] - bin_edges[0]
    body_r    = float(bin_edges[np.argmax(hist)]) + bin_width / 2
    body_dia  = 2 * body_r
    max_dia   = 2 * float(r_smooth.max())

    logger.info(
        f"Assembly: L={total_length*1000:.1f}mm  "
        f"body_D={body_dia*1000:.1f}mm  max_D={max_dia*1000:.1f}mm"
    )

    return RocketAssembly(
        mesh          = mesh,
        total_length  = total_length,
        max_diameter  = max_dia,
        body_diameter = body_dia,
        unit_scale    = scale,
        stl_path      = str(stl_path),
        profile_z     = z_vals,
        profile_r     = r_smooth,
    )


def get_rocket_silhouette(assembly: RocketAssembly, n_points: int = 200) -> np.ndarray:
    if assembly.profile_z is None:
        return np.zeros((n_points, 2))
    z_out = np.linspace(0, assembly.total_length, n_points)
    r_out = np.interp(z_out, assembly.profile_z, assembly.profile_r)  # type: ignore[arg-type]
    result = np.zeros((n_points, 2))
    result[:, 0] = z_out
    result[:, 1] = r_out
    return result
