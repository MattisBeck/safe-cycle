"""Startpunkt für den Livebetrieb der Vision-Komponente."""

from vision.vision import run_live_vision


def main() -> None:
    """Startet die Liveanalyse des Kamerafeeds."""
    run_live_vision()


if __name__ == "__main__":
    main()
