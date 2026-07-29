"""
sensors.py
Synthetic IMU (accelerometer + gyroscope) and barometer models with
realistic noise characteristics, matching what a real MPU-6050 + MS5611
would report on the MONK flight computer.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IMUNoiseConfig:
    accel_noise_std:  float = 0.05    # m/s^2, white noise
    accel_bias:       float = 0.02    # m/s^2, slowly-drifting bias
    accel_bias_walk:  float = 0.001   # m/s^2 per sqrt(s), random walk rate
    gyro_noise_std:   float = 0.002   # rad/s, white noise
    gyro_bias:        float = 0.001   # rad/s, slowly-drifting bias
    gyro_bias_walk:   float = 0.0002  # rad/s per sqrt(s), random walk rate


@dataclass
class BaroNoiseConfig:
    alt_noise_std:    float = 0.15    # m, white noise
    lag_tau:          float = 0.08    # s, first-order lag time constant


class IMUSensor:
    """Simulates a 3-axis accelerometer + gyroscope with bias drift and noise."""

    def __init__(self, config: Optional[IMUNoiseConfig] = None, seed: int = None):
        self.cfg = config or IMUNoiseConfig()
        self.rng = np.random.default_rng(seed)
        self.accel_bias_state = np.array([0.0, 0.0, self.cfg.accel_bias])
        self.gyro_bias_state  = np.zeros(3)

    def sample(self, true_accel_body: np.ndarray, true_gyro_body: np.ndarray, dt: float):
        """
        Returns (noisy_accel, noisy_gyro) in body frame, m/s^2 and rad/s.
        true_accel_body should include the "felt" acceleration (specific
        force) — i.e. true acceleration MINUS gravity in body frame, since
        that's what an accelerometer physically measures.
        """
        # Bias random walk
        self.accel_bias_state += self.rng.normal(0, self.cfg.accel_bias_walk*np.sqrt(dt), 3)
        self.gyro_bias_state  += self.rng.normal(0, self.cfg.gyro_bias_walk*np.sqrt(dt), 3)

        accel_noise = self.rng.normal(0, self.cfg.accel_noise_std, 3)
        gyro_noise  = self.rng.normal(0, self.cfg.gyro_noise_std, 3)

        noisy_accel = true_accel_body + self.accel_bias_state + accel_noise
        noisy_gyro  = true_gyro_body  + self.gyro_bias_state  + gyro_noise

        return noisy_accel, noisy_gyro


class BarometerSensor:
    """Simulates a barometric altimeter with noise and first-order response lag."""

    def __init__(self, config: Optional[BaroNoiseConfig] = None, seed: int = None):
        self.cfg = config or BaroNoiseConfig()
        self.rng = np.random.default_rng(seed)
        self.estimated_alt = 0.0

    def sample(self, true_alt: float, dt: float) -> float:
        """Returns noisy, lagged altitude estimate in metres."""
        alpha = dt / (self.cfg.lag_tau + dt)   # first-order lag coefficient
        self.estimated_alt += alpha * (true_alt - self.estimated_alt)
        noise = self.rng.normal(0, self.cfg.alt_noise_std)
        return self.estimated_alt + noise
