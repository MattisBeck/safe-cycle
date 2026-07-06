"""Anbindung der seitlich gerichteten ToF-Sensoren.

Dieses Modul liest Distanzwerte der zwei VL53L0X-Sensoren (links und rechts)
aus und veröffentlicht sie über MQTT.

Hardware-Pins am Radxa Q6A:
- Links: SCL = GPIO 49, SDA = GPIO 48
- Rechts: SCL = GPIO 1, SDA = GPIO 0
"""

import time
from typing import Protocol

from shared.data_models import TofPayload
from shared.mqtt_client import MQTTWrapper


class TofSensor(Protocol):
    """Schnittstelle für den ToF-Sensor für leichtere Testbarkeit."""

    @property
    def range(self) -> int:
        """Gibt die gemessene Distanz in Millimetern zurück."""
        ...


def create_tof_payload(distance_mm: int | None) -> TofPayload:
    """Wandelt die gelesene Distanz in eine MQTT-Payload um.

    Wenn None übergeben wird (z. B. bei Sensorfehlern oder fehlendem Sensor),
    wird eine Payload mit is_valid=False generiert. Die Distanz wird von
    Millimetern in Zentimeter umgerechnet.

    :param distance_mm: Die vom VL53L0X gemessene Distanz in Millimetern oder None.
    :return: Die fertige TofPayload mit der Distanz in cm.
    """
    now_ms = int(time.time() * 1000)

    if distance_mm is None:
        return TofPayload(timestamp_ms=now_ms, distance_cm=0.0, is_valid=False)

    # Werte über 8000 mm sind typischerweise Fehlercodes beim VL53L0X.
    is_valid = 0 < distance_mm < 8000
    return TofPayload(
        timestamp_ms=now_ms,
        distance_cm=distance_mm / 10.0,
        is_valid=is_valid,
    )

def read_sensor(sensor: TofSensor | None) -> int | None:
    """Liest den Sensorwert sicher aus (Boundary Function für I/O)."""
    if sensor is None:
        return None
    try:
        return sensor.range
    except Exception:
        return None


def run_node() -> None:
    """Initialisiert die Sensoren und veröffentlicht die Messwerte dauerhaft."""
    try:
        import adafruit_vl53l0x  # type: ignore[import-untyped]
        import board  # type: ignore[import-untyped]
        import busio  # type: ignore[import-untyped]
    except ImportError:
        print("Fehler: adafruit-circuitpython-vl53l0x oder blinka ist nicht installiert.")
        return

    mqtt = MQTTWrapper()

    sensor_left: adafruit_vl53l0x.VL53L0X | None = None
    sensor_right: adafruit_vl53l0x.VL53L0X | None = None

    # Linker Sensor: SCL = GPIO 49, SDA = GPIO 48
    try:
        i2c_left = busio.I2C(scl=board.D49, sda=board.D48)
        sensor_left = adafruit_vl53l0x.VL53L0X(i2c_left)
    except Exception as e:
        print(f"Linker Sensor konnte nicht initialisiert werden: {e}")

    # Rechter Sensor: SCL = GPIO 1, SDA = GPIO 0
    try:
        i2c_right = busio.I2C(scl=board.D1, sda=board.D0)
        sensor_right = adafruit_vl53l0x.VL53L0X(i2c_right)
    except Exception as e:
        print(f"Rechter Sensor konnte nicht initialisiert werden: {e}")

    try:
        while True:
            left_mm = read_sensor(sensor_left)
            left_payload = create_tof_payload(left_mm)
            mqtt.publish("sensors/tof/left", left_payload)

            right_mm = read_sensor(sensor_right)
            right_payload = create_tof_payload(right_mm)
            mqtt.publish("sensors/tof/right", right_payload)

            time.sleep(0.05)  # 20 Hz Leserate
    except KeyboardInterrupt:
        pass
    finally:
        mqtt.close()


if __name__ == "__main__":
    run_node()
