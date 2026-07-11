"""Tests für die Qualcomm-NPU-Hilfsfunktionen."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from vision import npu as npu_module


class FakeQnnConfig:
    """Speichert die QNN-Konfiguration ohne echte Qualcomm-Library."""

    def __init__(self) -> None:
        """Initialisiert den Speicher für den letzten Aufruf."""
        self.calls: list[tuple[str, str, int, int]] = []

    def Config(self, qnn_dir: str, runtime: str, log_level: int, profiling_level: int) -> None:
        """Merkt sich die übergebenen QNN-Parameter."""
        self.calls.append((qnn_dir, runtime, log_level, profiling_level))


class FakePerfProfile:
    """Simuliert das Leistungsprofil der NPU."""

    BURST = "burst"

    def __init__(self) -> None:
        """Initialisiert den Aufrufspeicher."""
        self.calls: list[str] = []

    def SetPerfProfileGlobal(self, profile: str) -> None:
        """Merkt sich das gesetzte Leistungsprofil."""
        self.calls.append(f"set:{profile}")

    def RelPerfProfileGlobal(self) -> None:
        """Merkt sich das Zurücksetzen des Leistungsprofils."""
        self.calls.append("release")


class FakeQnnContext:
    """Stellt einen AppBuilder-QNN-Kontext ohne NPU nach."""

    instances: list["FakeQnnContext"] = []

    def __init__(self, model_name: str, model_path: str) -> None:
        """Speichert Modellname und Pfad."""
        self.model_name = model_name
        self.model_path = model_path
        self.received_inputs: list[Any] = []
        FakeQnnContext.instances.append(self)

    def Inference(self, input_data: list[list[npu_module.ModelInputArray]]) -> list[np.ndarray[Any, Any]]:
        """Liefert eine minimale QNN-Ausgabe mit einem Auto."""
        self.received_inputs.append(input_data)
        scores = np.array([0.9], dtype=np.float32)
        class_ids = np.array([2], dtype=np.float32)
        boxes = np.array([[0.0, 0.0, 10.0, 10.0]], dtype=np.float32)
        return [scores, class_ids, boxes]


def create_fake_bindings(qnn_config: FakeQnnConfig, perf_profile: FakePerfProfile) -> npu_module.AppBuilderBindings:
    """Erzeugt AppBuilder-Ersatzobjekte für Tests."""
    return npu_module.AppBuilderBindings(
        qnn_context=FakeQnnContext,
        qnn_config=qnn_config,
        runtime=SimpleNamespace(HTP="Htp"),
        log_level=SimpleNamespace(WARN=2),
        profiling_level=SimpleNamespace(BASIC=1),
        perf_profile=perf_profile,
    )


def test_preprocess_frame_for_npu_converts_bgr_to_rgb_and_nhwc() -> None:
    """Prüft BGR-zu-RGB-Konvertierung, Skalierung und Wertebereich."""
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[:, :] = [10, 20, 30]

    result = npu_module.preprocess_frame_for_npu(image)

    assert result.shape == (1, npu_module.IMAGE_SIZE, npu_module.IMAGE_SIZE, 3)
    assert result.dtype == np.float32
    assert np.allclose(result[0, 0, 0], [30 / 255.0, 20 / 255.0, 10 / 255.0])


def test_preprocess_frame_for_npu_rejects_non_color_image() -> None:
    """Prüft den Fehlerfall für Graustufenbilder."""
    image = np.zeros((2, 2), dtype=np.uint8)

    with pytest.raises(ValueError, match="Farbbild"):
        npu_module.preprocess_frame_for_npu(image)


def test_extract_class_ids_after_nms_filters_scores_and_overlapping_boxes() -> None:
    """Prüft Score-Filter und Non-Maximum-Suppression."""
    scores = np.array([0.95, 0.90, 0.10], dtype=np.float32)
    class_ids = np.array([2, 2, 5], dtype=np.float32)
    boxes = np.array(
        [
            [0.0, 0.0, 10.0, 10.0],
            [0.2, 0.2, 10.2, 10.2],
            [100.0, 100.0, 110.0, 110.0],
        ],
        dtype=np.float32,
    )

    result = npu_module.extract_class_ids_after_nms([scores, class_ids, boxes])

    assert result == [2]


def test_extract_class_ids_after_nms_keeps_overlapping_boxes_of_different_classes() -> None:
    """Prüft, dass sich verschiedene Klassen nicht gegenseitig unterdrücken."""
    scores = np.array([0.95, 0.90], dtype=np.float32)
    class_ids = np.array([2, 7], dtype=np.float32)
    boxes = np.array(
        [
            [0.0, 0.0, 10.0, 10.0],
            [0.2, 0.2, 10.2, 10.2],
        ],
        dtype=np.float32,
    )

    result = npu_module.extract_class_ids_after_nms([scores, class_ids, boxes])

    assert result == [2, 7]


def test_extract_class_ids_after_nms_rejects_incomplete_output() -> None:
    """Prüft unvollständige QNN-Ausgaben."""
    with pytest.raises(RuntimeError, match="weniger Ausgaben"):
        npu_module.extract_class_ids_after_nms([np.array([], dtype=np.float32)])


def test_npu_yolov8_model_configures_qnn_and_runs_prediction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prüft Modellinitialisierung und Inferenzaufruf ohne echte NPU."""
    qnn_root = tmp_path / "qairt"
    qnn_lib_dir = qnn_root / "lib" / npu_module.QNN_LIB_ARCH
    qnn_lib_dir.mkdir(parents=True)
    model_path = tmp_path / "yolov8_det.bin"
    model_path.write_bytes(b"model")
    qnn_config = FakeQnnConfig()
    perf_profile = FakePerfProfile()
    bindings = create_fake_bindings(qnn_config, perf_profile)
    monkeypatch.setenv("QNN_SDK_ROOT", str(qnn_root))
    FakeQnnContext.instances = []

    model = npu_module.NpuYoloV8Model(model_path=model_path, appbuilder_bindings=bindings)
    prediction = model.predict(np.zeros((2, 2, 3), dtype=np.uint8))

    assert qnn_config.calls == [(str(qnn_lib_dir), "Htp", 2, 1)]
    assert prediction.class_ids == [2]
    assert prediction.inference_time_ms >= 0.0
    assert perf_profile.calls == ["set:burst", "release"]
    assert FakeQnnContext.instances[0].model_name == "yolov8"
    assert FakeQnnContext.instances[0].model_path == str(model_path)
    assert FakeQnnContext.instances[0].received_inputs[0][0][0].shape == (
        1,
        npu_module.IMAGE_SIZE,
        npu_module.IMAGE_SIZE,
        3,
    )


def test_npu_yolov8_model_requires_qnn_sdk_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prüft die klare Fehlermeldung ohne NPU-Umgebung."""
    model_path = tmp_path / "yolov8_det.bin"
    model_path.write_bytes(b"model")
    monkeypatch.delenv("QNN_SDK_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="QNN_SDK_ROOT"):
        npu_module.NpuYoloV8Model(
            model_path=model_path,
            appbuilder_bindings=create_fake_bindings(FakeQnnConfig(), FakePerfProfile()),
        )
