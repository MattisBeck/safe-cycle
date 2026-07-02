"""Tests für den gemeinsamen MQTT-Wrapper."""

import json
from dataclasses import asdict
from typing import Callable, ClassVar, TypeAlias, cast

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from shared.data_models import GpsPayload, RadarPayload
from shared.mqtt_client import MQTTWrapper

RADAR_TOPIC = "sensors/radar"
GPS_TOPIC = "sensors/gps"
MessagePayload: TypeAlias = GpsPayload | RadarPayload


class FakeMqttClient:
    """Brokerfreier Ersatz für den Paho-MQTT-Client."""

    last_instance: ClassVar["FakeMqttClient | None"] = None

    def __init__(self, callback_api_version: CallbackAPIVersion) -> None:
        """Speichert die Client-Konfiguration für spätere Assertions.

        :param callback_api_version: Von `MQTTWrapper` gewählte Paho-Callback-API.
        """
        self.callback_api_version = callback_api_version
        self.connected_to: tuple[str, int] | None = None
        self.loop_started = False
        self.published_messages: list[tuple[str, str]] = []
        self.subscribed_topics: list[str] = []
        self.on_message: Callable[[mqtt.Client, object, mqtt.MQTTMessage], None] | None = None
        FakeMqttClient.last_instance = self

    def connect(self, broker_ip: str, broker_port: int) -> None:
        """Merkt sich die simulierte Broker-Verbindung.

        :param broker_ip: IP-Adresse oder Hostname des Brokers.
        :param broker_port: Port des Brokers.
        """
        self.connected_to = (broker_ip, broker_port)

    def loop_start(self) -> None:
        """Merkt sich, dass die MQTT-Netzwerkschleife gestartet wurde."""
        self.loop_started = True

    def publish(self, topic: str, payload: str) -> None:
        """Merkt sich veröffentlichte Nachrichten.

        :param topic: MQTT-Topic der Nachricht.
        :param payload: JSON-Nutzdaten der Nachricht.
        """
        self.published_messages.append((topic, payload))

    def subscribe(self, topic: str) -> None:
        """Merkt sich abonnierte Topics.

        :param topic: MQTT-Topic, das der Wrapper abonnieren möchte.
        """
        self.subscribed_topics.append(topic)


def create_wrapper_with_fake_client(monkeypatch: pytest.MonkeyPatch) -> tuple[MQTTWrapper, FakeMqttClient]:
    """Erstellt einen MQTT-Wrapper mit Fake-Client statt echter Broker-Verbindung.

    :param monkeypatch: Pytest-Helfer zum Ersetzen des Paho-Clients.
    """
    FakeMqttClient.last_instance = None
    monkeypatch.setattr(mqtt, "Client", FakeMqttClient)

    wrapper = MQTTWrapper("127.0.0.1", 1883)
    client = FakeMqttClient.last_instance

    assert client is not None
    return wrapper, client


def make_message(topic: str, payload: MessagePayload) -> mqtt.MQTTMessage:
    """Erstellt eine echte Paho-Nachricht mit JSON-Payload.

    :param topic: MQTT-Topic der eingehenden Nachricht.
    :param payload: Dataclass-Payload, die als JSON codiert wird.
    """
    message = mqtt.MQTTMessage(topic=topic.encode("utf-8"))
    message.payload = json.dumps(asdict(payload)).encode("utf-8")
    return message


def test_wrapper_connects_client_and_starts_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Verbindungsaufbau und Start der MQTT-Netzwerkschleife."""
    wrapper, client = create_wrapper_with_fake_client(monkeypatch)

    assert client.callback_api_version is CallbackAPIVersion.VERSION2
    assert client.connected_to == ("127.0.0.1", 1883)
    assert client.loop_started is True
    assert client.on_message == wrapper._on_message


def test_publish_serializes_payload_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass `publish()` Dataclasses als JSON an Paho weitergibt."""
    wrapper, client = create_wrapper_with_fake_client(monkeypatch)
    payload = RadarPayload(
        timestamp_ms=1_717_618_000_000,
        distance_cm=420.0,
        rel_speed_kmh=18.5,
        is_valid=True,
    )

    wrapper.publish(RADAR_TOPIC, payload)

    topic, raw_payload = client.published_messages[0]
    assert topic == RADAR_TOPIC
    assert json.loads(raw_payload) == asdict(payload)


def test_publish_rejects_unknown_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass nur bekannte Topics veröffentlicht werden."""
    wrapper, _client = create_wrapper_with_fake_client(monkeypatch)
    payload = RadarPayload(
        timestamp_ms=1_717_618_000_000,
        distance_cm=420.0,
        rel_speed_kmh=18.5,
        is_valid=True,
    )

    with pytest.raises(TypeError, match="nicht gefunden"):
        wrapper.publish("unknown/topic", payload)


def test_publish_rejects_wrong_payload_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass Topic und Payload-Dataclass zusammenpassen müssen."""
    wrapper, _client = create_wrapper_with_fake_client(monkeypatch)
    payload = GpsPayload(
        timestamp_ms=1_717_618_000_000,
        latitude=51.3127,
        longitude=9.4924,
        speed_kmh=22.1,
        satellites_connected=12,
    )

    with pytest.raises(TypeError, match="RadarPayload"):
        wrapper.publish(RADAR_TOPIC, payload)


def test_publish_rejects_non_dataclass_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass rohe Objekte nicht als MQTT-Payload akzeptiert werden."""
    wrapper, _client = create_wrapper_with_fake_client(monkeypatch)

    with pytest.raises(TypeError, match="Payload muss eine Dataclass sein"):
        wrapper.publish(RADAR_TOPIC, object())


def test_subscribe_registers_topic_at_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass `subscribe()` das Topic beim Paho-Client anmeldet."""
    wrapper, client = create_wrapper_with_fake_client(monkeypatch)

    def collect_payload(payload: RadarPayload) -> None:
        """Nimmt Radar-Payloads für den Test entgegen.

        :param payload: Empfangene Radar-Payload.
        """
        assert payload.is_valid is True

    wrapper.subscribe(RADAR_TOPIC, collect_payload)

    assert client.subscribed_topics == [RADAR_TOPIC]


def test_subscribe_rejects_unknown_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass unbekannte Topics nicht abonniert werden."""
    wrapper, _client = create_wrapper_with_fake_client(monkeypatch)

    def collect_payload(payload: RadarPayload) -> None:
        """Würde im Fehlerfall eine Radar-Payload entgegennehmen.

        :param payload: Empfangene Radar-Payload.
        """
        assert payload.is_valid is True

    with pytest.raises(TypeError, match="nicht gefunden"):
        wrapper.subscribe("unknown/topic", collect_payload)


def test_on_message_deserializes_payload_and_calls_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft den Empfangspfad von JSON über Dataclass bis Callback."""
    wrapper, client = create_wrapper_with_fake_client(monkeypatch)
    received_payloads: list[RadarPayload] = []
    payload = RadarPayload(
        timestamp_ms=1_717_618_000_000,
        distance_cm=420.0,
        rel_speed_kmh=18.5,
        is_valid=True,
    )

    def collect_payload(received_payload: RadarPayload) -> None:
        """Merkt sich die empfangene Radar-Payload.

        :param received_payload: Von `_on_message()` deserialisierte Payload.
        """
        received_payloads.append(received_payload)

    wrapper.subscribe(RADAR_TOPIC, collect_payload)
    message = make_message(RADAR_TOPIC, payload)

    wrapper._on_message(cast(mqtt.Client, client), None, message)

    assert received_payloads == [payload]


def test_on_message_ignores_unregistered_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass Nachrichten ohne registriertes Callback ignoriert werden."""
    wrapper, client = create_wrapper_with_fake_client(monkeypatch)
    payload = GpsPayload(
        timestamp_ms=1_717_618_000_000,
        latitude=51.3127,
        longitude=9.4924,
        speed_kmh=22.1,
        satellites_connected=12,
    )
    message = make_message(GPS_TOPIC, payload)

    wrapper._on_message(cast(mqtt.Client, client), None, message)

    assert client.subscribed_topics == []
