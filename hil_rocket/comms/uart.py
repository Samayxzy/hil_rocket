"""
uart.py
Threaded serial manager for talking to the MONK flight computer.
Sends synthetic sensor packets, receives actuator (servo) commands on a
background thread so the main sim loop never blocks on serial I/O.

Falls back to "offline mode" automatically if no COM port is given or
the port fails to open — the offline PD controller in tvc.py takes over
attitude control in that case.
"""

import logging
import threading
import time
from typing import Optional
from queue import Queue, Empty

from comms.packet import format_sensor_packet, parse_actuator_packet, ActuatorCommand

logger = logging.getLogger(__name__)

try:
    import serial
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False
    logging.warning("pyserial not installed — UART will run in offline mode only")


class UARTManager:
    def __init__(self, port: Optional[str] = None, baud: int = 115200):
        self.port = port.strip() if port else None
        self.baud = baud
        self.ser = None
        self.connected = False

        self._rx_queue: Queue = Queue()
        self._stop_flag = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None

        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.last_packet_sent = ""
        self._last_rx_time = 0.0

        if self.port and PYSERIAL_AVAILABLE:
            self._connect()

    def _connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.05)
            self.connected = True
            self._stop_flag.clear()
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            logger.info(f"UART connected: {self.port} @ {self.baud} baud")
        except Exception as e:
            logger.warning(f"UART connection failed ({self.port}): {e} — running offline")
            self.connected = False
            self.ser = None

    def _rx_loop(self):
        """Background thread: continuously read lines and parse actuator commands."""
        buf = b""
        while not self._stop_flag.is_set():
            try:
                if self.ser and self.ser.in_waiting:
                    buf += self.ser.read(self.ser.in_waiting)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            decoded = line.decode("utf-8", errors="ignore")
                        except Exception:
                            continue
                        cmd = parse_actuator_packet(decoded)
                        if cmd:
                            self._rx_queue.put(cmd)
                            self.packets_received += 1
                            self._last_rx_time = time.time()
                        else:
                            self.packets_dropped += 1
                else:
                    time.sleep(0.002)
            except Exception as e:
                logger.error(f"UART RX error: {e}")
                time.sleep(0.1)

    def send_sensor_packet(self, ax, ay, az, gx, gy, gz, baro_alt):
        """Non-blocking send of a sensor packet. No-op if offline."""
        packet = format_sensor_packet(ax, ay, az, gx, gy, gz, baro_alt)
        self.last_packet_sent = packet.strip()
        if self.connected and self.ser:
            try:
                self.ser.write(packet.encode("utf-8"))
                self.packets_sent += 1
            except Exception as e:
                logger.error(f"UART send failed: {e}")
                self.connected = False
        else:
            # Offline: still count as "sent" for telemetry realism, since the
            # sim continues generating packets even with no HW attached
            self.packets_sent += 1

    def get_latest_actuator_command(self) -> Optional[ActuatorCommand]:
        """Drain the RX queue, returning only the most recent command (if any)."""
        latest = None
        while True:
            try:
                latest = self._rx_queue.get_nowait()
            except Empty:
                break
        return latest

    def link_quality(self) -> float:
        """0-1 estimate based on recent RX activity. 0 if offline or stale."""
        if not self.connected:
            return 0.0
        if time.time() - self._last_rx_time > 2.0:
            return 0.0
        return 1.0

    def close(self):
        self._stop_flag.set()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.connected = False
