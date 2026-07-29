# MONK HIL — Rocket Hardware-in-the-Loop Simulation Platform

## What this is

MONK HIL is a hardware-in-the-loop testing platform for a model rocket flight computer. The goal is simple to state and hard to build: before any firmware flies on a real rocket, it should prove itself against realistic sensor data and realistic timing, on the actual hardware it will fly on. This project does that by feeding synthetic flight data into a real flight computer PCB over UART, letting the board run its actual control firmware and compute real actuator commands, then feeding those commands back into a physics simulation. The flight computer has no idea it isn't flying. This is the same basic strategy aerospace companies use to de-risk flight software long before a real vehicle leaves the ground.

The project spans both hardware and software: a custom flight computer board, a physics and aerodynamics simulation, a 3D visualization frontend, and a physical motor test stand currently being brought online for full closed-loop hardware validation.

## How the loop works

A Python simulation running on a PC models the rocket's flight — thrust curve, mass properties, drag, atmosphere, and (eventually) wind. As the simulation steps forward, it packages up synthetic IMU and barometer readings, exactly as if they came from real sensors mid-flight, and streams them over UART to the flight computer board. The board runs its real control algorithm on this data and computes servo commands, the same way it would if it were actually correcting a rocket's trajectory in the air. Those commands get sent back over UART to the PC, which applies them to the simulated rocket as real actuator inputs, closing the loop. Nothing about the firmware's role in this process is faked — only the sensor inputs are synthetic.

## The flight computer — the MONK board

The MONK board is a custom PCB built around an STM32F407 microcontroller, designed from scratch in Autodesk Inventor. It carries an MPU-6050 six-axis IMU for acceleration and rotation sensing over I2C, and an MS5611 barometer for precise altitude. It has four PWM servo channels — two are dedicated to thrust vector control for pitch and yaw, and two are left free for future use, like fin actuation or parachute deployment. All HIL communication with the PC runs through a dedicated UART header, wired to USART1 on the board (PA9/PA10), and the board is powered and programmed over USB-C.

A two-axis TVC gimbal mechanism is already fully built and wired into the two dedicated servo channels, so the flight computer can physically redirect thrust to stabilize the vehicle — the same mechanism a real rocket would rely on for active control.

Flashing new firmware onto the board happens over UART using STM32's built-in bootloader, accessed through STM32CubeProgrammer. Getting into bootloader mode means pulling the BOOT0 pin high on reset, so a small pushbutton was added between BOOT0 and 3.3V to trigger that manually.

## The simulation software

The simulation itself is a Python backend (FastAPI, Uvicorn, NumPy) paired with a vanilla JavaScript and Three.js frontend for visualization, living in `HIL_ROCKET/hil_rocket/`. The backend runs a full 6-degree-of-freedom rigid body simulation of the rocket, tracking both translational and rotational motion, modeling the motor's thrust curve, changing mass as propellant burns, and atmospheric drag. Attitude control uses a PD controller that was tuned and verified empirically — worked out and confirmed by hand after some early derivation attempts gave inconsistent results. Once the motor burns out and the vehicle stops actively controlling itself, the simulation lets it tumble freely, which is correct physical behavior for a rocket with no post-burnout stabilization, not a bug to fix.

Alongside the flight dynamics, there's a separate wind tunnel model built for visualizing airflow around the rocket body. It uses a distributed doublet-panel model with streamlines integrated using RK4, combined with a ring-source disturbance field to capture how the flow behaves close to the body. Getting the wind direction to rotate correctly into the rocket's body frame took some real debugging — the fix was rotating the actual wind vector into body coordinates first, rather than rotating a simplified axial baseline and combining it with the disturbance afterward.

The frontend renders the rocket's live attitude, trajectory, and the wind tunnel streamlines in 3D, updated over a WebSocket feed running at 20Hz. Rocket geometry comes from STL files exported out of Inventor, with the body centered on the Z-axis, tail at Z=0 and nose pointing up, all in millimeter units; small CAD mating gaps between parts are bridged using a windowed-max radius slicing approach when processing the mesh.

All seven phases of the simulation software are complete and have been verified running in simulation-only mode, without the physical board yet in the loop.
