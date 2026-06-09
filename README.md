# Safe-Cycle

Safe-Cycle ist ein Uniprojekt mit dem Ziel, das Radfahren im urbanen Raum
sicherer zu machen. Das Projekt soll Fahrradfahrende während der Fahrt unterstützen
und objektive Daten über kritische Überholvorgänge und Gefahrenstellen erfassen.
Dafür führt das System Sensor- und Kameradaten zusammen, protokolliert
Abstandsunterschreitungen und stellt die Ergebnisse anschließend in einem
lokalen Dashboard dar.

## Architektur

Die Sensoren übernehmen getrennte Aufgaben:

- **Radar hinten:** Erkennt Fahrzeuge, die sich von hinten nähern, und erfasst
  Entfernung sowie relative Geschwindigkeit.
- **ToF seitlich:** Misst den tatsächlichen seitlichen Abstand während eines
  Überholvorgangs.
- **GPS:** Liefert Position und Geschwindigkeit für Route und Ereignisort.
- **IMU:** Erfasst Beschleunigungswerte und schafft die Grundlage für spätere
  Funktionen wie eine Sturzerkennung.

Die Komponenten sollen später über MQTT lose gekoppelt kommunizieren. Gemeinsame
Python-`dataclasses` definieren dafür einheitliche Datenformate. Die zentrale
Logik synchronisiert Sensordaten mit Kamerabildern und erzeugt Fahrtenprotokolle
für das Post-Ride-Dashboard.

## Ordnerstruktur

```text
safe-cycle/
├── .github/workflows/   # Automatische Tests auf GitHub
├── hardware_docs/       # Schaltpläne, Konstruktion und Hardware-Notizen
├── src/
│   ├── sensors/         # Anbindung von Radar, ToF, GPS und IMU
│   ├── vision/          # Kamera, YOLO-Inferenz, Tracking und KI-Modelle
│   ├── core/            # Synchronisierung, Ereignislogik und Logging
│   ├── dashboard/       # Lokale Auswertung nach einer Fahrt
│   └── shared/          # Gemeinsame Datenmodelle und Hilfsfunktionen
└── tests/
    ├── sensors/         # Tests der Sensormodule
    ├── vision/          # Tests der Bildverarbeitung
    ├── core/            # Tests der zentralen Verarbeitung
    ├── dashboard/       # Tests der lokalen Weboberfläche
    └── shared/          # Tests der gemeinsamen Datenmodelle
```

## Setup

Voraussetzung sind eine unterstützte Python-Version und
[`uv`](https://docs.astral.sh/uv/). Die Entwicklungsumgebung und alle
Abhängigkeiten werden aus der Projektkonfiguration installiert:

```bash
uv sync
```

## Tests

Die Tests werden über `pytest` in der von `uv` verwalteten Umgebung ausgeführt:

```bash
uv run pytest
```

Die Einhaltung der vereinbarten Python-, PEP-8-, Docstring- und
Type-Hint-Regeln wird mit Ruff geprüft:

```bash
uv run ruff check .
```

Die tatsächliche Typkonsistenz wird zusätzlich mit mypy geprüft:

```bash
uv run mypy
```
