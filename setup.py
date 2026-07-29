import os

folders = [
    "hil_rocket/simulator",
    "hil_rocket/comms",
    "hil_rocket/visualization",
    "hil_rocket/logs",
]

files = [
    "hil_rocket/main.py",
    "hil_rocket/config.py",
    "hil_rocket/simulator/__init__.py",
    "hil_rocket/simulator/physics.py",
    "hil_rocket/simulator/sensors.py",
    "hil_rocket/simulator/tvc.py",
    "hil_rocket/comms/__init__.py",
    "hil_rocket/comms/uart.py",
    "hil_rocket/visualization/__init__.py",
    "hil_rocket/visualization/dashboard.py",
]

for folder in folders:
    os.makedirs(folder, exist_ok=True)

for file in files:
    with open(file, 'w') as f:
        f.write("")

print("Project structure created successfully!")