"""Importtest für die zentrale Protokollierung."""


def test_main_logger_can_be_imported() -> None:
    """Prüft, ob die Hauptlogik ohne Hardwareabhängigkeiten importierbar ist."""
    from core import main_logger

    assert main_logger.__name__ == "core.main_logger"
