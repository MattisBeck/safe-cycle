"""Tests für die öffentliche Shared-Paketoberfläche."""

from shared import (
    TOPIC_PAYLOAD_TYPES,
    GpsPayload,
    ImuPayload,
    MQTTWrapper,
    PayloadType,
    RadarPayload,
    TofPayload,
    VisionPayload,
)


def test_shared_exports_payload_models() -> None:
    """Prüft direkte Imports der gemeinsamen Payload-Dataclasses."""
    assert GpsPayload.__name__ == "GpsPayload"
    assert ImuPayload.__name__ == "ImuPayload"
    assert RadarPayload.__name__ == "RadarPayload"
    assert TofPayload.__name__ == "TofPayload"
    assert VisionPayload.__name__ == "VisionPayload"


def test_shared_exports_mqtt_helpers() -> None:
    """Prüft direkte Imports der MQTT-Hilfstypen."""
    assert MQTTWrapper.__name__ == "MQTTWrapper"
    assert PayloadType is not None
    assert TOPIC_PAYLOAD_TYPES["sensors/radar"] is RadarPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/tof"] is TofPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/gps"] is GpsPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/imu"] is ImuPayload
    assert TOPIC_PAYLOAD_TYPES["vision/vehicles"] is VisionPayload
