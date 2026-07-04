"""Tests für die zentralen Projekteinstellungen."""

from shared.config import CAMERA_PIPELINE, MQTT_BROKER_IP, MQTT_BROKER_PORT


def test_config_contains_runtime_defaults() -> None:
    """Prüft die festen lokalen Defaults."""
    assert MQTT_BROKER_IP == "127.0.0.1"
    assert MQTT_BROKER_PORT == 1883
    assert "libcamerasrc" in CAMERA_PIPELINE
    assert "width=640" in CAMERA_PIPELINE
    assert "height=640" in CAMERA_PIPELINE
    assert "format=BGR" in CAMERA_PIPELINE
    assert "appsink" in CAMERA_PIPELINE
