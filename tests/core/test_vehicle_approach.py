"""Tests für die Annäherungsbewertung von Vision-Payloads."""

from core.vehicle_approach import VehicleApproachState, classify_vehicle_approach
from shared.data_models import VehicleDetection, VisionPayload


def make_vision_payload(timestamp_ms: int, areas: list[float]) -> VisionPayload:
    """Erstellt eine Vision-Payload mit vorgegebenen Boxflächen."""
    detections = [
        VehicleDetection(
            class_name="Car",
            confidence=0.9,
            x_min=0.0,
            y_min=0.0,
            x_max=area,
            y_max=1.0,
        )
        for area in areas
    ]
    return VisionPayload(
        timestamp_ms=timestamp_ms,
        found_vehicle=bool(detections),
        detected_types=[detection.class_name for detection in detections],
        vehicle_count=len(detections),
        inference_time_ms=12.5,
        detections=detections,
    )


def test_classify_vehicle_approach_returns_no_vehicle_without_boxes() -> None:
    """Prüft den Zustand ohne verwertbare Boxen."""
    events = [make_vision_payload(timestamp_ms=9_000, areas=[])]

    assert classify_vehicle_approach(events, reference_timestamp_ms=10_000) is VehicleApproachState.NO_VEHICLE


def test_classify_vehicle_approach_returns_present_for_stable_box() -> None:
    """Prüft, dass eine gleich große Box nicht als Annäherung gilt."""
    events = [
        make_vision_payload(timestamp_ms=timestamp_ms, areas=[0.2])
        for timestamp_ms in [8_000, 8_500, 9_000, 9_500, 10_000]
    ]

    assert classify_vehicle_approach(events, reference_timestamp_ms=10_000) is VehicleApproachState.PRESENT


def test_classify_vehicle_approach_returns_approaching_for_growing_largest_box() -> None:
    """Prüft eine deutliche Zunahme der größten Boxfläche."""
    events = [
        make_vision_payload(timestamp_ms=timestamp_ms, areas=[area])
        for timestamp_ms, area in [
            (8_000, 0.10),
            (8_500, 0.12),
            (9_000, 0.16),
            (9_500, 0.22),
            (10_000, 0.30),
        ]
    ]

    assert classify_vehicle_approach(events, reference_timestamp_ms=10_000) is VehicleApproachState.APPROACHING


def test_classify_vehicle_approach_uses_largest_box_per_frame() -> None:
    """Prüft die Auswahl der größten Box bei mehreren Fahrzeugen."""
    events = [
        make_vision_payload(timestamp_ms=timestamp_ms, areas=areas)
        for timestamp_ms, areas in [
            (8_000, [0.10, 0.05]),
            (8_500, [0.12, 0.06]),
            (9_000, [0.16, 0.07]),
            (9_500, [0.22, 0.08]),
            (10_000, [0.30, 0.09]),
        ]
    ]

    assert classify_vehicle_approach(events, reference_timestamp_ms=10_000) is VehicleApproachState.APPROACHING


def test_classify_vehicle_approach_rejects_insufficient_time_series() -> None:
    """Prüft zu wenige Beobachtungen und zu große Zeitlücken."""
    events = [
        make_vision_payload(timestamp_ms=timestamp_ms, areas=[area])
        for timestamp_ms, area in [(8_000, 0.10), (9_000, 0.20), (10_000, 0.30)]
    ]

    assert (
        classify_vehicle_approach(events, reference_timestamp_ms=10_000)
        is VehicleApproachState.INSUFFICIENT_DATA
    )


def test_classify_vehicle_approach_ignores_future_events() -> None:
    """Prüft, dass Daten nach dem ToF-Ereignis nicht verwendet werden."""
    events = [
        make_vision_payload(timestamp_ms=9_500, areas=[0.10]),
        make_vision_payload(timestamp_ms=10_001, areas=[0.30]),
    ]

    assert (
        classify_vehicle_approach(events, reference_timestamp_ms=10_000)
        is VehicleApproachState.INSUFFICIENT_DATA
    )
