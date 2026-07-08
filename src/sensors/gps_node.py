"""Anbindung des GPS-Moduls (L76X).

Dieses Modul liest NMEA-Sätze von einem per UART angeschlossenen L76X-GPS-Modul,
parst diese und veröffentlicht die Daten über MQTT.
"""

import time
from dataclasses import dataclass
from typing import Protocol

from shared.data_models import GpsPayload
from shared.mqtt_client import MQTTWrapper


@dataclass(frozen=True)
class GpsState:
    """Zwischenzustand der GPS-Daten, der aus mehreren NMEA-Sätzen aufgebaut wird."""

    latitude: float = 0.0
    longitude: float = 0.0
    speed_kmh: float = 0.0
    satellites: int = 0
    is_valid: bool = False


class SerialPort(Protocol):
    """Schnittstelle für den seriellen Port für leichtere Testbarkeit."""

    def readline(self) -> bytes:
        """Liest eine Zeile vom seriellen Port."""
        ...

    def close(self) -> None:
        """Schließt den seriellen Port."""
        ...


def verify_checksum(sentence: str) -> bool:
    """Prüft die NMEA-Checksumme eines Satzes.

    :param sentence: Ein NMEA-Satz, der mit '$' beginnt und mit '*' gefolgt von der Checksumme endet.
    :return: True, wenn die Checksumme gültig ist.
    """
    if not sentence.startswith("$") or "*" not in sentence:
        return False

    try:
        content, checksum_str = sentence[1:].rsplit("*", 1)
        calculated = 0
        for char in content:
            calculated ^= ord(char)
        expected = int(checksum_str.strip(), 16)
        return calculated == expected
    except ValueError:
        return False


def parse_coordinate(coord_str: str, direction: str) -> float | None:
    """Parst eine NMEA-Koordinate (z. B. '5133.82', 'N') in Dezimalgrad.

    :param coord_str: Die Koordinate im Format DDMM.MMMM oder DDDMM.MMMM.
    :param direction: Die Himmelsrichtung ('N', 'S', 'E', 'W').
    :return: Die Koordinate in Dezimalgrad oder None bei Fehlern.
    """
    if not coord_str or not direction:
        return None
    try:
        parts = coord_str.split(".")
        if len(parts) != 2 or len(parts[0]) < 3:
            return None

        degrees = float(parts[0][:-2])
        minutes = float(parts[0][-2:] + "." + parts[1])

        decimal_degrees = degrees + (minutes / 60.0)

        if direction in ["S", "W"]:
            decimal_degrees = -decimal_degrees

        return decimal_degrees
    except ValueError:
        return None


def parse_nmea_sentence(sentence: str, current_state: GpsState) -> GpsState:
    """Parst einen einzelnen NMEA-Satz und aktualisiert den GPS-Zustand.

    Es werden nur RMC- und GGA-Sätze berücksichtigt.

    :param sentence: Der empfangene NMEA-Satz (inklusive '$' und Checksumme).
    :param current_state: Der bisherige GPS-Zustand.
    :return: Der neue, aktualisierte GPS-Zustand.
    """
    if not verify_checksum(sentence):
        return current_state

    parts = sentence.strip().split(",")
    if not parts:
        return current_state

    sentence_id = parts[0][1:]  # Entfernt das '$'

    if sentence_id.endswith("RMC"):
        if len(parts) >= 8:
            status = parts[2]
            is_valid = status == "A"

            lat = parse_coordinate(parts[3], parts[4])
            lon = parse_coordinate(parts[5], parts[6])

            lat_val = lat if lat is not None else current_state.latitude
            lon_val = lon if lon is not None else current_state.longitude

            speed_kmh = current_state.speed_kmh
            try:
                if parts[7]:
                    speed_kmh = float(parts[7]) * 1.852
            except ValueError:
                pass

            return GpsState(
                latitude=lat_val,
                longitude=lon_val,
                speed_kmh=speed_kmh,
                satellites=current_state.satellites,
                is_valid=is_valid,
            )

    elif sentence_id.endswith("GGA"):
        if len(parts) >= 8:
            satellites = current_state.satellites
            try:
                if parts[7]:
                    satellites = int(parts[7])
            except ValueError:
                pass

            return GpsState(
                latitude=current_state.latitude,
                longitude=current_state.longitude,
                speed_kmh=current_state.speed_kmh,
                satellites=satellites,
                is_valid=current_state.is_valid,
            )

    return current_state


def create_gps_payload(state: GpsState) -> GpsPayload:
    """Erzeugt eine MQTT-Payload aus dem aktuellen GPS-Zustand.

    :param state: Der aktuelle GPS-Zustand.
    :return: Die fertige GpsPayload.
    """
    return GpsPayload(
        timestamp_ms=int(time.time() * 1000),
        latitude=state.latitude,
        longitude=state.longitude,
        speed_kmh=state.speed_kmh,
        satellites_connected=state.satellites,
    )


def read_sentence(serial_port: SerialPort | None) -> str | None:
    """Liest einen NMEA-Satz vom seriellen Port (Boundary Function für I/O).

    :param serial_port: Die serielle Schnittstelle.
    :return: Den gelesenen String oder None bei Fehlern/Timeout.
    """
    if serial_port is None:
        return None
    try:
        line_bytes = serial_port.readline()
        if not line_bytes:
            return None
        return line_bytes.decode("ascii", errors="replace").strip()
    except Exception:
        return None


def run_node(port_name: str = "/dev/ttyS0", baudrate: int = 9600) -> None:
    """Initialisiert das GPS-Modul und veröffentlicht die Messwerte dauerhaft.

    :param port_name: Name des seriellen Ports (Standard beim Radxa: /dev/ttyS0).
    :param baudrate: Baudrate für die serielle Verbindung (Standard L76X: 9600).
    """
    try:
        import serial
    except ImportError:
        print("Fehler: pyserial ist nicht installiert.")
        return

    mqtt = MQTTWrapper()

    serial_port: SerialPort | None = None
    try:
        serial_port = serial.Serial(port_name, baudrate, timeout=1.0)
    except Exception as e:
        print(f"GPS-Modul konnte nicht initialisiert werden: {e}")

    state = GpsState()

    try:
        while True:
            sentence = read_sentence(serial_port)
            if sentence is not None:
                new_state = parse_nmea_sentence(sentence, state)

                if new_state != state:
                    state = new_state
                    # Veröffentliche bei gültigen Zustandsänderungen
                    if state.is_valid:
                        payload = create_gps_payload(state)
                        mqtt.publish("sensors/gps", payload)
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if serial_port is not None:
            serial_port.close()
        mqtt.close()


if __name__ == "__main__":
    run_node()
