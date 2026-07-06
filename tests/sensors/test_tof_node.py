"""Tests für den ToF-Sensor-Node (VL53L1X)."""

from unittest.mock import Mock

from sensors.tof_node import create_tof_payload, read_sensor


def test_tof_node_can_be_imported() -> None:
    """Prüft, ob das ToF-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import tof_node

    assert tof_node.__name__ == "sensors.tof_node"


def test_create_tof_payload_valid() -> None:
    """Prüft die erfolgreiche Übernahme der Distanz in cm und is_valid=True."""
    payload = create_tof_payload(150.0)  # 150 cm

    assert payload.is_valid is True
    assert payload.distance_cm == 150.0
    assert payload.timestamp_ms > 0


def test_create_tof_payload_invalid_range() -> None:
    """Prüft das Verhalten bei unrealistischen Distanzwerten (Fehlercodes)."""
    payload = create_tof_payload(850.0)  # VL53L1X Fehlerwert (Out of range > 800cm)

    assert payload.is_valid is False
    assert payload.distance_cm == 850.0


def test_create_tof_payload_none() -> None:
    """Prüft das Verhalten, wenn kein Sensor-Wert gelesen werden konnte (None)."""
    payload = create_tof_payload(None)

    assert payload.is_valid is False
    assert payload.distance_cm == 0.0


def test_read_sensor_not_ready() -> None:
    """Prüft, dass None zurückgegeben wird, wenn keine Daten bereitstehen."""
    mock_sensor = Mock()
    mock_sensor.data_ready = False

    result = read_sensor(mock_sensor)
    assert result is None


def test_read_sensor_valid() -> None:
    """Prüft, dass die Distanz gelesen und der Interrupt gelöscht wird."""
    mock_sensor = Mock()
    mock_sensor.data_ready = True
    mock_sensor.distance = 120.5

    result = read_sensor(mock_sensor)
    assert result == 120.5
    mock_sensor.clear_interrupt.assert_called_once()


def test_read_sensor_none() -> None:
    """Prüft, dass None zurückgegeben wird, wenn das Sensorobjekt None ist."""
    result = read_sensor(None)
    assert result is None


def test_read_sensor_exception() -> None:
    """Prüft, dass bei I2C-Fehlern None zurückgegeben wird."""
    mock_sensor = Mock()
    mock_sensor.data_ready = True
    # Zugriff auf distance wirft Exception
    type(mock_sensor).distance = PropertyMock(side_effect=OSError("I2C failure"))

    from unittest.mock import PropertyMock

    result = read_sensor(mock_sensor)
    assert result is None
