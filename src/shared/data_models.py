"""Gemeinsame Datenmodelle für die Kommunikation zwischen Komponenten."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


@dataclass
class TimestampedPayload:
    """Gemeinsame Basis für Payloads mit Messzeitpunkt.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    """

    timestamp_ms: int


@dataclass
class TofPayload(TimestampedPayload):
    """Messwert eines seitlich montierten ToF-Sensors.

    :param distance_cm: Gemessener seitlicher Abstand in Zentimetern.
    :param is_valid: Gibt an, ob der Sensor einen verwertbaren Wert geliefert hat.
    """

    distance_cm: float
    is_valid: bool


@dataclass
class RadarPayload(TimestampedPayload):
    """Messwert des rückwärts gerichteten Radars.

    :param distance_cm: Entfernung des erkannten Fahrzeugs in Zentimetern.
    :param rel_speed_kmh: Relative Geschwindigkeit gegenüber dem Fahrrad.
    :param is_valid: Gibt an, ob das Radar einen verwertbaren Wert geliefert hat.
    """

    distance_cm: float
    rel_speed_kmh: float
    is_valid: bool


@dataclass
class GpsPayload(TimestampedPayload):
    """Positions- und Geschwindigkeitsdaten des GPS-Moduls.

    :param latitude: Breitengrad in Dezimalgrad.
    :param longitude: Längengrad in Dezimalgrad.
    :param speed_kmh: Geschwindigkeit des Fahrrads in Kilometern pro Stunde.
    :param satellites_connected: Anzahl der verbundenen Satelliten.
    """

    latitude: float
    longitude: float
    speed_kmh: float
    satellites_connected: int


@dataclass
class ImuPayload(TimestampedPayload):
    """Beschleunigungsdaten der inertialen Messeinheit.

    :param accel_x: Beschleunigung entlang der x-Achse.
    :param accel_y: Beschleunigung entlang der y-Achse.
    :param accel_z: Beschleunigung entlang der z-Achse.
    """

    accel_x: float
    accel_y: float
    accel_z: float


@dataclass
class VisionPayload(TimestampedPayload):
    """Ergebnisse der YOLO-Fahrzeugerkennung im aktuellen Frame.

    :param found_vehicle: Gibt an, ob mindestens ein relevantes Fahrzeug erkannt wurde.
    :param detected_types: Liste der erkannten Fahrzeugtypen (z. B. ['Car', 'Truck']).
    :param vehicle_count: Anzahl der relevanten Fahrzeugerkennungen im Bild.
    :param inference_time_ms: Reine Berechnungszeit des Modells für diesen Frame.
    """

    found_vehicle: bool
    detected_types: list[str]
    vehicle_count: int
    inference_time_ms: float


@dataclass
class Coordinates:
    """Geografische Position eines aufgezeichneten Ereignisses.

    :param lat: Breitengrad in Dezimalgrad.
    :param lon: Längengrad in Dezimalgrad.
    """

    lat: float
    lon: float


@dataclass
class Violation:
    """Daten eines erkannten Abstandsverstoßes.

    :param timestamp: Unix-Zeitstempel des Verstoßes in Sekunden.
    :param coordinates: Position des Verstoßes.
    :param distance_cm: Gemessener seitlicher Abstand in Zentimetern.
    :param speed_kmh: Geschwindigkeit des Fahrrads in Kilometern pro Stunde.
    :param image_path: Relativer Pfad zum Beweisbild, falls bereits vorhanden.
    """

    timestamp: int
    coordinates: Coordinates
    distance_cm: float
    speed_kmh: float
    image_path: Path | None = None

PayloadType: TypeAlias = (
    type[GpsPayload]
    | type[ImuPayload]
    | type[RadarPayload]
    | type[TofPayload]
    | type[VisionPayload]
)

PayloadInstance: TypeAlias = GpsPayload | ImuPayload | RadarPayload | TofPayload | VisionPayload
