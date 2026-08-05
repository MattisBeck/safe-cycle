"""Tests für die zentrale Protokollierung."""

import time
from collections.abc import Callable
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from core import main_logger
from shared import (
    TOPIC_PAYLOAD_TYPES,
    Coordinates,
    GpsPayload,
    MQTTWrapper,
    PayloadInstance,
    RadarPayload,
    RideData,
    RoutePoint,
    TofPayload,
    VehicleDetection,
    Violation,
    VisionPayload,
)

RADAR_TOPIC = "sensors/radar"
VISION_TOPIC = "vision/vehicles"
GPS_TOPIC = "sensors/gps"


class FakeMqttWrapper:
    """Brokerfreier Ersatz für den MQTT-Wrapper."""

    def __init__(self) -> None:
        """Erstellt einen leeren Abonnement-Speicher."""
        self.subscriptions: dict[str, Callable[[PayloadInstance], None]] = {}

    def subscribe(self, topic: str, action: Callable[[PayloadInstance], None]) -> None:
        """Speichert Callback-Funktionen nach Topic.

        :param topic: MQTT-Topic des Abonnements.
        :param action: Callback für empfangene Payloads.
        """
        self.subscriptions[topic] = action

    def emit(self, topic: str, payload: PayloadInstance) -> None:
        """Löst das gespeicherte Callback für ein Topic aus.

        :param topic: MQTT-Topic der simulierten Nachricht.
        :param payload: Simulierte Payload.
        """
        self.subscriptions[topic](payload)


def make_radar_payload(timestamp_ms: int) -> RadarPayload:
    """Erstellt eine Radar-Payload mit festem Zeitstempel.

    :param timestamp_ms: Unix-Zeitstempel der simulierten Messung.
    """
    return RadarPayload(
        timestamp_ms=timestamp_ms,
        distance_cm=420.0,
        rel_speed_kmh=18.5,
        is_valid=True,
        angle=0,
        snr=0,
    )


def make_vision_payload(
    timestamp_ms: int,
    *,
    found_vehicle: bool,
    area: float = 0.1,
) -> VisionPayload:
    """Erstellt eine Vision-Payload für die Überholprüfung.

    :param timestamp_ms: Unix-Zeitstempel der simulierten Erkennung.
    :param found_vehicle: Gibt an, ob ein Fahrzeug erkannt wurde.
    :param area: Simulierte normalisierte Boxfläche.
    """
    return VisionPayload(
        timestamp_ms=timestamp_ms,
        found_vehicle=found_vehicle,
        detected_types=["Car"] if found_vehicle else [],
        vehicle_count=1 if found_vehicle else 0,
        inference_time_ms=12.5,
        detections=[
            VehicleDetection(
                class_name="Car",
                confidence=0.9,
                x_min=0.0,
                y_min=0.0,
                x_max=area,
                y_max=1.0,
            )
        ]
        if found_vehicle
        else [],
    )


def append_approaching_vision(history: main_logger.SensorHistory) -> None:
    """Fügt einen wachsenden Boxverlauf für einen Test hinzu."""
    for timestamp_ms, area in [
        (8_000, 0.10),
        (8_500, 0.12),
        (9_000, 0.16),
        (9_500, 0.22),
        (10_000, 0.30),
    ]:
        history._append_event(
            make_vision_payload(timestamp_ms=timestamp_ms, found_vehicle=True, area=area)
        )


def make_tof_payload(
    timestamp_ms: int,
    *,
    distance_cm: float = 100.0,
    is_valid: bool = True,
) -> TofPayload:
    """Erstellt eine ToF-Payload für die Überholprüfung.

    :param timestamp_ms: Unix-Zeitstempel der simulierten Messung.
    :param distance_cm: Gemessener seitlicher Abstand.
    :param is_valid: Gibt an, ob die Messung gültig ist.
    """
    return TofPayload(timestamp_ms=timestamp_ms, distance_cm=distance_cm, is_valid=is_valid)


def make_vision_history() -> main_logger.SensorHistory:
    """Erstellt eine brokerfreie Vision-History."""
    mqtt_wrapper = FakeMqttWrapper()
    return main_logger.SensorHistory(
        max_items=10,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=VISION_TOPIC,
    )


def make_gps_payload(
    timestamp_ms: int,
    *,
    satellites_connected: int = 12,
) -> GpsPayload:
    """Erstellt eine GPS-Payload für die Ereigniszuordnung.

    :param timestamp_ms: Unix-Zeitstempel der simulierten Messung.
    :param satellites_connected: Anzahl der simulierten Satellitenverbindungen.
    """
    return GpsPayload(
        timestamp_ms=timestamp_ms,
        latitude=51.31275,
        longitude=9.49245,
        speed_kmh=22.1,
        satellites_connected=satellites_connected,
    )


def make_gps_history() -> main_logger.SensorHistory:
    """Erstellt eine brokerfreie GPS-History."""
    mqtt_wrapper = FakeMqttWrapper()
    return main_logger.SensorHistory(
        max_items=10,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=GPS_TOPIC,
    )


def test_main_logger_can_be_imported() -> None:
    """Prüft, ob die Hauptlogik ohne Hardwareabhängigkeiten importierbar ist."""
    assert main_logger.__name__ == "core.main_logger"


def test_sensor_history_subscribes_topic_and_stores_wrapper() -> None:
    """Prüft Topic-Abonnement und gespeicherten MQTT-Wrapper."""
    mqtt_wrapper = FakeMqttWrapper()

    history = main_logger.SensorHistory(
        max_items=3,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )

    assert history.mqtt_wrapper is cast(MQTTWrapper, mqtt_wrapper)
    assert list(mqtt_wrapper.subscriptions) == [RADAR_TOPIC]
    assert mqtt_wrapper.subscriptions[RADAR_TOPIC] == history._append_event


def test_sensor_history_appends_payload_from_callback() -> None:
    """Prüft, dass empfangene Payloads im Verlauf landen."""
    mqtt_wrapper = FakeMqttWrapper()
    history = main_logger.SensorHistory(
        max_items=3,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )
    payload = make_radar_payload(timestamp_ms=1_000)

    mqtt_wrapper.emit(RADAR_TOPIC, payload)

    assert list(history._history) == [payload]


def test_sensor_history_discards_oldest_payload_when_full() -> None:
    """Prüft, dass der Ringpuffer bei Überlauf das älteste Element entfernt."""
    mqtt_wrapper = FakeMqttWrapper()
    history = main_logger.SensorHistory(
        max_items=2,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )
    first_payload = make_radar_payload(timestamp_ms=1_000)
    second_payload = make_radar_payload(timestamp_ms=2_000)
    third_payload = make_radar_payload(timestamp_ms=3_000)

    history._append_event(first_payload)
    history._append_event(second_payload)
    history._append_event(third_payload)

    assert list(history._history) == [second_payload, third_payload]


def test_get_events_returns_empty_list_for_empty_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft ein leeres Zeitfenster ohne gespeicherte Payloads.

    :param monkeypatch: Pytest-Helfer zum Fixieren der aktuellen Zeit.
    """
    monkeypatch.setattr(time, "time", lambda: 10.0)
    mqtt_wrapper = FakeMqttWrapper()
    history = main_logger.SensorHistory(
        max_items=3,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )

    assert history.get_events(lookback_period_ms=1_000) == []


def test_get_events_returns_recent_payloads_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Zeitfilterung und Sortierung von neu nach alt.

    :param monkeypatch: Pytest-Helfer zum Fixieren der aktuellen Zeit.
    """
    monkeypatch.setattr(time, "time", lambda: 10.0)
    mqtt_wrapper = FakeMqttWrapper()
    history = main_logger.SensorHistory(
        max_items=5,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )
    old_payload = make_radar_payload(timestamp_ms=7_999)
    boundary_payload = make_radar_payload(timestamp_ms=9_000)
    recent_payload = make_radar_payload(timestamp_ms=9_900)

    history._append_event(old_payload)
    history._append_event(boundary_payload)
    history._append_event(recent_payload)

    assert history.get_events(lookback_period_ms=1_000) == [recent_payload, boundary_payload]


def test_get_events_stops_when_newest_payload_is_too_old(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft den schnellen Abbruch, wenn kein Event im Zeitfenster liegt.

    :param monkeypatch: Pytest-Helfer zum Fixieren der aktuellen Zeit.
    """
    monkeypatch.setattr(time, "time", lambda: 10.0)
    mqtt_wrapper = FakeMqttWrapper()
    history = main_logger.SensorHistory(
        max_items=3,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        topic=RADAR_TOPIC,
    )

    history._append_event(make_radar_payload(timestamp_ms=8_999))

    assert history.get_events(lookback_period_ms=1_000) == []


def test_get_events_uses_reference_timestamp_and_ignores_later_events() -> None:
    """Prüft ein Zeitfenster relativ zu einem historischen Ereignis."""
    history = make_vision_history()
    boundary_payload = make_vision_payload(timestamp_ms=7_000, found_vehicle=True)
    recent_payload = make_vision_payload(timestamp_ms=9_500, found_vehicle=False)
    later_payload = make_vision_payload(timestamp_ms=10_001, found_vehicle=True)
    history._append_event(boundary_payload)
    history._append_event(recent_payload)
    history._append_event(later_payload)

    events = history.get_events(3_000, reference_timestamp_ms=10_000)

    assert events == [recent_payload, boundary_payload]


def test_check_unsafe_overtake_returns_true_for_recent_vehicle() -> None:
    """Prüft eine Abstandsunterschreitung mit erkannter Annäherung."""
    history = make_vision_history()
    append_approaching_vision(history)

    result = main_logger.check_unsafe_overtake(make_tof_payload(timestamp_ms=10_000), history)

    assert result is True


@pytest.mark.parametrize(
    ("vision_timestamp_ms", "found_vehicle"),
    [(6_999, True), (9_000, False), (10_001, True)],
)
def test_check_unsafe_overtake_rejects_unmatched_vision_events(
    vision_timestamp_ms: int,
    found_vehicle: bool,
) -> None:
    """Prüft zu alte, negative und spätere Fahrzeugerkennungen.

    :param vision_timestamp_ms: Zeitstempel der Vision-Payload.
    :param found_vehicle: Simuliertes Erkennungsergebnis.
    """
    history = make_vision_history()
    history._append_event(
        make_vision_payload(timestamp_ms=vision_timestamp_ms, found_vehicle=found_vehicle)
    )

    result = main_logger.check_unsafe_overtake(make_tof_payload(timestamp_ms=10_000), history)

    assert result is False


def test_check_unsafe_overtake_includes_lookback_boundary() -> None:
    """Prüft eine Box exakt auf der Zeitfenstergrenze."""
    history = make_vision_history()
    append_approaching_vision(history)

    result = main_logger.check_unsafe_overtake(make_tof_payload(timestamp_ms=10_000), history)

    assert result is True


@pytest.mark.parametrize(
    ("distance_cm", "is_valid"),
    [(150.0, True), (151.0, True), (100.0, False)],
)
def test_check_unsafe_overtake_rejects_noncritical_tof_payloads(
    distance_cm: float,
    is_valid: bool,
) -> None:
    """Prüft sichere Abstände und ungültige ToF-Messungen.

    :param distance_cm: Simulierter seitlicher Abstand.
    :param is_valid: Simulierter Gültigkeitszustand.
    """
    history = make_vision_history()
    history._append_event(make_vision_payload(timestamp_ms=9_000, found_vehicle=True))
    tof_payload = make_tof_payload(
        timestamp_ms=10_000,
        distance_cm=distance_cm,
        is_valid=is_valid,
    )

    assert main_logger.check_unsafe_overtake(tof_payload, history) is False


def test_gather_violation_data_collects_tof_and_gps_values() -> None:
    """Prüft die Zusammenführung eines bestätigten Verstoßes."""
    tof_payload = make_tof_payload(timestamp_ms=1_717_618_015_999, distance_cm=85.5)
    gps_payload = GpsPayload(
        timestamp_ms=1_717_618_015_500,
        latitude=51.31275,
        longitude=9.49245,
        speed_kmh=22.1,
        satellites_connected=12,
    )

    violation = main_logger.gather_violation_data(tof_payload, gps_payload)

    assert violation == Violation(
        timestamp=1_717_618_015,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
        image_path=None,
    )


def test_get_nearest_event_selects_smallest_absolute_difference() -> None:
    """Prüft die GPS-Auswahl vor und nach dem Ereigniszeitpunkt."""
    history = make_gps_history()
    earlier_payload = make_gps_payload(timestamp_ms=8_000)
    later_payload = make_gps_payload(timestamp_ms=10_500)
    history._append_event(earlier_payload)
    history._append_event(later_payload)

    result = main_logger.get_nearest_event(history, timestamp_ms=10_000)

    assert result == later_payload


def test_get_nearest_event_prefers_earlier_payload_on_tie() -> None:
    """Prüft den früheren GPS-Wert als Tie-Breaker."""
    history = make_gps_history()
    earlier_payload = make_gps_payload(timestamp_ms=9_000)
    history._append_event(earlier_payload)
    history._append_event(make_gps_payload(timestamp_ms=11_000))

    assert main_logger.get_nearest_event(history, timestamp_ms=10_000) == earlier_payload


@pytest.mark.parametrize("offset_ms", [-3_000, 3_000])
def test_get_nearest_event_includes_window_boundaries(offset_ms: int) -> None:
    """Prüft beide Grenzen des symmetrischen GPS-Fensters.

    :param offset_ms: Abstand zum Mittelpunkt des Suchfensters.
    """
    history = make_gps_history()
    boundary_payload = make_gps_payload(timestamp_ms=10_000 + offset_ms)
    history._append_event(boundary_payload)

    assert main_logger.get_nearest_event(history, timestamp_ms=10_000) == boundary_payload


def test_get_nearest_event_skips_invalid_gps_payload() -> None:
    """Prüft, dass ein GPS-Paket ohne Satelliten nicht ausgewählt wird."""
    history = make_gps_history()
    valid_payload = make_gps_payload(timestamp_ms=9_000)
    history._append_event(valid_payload)
    history._append_event(make_gps_payload(timestamp_ms=9_900, satellites_connected=0))

    assert main_logger.get_nearest_event(history, timestamp_ms=10_000) == valid_payload


def test_get_nearest_event_returns_none_without_valid_candidate() -> None:
    """Prüft zu alte, typfremde und ungültige Ereignisse."""
    history = make_gps_history()
    history._append_event(make_gps_payload(timestamp_ms=6_999))
    history._append_event(make_gps_payload(timestamp_ms=10_000, satellites_connected=0))
    history._append_event(make_radar_payload(timestamp_ms=10_000))

    assert main_logger.get_nearest_event(history, timestamp_ms=10_000) is None


def test_process_tof_alert_returns_complete_violation() -> None:
    """Prüft die Orchestrierung eines bestätigten ToF-Alarms."""
    vision_history = make_vision_history()
    gps_history = make_gps_history()
    tof_payload = make_tof_payload(timestamp_ms=10_000, distance_cm=85.5)
    append_approaching_vision(vision_history)
    gps_history._append_event(make_gps_payload(timestamp_ms=10_500))

    result = main_logger.process_tof_alert(tof_payload, vision_history, gps_history)

    assert result == Violation(
        timestamp=10,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
        image_path=None,
    )


def test_process_tof_alert_returns_none_without_vision_confirmation() -> None:
    """Prüft einen Alarm ohne bestätigte Fahrzeugerkennung."""
    vision_history = make_vision_history()
    gps_history = make_gps_history()
    gps_history._append_event(make_gps_payload(timestamp_ms=10_000))

    result = main_logger.process_tof_alert(
        make_tof_payload(timestamp_ms=10_000),
        vision_history,
        gps_history,
    )

    assert result is None


def test_process_tof_alert_returns_none_without_gps_payload() -> None:
    """Prüft einen bestätigten Alarm ohne passenden GPS-Wert."""
    vision_history = make_vision_history()
    gps_history = make_gps_history()
    vision_history._append_event(make_vision_payload(timestamp_ms=9_000, found_vehicle=True))

    result = main_logger.process_tof_alert(
        make_tof_payload(timestamp_ms=10_000),
        vision_history,
        gps_history,
    )

    assert result is None


def test_ride_session_collects_route_and_violation() -> None:
    """Prüft den vollständigen In-Memory-Fahrtzustand."""
    start_datetime = datetime(2026, 6, 5, 14, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    start_timestamp_ms = int(start_datetime.timestamp() * 1_000)
    session = main_logger.RideSession.start(start_timestamp_ms)
    first_gps = make_gps_payload(timestamp_ms=start_timestamp_ms + 1_500)
    second_gps = GpsPayload(
        timestamp_ms=start_timestamp_ms + 2_999,
        latitude=51.3128,
        longitude=9.4925,
        speed_kmh=23.0,
        satellites_connected=10,
    )
    violation = Violation(
        timestamp=start_timestamp_ms // 1_000 + 2,
        coordinates=Coordinates(lat=51.31275, lon=9.49245),
        distance_cm=85.5,
        speed_kmh=22.1,
    )

    assert session.add_gps_payload(first_gps) is True
    assert session.add_gps_payload(second_gps) is True
    session.add_violation(violation)
    ride_data = session.finish(start_timestamp_ms + 5_999)

    assert ride_data == RideData(
        ride_id="tour_2026_06_05_1430",
        start_time=start_timestamp_ms // 1_000,
        end_time=start_timestamp_ms // 1_000 + 5,
        route_logs=[
            RoutePoint(
                timestamp=start_timestamp_ms // 1_000 + 1,
                lat=51.31275,
                lon=9.49245,
            ),
            RoutePoint(
                timestamp=start_timestamp_ms // 1_000 + 2,
                lat=51.3128,
                lon=9.4925,
            ),
        ],
        violations=[violation],
    )


def test_ride_session_ignores_gps_without_satellites() -> None:
    """Prüft, dass eine ungültige GPS-Messung nicht zur Route gehört."""
    session = main_logger.RideSession.start(start_timestamp_ms=10_000)

    was_added = session.add_gps_payload(
        make_gps_payload(timestamp_ms=11_000, satellites_connected=0)
    )
    ride_data = session.finish(end_timestamp_ms=12_000)

    assert was_added is False
    assert ride_data.route_logs == []


def test_ride_session_rejects_end_before_start() -> None:
    """Prüft eine Endzeit vor dem Fahrtbeginn."""
    session = main_logger.RideSession.start(start_timestamp_ms=10_000)

    with pytest.raises(ValueError, match="Endzeit"):
        session.finish(end_timestamp_ms=9_999)


def test_ride_session_rejects_changes_after_finish() -> None:
    """Prüft, dass eine abgeschlossene Fahrt unveränderlich bleibt."""
    session = main_logger.RideSession.start(start_timestamp_ms=10_000)
    session.finish(end_timestamp_ms=12_000)

    with pytest.raises(ValueError, match="bereits beendet"):
        session.finish(end_timestamp_ms=13_000)
    with pytest.raises(ValueError, match="bereits beendet"):
        session.add_gps_payload(make_gps_payload(timestamp_ms=13_000))
    with pytest.raises(ValueError, match="bereits beendet"):
        session.add_violation(
            Violation(
                timestamp=13,
                coordinates=Coordinates(lat=51.31275, lon=9.49245),
                distance_cm=85.5,
                speed_kmh=22.1,
            )
        )


def test_subscribe_sensors_creates_history_for_each_known_topic() -> None:
    """Prüft, dass alle bekannten Topics einen eigenen Verlauf bekommen."""
    mqtt_wrapper = FakeMqttWrapper()

    histories = main_logger.subscribe_topics(
        max_items=2,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
    )

    assert set(histories) == set(TOPIC_PAYLOAD_TYPES)
    assert set(mqtt_wrapper.subscriptions) == set(TOPIC_PAYLOAD_TYPES)
    assert all(isinstance(history, main_logger.SensorHistory) for history in histories.values())


def test_subscribe_sensors_passes_max_items_to_histories() -> None:
    """Prüft, dass alle Verläufe die gewünschte Puffergröße verwenden."""
    mqtt_wrapper = FakeMqttWrapper()
    histories = main_logger.subscribe_topics(
        max_items=1,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
    )
    radar_history = histories[RADAR_TOPIC]
    first_payload = make_radar_payload(timestamp_ms=1_000)
    second_payload = make_radar_payload(timestamp_ms=2_000)

    radar_history._append_event(first_payload)
    radar_history._append_event(second_payload)

    assert list(radar_history._history) == [second_payload]
