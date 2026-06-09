"""Importtest für das IMU-Modul."""


def test_imu_node_can_be_imported() -> None:
    """Prüft, ob das IMU-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import imu_node

    assert imu_node.__name__ == "sensors.imu_node"
