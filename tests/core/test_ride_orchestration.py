"""Tests für die äußerste Orchestrierung einer Fahrt."""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import cast

import pytest

from core import main_logger
from shared import (
    TOPIC_PAYLOAD_TYPES,
    GpsPayload,
    MQTTWrapper,
    PayloadInstance,
    TofPayload,
    VisionPayload,
)


class FakeMqttWrapper:
    """Brokerfreier MQTT-Wrapper für Orchestrierungstests."""

    def __init__(self) -> None:
        """Erstellt leere Abonnements und Zustandssignale."""
        self.subscriptions: dict[str, Callable[[PayloadInstance], None]] = {}
        self.all_topics_subscribed = Event()
        self.closed = False

    def subscribe(self, topic: str, action: Callable[[PayloadInstance], None]) -> None:
        """Speichert einen Topic-Callback.

        :param topic: Abonniertes MQTT-Topic.
        :param action: Callback für deserialisierte Payloads.
        """
        self.subscriptions[topic] = action
        if set(self.subscriptions) == set(TOPIC_PAYLOAD_TYPES):
            self.all_topics_subscribed.set()

    def emit(self, topic: str, payload: PayloadInstance) -> None:
        """Sendet ein Payload an den registrierten Callback.

        :param topic: MQTT-Topic des Payloads.
        :param payload: Simuliertes Payload.
        """
        self.subscriptions[topic](payload)

    def close(self) -> None:
        """Markiert den Wrapper als geschlossen."""
        self.closed = True


def make_gps_payload(timestamp_ms: int) -> GpsPayload:
    """Erstellt eine gültige GPS-Messung.

    :param timestamp_ms: Unix-Zeitstempel in Millisekunden.
    """
    return GpsPayload(
        timestamp_ms=timestamp_ms,
        latitude=51.31275,
        longitude=9.49245,
        speed_kmh=22.1,
        satellites_connected=12,
    )


def make_vision_payload(timestamp_ms: int) -> VisionPayload:
    """Erstellt eine positive Fahrzeugerkennung.

    :param timestamp_ms: Unix-Zeitstempel in Millisekunden.
    """
    return VisionPayload(
        timestamp_ms=timestamp_ms,
        found_vehicle=True,
        detected_types=["Car"],
        vehicle_count=1,
        inference_time_ms=12.5,
    )


def make_tof_payload(timestamp_ms: int) -> TofPayload:
    """Erstellt einen gültigen ToF-Alarm.

    :param timestamp_ms: Unix-Zeitstempel in Millisekunden.
    """
    return TofPayload(timestamp_ms=timestamp_ms, distance_cm=85.5, is_valid=True)


def test_orchestrator_processes_alert_after_gps_window() -> None:
    """Prüft die verzögerte und einmalige Verarbeitung eines ToF-Alarms."""
    mqtt_wrapper = FakeMqttWrapper()
    orchestrator = main_logger.RideOrchestrator(
        start_timestamp_ms=8_000,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        max_history_items=20,
    )
    mqtt_wrapper.emit("vision/vehicles", make_vision_payload(timestamp_ms=9_000))
    mqtt_wrapper.emit("sensors/tof", make_tof_payload(timestamp_ms=10_000))
    mqtt_wrapper.emit("sensors/gps", make_gps_payload(timestamp_ms=10_500))

    assert orchestrator.process_pending(current_timestamp_ms=12_999) == 0
    assert orchestrator.process_pending(current_timestamp_ms=13_000) == 1
    assert orchestrator.process_pending(current_timestamp_ms=14_000) == 0

    ride_data = orchestrator.finish(end_timestamp_ms=14_000)

    assert len(ride_data.route_logs) == 1
    assert len(ride_data.violations) == 1
    assert ride_data.violations[0].timestamp == 10


def test_orchestrator_finish_flushes_immature_alert() -> None:
    """Prüft den finalen Flush eines noch nicht gereiften ToF-Alarms."""
    mqtt_wrapper = FakeMqttWrapper()
    orchestrator = main_logger.RideOrchestrator(
        start_timestamp_ms=8_000,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        max_history_items=20,
    )
    mqtt_wrapper.emit("vision/vehicles", make_vision_payload(timestamp_ms=9_000))
    mqtt_wrapper.emit("sensors/tof", make_tof_payload(timestamp_ms=10_000))
    mqtt_wrapper.emit("sensors/gps", make_gps_payload(timestamp_ms=10_500))

    ride_data = orchestrator.finish(end_timestamp_ms=11_000)

    assert len(ride_data.violations) == 1
    with pytest.raises(ValueError, match="bereits beendet"):
        orchestrator.process_pending(current_timestamp_ms=14_000)


def test_orchestrator_tof_queue_does_not_block_at_history_limit() -> None:
    """Prüft mehrere ToF-Alarme bei einer History-Größe von eins."""
    mqtt_wrapper = FakeMqttWrapper()
    orchestrator = main_logger.RideOrchestrator(
        start_timestamp_ms=8_000,
        mqtt_wrapper=cast(MQTTWrapper, mqtt_wrapper),
        max_history_items=1,
    )
    mqtt_wrapper.emit("vision/vehicles", make_vision_payload(timestamp_ms=9_000))
    mqtt_wrapper.emit("sensors/gps", make_gps_payload(timestamp_ms=10_000))

    mqtt_wrapper.emit("sensors/tof", make_tof_payload(timestamp_ms=10_000))
    mqtt_wrapper.emit("sensors/tof", make_tof_payload(timestamp_ms=10_100))
    ride_data = orchestrator.finish(end_timestamp_ms=11_000)

    assert len(ride_data.violations) == 2


def test_run_ride_writes_complete_json_and_closes_mqtt(tmp_path: Path) -> None:
    """Prüft den vollständigen Ablauf der äußersten Fahrtfunktion.

    :param tmp_path: Temporäres Ausgabeverzeichnis.
    """
    mqtt_wrapper = FakeMqttWrapper()
    stop_event = Event()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            main_logger.run_ride,
            cast(MQTTWrapper, mqtt_wrapper),
            tmp_path,
            stop_event,
            clock_ms=lambda: 10_000,
        )
        assert mqtt_wrapper.all_topics_subscribed.wait(timeout=5)
        mqtt_wrapper.emit("vision/vehicles", make_vision_payload(timestamp_ms=9_000))
        mqtt_wrapper.emit("sensors/tof", make_tof_payload(timestamp_ms=10_000))
        mqtt_wrapper.emit("sensors/gps", make_gps_payload(timestamp_ms=10_500))
        stop_event.set()
        output_path = future.result(timeout=5)

    written_data = json.loads(output_path.read_text(encoding="utf-8"))
    assert mqtt_wrapper.closed is True
    assert written_data["start_time"] == 10
    assert written_data["end_time"] == 10
    assert len(written_data["route_logs"]) == 1
    assert len(written_data["violations"]) == 1


def test_run_ride_closes_mqtt_without_writing_after_error(tmp_path: Path) -> None:
    """Prüft den Abbruch ohne Fahrtdatei nach einem Laufzeitfehler.

    :param tmp_path: Temporäres Ausgabeverzeichnis.
    """
    mqtt_wrapper = FakeMqttWrapper()
    clock_calls = 0

    def failing_clock() -> int:
        """Liefert einmal die Startzeit und schlägt danach fehl."""
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 1:
            return 10_000
        raise RuntimeError("simulierter Uhrfehler")

    with pytest.raises(RuntimeError, match="simulierter Uhrfehler"):
        main_logger.run_ride(
            cast(MQTTWrapper, mqtt_wrapper),
            tmp_path,
            Event(),
            poll_interval_s=0.0,
            clock_ms=failing_clock,
        )

    assert mqtt_wrapper.closed is True
    assert list(tmp_path.iterdir()) == []
