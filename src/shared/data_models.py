"""Gemeinsame Datenmodelle für die Kommunikation zwischen Komponenten."""

from dataclasses import dataclass


@dataclass
class TofPayload:
    """Messwert eines seitlich montierten ToF-Sensors.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param distance_cm: Gemessener seitlicher Abstand in Zentimetern.
    :param is_valid: Gibt an, ob der Sensor einen verwertbaren Wert geliefert hat.
    """

    timestamp_ms: int
    distance_cm: float
    is_valid: bool


@dataclass
class RadarPayload:
    """Messwert des rückwärts gerichteten Radars.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param distance_cm: Entfernung des erkannten Fahrzeugs in Zentimetern.
    :param rel_speed_kmh: Relative Geschwindigkeit gegenüber dem Fahrrad.
    :param is_valid: Gibt an, ob das Radar einen verwertbaren Wert geliefert hat.
    """

    timestamp_ms: int
    distance_cm: float
    rel_speed_kmh: float
    is_valid: bool


@dataclass
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


@dataclass
class ImuPayload:
    """Beschleunigungsdaten der inertialen Messeinheit.

    :param timestamp_ms: Unix-Zeitstempel der Messung in Millisekunden.
    :param accel_x: Beschleunigung entlang der X-Achse.
    :param accel_y: Beschleunigung entlang der Y-Achse.
    :param accel_z: Beschleunigung entlang der Z-Achse.
    """

    timestamp_ms: int
    accel_x: float
    accel_y: float
    accel_z: float
