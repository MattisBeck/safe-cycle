"""Tests für die NPU-basierte Fahrzeugerkennung."""

import threading
import time
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import pytest

from shared.data_models import VehicleDetection, VisionPayload
from vision import npu as npu_module
from vision import vision as vision_module


class FakeModel:
    """Stellt ein NPU-Modell ohne echte Hardware nach."""

    def __init__(
        self,
        class_ids: list[int],
        inference_time_ms: float,
        detections: list[npu_module.ModelDetection] | None = None,
    ) -> None:
        """Speichert das vorbereitete Ergebnis und spätere Aufrufdaten."""
        self.class_ids = class_ids
        self.inference_time_ms = inference_time_ms
        self.detections = detections if detections is not None else []
        self.received_image: npt.NDArray[np.uint8] | None = None
        self.released = False

    def predict(self, image_source: npt.NDArray[np.uint8]) -> npu_module.ModelPrediction:
        """Speichert den Aufruf und gibt ein vorbereitetes Ergebnis zurück."""
        self.received_image = image_source
        return npu_module.ModelPrediction(
            class_ids=self.class_ids,
            inference_time_ms=self.inference_time_ms,
            detections=self.detections,
        )

    def release(self) -> None:
        """Merkt sich die Freigabe des simulierten Modells."""
        self.released = True


class FakeCapture:
    """Stellt eine OpenCV-Kamera ohne Hardware nach."""

    def __init__(self, frames: list[npt.NDArray[np.uint8] | None] | None = None, opened: bool = True) -> None:
        """Speichert synthetische Frames und Öffnungszustand."""
        self.frames = frames if frames is not None else []
        self.opened = opened
        self.released = False
        self.read_calls = 0

    def isOpened(self) -> bool:
        """Gibt den simulierten Öffnungszustand zurück."""
        return self.opened

    def read(self) -> tuple[bool, npt.NDArray[np.uint8] | None]:
        """Liefert den nächsten synthetischen Frame."""
        self.read_calls += 1
        if not self.frames:
            return False, None
        frame = self.frames.pop(0)
        return frame is not None, frame

    def release(self) -> None:
        """Merkt sich die Freigabe der Kamera."""
        self.released = True


class FakeMqttWrapper:
    """Sammelt veröffentlichte Vision-Payloads ohne MQTT-Broker."""

    instances: list["FakeMqttWrapper"] = []

    def __init__(self) -> None:
        """Merkt sich die erzeugte Wrapper-Instanz."""
        self.published_payloads: list[tuple[str, VisionPayload]] = []
        self.closed = False
        FakeMqttWrapper.instances.append(self)

    def publish(self, topic: str, payload: VisionPayload) -> None:
        """Merkt sich veröffentlichte Payloads."""
        self.published_payloads.append((topic, payload))

    def close(self) -> None:
        """Merkt sich die Freigabe des simulierten MQTT-Wrappers."""
        self.closed = True


def test_detect_vehicles_counts_only_relevant_vehicle_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Fahrzeugfilter, Anzahl, Timestamp und Modellaufruf."""
    monkeypatch.setattr(time, "time", lambda: 1_717_618_000.123)
    image_source = np.zeros((2, 2, 3), dtype=np.uint8)
    model = FakeModel(class_ids=[2, 0, 7, 5], inference_time_ms=12.5)

    payload = vision_module.detect_vehicles(image_source, model)

    assert payload.timestamp_ms == 1_717_618_000_123
    assert payload.found_vehicle is True
    assert payload.detected_types == ["Car", "Truck", "Bus"]
    assert payload.vehicle_count == 3
    assert payload.inference_time_ms == 12.5
    assert model.received_image is image_source


def test_detect_vehicles_publishes_normalized_relevant_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Boxkonvertierung und Filterung nicht relevanter Klassen."""
    monkeypatch.setattr(time, "time", lambda: 1_717_618_000.123)
    image_source = np.zeros((2, 2, 3), dtype=np.uint8)
    model = FakeModel(
        class_ids=[2, 0],
        inference_time_ms=12.5,
        detections=[
            npu_module.ModelDetection(
                class_id=2,
                confidence=0.9,
                x_min=0.0,
                y_min=64.0,
                x_max=320.0,
                y_max=640.0,
            ),
            npu_module.ModelDetection(
                class_id=0,
                confidence=0.95,
                x_min=0.0,
                y_min=0.0,
                x_max=640.0,
                y_max=640.0,
            ),
        ],
    )

    payload = vision_module.detect_vehicles(image_source, model)

    assert payload.detections == [
        VehicleDetection(
            class_name="Car",
            confidence=0.9,
            x_min=0.0,
            y_min=0.1,
            x_max=0.5,
            y_max=1.0,
        )
    ]
    assert payload.found_vehicle is True
    assert payload.vehicle_count == 1


def test_open_camera_capture_uses_gstreamer_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass die Radxa-Pipeline über GStreamer geöffnet wird."""
    created_captures: list[tuple[str, int]] = []
    fake_capture = FakeCapture(opened=True)

    def fake_video_capture(pipeline: str, backend: int) -> FakeCapture:
        """Ersetzt OpenCVs Kameraerzeugung."""
        created_captures.append((pipeline, backend))
        return fake_capture

    monkeypatch.setattr(cv2, "VideoCapture", fake_video_capture)

    capture = vision_module.open_camera_capture("pipeline")

    assert id(capture) == id(fake_capture)
    assert created_captures == [("pipeline", cv2.CAP_GSTREAMER)]


def test_open_camera_capture_rejects_closed_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft den Fehlerfall bei nicht geöffneter Kamera."""
    monkeypatch.setattr(cv2, "VideoCapture", lambda _pipeline, _backend: FakeCapture(opened=False))

    with pytest.raises(RuntimeError, match="Kamera-Pipeline"):
        vision_module.open_camera_capture("pipeline")


def test_detect_vehicles_returns_empty_payload_without_relevant_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Bilder ohne relevante Fahrzeugklassen."""
    monkeypatch.setattr(time, "time", lambda: 1_717_618_001.0)
    image_source = np.zeros((2, 2, 3), dtype=np.uint8)
    model = FakeModel(class_ids=[0, 1, 15], inference_time_ms=8.0)

    payload = vision_module.detect_vehicles(image_source, model)

    assert payload.timestamp_ms == 1_717_618_001_000
    assert payload.found_vehicle is False
    assert payload.detected_types == []
    assert payload.vehicle_count == 0
    assert payload.inference_time_ms == 8.0


def test_run_live_vision_publishes_payloads_and_releases_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft Orchestrierung von Kamera, NPU-Modell und MQTT."""
    first_frame = np.zeros((1, 1, 3), dtype=np.uint8)
    second_frame = np.ones((1, 1, 3), dtype=np.uint8)
    capture = FakeCapture(frames=[first_frame, second_frame])
    fake_model = FakeModel(class_ids=[], inference_time_ms=1.0)
    stop_event = threading.Event()
    created_model_paths: list[Path] = []
    opened_camera = False
    received_frames: list[npt.NDArray[np.uint8]] = []

    def fake_open_camera_capture() -> FakeCapture:
        """Ersetzt die Hardwarekamera."""
        nonlocal opened_camera
        opened_camera = True
        return capture

    def fake_npu_model(model_path: Path) -> FakeModel:
        """Ersetzt das echte NPU-Modell."""
        created_model_paths.append(model_path)
        return fake_model

    def fake_detect_vehicles(image_source: npt.NDArray[np.uint8], model: object) -> VisionPayload:
        """Erzeugt Payloads aus der Frame-Helligkeit."""
        assert model is fake_model
        received_frames.append(image_source)
        found_vehicle = bool(image_source[0, 0, 0])
        if found_vehicle:
            stop_event.set()
        return VisionPayload(
            timestamp_ms=1 if not found_vehicle else 2,
            found_vehicle=found_vehicle,
            detected_types=["Car"] if found_vehicle else [],
            vehicle_count=1 if found_vehicle else 0,
            inference_time_ms=1.0,
        )

    FakeMqttWrapper.instances = []
    monkeypatch.setattr(vision_module, "open_camera_capture", fake_open_camera_capture)
    monkeypatch.setattr(vision_module, "NpuYoloV8Model", fake_npu_model)
    monkeypatch.setattr(vision_module, "detect_vehicles", fake_detect_vehicles)
    monkeypatch.setattr(vision_module, "MQTTWrapper", FakeMqttWrapper)

    vision_module.run_live_vision(stop_event=stop_event)

    assert opened_camera is True
    assert created_model_paths == [vision_module.MODEL_PATH]
    assert received_frames == [first_frame, second_frame]
    assert fake_model.released is True
    assert capture.read_calls == 2
    assert capture.released is True
    assert len(FakeMqttWrapper.instances) == 1
    mqtt_wrapper = FakeMqttWrapper.instances[0]
    assert [topic for topic, _payload in mqtt_wrapper.published_payloads] == [
        "vision/vehicles",
        "vision/vehicles",
    ]
    assert [payload.found_vehicle for _topic, payload in mqtt_wrapper.published_payloads] == [False, True]
    assert mqtt_wrapper.closed is True


def test_run_live_vision_retries_temporary_camera_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft, dass ein kurzer Kameraaussetzer nicht sofort beendet."""
    frame = np.ones((1, 1, 3), dtype=np.uint8)
    capture = FakeCapture(frames=[None, None, frame])
    fake_model = FakeModel(class_ids=[], inference_time_ms=1.0)
    stop_event = threading.Event()

    def fake_detect_vehicles(image_source: npt.NDArray[np.uint8], _model: object) -> VisionPayload:
        """Beendet den Test nach dem ersten gültigen Frame."""
        assert image_source is frame
        stop_event.set()
        return VisionPayload(
            timestamp_ms=1,
            found_vehicle=True,
            detected_types=["Car"],
            vehicle_count=1,
            inference_time_ms=1.0,
        )

    FakeMqttWrapper.instances = []
    monkeypatch.setattr(vision_module, "open_camera_capture", lambda: capture)
    monkeypatch.setattr(vision_module, "NpuYoloV8Model", lambda _model_path: fake_model)
    monkeypatch.setattr(vision_module, "detect_vehicles", fake_detect_vehicles)
    monkeypatch.setattr(vision_module, "MQTTWrapper", FakeMqttWrapper)

    vision_module.run_live_vision(stop_event=stop_event)

    assert capture.read_calls == 3
    assert capture.released is True
    assert fake_model.released is True
    assert len(FakeMqttWrapper.instances) == 1
    mqtt_wrapper = FakeMqttWrapper.instances[0]
    assert len(mqtt_wrapper.published_payloads) == 1
    assert mqtt_wrapper.closed is True


def test_run_live_vision_raises_after_repeated_camera_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft den sichtbaren Fehler nach mehreren Kameraaussetzern."""
    capture = FakeCapture(frames=[None] * vision_module.MAX_CAMERA_READ_FAILURES)
    fake_model = FakeModel(class_ids=[], inference_time_ms=1.0)

    FakeMqttWrapper.instances = []
    monkeypatch.setattr(vision_module, "open_camera_capture", lambda: capture)
    monkeypatch.setattr(vision_module, "NpuYoloV8Model", lambda _model_path: fake_model)
    monkeypatch.setattr(vision_module, "MQTTWrapper", FakeMqttWrapper)

    with pytest.raises(RuntimeError, match="keinen gültigen Frame"):
        vision_module.run_live_vision(stop_event=threading.Event())

    assert capture.read_calls == vision_module.MAX_CAMERA_READ_FAILURES
    assert capture.released is True
    assert fake_model.released is True
    assert len(FakeMqttWrapper.instances) == 1
    assert FakeMqttWrapper.instances[0].closed is True


def test_run_live_vision_releases_capture_when_publish_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft die Kamerafreigabe bei Fehlern in der Orchestrierung."""
    capture = FakeCapture(frames=[np.zeros((1, 1, 3), dtype=np.uint8)])
    payload = VisionPayload(
        timestamp_ms=1,
        found_vehicle=False,
        detected_types=[],
        vehicle_count=0,
        inference_time_ms=1.0,
    )

    class FailingMqttWrapper:
        """Simuliert einen Fehler beim MQTT-Versand."""

        def __init__(self) -> None:
            """Erstellt den simulierten Wrapper."""

        def publish(self, _topic: str, _payload: VisionPayload) -> None:
            """Bricht den Versand gezielt ab."""
            raise RuntimeError("MQTT kaputt")

        def close(self) -> None:
            """Simuliert ein erfolgreiches Schließen nach dem Fehler."""
            return None

    monkeypatch.setattr(vision_module, "open_camera_capture", lambda: capture)
    fake_model = FakeModel(class_ids=[], inference_time_ms=1.0)

    monkeypatch.setattr(vision_module, "NpuYoloV8Model", lambda _model_path: fake_model)
    monkeypatch.setattr(vision_module, "detect_vehicles", lambda _image_source, _model: payload)
    monkeypatch.setattr(vision_module, "MQTTWrapper", FailingMqttWrapper)

    with pytest.raises(RuntimeError, match="MQTT kaputt"):
        vision_module.run_live_vision(stop_event=threading.Event())

    assert capture.released is True
    assert fake_model.released is True


def test_run_live_vision_shows_video_feed_until_q(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prüft den temporären OpenCV-Videofeed."""
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    capture = FakeCapture(frames=[frame])
    created_windows: list[tuple[str, int]] = []
    shown_frames: list[tuple[str, npt.NDArray[np.uint8]]] = []
    wait_delays: list[int] = []
    destroyed_windows: list[str] = []

    def fake_wait_key(delay: int) -> int:
        """Speichert die Wartezeit und simuliert die Taste q."""
        wait_delays.append(delay)
        return ord("q")

    monkeypatch.setattr(vision_module, "open_camera_capture", lambda: capture)
    monkeypatch.setattr(
        vision_module,
        "NpuYoloV8Model",
        lambda _model_path: FakeModel(class_ids=[], inference_time_ms=1.0),
    )
    monkeypatch.setattr(vision_module, "MQTTWrapper", FakeMqttWrapper)
    monkeypatch.setattr(vision_module, "detect_vehicles", lambda _image_source, _model: pytest.fail("q beendet vorher"))
    monkeypatch.setattr(cv2, "namedWindow", lambda name, flag: created_windows.append((name, flag)))
    monkeypatch.setattr(cv2, "imshow", lambda name, image: shown_frames.append((name, image)))
    monkeypatch.setattr(cv2, "waitKey", fake_wait_key)
    monkeypatch.setattr(cv2, "destroyWindow", lambda name: destroyed_windows.append(name))

    vision_module.run_live_vision(stop_event=threading.Event(), show_video_feed=True)

    assert created_windows == [(vision_module.VIDEO_FEED_WINDOW_NAME, cv2.WINDOW_NORMAL)]
    assert shown_frames == [(vision_module.VIDEO_FEED_WINDOW_NAME, frame)]
    assert wait_delays == [1]
    assert destroyed_windows == [vision_module.VIDEO_FEED_WINDOW_NAME]
    assert capture.released is True


def test_run_example_detection_creates_model_once_and_reuses_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prüft den lokalen Beispiel-Runner ohne echte Bilder oder NPU-Modell."""
    example_image_directory_path = tmp_path / ".local" / "test_images"
    example_image_directory_path.mkdir(parents=True)
    vehicle_image_path = example_image_directory_path / "vehicle.JPG"
    empty_image_path = example_image_directory_path / "empty.JPG"
    vehicle_image_path.write_bytes(b"kein echtes Bild")
    empty_image_path.write_bytes(b"kein echtes Bild")

    fake_model = FakeModel(class_ids=[], inference_time_ms=1.0)
    created_model_paths: list[Path] = []
    received_models: list[object] = []

    def fake_npu_model(model_path: Path) -> FakeModel:
        """Ersetzt die echte NPU-Modellerzeugung im Test."""
        created_model_paths.append(model_path)
        return fake_model

    def fake_imread(image_path: str) -> npt.NDArray[np.uint8]:
        """Erzeugt ein synthetisches Bild anhand des Dateinamens."""
        image = np.zeros((1, 1, 3), dtype=np.uint8)
        if Path(image_path).name == "vehicle.JPG":
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

    monkeypatch.setattr(vision_module, "NpuYoloV8Model", fake_npu_model)
    monkeypatch.setattr(cv2, "imread", fake_imread)
    monkeypatch.setattr(vision_module, "detect_vehicles", fake_detect_vehicles)

    vision_module.run_example_detection(example_image_directory_path)

    captured = capsys.readouterr()
    assert created_model_paths == [vision_module.MODEL_PATH]
    assert received_models == [fake_model, fake_model]
    assert f"Bilder ohne Fahrzeug: [{empty_image_path!r}]" in captured.out
