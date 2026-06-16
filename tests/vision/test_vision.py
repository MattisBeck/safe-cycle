"""Tests für die YOLO-basierte Fahrzeugerkennung."""

import builtins
import time
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import numpy.typing as npt
import pytest

from shared.data_models import VisionPayload
from vision import vision as vision_module


class FakeClassIds:
    """Stellt die von YOLO gelieferte Klassen-ID-Kette nach."""

    def __init__(self, values: list[builtins.int]) -> None:
        """Speichert die simulierten Klassen-IDs."""
        self._values = values

    def int(self) -> "FakeClassIds":
        """Gibt die IDs als ganzzahlige Werte zurück."""
        return self

    def tolist(self) -> list[builtins.int]:
        """Wandelt die IDs in eine Python-Liste um."""
        return self._values


class FakeBoxes:
    """Stellt die Box-Daten eines YOLO-Ergebnisses nach."""

    def __init__(self, class_ids: list[int]) -> None:
        """Speichert die simulierten Klassen-IDs als Box-Daten."""
        self.cls = FakeClassIds(class_ids)


class FakeResult:
    """Stellt ein einzelnes YOLO-Ergebnis nach."""

    def __init__(self, class_ids: list[int], inference_time_ms: float) -> None:
        """Speichert Boxen und Laufzeitdaten des simulierten Ergebnisses."""
        self.boxes = FakeBoxes(class_ids)
        self.speed = {"inference": inference_time_ms}


class FakeModel:
    """Stellt ein aufrufbares YOLO-Modell nach."""

    def __init__(self, class_ids: list[int], inference_time_ms: float) -> None:
        """Speichert das vorbereitete Ergebnis und spätere Aufrufdaten."""
        self.result = FakeResult(class_ids, inference_time_ms)
        self.received_image: npt.NDArray[np.uint8] | None = None
        self.received_verbose: bool | None = None

    def __call__(self, image_source: npt.NDArray[np.uint8], verbose: bool) -> list[FakeResult]:
        """Speichert den Aufruf und gibt ein vorbereitetes Ergebnis zurück."""
        self.received_image = image_source
        self.received_verbose = verbose
        return [self.result]


def test_detect_vehicles_counts_only_relevant_vehicle_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Fahrzeugfilter, Anzahl, Timestamp und Modellaufruf."""
    monkeypatch.setattr(time, "time", lambda: 1_717_618_000.123)
    image_source = np.zeros((2, 2, 3), dtype=np.uint8)
    model = FakeModel(class_ids=[2, 0, 7, 5], inference_time_ms=12.5)

    payload = vision_module.detect_vehicles(image_source, cast(Any, model))

    assert payload.timestamp_ms == 1_717_618_000_123
    assert payload.found_vehicle is True
    assert payload.detected_types == ["Car", "Truck", "Bus"]
    assert payload.vehicle_count == 3
    assert payload.inference_time_ms == 12.5
    assert model.received_image is image_source
    assert model.received_verbose is False


def test_detect_vehicles_returns_empty_payload_without_relevant_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Bilder ohne relevante Fahrzeugklassen."""
    monkeypatch.setattr(time, "time", lambda: 1_717_618_001.0)
    image_source = np.zeros((2, 2, 3), dtype=np.uint8)
    model = FakeModel(class_ids=[0, 1, 15], inference_time_ms=8.0)

    payload = vision_module.detect_vehicles(image_source, cast(Any, model))

    assert payload.timestamp_ms == 1_717_618_001_000
    assert payload.found_vehicle is False
    assert payload.detected_types == []
    assert payload.vehicle_count == 0
    assert payload.inference_time_ms == 8.0


def test_run_example_detection_creates_model_once_and_reuses_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prüft den lokalen Beispiel-Runner ohne echte Bilder oder YOLO-Modell."""
    example_image_directory_path = tmp_path / ".local" / "test_images"
    example_image_directory_path.mkdir(parents=True)
    vehicle_image_path = example_image_directory_path / "vehicle.JPG"
    empty_image_path = example_image_directory_path / "empty.JPG"
    vehicle_image_path.write_bytes(b"kein echtes Bild")
    empty_image_path.write_bytes(b"kein echtes Bild")

    fake_model = object()
    created_model_paths: list[Path] = []
    received_models: list[object] = []

    def fake_yolo(model_path: Path) -> object:
        """Ersetzt die echte YOLO-Erzeugung im Test."""
        created_model_paths.append(model_path)
        return fake_model

    def fake_imread(image_path: Path) -> npt.NDArray[np.uint8]:
        """Erzeugt ein synthetisches Bild anhand des Dateinamens."""
        image = np.zeros((1, 1, 3), dtype=np.uint8)
        if image_path.name == "vehicle.JPG":
            image[0, 0, 0] = 1
        return image

    def fake_detect_vehicles(image_source: npt.NDArray[np.uint8], model: object) -> VisionPayload:
        """Ersetzt die eigentliche Erkennung durch eine deterministische Auswertung."""
        received_models.append(model)
        found_vehicle = bool(image_source[0, 0, 0])
        return VisionPayload(
            timestamp_ms=1,
            found_vehicle=found_vehicle,
            detected_types=["Car"] if found_vehicle else [],
            vehicle_count=1 if found_vehicle else 0,
            inference_time_ms=1.0,
        )

    monkeypatch.setattr(vision_module, "YOLO", fake_yolo)
    monkeypatch.setattr(cv2, "imread", fake_imread)
    monkeypatch.setattr(vision_module, "detect_vehicles", fake_detect_vehicles)

    vision_module.run_example_detection(example_image_directory_path)

    captured = capsys.readouterr()
    assert created_model_paths == [vision_module.MODEL_PATH]
    assert received_models == [fake_model, fake_model]
    assert f"Bilder ohne Fahrzeug: [{empty_image_path!r}]" in captured.out
