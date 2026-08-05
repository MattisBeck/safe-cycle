"""Gemeinsame Datenmodelle für die Kommunikation zwischen Komponenten."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True)
class TofPayload:
    """Messwert eines seitlich montierten ToF-Sensors.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param distance_cm: Gemessener seitlicher Abstand in Zentimetern.
    :param is_valid: Gibt an, ob der Sensor einen verwertbaren Wert geliefert hat.
    """

    timestamp_ms: int
    distance_cm: float
    is_valid: bool


@dataclass(frozen=True)
class RadarPayload:
    """Messwert des rückwärts gerichteten Radars.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param distance_cm: Entfernung des erkannten Fahrzeugs in Zentimetern.
    :param rel_speed_kmh: Relative Geschwindigkeit gegenüber dem Fahrrad.
    :param is_valid: Gibt an, ob das Radar einen verwertbaren Wert geliefert hat.
    :param angle: Winkel des erkannten Fahrzeugs.
    :param snr: Signal-Rausch-Verhältnis des erkannten Fahrzeugs.
    """

    timestamp_ms: int
    distance_cm: float
    rel_speed_kmh: float
    is_valid: bool
    angle: int
    snr: int


@dataclass(frozen=True)
class GpsPayload:
    """Positions- und Geschwindigkeitsdaten des GPS-Moduls.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param latitude: Breitengrad in Dezimalgrad.
    :param longitude: Längengrad in Dezimalgrad.
    :param speed_kmh: Geschwindigkeit des Fahrrads in Kilometern pro Stunde.
    :param satellites_connected: Anzahl der verbundenen Satelliten.
    """

    timestamp_ms: int
    latitude: float
    longitude: float
    speed_kmh: float
    satellites_connected: int


@dataclass(frozen=True)
class ImuPayload:
    """Beschleunigungsdaten der inertialen Messeinheit.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param accel_x: Beschleunigung entlang der x-Achse.
    :param accel_y: Beschleunigung entlang der y-Achse.
    :param accel_z: Beschleunigung entlang der z-Achse.
    """

    timestamp_ms: int
    accel_x: float
    accel_y: float
    accel_z: float


@dataclass(frozen=True)
class VehicleDetection:
    """Ein erkanntes Fahrzeug mit normalisierter Bounding-Box.

    :param class_name: Erkannte Fahrzeugklasse.
    :param confidence: Konfidenz der Modellerkennung zwischen 0.0 und 1.0.
    :param x_min: Linke Boxgrenze relativ zur Bildbreite.
    :param y_min: Obere Boxgrenze relativ zur Bildhöhe.
    :param x_max: Rechte Boxgrenze relativ zur Bildbreite.
    :param y_max: Untere Boxgrenze relativ zur Bildhöhe.
    """

    class_name: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def area(self) -> float:
        """Gibt die normalisierte Fläche der Box zurück."""
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)


@dataclass(frozen=True)
class VisionPayload:
    """Ergebnisse der YOLO-Fahrzeugerkennung im aktuellen Frame.

    :param timestamp_ms: Unix-Zeitstempel der Bildverarbeitung in Millisekunden.
    :param found_vehicle: Gibt an, ob ein relevantes Fahrzeug erkannt wurde.
    :param detected_types: Liste der erkannten Fahrzeugtypen.
    :param vehicle_count: Anzahl der relevanten Fahrzeugerkennungen im Bild.
    :param inference_time_ms: Reine Berechnungszeit des Modells für diesen Frame.
    :param detections: Einzelne Fahrzeugerkennungen mit Bounding-Boxen.
    """

    timestamp_ms: int
    found_vehicle: bool
    detected_types: list[str]
    vehicle_count: int
    inference_time_ms: float
    detections: list[VehicleDetection] = field(default_factory=list)


@dataclass
class Coordinates:
    """Geografische Position eines aufgezeichneten Ereignisses."""

    lat: float
    lon: float


@dataclass
class Violation:
    """Daten eines erkannten Abstandsverstoßes."""

    timestamp: int
    coordinates: Coordinates
    distance_cm: float
    speed_kmh: float
    image_path: Path | None = None


@dataclass
class RoutePoint:
    """Aufgezeichneter Punkt einer gefahrenen Route."""

    timestamp: int
    lat: float
    lon: float


@dataclass
class RideData:
    """Vollständige Daten einer abgeschlossenen Fahrt."""

    ride_id: str
    start_time: int
    end_time: int
    route_logs: list[RoutePoint]
    violations: list[Violation]


PayloadInstance: TypeAlias = GpsPayload | ImuPayload | RadarPayload | TofPayload | VisionPayload
