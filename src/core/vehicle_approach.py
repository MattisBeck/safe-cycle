"""Bewertung der Größenentwicklung erkannter Fahrzeuge."""

from collections.abc import Sequence
from enum import Enum
from statistics import median

from shared.data_models import VisionPayload

APPROACH_LOOKBACK_PERIOD_MS = 2_000
APPROACH_MIN_GROWTH_RATIO = 0.25
APPROACH_MIN_OBSERVATIONS = 3
APPROACH_MIN_SPAN_MS = 500
APPROACH_MAX_GAP_MS = 750


class VehicleApproachState(Enum):
    """Zustand eines Fahrzeugs im betrachteten Zeitfenster."""

    NO_VEHICLE = "no_vehicle"
    PRESENT = "present"
    INSUFFICIENT_DATA = "insufficient_data"
    APPROACHING = "approaching"


def classify_vehicle_approach(
    vision_events: Sequence[VisionPayload],
    *,
    reference_timestamp_ms: int,
) -> VehicleApproachState:
    """Bewertet eine robuste Zunahme der größten Boxfläche.

    :param vision_events: Vision-Payloads aus dem Sensorverlauf.
    :param reference_timestamp_ms: Zeitpunkt des ToF-Ereignisses.
    :return: Ermittelter Annäherungszustand.
    """
    first_timestamp_ms = reference_timestamp_ms - APPROACH_LOOKBACK_PERIOD_MS
    observations: list[tuple[int, float]] = []

    for event in vision_events:
        # Nur Vision-Daten vor dem ToF-Zeitpunkt gehören zur Annäherung vor dem Ereignis.
        event_is_in_window = first_timestamp_ms <= event.timestamp_ms <= reference_timestamp_ms
        if not event_is_in_window:
            continue

        # Wir verwenden pro Frame die größte Fahrzeugbox als Kandidat.
        box_areas = [detection.area for detection in event.detections]
        largest_box_area = max(box_areas, default=0.0)
        if largest_box_area <= 0.0:
            continue

        observations.append((event.timestamp_ms, largest_box_area))

    observations.sort(key=lambda observation: observation[0])

    if not observations:
        return VehicleApproachState.NO_VEHICLE

    observation_count = len(observations)
    if observation_count < APPROACH_MIN_OBSERVATIONS:
        return VehicleApproachState.INSUFFICIENT_DATA

    # Zu wenige oder zu weit auseinanderliegende Messungen wären zu unsicher für
    # einen Größenvergleich. Einzelne fehlende Frames sind dagegen erlaubt.
    observation_timestamps = [timestamp_ms for timestamp_ms, _area in observations]
    observation_span_ms = observation_timestamps[-1] - observation_timestamps[0]
    if observation_span_ms < APPROACH_MIN_SPAN_MS:
        return VehicleApproachState.INSUFFICIENT_DATA

    has_large_gap = any(
        later_timestamp_ms - earlier_timestamp_ms > APPROACH_MAX_GAP_MS
        for earlier_timestamp_ms, later_timestamp_ms in zip(
            observation_timestamps,
            observation_timestamps[1:],
            strict=False,
        )
    )
    if has_large_gap:
        return VehicleApproachState.INSUFFICIENT_DATA

    # Der Median des ersten und letzten Drittels unterdrückt einzelne fehlerhafte
    # YOLO-Boxen. Deshalb muss nicht jede Box gegenüber dem vorherigen Frame wachsen.
    box_areas = [area for _timestamp_ms, area in observations]
    section_size = max(1, observation_count // 3)
    early_box_areas = box_areas[:section_size]
    late_box_areas = box_areas[-section_size:]
    early_median_area = median(early_box_areas)
    late_median_area = median(late_box_areas)
    required_late_area = early_median_area * (1.0 + APPROACH_MIN_GROWTH_RATIO)

    if late_median_area >= required_late_area:
        return VehicleApproachState.APPROACHING

    return VehicleApproachState.PRESENT
