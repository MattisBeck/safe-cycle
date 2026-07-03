"""Dieses Modul stellt Funktionen zur Objekterkennung für das Projekt bereit."""

import threading
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO  # type: ignore[attr-defined]

from shared.config import CAMERA_PIPELINE
from shared.data_models import VisionPayload
from shared.mqtt_client import MQTTWrapper

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "yolo11s.pt"
VISION_TOPIC = "vision/vehicles"

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


def detect_vehicles(image_source: np.ndarray, model: YOLO) -> VisionPayload:
    """Erkennt relevante Fahrzeuge in einem Bild.

    :param image_source: numpy-Array des Bildes.
    :param model: Bereits geladenes YOLO-Modell.
    :return: Erkennungsergebnis für den aktuellen Frame.
    """
    # Inference mit dem bereits geladenen Modell ausführen.
    results = model(image_source, verbose=False)
    first_result = results[0]

    # Erkannte Klassen-IDs aus dem ersten Ergebnis herauslesen.
    detected_ids = first_result.boxes.cls.int().tolist()

    # Nur relevante Fahrzeugklassen übernehmen und in Text-Namen übersetzen.
    detected_types = [VEHICLE_CLASSES[cid] for cid in detected_ids if cid in VEHICLE_CLASSES]

    # Unix-Zeitstempel in Millisekunden generieren.
    current_timestamp = int(time.time() * 1000)

    # Reine Inference-Zeit aus dem YOLO-Ergebnis übernehmen.
    inference_time_ms = float(first_result.speed["inference"])

    return VisionPayload(
        timestamp_ms=current_timestamp,
        found_vehicle=len(detected_types) > 0,
        detected_types=detected_types,
        vehicle_count=len(detected_types),
        inference_time_ms=inference_time_ms,
    )


def run_live_vision(
    stop_event: threading.Event | None = None,
) -> None:
    """Startet Live-Kamera, YOLO-Erkennung und MQTT-Versand.

    :param stop_event: Optionales Stoppsignal für Tests oder eingebettete Starts.
    """
    capture = open_camera_capture()
    try:
        model = YOLO(MODEL_PATH)
        mqtt_wrapper = MQTTWrapper()

        while stop_event is None or not stop_event.is_set():
            has_frame, frame = capture.read()
            if not has_frame:
                break

            payload = detect_vehicles(frame, model)
            mqtt_wrapper.publish(VISION_TOPIC, payload)
    finally:
        capture.release()


def run_example_detection(image_directory_path: Path) -> None:
    """Führt die Fahrzeugerkennung für lokale Beispielbilder aus.

    :param image_directory_path: Verzeichnis mit den Beispielbildern.
    """
    # Modell einmal laden und für mehrere Bilder wiederverwenden.
    model = YOLO(MODEL_PATH)

    all_results = []
    for example_image_path in image_directory_path.glob("*.JPG"):
        example_image_array = cv2.imread(example_image_path)
        if example_image_array is None:
            raise FileNotFoundError(f"Bild konnte nicht gelesen werden: {example_image_path}")

        print(f"Teste Bild: {example_image_path}")
        detection_result = detect_vehicles(example_image_array, model)
        all_results.append((example_image_path, detection_result))
        print(f"Fahrzeug erkannt: {detection_result.found_vehicle}")

    print(f"Bilder ohne Fahrzeug: {[image_path for image_path, result in all_results if not result.found_vehicle]}")


if __name__ == "__main__":
    run_live_vision()
