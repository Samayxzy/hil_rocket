CONFIG = {
    # Rocket physical properties
    'mass': 2.5,                        # kg
    'inertia': [0.05, 0.05, 0.01],     # kg*m^2 (Ixx, Iyy, Izz)
    'thrust_moment_arm': 0.3,           # meters from CG to engine

    # Aerodynamics
    'Cd': 0.4,                          # drag coefficient
    'A': 0.007,                         # cross sectional area m^2

    # Motor
    'thrust': 30.0,                     # Newtons
    'burn_time': 3.5,                   # seconds

    # Simulation
    'dt': 0.01,                         # timestep (100 Hz)
    'max_time': 10.0,                   # seconds to simulate

    # UART
    'uart_port': 'COM3',                # change to your actual COM port
    'uart_baud': 115200,

    # PID (will be tuned later)
    'Kp': 1.0,
    'Ki': 0.0,
    'Kd': 0.1,
}