"""Anbindung der seitlich gerichteten ToF-Sensoren.

Dieses Modul liest Distanzwerte der zwei VL53L0X-Sensoren (links und rechts)
aus und veröffentlicht sie über MQTT.

"""

import time
from typing import Protocol

from shared.data_models import TofPayload
from shared.mqtt_client import MQTTWrapper


class TofSensor(Protocol):
    """Schnittstelle für den ToF-Sensor für leichtere Testbarkeit."""

    @property
    def distance(self) -> float:
        """Gibt die gemessene Distanz in Zentimetern zurück."""
        ...

    @property
    def data_ready(self) -> bool:
        """Gibt True zurück, wenn neue Messdaten bereitstehen."""
        ...

    def clear_interrupt(self) -> None:
        """Löscht den Interrupt, um die nächste Messung zu starten."""
        ...


def create_tof_payload(distance_cm: float | None) -> TofPayload:
    """Wandelt die gelesene Distanz in eine MQTT-Payload um.

    Wenn None übergeben wird (z. B. bei Sensorfehlern oder fehlendem Sensor),
    wird eine Payload mit is_valid=False generiert.

    :param distance_cm: Die vom VL53L1X gemessene Distanz in Zentimetern oder None.
    :return: Die fertige TofPayload mit der Distanz in cm.
    """
    now_ms = int(time.time() * 1000)

    if distance_cm is None:
        return TofPayload(timestamp_ms=now_ms, distance_cm=0.0, is_valid=False)

    # VL53L1X kann im Long-Range-Modus bis zu 400 cm (oder mehr) messen.
    # Werte über 800 cm sind typischerweise Fehler- bzw. Out-of-Range-Werte.
    is_valid = 0 < distance_cm < 800.0
    return TofPayload(
        timestamp_ms=now_ms,
        distance_cm=distance_cm,
        is_valid=is_valid,
    )


def read_sensor(sensor: TofSensor | None) -> float | None:
    """Liest den Sensorwert sicher aus (Boundary Function für I/O).

    Gibt den Abstand in cm zurück, falls neue Daten bereitstehen, andernfalls None.
    Bei Fehlern wird None zurückgegeben, was im weiteren Verlauf als ungültig markiert wird.
    """
    if sensor is None:
        return None
    try:
        if sensor.data_ready:
            dist = sensor.distance
            sensor.clear_interrupt()
            return dist
    except Exception:
        return None
    return None


def run_node() -> None:
    """Initialisiert die Sensoren und veröffentlicht die Messwerte dauerhaft."""
    try:
        import adafruit_vl53l1x
        from adafruit_extended_bus import ExtendedI2C as I2C
    except ImportError:
        print("Fehler: adafruit-circuitpython-vl53l1x oder adafruit-extended-bus ist nicht installiert.")
        return

    mqtt = MQTTWrapper()

    sensor_left: adafruit_vl53l1x.VL53L1X | None = None
    sensor_right: adafruit_vl53l1x.VL53L1X | None = None

    # Linker Sensor: I2C-Bus 6
    try:
        i2c_left = I2C(6)
        sensor_left = adafruit_vl53l1x.VL53L1X(i2c_left)
        sensor_left.start_ranging()
    except Exception as e:
        print(f"Linker Sensor konnte nicht initialisiert werden: {e}")

    # Rechter Sensor: I2C-Bus 0
    try:
        i2c_right = I2C(0)
        sensor_right = adafruit_vl53l1x.VL53L1X(i2c_right)
        sensor_right.start_ranging()
    except Exception as e:
        print(f"Rechter Sensor konnte nicht initialisiert werden: {e}")

    try:
        while True:
            left_cm = read_sensor(sensor_left)
            # Nur senden, wenn tatsächlich neue Sensordaten gelesen wurden
            if left_cm is not None:
                left_payload = create_tof_payload(left_cm)
                mqtt.publish("sensors/tof/left", left_payload)

            right_cm = read_sensor(sensor_right)
            if right_cm is not None:
                right_payload = create_tof_payload(right_cm)
                mqtt.publish("sensors/tof/right", right_payload)

            time.sleep(0.05)  # 20 Hz Leserate
    except KeyboardInterrupt:
        pass
    finally:
        mqtt.close()


if __name__ == "__main__":
    run_node()
