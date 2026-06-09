"""Importtest für das GPS-Modul."""


def test_gps_node_can_be_imported() -> None:
    """Prüft, ob das GPS-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import gps_node

    assert gps_node.__name__ == "sensors.gps_node"
