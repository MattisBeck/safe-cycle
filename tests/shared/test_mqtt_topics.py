"""Tests für die gemeinsamen MQTT-Topics."""

from dataclasses import is_dataclass
from typing import Final

from shared.data_models import GpsPayload, ImuPayload, RadarPayload, TofPayload, VisionPayload
from shared.mqtt_topics import TOPIC_PAYLOAD_TYPES, PayloadType

EXPECTED_TOPIC_PAYLOAD_TYPES: Final[dict[str, PayloadType]] = {
    "sensors/radar": RadarPayload,
    "sensors/tof/left": TofPayload,
    "sensors/tof/right": TofPayload,
    "sensors/gps": GpsPayload,
    "sensors/imu": ImuPayload,
    "vision/vehicles": VisionPayload,
}


def test_topic_schema_contains_expected_payload_types() -> None:
    """Prüft die vereinbarten Topics und ihre Payload-Dataclasses."""
    assert TOPIC_PAYLOAD_TYPES == EXPECTED_TOPIC_PAYLOAD_TYPES


def test_topic_schema_keys_are_unique() -> None:
    """Prüft, dass kein MQTT-Topic versehentlich doppelt vergeben ist."""
    topics = set(TOPIC_PAYLOAD_TYPES)

    assert len(topics) == len(EXPECTED_TOPIC_PAYLOAD_TYPES)


def test_topic_payload_types_are_dataclasses() -> None:
    """Prüft, dass jedes Topic auf eine serialisierbare Dataclass zeigt."""
    for payload_type in TOPIC_PAYLOAD_TYPES.values():
        assert is_dataclass(payload_type)
