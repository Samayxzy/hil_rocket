"""
mass_props.py
Computes centre of mass and inertia tensor for each STL component,
then combines them into rocket-wide mass properties.

The user either supplies:
  - A known total mass (kg) and material density is back-calculated, or
  - A material density (kg/m³) and mass is derived from mesh volume.

All results are in SI units, with Z as the rocket axis (tail at Z=0).
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional

from aero.mesh_import import RocketAssembly, ComponentMesh

logger = logging.getLogger(__name__)

# Common material densities (kg/m³) for reference
MATERIAL_DENSITY = {
    "pla":          1240,
    "abs":          1050,
    "petg":         1270,
    "fiberglass":   1800,
    "carbon_fiber": 1600,
    "balsa":         130,
    "plywood":       600,
    "aluminum":     2700,
    "custom":          0,   # user-specified
}


@dataclass
class ComponentMassProps:
    name:       str
    mass:       float           # kg
    volume:     float           # m³
    density:    float           # kg/m³
    com:        np.ndarray      # [x, y, z] m — centre of mass in rocket coords
    inertia:    np.ndarray      # (3,3) inertia tensor about component CoM (kg·m²)


@dataclass
class RocketMassProps:
    total_mass:   float          # kg
    com:          np.ndarray     # [x, y, z] centre of mass in rocket coords (Z from tail)
    inertia:      np.ndarray     # (3,3) inertia tensor about rocket CoM (kg·m²)
    components:   Dict[str, ComponentMassProps]

    @property
    def cg_from_nose(self) -> float:
        """Distance of CoG from nose tip (m). Requires total_length from assembly."""
        return self._total_length - self.com[2]

    @property
    def cg_from_tail(self) -> float:
        return float(self.com[2])

    def set_total_length(self, L: float):
        self._total_length = L

    def summary(self) -> dict:
        return {
            "total_mass_kg":    round(self.total_mass, 4),
            "com_x_m":          round(float(self.com[0]), 5),
            "com_y_m":          round(float(self.com[1]), 5),
            "com_z_m":          round(float(self.com[2]), 4),
            "cg_from_tail_m":   round(self.cg_from_tail, 4),
            "Ixx":              round(float(self.inertia[0,0]), 6),
            "Iyy":              round(float(self.inertia[1,1]), 6),
            "Izz":              round(float(self.inertia[2,2]), 6),
        }


def _component_mass_props(
    comp: ComponentMesh,
    density: float,
) -> ComponentMassProps:
    """
    Use trimesh to compute mass properties for one component.
    trimesh.Trimesh.moment_inertia returns the inertia tensor about the mesh CoM.
    """
    mesh   = comp.mesh
    volume = float(abs(mesh.volume))
    mass   = density * volume
    com    = np.array(mesh.center_mass, dtype=float)

    # trimesh gives principal inertia eigenvalues; we want the full tensor.
    # Use moment_inertia which is (3,3) about mesh origin, then shift to CoM.
    try:
        I_origin = np.array(mesh.moment_inertia, dtype=float) * density
        # Parallel axis theorem: I_com = I_origin - m*(|r|²E - r⊗r)
        r   = com
        rrt = np.outer(r, r)
        rr  = np.dot(r, r) * np.eye(3)
        I_com = I_origin - mass * (rr - rrt)
    except Exception:
        # Fallback: treat as solid cylinder
        R  = comp.diameter / 2
        L  = comp.length
        Ia = 0.5 * mass * R**2                              # axial (Z)
        It = mass * (3*R**2 + L**2) / 12                   # transverse
        I_com = np.diag([It, It, Ia])

    logger.debug(f"{comp.name}: m={mass*1000:.1f}g  CoM={com}")
    return ComponentMassProps(
        name=comp.name, mass=mass, volume=volume,
        density=density, com=com, inertia=I_com
    )


def compute_mass_props(
    assembly: RocketAssembly,
    total_mass: Optional[float] = None,
    density: Optional[float] = None,
    material: str = "pla",
    component_overrides: Optional[Dict[str, float]] = None,
) -> RocketMassProps:
    """
    Compute combined mass properties for the full rocket assembly.

    Args:
        assembly:           RocketAssembly from mesh_import.load_assembly()
        total_mass:         If given, scale density so volumes sum to this mass.
        density:            Uniform material density (kg/m³). Ignored if total_mass set.
        material:           Material name from MATERIAL_DENSITY (used if density=None).
        component_overrides: Optional per-component density overrides {name: kg/m³}.

    Returns:
        RocketMassProps with combined CoM and inertia tensor.
    """
    if not assembly.components:
        raise ValueError("Assembly has no components loaded")

    # Resolve density
    if total_mass is not None:
        total_volume = sum(abs(c.mesh.volume) for c in assembly.components.values())
        if total_volume < 1e-9:
            raise ValueError("Total mesh volume is near-zero — check STL files")
        base_density = total_mass / total_volume
        logger.info(f"Back-calculated density: {base_density:.1f} kg/m³ from mass={total_mass}kg")
    elif density is not None:
        base_density = density
    else:
        base_density = MATERIAL_DENSITY.get(material, MATERIAL_DENSITY["pla"])
        logger.info(f"Using material '{material}': {base_density} kg/m³")

    overrides = component_overrides or {}

    # Per-component props
    comp_props: Dict[str, ComponentMassProps] = {}
    for name, comp in assembly.components.items():
        d = overrides.get(name, base_density)
        comp_props[name] = _component_mass_props(comp, d)

    # Combined CoM (mass-weighted average)
    total_m = sum(cp.mass for cp in comp_props.values())
    if total_m < 1e-9:
        raise ValueError("Total mass is near-zero")

    com = np.zeros(3)
    for cp in comp_props.values():
        com += cp.mass * cp.com
    com /= total_m

    # Combined inertia tensor about rocket CoM (parallel axis theorem)
    I_total = np.zeros((3, 3))
    for cp in comp_props.values():
        r   = cp.com - com
        rrt = np.outer(r, r)
        rr  = np.dot(r, r) * np.eye(3)
        I_total += cp.inertia + cp.mass * (rr - rrt)

    result = RocketMassProps(
        total_mass=total_m, com=com,
        inertia=I_total, components=comp_props
    )
    result.set_total_length(assembly.total_length)

    logger.info(f"Mass props: total={total_m*1000:.1f}g  "
                f"CoM={com[2]*1000:.1f}mm from tail  "
                f"({result.cg_from_nose*1000:.1f}mm from nose)")
    return result
