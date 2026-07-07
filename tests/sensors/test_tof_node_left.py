"""Tests für den ToF-Sensor-Node (VL53L1X mit Pimoroni-Bibliothek) (links)."""

from unittest.mock import Mock

from sensors.tof_node_left import create_tof_payload, read_sensor


def test_tof_node_can_be_imported() -> None:
    """Prüft, ob das ToF-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import tof_node_left

    assert tof_node_left.__name__ == "sensors.tof_node_left"


def test_create_tof_payload_valid() -> None:
    """Prüft die erfolgreiche Payload-Generierung mit gültigen Werten."""
    payload = create_tof_payload(150.0)  # 150.0 cm

    assert payload.is_valid is True
    assert payload.distance_cm == 150.0
    assert payload.timestamp_ms > 0


def test_create_tof_payload_invalid_range() -> None:
    """Prüft das Verhalten bei Distanzwerten außerhalb der Reichweite."""
    payload = create_tof_payload(450.0)  # 450.0 cm (VL53L1X max ist ~400 cm)

    assert payload.is_valid is False
    assert payload.distance_cm == 450.0


def test_create_tof_payload_none() -> None:
    """Prüft das Verhalten, wenn kein Sensor-Wert gelesen werden konnte."""
    payload = create_tof_payload(None)

    assert payload.is_valid is False
    assert payload.distance_cm == 0.0


def test_read_sensor_valid() -> None:
    """Prüft, dass die Distanz aus get_distance() gelesen und in cm umgerechnet wird."""
    mock_sensor = Mock()
    mock_sensor.get_distance.return_value = 1500  # 1500 mm = 150 cm

    result = read_sensor(mock_sensor)
    assert result == 150.0


def test_read_sensor_none() -> None:
    """Prüft, dass None zurückgegeben wird, wenn das Sensorobjekt None ist."""
    result = read_sensor(None)
    assert result is None


def test_read_sensor_exception() -> None:
    """Prüft, dass bei I2C-Fehlern None zurückgegeben wird."""
    mock_sensor = Mock()
    mock_sensor.get_distance.side_effect = OSError("I2C failure")

    result = read_sensor(mock_sensor)
    assert result is None
