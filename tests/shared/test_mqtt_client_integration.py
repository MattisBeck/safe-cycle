"""Integrationstests für den MQTT-Wrapper mit echtem Broker."""

import os
import threading
import time
from typing import cast

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from shared.data_models import RadarPayload
from shared.mqtt_client import MQTTWrapper

RADAR_TOPIC = "sensors/radar"
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883

pytestmark = pytest.mark.skipif(
    os.environ.get("SAFE_CYCLE_MQTT_INTEGRATION") != "1",
    reason="MQTT-Integrationstest benötigt einen laufenden Broker.",
)


def test_wrapper_publishes_and_receives_radar_payload() -> None:
    """Prüft den Dataclass-Roundtrip über einen echten MQTT-Broker."""
    subscription_ready = threading.Event()
    payload_received = threading.Event()
    received_payloads: list[RadarPayload] = []
    wrappers: list[MQTTWrapper] = []

    expected_payload = RadarPayload(
        timestamp_ms=time.time_ns() // 1_000_000,
        distance_cm=420.0,
        rel_speed_kmh=18.5,
        is_valid=True,
    )

    def mark_subscription_ready(
        _client: mqtt.Client,
        _userdata: object,
        _mid: int,
        _reason_code_list: list[ReasonCode],
        _properties: Properties | None,
    ) -> None:
        """Merkt sich, dass der Broker das Abo bestätigt hat."""
        subscription_ready.set()

    def collect_payload(payload: RadarPayload) -> None:
        """Merkt sich die erwartete Nutzlast aus dem MQTT-Callback."""
        if payload == expected_payload:
            received_payloads.append(payload)
            payload_received.set()

    try:
        subscriber = MQTTWrapper(BROKER_HOST, BROKER_PORT)
        wrappers.append(subscriber)
        publisher = MQTTWrapper(BROKER_HOST, BROKER_PORT)
        wrappers.append(publisher)

        subscriber.mqttc.on_subscribe = cast(mqtt.CallbackOnSubscribe, mark_subscription_ready)
        subscriber.subscribe(RADAR_TOPIC, collect_payload)

        assert subscription_ready.wait(timeout=5.0)

        publisher.publish(RADAR_TOPIC, expected_payload)

        assert payload_received.wait(timeout=5.0)
        assert received_payloads == [expected_payload]
    finally:
        for wrapper in wrappers:
            wrapper.close()
