"""Tests für die zentrale Protokollierung."""

import time
from collections.abc import Callable
from typing import cast

import pytest

from core import main_logger
from shared import TOPIC_PAYLOAD_TYPES, MQTTWrapper, PayloadInstance, RadarPayload

RADAR_TOPIC = "sensors/radar"


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


def test_subscribe_sensors_creates_history_for_each_known_topic() -> None:
    """Prüft, dass alle bekannten Topics einen eigenen Verlauf bekommen."""
    mqtt_wrapper = FakeMqttWrapper()

    histories = main_logger.subscribe_sensors(
        max_items=2,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
    )

    assert set(histories) == set(TOPIC_PAYLOAD_TYPES)
    assert set(mqtt_wrapper.subscriptions) == set(TOPIC_PAYLOAD_TYPES)
    assert all(isinstance(history, main_logger.SensorHistory) for history in histories.values())


def test_subscribe_sensors_passes_max_items_to_histories() -> None:
    """Prüft, dass alle Verläufe die gewünschte Puffergröße verwenden."""
    mqtt_wrapper = FakeMqttWrapper()
    histories = main_logger.subscribe_sensors(
        max_items=1,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
    )
    radar_history = histories[RADAR_TOPIC]
    first_payload = make_radar_payload(timestamp_ms=1_000)
    second_payload = make_radar_payload(timestamp_ms=2_000)

    radar_history._append_event(first_payload)
    radar_history._append_event(second_payload)

    assert list(radar_history._history) == [second_payload]
