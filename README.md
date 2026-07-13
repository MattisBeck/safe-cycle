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

Die Komponenten kommunizieren lose gekoppelt über MQTT. Gemeinsame
Python-`dataclasses` definieren dafür einheitliche Datenformate. Das Vision-Modul
erkennt Fahrzeuge mit YOLOv8 auf der Qualcomm-NPU und veröffentlicht die
Ergebnisse ebenfalls über MQTT. Objekt-Tracking ist für eine spätere
Ausbaustufe vorgesehen und noch nicht Teil des MVP.

Die zentrale Logik synchronisiert Sensor- und Kameradaten und erzeugt
Fahrtenprotokolle für das Post-Ride-Dashboard.

## Ordnerstruktur

```text
safe-cycle/
├── .github/workflows/   # Automatische Tests auf GitHub
├── hardware_docs/       # Schaltpläne, Konstruktion und Hardware-Notizen
├── src/
│   ├── sensors/         # Anbindung von Radar, ToF, GPS und IMU
│   ├── vision/          # Kamera, NPU-basierte YOLOv8-Inferenz und KI-Modelle
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

Voraussetzung sind [`uv`](https://docs.astral.sh/uv/) sowie Docker mit Docker Compose. Die
Entwicklungsumgebung und die allgemeinen Abhängigkeiten werden aus der
Projektkonfiguration installiert:

```bash
uv sync
```

Für die Entwicklung des Vision-Moduls auf einem Desktop-System wird zusätzlich
OpenCV installiert:

```bash
uv sync --extra desktop-vision
```

Der MQTT-Broker wird anschließend mit Docker Compose gestartet:

```bash
docker compose up -d
```

## Vision auf dem Radxa starten

Der Betrieb auf dem Radxa Dragon Q6A benötigt das lokal bereitgestellte
QNN-Modell, die Qualcomm-Laufzeit und ein OpenCV mit GStreamer-Unterstützung.
Die vollständige Einrichtung ist in den
[Radxa-Softwareabhängigkeiten](hardware_docs/RADXA_SOFTWARE_DEPENDENCIES.md)
beschrieben.

Nach abgeschlossener Einrichtung können alle implementierten Sensoren und das
Vision-Modul gemeinsam gestartet werden. Der lokale MQTT-Broker muss vorher
erreichbar sein:

```bash
docker compose up -d mqtt
./run_safe_cycle.sh
```

Das Startskript bleibt als Supervisor im Vordergrund. `Ctrl+C` beendet alle
gestarteten Module sauber. Vor dem Start zeigt es den geladenen OpenCV-Pfad und
die GStreamer-Buildzeile an; ohne `GStreamer: YES` bricht es ab. Soll nur das
Vision-Modul gestartet werden, wird die NPU-Umgebung separat geladen:

```bash
source ./src/vision/start_npu.sh
UV_CACHE_DIR=/tmp/safe-cycle-uv-cache PYTHONPATH=src uv run --no-sync --no-dev python -m vision
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
