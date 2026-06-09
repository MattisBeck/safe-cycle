"""Importtest für das Radarmodul."""


def test_radar_node_can_be_imported() -> None:
    """Prüft, ob das Radarmodul ohne angeschlossene Hardware importierbar ist."""
    from sensors import radar_node

    assert radar_node.__name__ == "sensors.radar_node"
