"""NPU-Anbindung für das Qualcomm-QNN-YOLOv8-Modell."""

from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

import cv2
import numpy as np
import numpy.typing as npt

IMAGE_SIZE = 640
NMS_SCORE_THRESHOLD = 0.45
NMS_IOU_THRESHOLD = 0.7
QNN_MODEL_NAME = "yolov8"
QNN_LIB_ARCH = "aarch64-oe-linux-gcc11.2"

ImageArray = npt.NDArray[np.uint8]
FrameArray = npt.NDArray[Any]
ModelInputArray = npt.NDArray[np.float32]


@dataclass(frozen=True)
class AppBuilderBindings:
    """Hält die dynamisch geladenen AppBuilder-Objekte zusammen."""

    qnn_context: Any
    qnn_config: Any
    runtime: Any
    log_level: Any
    profiling_level: Any
    perf_profile: Any


@dataclass(frozen=True)
class ModelDetection:
    """Eine vom Modell nach NMS verbliebene Erkennung."""

    class_id: int
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass(frozen=True)
class ModelPrediction:
    """Reduziertes Ergebnis der NPU-Erkennung für Safe Cycle."""

    class_ids: list[int]
    inference_time_ms: float
    detections: list[ModelDetection] = field(default_factory=list)


class VehicleDetector(Protocol):
    """Beschreibt die minimale Modell-Schnittstelle für die Vision-Logik."""

    def predict(self, image_source: FrameArray) -> ModelPrediction:
        """Erkennt Objektklassen in einem Kameraframe."""


def load_appbuilder_bindings() -> AppBuilderBindings:
    """Lädt Qualcomm AppBuilder erst, wenn die NPU wirklich benutzt wird.

    :return: AppBuilder-Klassen und Konstanten.
    :raises RuntimeError: Wenn `qai_appbuilder` nicht in der Python-Umgebung liegt.
    """
    try:
        appbuilder = importlib.import_module("qai_appbuilder")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "qai_appbuilder wurde nicht gefunden. Installiere ai-engine-direct-helper "
            "in die Safe-Cycle-Umgebung, bevor die NPU-Erkennung gestartet wird."
        ) from exc

    return AppBuilderBindings(
        qnn_context=appbuilder.QNNContext,
        qnn_config=appbuilder.QNNConfig,
        runtime=appbuilder.Runtime,
        log_level=appbuilder.LogLevel,
        profiling_level=appbuilder.ProfilingLevel,
        perf_profile=appbuilder.PerfProfile,
    )


def preprocess_frame_for_npu(image_source: FrameArray) -> ModelInputArray:
    """Wandelt einen OpenCV-Kameraframe in das Eingabeformat der NPU um.

    OpenCV liefert Bilder als BGR-Array. Das Qualcomm-YOLOv8-Modell erwartet
    RGB-Daten mit Werten zwischen 0.0 und 1.0 und der Form `1 x 640 x 640 x 3`.

    :param image_source: Kameraframe als OpenCV-BGR-Bild.
    :return: Normalisierter Eingabetensor im NHWC-Format.
    """
    if image_source.ndim != 3 or image_source.shape[2] != 3:
        raise ValueError("NPU-Eingabe muss ein Farbbild mit drei Kanälen sein.")

    # Die Kamera liefert BGR, YOLO wurde aber auf RGB-Bildern trainiert.
    rgb_image = cv2.cvtColor(image_source, cv2.COLOR_BGR2RGB)

    # Das QNN-Modell hat eine feste Eingabegröße. Wir skalieren deshalb jeden
    # Frame auf 640 x 640 Pixel.
    resized_image = cv2.resize(rgb_image, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_LINEAR)

    # Die NPU erwartet float32-Werte von 0.0 bis 1.0 statt uint8-Werte von 0 bis 255.
    normalized_image = resized_image.astype(np.float32) / 255.0

    # QNN/AppBuilder arbeitet hier mit NHWC: Batch, Höhe, Breite, Kanäle.
    return np.expand_dims(normalized_image, axis=0)


def extract_detections_after_nms(
    model_output: Sequence[npt.NDArray[Any]],
    score_threshold: float = NMS_SCORE_THRESHOLD,
    iou_threshold: float = NMS_IOU_THRESHOLD,
) -> list[ModelDetection]:
    """Extrahiert Erkennungen aus der QNN-Ausgabe und entfernt doppelte Boxen.

    :param model_output: Rohe QNN-Ausgabe in der Reihenfolge Scores, Klassen, Boxen.
    :param score_threshold: Mindestwahrscheinlichkeit für eine Erkennung.
    :param iou_threshold: Überschneidungsschwelle für Non-Maximum-Suppression.
    :return: Verbleibende Erkennungen mit Boxen und Konfidenzen.
    """
    if len(model_output) < 3:
        raise RuntimeError("QNN-Modell hat weniger Ausgaben geliefert als erwartet.")

    # Die Linux-Variante des Qualcomm-Beispiels liefert:
    # model_output[0] = Scores, model_output[1] = Klassen, model_output[2] = Boxen.
    scores = np.asarray(model_output[0], dtype=np.float32).reshape(-1)
    class_ids = np.asarray(model_output[1], dtype=np.int64).reshape(-1)
    boxes = np.asarray(model_output[2], dtype=np.float32).reshape(-1, 4)

    if scores.shape[0] != class_ids.shape[0] or scores.shape[0] != boxes.shape[0]:
        raise RuntimeError("QNN-Modell hat Ausgaben mit unterschiedlichen Längen geliefert.")

    valid_mask = scores >= score_threshold
    if not np.any(valid_mask):
        return []

    filtered_scores = scores[valid_mask]
    filtered_class_ids = class_ids[valid_mask]
    filtered_boxes = boxes[valid_mask]

    # NMS entfernt mehrere stark überlappende Boxen derselben Klasse. Boxen
    # verschiedener Klassen bleiben erhalten, weil sie unterschiedliche Objekte
    # darstellen können.
    selected_indices: list[int] = []
    ordered_indices = np.argsort(filtered_scores)[::-1]
    while ordered_indices.size > 0:
        current_index = int(ordered_indices[0])
        selected_indices.append(current_index)

        if ordered_indices.size == 1:
            break

        current_box = filtered_boxes[current_index]
        remaining_indices = ordered_indices[1:]
        remaining_boxes = filtered_boxes[remaining_indices]

        intersection_left = np.maximum(current_box[0], remaining_boxes[:, 0])
        intersection_top = np.maximum(current_box[1], remaining_boxes[:, 1])
        intersection_right = np.minimum(current_box[2], remaining_boxes[:, 2])
        intersection_bottom = np.minimum(current_box[3], remaining_boxes[:, 3])

        intersection_width = np.maximum(0.0, intersection_right - intersection_left)
        intersection_height = np.maximum(0.0, intersection_bottom - intersection_top)
        intersection_area = intersection_width * intersection_height

        current_area = max(0.0, float(current_box[2] - current_box[0])) * max(
            0.0,
            float(current_box[3] - current_box[1]),
        )
        remaining_areas = np.maximum(0.0, remaining_boxes[:, 2] - remaining_boxes[:, 0]) * np.maximum(
            0.0,
            remaining_boxes[:, 3] - remaining_boxes[:, 1],
        )

        union_area = current_area + remaining_areas - intersection_area
        iou = np.divide(
            intersection_area,
            union_area,
            out=np.zeros_like(intersection_area),
            where=union_area > 0.0,
        )
        remaining_class_ids = filtered_class_ids[remaining_indices]
        belongs_to_other_class = remaining_class_ids != filtered_class_ids[current_index]
        ordered_indices = remaining_indices[(iou <= iou_threshold) | belongs_to_other_class]

    return [
        ModelDetection(
            class_id=int(filtered_class_ids[index]),
            confidence=float(filtered_scores[index]),
            x_min=float(filtered_boxes[index][0]),
            y_min=float(filtered_boxes[index][1]),
            x_max=float(filtered_boxes[index][2]),
            y_max=float(filtered_boxes[index][3]),
        )
        for index in selected_indices
    ]


def extract_class_ids_after_nms(
    model_output: Sequence[npt.NDArray[Any]],
    score_threshold: float = NMS_SCORE_THRESHOLD,
    iou_threshold: float = NMS_IOU_THRESHOLD,
) -> list[int]:
    """Gibt zur Kompatibilität nur die Klassen-IDs nach NMS zurück."""
    return [
        detection.class_id
        for detection in extract_detections_after_nms(
            model_output,
            score_threshold=score_threshold,
            iou_threshold=iou_threshold,
        )
    ]


class NpuYoloV8Model:
    """Kapselt das Qualcomm-QNN-YOLOv8-Modell für die Live-Erkennung."""

    def __init__(
        self,
        model_path: Path,
        appbuilder_bindings: AppBuilderBindings | None = None,
    ) -> None:
        """Initialisiert das QNN-Modell einmalig für mehrere Frames.

        :param model_path: Pfad zum QNN-Context-Binary des YOLOv8-Modells.
        :param appbuilder_bindings: Optionaler Ersatz für Tests ohne echte NPU.
        """
        self.model_path = model_path
        self._appbuilder = appbuilder_bindings or load_appbuilder_bindings()
        self._context: Any | None = None

        qnn_sdk_root = os.environ.get("QNN_SDK_ROOT")
        if qnn_sdk_root is None:
            raise RuntimeError("QNN_SDK_ROOT ist nicht gesetzt. Lade zuerst 'source ./src/vision/start_npu.sh'.")

        if not self.model_path.is_file():
            raise RuntimeError(f"NPU-Modell wurde nicht gefunden: {self.model_path}")

        qnn_lib_dir = Path(qnn_sdk_root) / "lib" / QNN_LIB_ARCH
        if not qnn_lib_dir.is_dir():
            raise RuntimeError(f"QNN-Bibliotheksordner wurde nicht gefunden: {qnn_lib_dir}")

        # QNNConfig verbindet AppBuilder mit der Qualcomm-Runtime und wählt HTP,
        # also den NPU/DSP-Pfad. Ohne diese Konfiguration würde AppBuilder nicht
        # wissen, welche nativen Bibliotheken geladen werden sollen.
        # AppBuilder protokolliert jede Inferenzzeit als Warnung, daher zeigt der
        # Dauerbetrieb nur echte Fehler an.
        self._appbuilder.qnn_config.Config(
            str(qnn_lib_dir),
            self._appbuilder.runtime.HTP,
            self._appbuilder.log_level.ERROR,
            self._appbuilder.profiling_level.BASIC,
        )

        # Das Context-Binary enthält bereits das für die NPU vorbereitete Modell.
        # Es wird einmal geladen und danach für jeden Kameraframe wiederverwendet.
        self._context = self._appbuilder.qnn_context(QNN_MODEL_NAME, str(self.model_path))

    def predict(self, image_source: FrameArray) -> ModelPrediction:
        """Führt eine YOLOv8-Inferenz auf der NPU aus.

        :param image_source: Kameraframe als OpenCV-BGR-Bild.
        :return: Klassen-IDs und gemessene Inferenzzeit.
        """
        if self._context is None:
            raise RuntimeError("NPU-Modell wurde bereits freigegeben.")

        model_input = preprocess_frame_for_npu(image_source)

        # BURST hebt die NPU kurzfristig auf ein hohes Leistungsprofil. Das ist
        # für Livebilder sinnvoll, weil die reine Modelllaufzeit niedrig bleiben soll.
        self._appbuilder.perf_profile.SetPerfProfileGlobal(self._appbuilder.perf_profile.BURST)
        start_time = time.perf_counter()
        try:
            # AppBuilder erwartet eine Liste von Modell-Eingaben. Unser YOLO hat
            # genau eine Eingabe, deshalb wird der Tensor in zwei Listen verpackt:
            # äußerer Aufruf = Inferenzbatch, innerer Eintrag = Modellinput.
            model_output = self._context.Inference([[model_input]])
        finally:
            # Das Leistungsprofil muss auch bei Fehlern zurückgesetzt werden.
            self._appbuilder.perf_profile.RelPerfProfileGlobal()

        inference_time_ms = (time.perf_counter() - start_time) * 1000.0
        detections = extract_detections_after_nms(model_output)
        class_ids = [detection.class_id for detection in detections]
        return ModelPrediction(
            class_ids=class_ids,
            inference_time_ms=inference_time_ms,
            detections=detections,
        )

    def release(self) -> None:
        """Gibt den nativen AppBuilder-Kontext frei."""
        if self._context is not None:
            del self._context
            self._context = None
