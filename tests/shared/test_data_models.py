"""Tests für die gemeinsamen MQTT-Datenmodelle."""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from shared.data_models import (
    Coordinates,
    GpsPayload,
    ImuPayload,
    PayloadInstance,
    RadarPayload,
    RideData,
    RoutePoint,
    TofPayload,
    VehicleDetection,
    Violation,
    VisionPayload,
)


def test_payloads_share_timestamp_field() -> None:
    """Prüft, dass alle Payloads den gemeinsamen Zeitstempel-Vertrag erfüllen."""
    payloads: list[PayloadInstance] = [
        TofPayload(timestamp_ms=1, distance_cm=85.5, is_valid=True),
        RadarPayload(
            timestamp_ms=1,
            distance_cm=420.0,
            rel_speed_kmh=18.5,
            is_valid=True,
            angle=0,
            snr=0,
        ),
        GpsPayload(timestamp_ms=1, latitude=51.3127, longitude=9.4924, speed_kmh=22.1, satellites_connected=12),
        ImuPayload(timestamp_ms=1, accel_x=0.1, accel_y=-0.2, accel_z=9.81),
        VisionPayload(
            timestamp_ms=1,
            found_vehicle=True,
            detected_types=["Car"],
            vehicle_count=1,
            inference_time_ms=12.5,
        ),
    ]

    for payload in payloads:
        assert asdict(payload)["timestamp_ms"] == 1


@pytest.mark.parametrize("is_valid", [True, False])
def test_tof_payload_is_json_compatible(is_valid: bool) -> None:
    """Prüft gültige und ungültige ToF-Messungen auf JSON-Kompatibilität.

    :param is_valid: Simulierter Gültigkeitszustand der Sensormessung.
    """
    payload = TofPayload(
        timestamp_ms=1_717_618_000_000,
        distance_cm=85.5,
        is_valid=is_valid,
    )

    serialized = json.loads(json.dumps(asdict(payload)))

    assert serialized["distance_cm"] == 85.5
    assert serialized["is_valid"] is is_valid


@pytest.mark.parametrize("rel_speed_kmh", [18.5, -5.0])
def test_radar_payload_preserves_relative_speed(rel_speed_kmh: float) -> None:
    """Prüft Annäherung und Entfernung eines erkannten Fahrzeugs.

    :param rel_speed_kmh: Simulierte relative Geschwindigkeit des Fahrzeugs.
    """
    payload = RadarPayload(
        timestamp_ms=1_717_618_000_000,
        distance_cm=420.0,
        rel_speed_kmh=rel_speed_kmh,
        is_valid=True,
        angle=0,
        snr=0,
    )

    serialized = json.loads(json.dumps(asdict(payload)))

    assert serialized["rel_speed_kmh"] == rel_speed_kmh


def test_gps_payload_is_json_compatible() -> None:
    """Prüft die GPS-Daten auf verlustfreie JSON-Serialisierung."""
    payload = GpsPayload(
        timestamp_ms=1_717_618_000_000,
        latitude=51.3127,
        longitude=9.4924,
        speed_kmh=22.1,
        satellites_connected=12,
    )

    serialized = json.loads(json.dumps(asdict(payload)))

    assert serialized == asdict(payload)


def test_imu_payload_is_json_compatible() -> None:
    """Prüft die Beschleunigungsdaten auf JSON-Kompatibilität."""
    payload = ImuPayload(
        timestamp_ms=1_717_618_000_000,
        accel_x=0.1,
        accel_y=-0.2,
        accel_z=9.81,
    )

    serialized = json.loads(json.dumps(asdict(payload)))

    assert serialized == asdict(payload)


def test_vision_payload_is_json_compatible() -> None:
    """Prüft die Ergebnisse der Fahrzeugerkennung auf JSON-Kompatibilität."""
    detection = VehicleDetection(
        class_name="Car",
        confidence=0.9,
        x_min=0.1,
        y_min=0.2,
        x_max=0.6,
        y_max=0.8,
    )
    payload = VisionPayload(
        timestamp_ms=1_717_618_000_000,
        found_vehicle=True,
        detected_types=["Car", "Truck"],
        vehicle_count=2,
        inference_time_ms=12.5,
        detections=[detection],
    )

    serialized = json.loads(json.dumps(asdict(payload)))

    assert serialized == asdict(payload)
    assert serialized["detections"] == [asdict(detection)]


def test_vehicle_detection_calculates_normalized_area() -> None:
    """Prüft die Flächenberechnung einer Bounding-Box."""
    detection = VehicleDetection(
        class_name="Car",
        confidence=0.9,
        x_min=0.1,
        y_min=0.2,
        x_max=0.6,
        y_max=0.8,
    )

    assert detection.area == pytest.approx(0.3)


def test_violation_matches_agreed_data_structure() -> None:
    """Prüft die vereinbarte verschachtelte Struktur eines Verstoßes."""
    violation = Violation(
        timestamp=1_717_618_015,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
    )

    assert asdict(violation) == {
        "timestamp": 1_717_618_015,
        "coordinates": {"lat": 51.31275, "lon": 9.49245},
        "distance_cm": 85.5,
        "speed_kmh": 22.1,
        "image_path": None,
    }


def test_violation_accepts_relative_image_path() -> None:
    """Prüft einen später ergänzten relativen Bildpfad."""
    image_path = Path("images/violations/auto_id_5_1717618015.jpg")
    violation = Violation(
        timestamp=1_717_618_015,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
        image_path=image_path,
    )

    assert violation.image_path == image_path


def test_ride_data_matches_agreed_data_structure() -> None:
    """Prüft die vereinbarte Struktur einer abgeschlossenen Fahrt."""
    violation = Violation(
        timestamp=1_717_618_015,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
    )
    ride_data = RideData(
        ride_id="tour_2026_06_05_1430",
        start_time=1_717_618_000,
        end_time=1_717_625_000,
        route_logs=[RoutePoint(timestamp=1_717_618_010, lat=51.3127, lon=9.4924)],
        violations=[violation],
    )

    assert asdict(ride_data) == {
        "ride_id": "tour_2026_06_05_1430",
        "start_time": 1_717_618_000,
        "end_time": 1_717_625_000,
        "route_logs": [{"timestamp": 1_717_618_010, "lat": 51.3127, "lon": 9.4924}],
        "violations": [
            {
                "timestamp": 1_717_618_015,
                "coordinates": {"lat": 51.31275, "lon": 9.49245},
                "distance_cm": 85.5,
                "speed_kmh": 22.1,
                "image_path": None,
            }
        ],
    }
