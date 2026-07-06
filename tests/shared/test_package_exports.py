"""Tests für die öffentliche Shared-Paketoberfläche."""

from shared import (
    CAMERA_PIPELINE,
    MQTT_BROKER_IP,
    MQTT_BROKER_PORT,
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
    assert TOPIC_PAYLOAD_TYPES["sensors/tof/left"] is TofPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/tof/right"] is TofPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/gps"] is GpsPayload
    assert TOPIC_PAYLOAD_TYPES["sensors/imu"] is ImuPayload
    assert TOPIC_PAYLOAD_TYPES["vision/vehicles"] is VisionPayload


def test_shared_exports_config_helpers() -> None:
    """Prüft direkte Imports der zentralen Einstellungen."""
    assert MQTT_BROKER_IP == "127.0.0.1"
    assert MQTT_BROKER_PORT == 1883
    assert "libcamerasrc" in CAMERA_PIPELINE
    assert "width=640" in CAMERA_PIPELINE
    assert "height=640" in CAMERA_PIPELINE
