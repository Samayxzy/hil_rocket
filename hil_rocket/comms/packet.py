"""
packet.py
UART packet formatting/parsing matching the MONK board's protocol.

Outgoing (sim -> flight computer), $S = "sensor" packet:
  $S,ax,ay,az,gx,gy,gz,baro_alt\n
  ax/ay/az in m/s^2, gx/gy/gz in rad/s, baro_alt in metres.

Incoming (flight computer -> sim), $A = "actuator" packet:
  $A,servo_pitch_deg,servo_yaw_deg\n
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def format_sensor_packet(ax, ay, az, gx, gy, gz, baro_alt) -> str:
    return f"$S,{ax:.4f},{ay:.4f},{az:.4f},{gx:.5f},{gy:.5f},{gz:.5f},{baro_alt:.2f}\n"


@dataclass
class ActuatorCommand:
    servo_pitch_deg: float
    servo_yaw_deg:   float


def parse_actuator_packet(line: str) -> Optional[ActuatorCommand]:
    """Parse a $A,pitch,yaw packet. Returns None if malformed."""
    line = line.strip()
    if not line.startswith("$A,"):
        return None
    try:
        parts = line[3:].split(",")
        if len(parts) < 2:
            return None
        return ActuatorCommand(
            servo_pitch_deg=float(parts[0]),
            servo_yaw_deg=float(parts[1]),
        )
    except (ValueError, IndexError):
        logger.debug(f"Malformed actuator packet: {line!r}")
        return None
