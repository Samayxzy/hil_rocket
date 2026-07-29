from aero.mesh_import import load_assembly
from aero.barrowman import run_barrowman

a = load_assembly()
print("\n── Assembly ──")
print(f"  Length:        {a.total_length*1000:.1f} mm")
print(f"  Body diameter: {a.body_diameter*1000:.1f} mm")
print(f"  Max diameter:  {a.max_diameter*1000:.1f} mm")
print(f"  Unit scale:    {a.unit_scale}")

r = run_barrowman(a)
print("\n── Barrowman ──")
for k, v in r.summary().items():
    print(f"  {k}: {v}")

from simulator.motors import get_motor, motors_by_class, build_custom_motor

# Estes lookup
m = get_motor("F15-0")
print(m.summary())
print("Thrust at 1s:", m.curve.thrust_at(1.0))

# Custom motor
c = build_custom_motor("MyMotor", avg_thrust_n=25.0, burn_time_s=2.5)
print(c.summary())

# Grouped list for dropdown
print(list(motors_by_class().keys()))