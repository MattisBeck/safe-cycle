"""Tests für den ToF-Sensor-Node."""

from sensors.tof_node import create_tof_payload


def test_tof_node_can_be_imported() -> None:
    """Prüft, ob das ToF-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import tof_node

    assert tof_node.__name__ == "sensors.tof_node"


def test_create_tof_payload_valid() -> None:
    """Prüft die erfolgreiche Umrechnung von mm in cm und is_valid=True."""
    payload = create_tof_payload(1500)  # 1500 mm = 150 cm

    assert payload.is_valid is True
    assert payload.distance_cm == 150.0
    assert payload.timestamp_ms > 0


def test_create_tof_payload_invalid_range() -> None:
    """Prüft das Verhalten bei unrealistischen Distanzwerten (Fehlercodes)."""
    payload = create_tof_payload(8190)  # VL53L0X Fehlerwert (Out of range)

    assert payload.is_valid is False
    assert payload.distance_cm == 819.0


def test_create_tof_payload_none() -> None:
    """Prüft das Verhalten, wenn kein Sensor-Wert gelesen werden konnte."""
    payload = create_tof_payload(None)

    assert payload.is_valid is False
    assert payload.distance_cm == 0.0
