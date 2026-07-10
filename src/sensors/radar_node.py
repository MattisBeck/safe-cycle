"""Anbindung des rückwärts gerichteten Radars (HLK-LD2451).

Dieses Modul liest die seriellen Daten eines per UART angeschlossenen
HLK-LD2451 Radarsensors, parst die erkannten Ziele und veröffentlicht
die Daten über MQTT.
"""

import time
from dataclasses import dataclass
from typing import Protocol

from shared.data_models import RadarPayload
from shared.mqtt_client import MQTTWrapper

HEADER = b"\xf4\xf3\xf2\xf1"
TAIL = b"\xf8\xf7\xf6\xf5"


@dataclass(frozen=True)
class TargetData:
    """Repräsentiert ein einzelnes erkanntes Ziel des Radars."""

    angle: int
    distance_cm: float
    rel_speed_kmh: float
    snr: int


class SerialPort(Protocol):
    """Schnittstelle für den seriellen Port für leichtere Testbarkeit."""

    def read(self, size: int = 1) -> bytes:
        """Liest die angegebene Anzahl an Bytes."""
        ...

    def close(self) -> None:
        """Schließt den seriellen Port."""
        ...


def parse_radar_payload(payload: bytes) -> list[TargetData]:
    """Parst die Nutzdaten eines Radar-Frames in eine Liste von Zielen.

    :param payload: Die binären Nutzdaten (ohne Header, Länge und Tail).
    :return: Eine Liste der erkannten Ziele.
    """
    if len(payload) < 2:
        return []

    num_targets = payload[0]
    # payload[1] enthält normalerweise Alarm-Informationen, die hier ignoriert werden.

    targets = []
    idx = 2
    for _ in range(num_targets):
        if idx + 5 > len(payload):
            break

        angle_raw = payload[idx]
        distance_m = payload[idx + 1]
        speed_dir = payload[idx + 2]
        speed_val = payload[idx + 3]
        snr = payload[idx + 4]

        # Umrechnung laut Protokoll
        angle = angle_raw - 0x80
        distance_cm = float(distance_m * 100)

        speed_kmh = float(speed_val)
        # 0x01 bedeutet Annäherung, 0x00 bedeutet Entfernung
        if speed_dir == 0x00:
            speed_kmh = -speed_kmh

        targets.append(TargetData(
            angle=angle,
            distance_cm=distance_cm,
            rel_speed_kmh=speed_kmh,
            snr=snr,
        ))
        idx += 5

    return targets


def select_primary_target(targets: list[TargetData]) -> TargetData | None:
    """Wählt das relevanteste Ziel aus einer Liste von Zielen aus.

    Priorisiert sich nähernde Fahrzeuge (relative Geschwindigkeit > 0).
    Wenn mehrere Ziele existieren, wird das nächstgelegene gewählt.

    :param targets: Die Liste der geparsten Ziele.
    :return: Das primäre Ziel oder None, wenn keine Ziele vorhanden sind.
    """
    approaching = [t for t in targets if t.rel_speed_kmh > 0.0]

    if approaching:
        return min(approaching, key=lambda t: t.distance_cm)

    if targets:
        return min(targets, key=lambda t: t.distance_cm)

    return None


def create_radar_payload(target: TargetData | None) -> RadarPayload:
    """Erzeugt eine MQTT-Payload aus dem ausgewählten Radar-Ziel.

    :param target: Das ausgewählte Ziel oder None.
    :return: Die fertige RadarPayload.
    """
    now_ms = int(time.time() * 1000)
    if target is None:
        return RadarPayload(
            timestamp_ms=now_ms,
            distance_cm=0.0,
            rel_speed_kmh=0.0,
            is_valid=False,
        )
    return RadarPayload(
        timestamp_ms=now_ms,
        distance_cm=target.distance_cm,
        rel_speed_kmh=target.rel_speed_kmh,
        is_valid=True,
    )


def read_frame(serial_port: SerialPort | None) -> bytes | None:
    """Liest einen vollständigen Frame vom Radar (Boundary Function für I/O).

    Sucht nach dem Start-Header, liest die Längenangabe, die Nutzdaten
    und verifiziert den End-Tail.

    :param serial_port: Die serielle Schnittstelle.
    :return: Die Nutzdaten (Payload) als Bytes oder None bei Fehlern/Timeout.
    """
    if serial_port is None:
        return None

    try:
        # 1. Warte auf Header
        state = 0
        while state < 4:
            b = serial_port.read(1)
            if not b:
                return None
            if b[0] == HEADER[state]:
                state += 1
            else:
                if b[0] == HEADER[0]:
                    state = 1
                else:
                    state = 0

        # 2. Lese Längenfeld (2 Bytes, Little Endian)
        len_bytes = serial_port.read(2)
        if len(len_bytes) < 2:
            return None

        payload_len = int.from_bytes(len_bytes, byteorder="little")

        # 3. Lese Payload
        payload = serial_port.read(payload_len)
        if len(payload) < payload_len:
            return None

        # 4. Lese Tail und verifiziere
        tail = serial_port.read(4)
        if tail != TAIL:
            return None

        return payload
    except Exception:
        return None


def run_radar_node(port_name: str = "/dev/ttyS6", baudrate: int = 115200) -> None:
    """Initialisiert das Radar und veröffentlicht die Messwerte dauerhaft.

    :param port_name: Name des seriellen Ports (Standard: /dev/ttyS6 für UART 6).
    :param baudrate: Baudrate für die serielle Verbindung (Standard LD2451: 115200).
    """
    try:
        import serial
    except ImportError:
        print("Fehler: pyserial ist nicht installiert.")
        return

    mqtt = MQTTWrapper()

    serial_port: SerialPort | None = None
    try:
        serial_port = serial.Serial(port_name, baudrate, timeout=0.5)
    except Exception as e:
        print(f"Radar konnte nicht initialisiert werden: {e}")

    try:
        while True:
            payload = read_frame(serial_port)
            if payload is not None:
                targets = parse_radar_payload(payload)
                primary_target = select_primary_target(targets)
                mqtt_payload = create_radar_payload(primary_target)
                mqtt.publish("sensors/radar", mqtt_payload)
            else:
                # Kurze Pause, wenn kein vollständiger Frame gelesen wurde
                time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        if serial_port is not None:
            serial_port.close()
        mqtt.close()


if __name__ == "__main__":
    run_radar_node()
