"""Anbindung des rechten ToF-Sensors.

Dieses Modul liest Distanzwerte des rechten VL53L1X-Sensors aus und
veröffentlicht sie über MQTT. Es nutzt die Pimoroni VL53L1X-Bibliothek.

"""

import time
from typing import Any, Protocol

from shared.data_models import TofPayload
from shared.mqtt_client import MQTTWrapper


class TofSensor(Protocol):
    """Schnittstelle für den ToF-Sensor für leichtere Testbarkeit."""

    def open(self) -> None:
        """Öffnet die I2C-Verbindung zum Sensor."""
        ...

    def set_timing(self, timing_budget: int, inter_measurement_period: int) -> None:
        """Setzt das Timing-Budget und das Messintervall."""
        ...

    def start_ranging(self, mode: int) -> None:
        """Startet die kontinuierliche Messung im angegebenen Modus."""
        ...

    def stop_ranging(self) -> None:
        """Stoppt die kontinuierliche Messung."""
        ...

    def get_distance(self) -> int:
        """Gibt die gemessene Distanz in Millimetern zurück."""
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

    is_valid = 0.0 < distance_cm < 400.0
    return TofPayload(
        timestamp_ms=now_ms,
        distance_cm=float(distance_cm),
        is_valid=is_valid,
    )


def read_sensor(sensor: TofSensor | None) -> float | None:
    """Liest den Sensorwert sicher aus (Boundary Function für I/O).

    Der gelesene Wert in Millimetern wird in Zentimeter umgerechnet.
    Bei Fehlern oder wenn kein Sensor vorhanden ist, wird None zurückgegeben.
    Dies blockiert im Normalbetrieb nicht länger als das Timing-Budget (50 ms).
    """
    if sensor is None:
        return None
    try:
        dist_mm = sensor.get_distance()
        return dist_mm / 10.0
    except Exception:
        return None


def run_right_node() -> None:
    """Initialisiert den rechten Sensor und veröffentlicht die Messwerte dauerhaft."""
    try:
        import VL53L1X
    except ImportError:
        print("Fehler: VL53L1X ist nicht installiert.")
        return

    mqtt = MQTTWrapper()

    sensor_right: Any = None

    # Rechter Sensor: I2C-Bus 0
    try:
        sensor_right = VL53L1X.VL53L1X(i2c_bus=0, i2c_address=0x29)
        sensor_right.open()
        sensor_right.set_timing(33000, 50)
        sensor_right.start_ranging(3)
    except Exception as e:
        print(f"Rechter Sensor konnte nicht initialisiert werden: {e}")
        sensor_right = None

    try:
        while True:
            start_time = time.time()

            right_cm = read_sensor(sensor_right)
            right_payload = create_tof_payload(right_cm)
            mqtt.publish("sensors/tof/right", right_payload)

            #20 Hz (50 ms Periode)
            elapsed = time.time() - start_time
            sleep_time = max(0.001, 0.05 - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass
    finally:
        if sensor_right is not None:
            try:
                sensor_right.stop_ranging()
            except Exception:
                pass
        mqtt.close()


if __name__ == "__main__":
    run_right_node()
