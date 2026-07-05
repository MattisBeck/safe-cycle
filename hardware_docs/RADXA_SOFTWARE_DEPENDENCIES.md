# Radxa Software Dependencies

Diese Anleitung beschreibt den funktionierenden Startpfad für das Vision-Modul
auf dem Radxa Dragon Q6A: Kamera über GStreamer, YOLOv8 über Qualcomm NPU und
Ausgabe als MQTT-`VisionPayload`.

## Ziel

Am Ende soll dieser Befehl auf dem Radxa laufen:

```bash
source ./start_npu.sh
UV_CACHE_DIR=/tmp/safe-cycle-uv-cache PYTHONPATH=src uv run --no-sync --no-dev python -m vision.vision
```

`--no-sync` ist wichtig: `uv run` darf kurz vor dem Start keine Pakete ändern,
sonst kann das systemweite OpenCV wieder verdeckt werden.

## Referenzen und lokale Dateien

Offizielle Radxa-Doku zum Nachschlagen:

- Kamera: <https://docs.radxa.com/en/dragon/q6a/accessories/camera-4k>
- QAIRT SDK Installation: <https://docs.radxa.com/en/dragon/q6a/app-dev/npu-dev/qairt-install>
- QAI AppBuilder: <https://docs.radxa.com/en/fogwise/airbox-q900/ai-dev/qai-appbuilder>

Lokal erwartet und nicht in Git: `Qualcomm/qairt/2.42.0.251225/`,
`Qualcomm/ai-engine-direct-helper/`, `src/vision/models/yolov8_det.bin`.

## 1. Kamera und GStreamer prüfen

Die Radxa Camera 4K muss über `rsetup` aktiviert sein:

```bash
rsetup
```

Danach unter `Overlays` die passende Radxa-Camera-Option aktivieren und neu starten.

Safe Cycle nutzt OpenCV nicht direkt über `/dev/video*`, sondern über diese
GStreamer-Pipeline:

```text
libcamerasrc ! video/x-raw,width=640,height=640 ! videoconvert ! video/x-raw,format=BGR,width=640,height=640 ! appsink drop=true max-buffers=1 sync=false
```

Prüfen, ob GStreamer die libcamera-Quelle kennt:

```bash
gst-inspect-1.0 libcamerasrc
```

Erwartung: Der Befehl zeigt `libcamera Source`. Wenn nicht, fehlt das
libcamera-GStreamer-Plugin.

## 2. Python-Umgebung auf dem Radxa erstellen

Auf dem Radxa darf nicht das PyPI-Paket `opencv-python` verwendet werden. Es ist
normalerweise ohne GStreamer gebaut. Die `.venv` muss deshalb das systemweite
OpenCV sehen:

```bash
rm -rf .venv
uv venv --python /usr/bin/python3 --system-site-packages
uv sync --no-dev
```

Prüfen:

```bash
.venv/bin/python -c "import cv2; print(cv2.__file__); print([line.strip() for line in cv2.getBuildInformation().splitlines() if 'GStreamer' in line])"
```

Erwartung:

```text
/usr/lib/python3/dist-packages/cv2...
GStreamer: YES
```

Wenn dort `GStreamer: NO` steht, nutzt Python das falsche OpenCV.

## 3. Qualcomm NPU vorbereiten

NPU-Variablen in der aktuellen Shell laden:

```bash
source ./start_npu.sh
```

Danach muss `qai_appbuilder` in der Safe-Cycle-`.venv` installiert werden. Der
getestete Weg ist ein lokaler Wheel-Build aus dem Qualcomm-Helper:

```bash
git -C Qualcomm/ai-engine-direct-helper submodule update --init pybind/pybind11
uv pip install -r Qualcomm/ai-engine-direct-helper/requirements.txt
mkdir -p Qualcomm/ai-engine-direct-helper/dist
cd Qualcomm/ai-engine-direct-helper
../../.venv/bin/python setup.py bdist_wheel
cd ../..
uv pip install Qualcomm/ai-engine-direct-helper/dist/qai_appbuilder-2.38.0-cp312-cp312-linux_aarch64.whl
```

Prüfen:

```bash
.venv/bin/python -c "import qai_appbuilder; print(qai_appbuilder.__file__)"
```

Wenn dieser Import fehlschlägt, kann `vision.vision` die NPU nicht benutzen.

## 4. NPU ohne Kamera testen

Dieser Test verarbeitet kein Kamerabild. Er prüft nur, ob das Safe-Cycle-Modell
über Qualcomm AppBuilder eine Inferenz auf der NPU starten kann:

```bash
source ./start_npu.sh
PYTHONPATH=src .venv/bin/python -c "import numpy as np; from vision.vision import MODEL_PATH; from vision.npu import NpuYoloV8Model; model = NpuYoloV8Model(MODEL_PATH); print(model.predict(np.zeros((640, 640, 3), dtype=np.uint8))); model.release()"
```

Eine leere Szene darf `class_ids=[]` liefern. Wichtig ist, dass keine
`qai_appbuilder`-, `QNN_SDK_ROOT`- oder Modellpfad-Fehlermeldung kommt.

## 5. Vision-Modul starten

MQTT-Broker starten:

```bash
docker compose up -d mqtt
```

Vision starten:

```bash
source ./start_npu.sh
UV_CACHE_DIR=/tmp/safe-cycle-uv-cache PYTHONPATH=src uv run --no-sync --no-dev python -m vision.vision
```

Payloads in einem zweiten Terminal mitschneiden:

```bash
docker exec -it mqtt mosquitto_sub -h 127.0.0.1 -p 1883 -t "vision/vehicles" -v
```

## Entwicklung auf anderen Geräten

Auf Geräten ohne Radxa-Kamera kann `uv sync --extra desktop-vision` genutzt
werden. Für den Radxa-Hardwarebetrieb immer die `.venv` mit
`--system-site-packages` verwenden.
