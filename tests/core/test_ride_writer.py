"""Tests für die JSON-Ausgabe abgeschlossener Fahrten."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.ride_writer import resolve_ride_output, write_ride_data
from shared import Coordinates, RideData, RoutePoint, Violation


def make_ride_data(*, image_path: Path | None = None) -> RideData:
    """Erstellt vollständige Testdaten einer Fahrt.

    :param image_path: Optionaler relativer Pfad zum Beweisbild.
    """
    return RideData(
        ride_id="tour_2026_06_05_1430",
        start_time=1_717_618_000,
        end_time=1_717_625_000,
        route_logs=[
            RoutePoint(timestamp=1_717_618_010, lat=51.3127, lon=9.4924),
            RoutePoint(timestamp=1_717_618_020, lat=51.3128, lon=9.4925),
        ],
        violations=[
            Violation(
                timestamp=1_717_618_015,
                coordinates=Coordinates(lat=51.31275, lon=9.49245),
                distance_cm=85.5,
                speed_kmh=22.1,
                image_path=image_path,
            )
        ],
    )


def test_write_ride_data_creates_dashboard_json(tmp_path: Path) -> None:
    """Prüft die vollständige Ausgabe im vereinbarten JSON-Format.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    output_directory = tmp_path / "data" / "rides"

    output_path = write_ride_data(make_ride_data(), output_directory)

    assert output_path == output_directory / "tour_2026_06_05_1430.json"
    assert output_path.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "ride_id": "tour_2026_06_05_1430",
        "start_time": 1_717_618_000,
        "end_time": 1_717_625_000,
        "route_logs": [
            {"timestamp": 1_717_618_010, "lat": 51.3127, "lon": 9.4924},
            {"timestamp": 1_717_618_020, "lat": 51.3128, "lon": 9.4925},
        ],
        "violations": [
            {
                "timestamp": 1_717_618_015,
                "coordinates": {"lat": 51.31275, "lon": 9.49245},
                "distance_cm": 85.5,
                "speed_kmh": 22.1,
                "image_path": None,
            }
        ],
    }
    assert list(output_directory.glob("*.tmp")) == []


def test_write_ride_data_serializes_relative_image_path(tmp_path: Path) -> None:
    """Prüft die Konvertierung eines relativen Bildpfads.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    image_path = Path("images/violations/auto_id_5_1717618015.jpg")

    output_path = write_ride_data(make_ride_data(image_path=image_path), tmp_path)
    written_data = json.loads(output_path.read_text(encoding="utf-8"))

    assert written_data["violations"][0]["image_path"] == image_path.as_posix()


def test_resolve_ride_output_adds_suffix_without_mutating_input(tmp_path: Path) -> None:
    """Prüft Kollisionsauflösung und unveränderte Eingabedaten.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    ride_data = make_ride_data()
    (tmp_path / "tour_2026_06_05_1430.json").write_text("erste Fahrt", encoding="utf-8")
    (tmp_path / "tour_2026_06_05_1430_2.json").write_text("zweite Fahrt", encoding="utf-8")

    resolved_ride_data, output_path = resolve_ride_output(ride_data, tmp_path)

    assert resolved_ride_data.ride_id == "tour_2026_06_05_1430_3"
    assert output_path == tmp_path / "tour_2026_06_05_1430_3.json"
    assert ride_data.ride_id == "tour_2026_06_05_1430"


def test_write_ride_data_preserves_existing_rides(tmp_path: Path) -> None:
    """Prüft, dass vorhandene Fahrtdateien nicht überschrieben werden.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    first_path = write_ride_data(make_ride_data(), tmp_path)
    second_path = write_ride_data(make_ride_data(), tmp_path)

    assert first_path.name == "tour_2026_06_05_1430.json"
    assert second_path.name == "tour_2026_06_05_1430_2.json"
    assert json.loads(second_path.read_text(encoding="utf-8"))["ride_id"] == second_path.stem


def test_write_ride_data_rejects_absolute_image_path(tmp_path: Path) -> None:
    """Prüft die Ablehnung absoluter Bildpfade.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    ride_data = make_ride_data(image_path=tmp_path / "evidence.jpg")

    with pytest.raises(ValueError, match="relativ"):
        write_ride_data(ride_data, tmp_path / "rides")

    assert list((tmp_path / "rides").iterdir()) == []


def test_write_ride_data_removes_temporary_file_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prüft das Aufräumen nach einem fehlgeschlagenen atomaren Ersetzen.

    :param tmp_path: Temporäres Testverzeichnis.
    :param monkeypatch: Pytest-Helfer zum Simulieren eines Dateisystemfehlers.
    """
    def fail_replace(_source: Path, _target: Path) -> Path:
        """Simuliert einen Fehler beim finalen Ersetzen."""
        raise OSError("simulierter Dateisystemfehler")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulierter Dateisystemfehler"):
        write_ride_data(make_ride_data(), tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_write_ride_data_reserves_paths_for_concurrent_writers(tmp_path: Path) -> None:
    """Prüft verlustfreie Dateinamen bei parallelen Schreibvorgängen.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    def write_ride() -> Path:
        """Schreibt eine Fahrt aus einem parallelen Worker."""
        return write_ride_data(make_ride_data(), tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write_ride) for _ in range(2)]
        output_paths = [future.result() for future in futures]

    assert {path.name for path in output_paths} == {
        "tour_2026_06_05_1430.json",
        "tour_2026_06_05_1430_2.json",
    }
    assert {
        json.loads(path.read_text(encoding="utf-8"))["ride_id"] for path in output_paths
    } == {path.stem for path in output_paths}


def test_write_ride_data_rejects_non_finite_numbers(tmp_path: Path) -> None:
    """Prüft, dass nicht-endliche Sensorwerte kein ungültiges JSON erzeugen.

    :param tmp_path: Temporäres Testverzeichnis.
    """
    ride_data = make_ride_data()
    ride_data.route_logs[0].lat = float("nan")

    with pytest.raises(ValueError, match="Out of range"):
        write_ride_data(ride_data, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_write_ride_data_does_not_publish_empty_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prüft, dass vor dem atomaren Ersetzen keine finale JSON sichtbar ist.

    :param tmp_path: Temporäres Testverzeichnis.
    :param monkeypatch: Pytest-Helfer zum Pausieren des finalen Ersetzens.
    """
    replace_started = threading.Event()
    continue_replace = threading.Event()
    original_replace = Path.replace

    def paused_replace(source: Path, target: Path) -> Path:
        """Pausiert den Writer unmittelbar vor Veröffentlichung der JSON-Datei."""
        replace_started.set()
        continue_replace.wait(timeout=5)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", paused_replace)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(write_ride_data, make_ride_data(), tmp_path)
        assert replace_started.wait(timeout=5)
        assert list(tmp_path.glob("*.json")) == []
        assert list(tmp_path.glob("*.lock")) != []
        continue_replace.set()
        future.result(timeout=5)

    assert [path.name for path in tmp_path.glob("*.json")] == [
        "tour_2026_06_05_1430.json"
    ]
    assert list(tmp_path.glob("*.lock")) == []
