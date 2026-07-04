# Radxa Software Dependencies

Diese Notiz beschreibt die Software, die auf dem Radxa Dragon Q6A für die
Radxa Camera 4K und das Vision-Modul benötigt wird.

## Warum das nötig ist

Safe Cycle öffnet die Kamera nicht direkt, sondern über eine
GStreamer-Pipeline:

```text
libcamerasrc ! videoconvert ! video/x-raw,format=BGR ! appsink
```

Dafür müssen drei Dinge gleichzeitig stimmen:

1. Die Radxa Camera 4K muss im System aktiviert sein.
2. GStreamer muss die Quelle `libcamerasrc` kennen.
3. Das von Python importierte `cv2` muss mit GStreamer-Unterstützung gebaut
   sein.

Das normale PyPI-Paket `opencv-python` ist auf dem Radxa nicht ausreichend,
weil es ohne GStreamer-Unterstützung gebaut wurde.

## Radxa-Kamera aktivieren

Die Kamera wird mit dem Radxa-Tool `rsetup` aktiviert:

```bash
rsetup
```

Dann in `Overlays` -> `Manage overlays` die passende Option für die Radxa
Camera 4K am verwendeten CAM-Anschluss aktivieren und danach neu starten.

Die offizielle Anleitung steht hier:
<https://docs.radxa.com/en/dragon/q6a/accessories/camera-4k>

## libcamera und GStreamer

Die Radxa-Anleitung baut libcamera für den einfachen Kameratest mit `qcam`.
Für Safe Cycle ist zusätzlich wichtig, dass das libcamera-GStreamer-Plugin
vorhanden ist. Dieses Plugin stellt `libcamerasrc` bereit.

Beim lokalen funktionierenden Stand ist libcamera so gebaut:

```text
gstreamer: enabled
pipelines: simple
v4l2: enabled
qcam: enabled
```

Prüfen:

```bash
gst-inspect-1.0 libcamerasrc
```

Erwartung: Der Befehl zeigt `libcamera Source`. Wenn der Befehl nichts findet,
fehlt das GStreamer-Plugin. Dann muss libcamera mit GStreamer-Unterstützung
neu gebaut werden.

Wichtige Pakete für GStreamer und den Build sind unter anderem:

```bash
sudo apt install gstreamer1.0-tools libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
```

## OpenCV in Python

Auf dem Radxa soll für den Hardwarebetrieb das systemweite OpenCV verwendet
werden:

```bash
python3 -c "import cv2; print(cv2.__file__); print([line for line in cv2.getBuildInformation().splitlines() if 'GStreamer' in line])"
```

Erwartung:

```text
/usr/lib/python3/dist-packages/cv2...
GStreamer: YES
```

Wenn dort `GStreamer: NO` steht, kann OpenCV die Kamera-Pipeline nicht öffnen.

## uv-Umgebung auf dem Radxa

Die virtuelle Umgebung muss das systemweite OpenCV sehen können. Gleichzeitig
darf `uv` nicht das PyPI-Paket `opencv-python` in die venv installieren, weil
dieses das systemweite `cv2` verdecken würde.

Radxa-Setup:

```bash
rm -rf .venv
uv venv --python /usr/bin/python3 --system-site-packages
uv sync --no-dev --no-install-package opencv-python
```

Beim Start auf dem Radxa `--no-sync` verwenden, sonst installiert `uv run`
`opencv-python` wieder nach:

```bash
PYTHONPATH=src uv run --no-sync --no-dev python -m vision.vision
```

## MQTT-Payloads mitlesen

```bash
docker compose up -d mqtt
```

```bash
docker exec -it mqtt mosquitto_sub -h 127.0.0.1 -p 1883 -t "vision/vehicles" -v
```
