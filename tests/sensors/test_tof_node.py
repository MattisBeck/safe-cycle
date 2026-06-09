"""Importtest für das ToF-Modul."""


def test_tof_node_can_be_imported() -> None:
    """Prüft, ob das ToF-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import tof_node

    assert tof_node.__name__ == "sensors.tof_node"
