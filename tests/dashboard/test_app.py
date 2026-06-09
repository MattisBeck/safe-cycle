"""Importtest für das Dashboard."""


def test_dashboard_app_can_be_imported() -> None:
    """Prüft, ob das Dashboard ohne Webabhängigkeiten importierbar ist."""
    from dashboard import app

    assert app.__name__ == "dashboard.app"
