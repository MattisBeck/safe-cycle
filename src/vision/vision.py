"""Dieses Modul stellt Funktionen zur Objekterkennung für das Projekt bereit."""

import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from shared.config import CAMERA_PIPELINE
from shared.data_models import VisionPayload
from shared.mqtt_client import MQTTWrapper
from vision.npu import NpuYoloV8Model, VehicleDetector

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "yolov8_det.bin"
VISION_TOPIC = "vision/vehicles"
VIDEO_FEED_WINDOW_NAME = "Safe Cycle Live Vision"

VEHICLE_CLASSES = {
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck",
}


def open_camera_capture(pipeline: str = CAMERA_PIPELINE) -> cv2.VideoCapture:
    """Öffnet die Radxa-Kamera über die konfigurierte GStreamer-Pipeline.

    :param pipeline: GStreamer-Pipeline für OpenCV.
    :return: Geöffnete OpenCV-Capture.
    :raises RuntimeError: Wenn die Kamera nicht geöffnet werden kann.
    """
    capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not capture.isOpened():
        raise RuntimeError("Kamera-Pipeline konnte nicht geöffnet werden.")
    return capture


def detect_vehicles(image_source: npt.NDArray[Any], model: VehicleDetector) -> VisionPayload:
    """Erkennt relevante Fahrzeuge in einem Bild.

    :param image_source: numpy-Array des Bildes.
    :param model: Bereits geladenes NPU-YOLOv8-Modell.
    :return: Erkennungsergebnis für den aktuellen Frame.
    """
    # Das Modell liefert COCO-Klassen-IDs. Safe Cycle braucht hier nur die
    # Fahrzeugklassen, weil Fußgänger oder Tiere einen normalerweise nicht überholen :).
    prediction = model.predict(image_source)
    detected_types = [VEHICLE_CLASSES[class_id] for class_id in prediction.class_ids if class_id in VEHICLE_CLASSES]

    # Unix-Zeitstempel in Millisekunden generieren.
    current_timestamp = int(time.time() * 1000)

    return VisionPayload(
        timestamp_ms=current_timestamp,
        found_vehicle=len(detected_types) > 0,
        detected_types=detected_types,
        vehicle_count=len(detected_types),
        inference_time_ms=prediction.inference_time_ms,
    )


def run_live_vision(
    stop_event: threading.Event | None = None,
    show_video_feed: bool = False,
) -> None:
    """Startet Live-Kamera, NPU-YOLOv8-Erkennung und MQTT-Versand.

    :param stop_event: Optionales Stoppsignal für Tests oder eingebettete Starts.
    :param show_video_feed: Zeigt den Live-Feed in einem temporären OpenCV-Fenster.
    """
    capture = open_camera_capture()
    model: NpuYoloV8Model | None = None
    window_created = False
    try:
        if show_video_feed:
            cv2.namedWindow(VIDEO_FEED_WINDOW_NAME, cv2.WINDOW_NORMAL)
            window_created = True

        model = NpuYoloV8Model(MODEL_PATH)
        mqtt_wrapper = MQTTWrapper()

        while stop_event is None or not stop_event.is_set():
            has_frame, frame = capture.read()
            if not has_frame or frame is None:
                break

            if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
                raise ValueError("Vision erwartet ein BGR-Farbbild mit uint8-Daten.")

            if show_video_feed:
                cv2.imshow(VIDEO_FEED_WINDOW_NAME, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            payload = detect_vehicles(frame, model)
            mqtt_wrapper.publish(VISION_TOPIC, payload)
    finally:
        capture.release()
        if model is not None:
            model.release()
        if window_created:
            cv2.destroyWindow(VIDEO_FEED_WINDOW_NAME)


def run_example_detection(image_directory_path: Path) -> None:
    """Führt die Fahrzeugerkennung für lokale Beispielbilder aus.

    :param image_directory_path: Verzeichnis mit den Beispielbildern.
    """
    # Modell einmal laden und für mehrere Bilder wiederverwenden.
    model = NpuYoloV8Model(MODEL_PATH)

    try:
        all_results = []
        for example_image_path in image_directory_path.glob("*.JPG"):
            example_image_array = cv2.imread(str(example_image_path))
            if example_image_array is None:
                raise FileNotFoundError(f"Bild konnte nicht gelesen werden: {example_image_path}")
            if (
                example_image_array.dtype != np.uint8
                or example_image_array.ndim != 3
                or example_image_array.shape[2] != 3
            ):
                raise ValueError("Vision erwartet ein BGR-Farbbild mit uint8-Daten.")

            print(f"Teste Bild: {example_image_path}")
            detection_result = detect_vehicles(example_image_array, model)
            all_results.append((example_image_path, detection_result))
            print(f"Fahrzeug erkannt: {detection_result.found_vehicle}")

        print(f"Bilder ohne Fahrzeug: {[image_path for image_path, result in all_results if not result.found_vehicle]}")
    finally:
        model.release()


if __name__ == "__main__":
    run_live_vision(show_video_feed=True)
