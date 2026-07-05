# Qualcomm-Dateien für die NPU

Dieser Ordner enthält lokale Qualcomm-Dateien für die NPU auf dem Radxa Dragon
Q6A. Die Dateien sind groß, teilweise plattformspezifisch und bleiben deshalb
aus Git ausgeschlossen.

## Erwartete Struktur

```text
Qualcomm/
├── README.md
├── .gitignore
├── qairt/
│   └── 2.42.0.251225/
└── ai-engine-direct-helper/
```

## Was die Ordner bedeuten

`qairt/2.42.0.251225/` ist die Qualcomm AI Runtime. Sie enthält die QNN- und
HTP-Bibliotheken, die das Modell später auf der NPU ausführen.

`ai-engine-direct-helper/` enthält den Python-Zugriff über `qai_appbuilder` und
Qualcomm-Beispiele. Aus diesem Ordner wird lokal ein Wheel gebaut und in die
Safe-Cycle-`.venv` installiert.

Offizielle Radxa-Referenzen:

- QAIRT SDK Installation: <https://docs.radxa.com/en/dragon/q6a/app-dev/npu-dev/qairt-install>
- QAI AppBuilder: <https://docs.radxa.com/en/fogwise/airbox-q900/ai-dev/qai-appbuilder>

Das eigentliche Safe-Cycle-Modell liegt nicht hier, sondern unter:

```text
src/vision/models/yolov8_det.bin
```

## NPU-Umgebung laden

Vor jedem Start des Vision-Moduls muss die aktuelle Shell die Qualcomm-Variablen
bekommen:

```bash
source ./start_npu.sh
```

Das Script setzt unter anderem:

```text
QNN_SDK_ROOT
PRODUCT_SOC
DSP_ARCH
ADSP_LIBRARY_PATH
LD_LIBRARY_PATH
```

Ein normaler Aufruf mit `bash start_npu.sh` reicht nicht aus, weil die Variablen
dann nur in einem Unterprozess gesetzt werden.

## Wo die vollständigen Startschritte stehen

Die konkrete Anleitung für Kamera, `.venv`, AppBuilder-Wheel, NPU-Test und
MQTT-Start steht hier:

```text
hardware_docs/RADXA_SOFTWARE_DEPENDENCIES.md
```

Wenn später ein gemeinsames `start.sh` für MQTT, Sensoren und Vision entsteht,
sollte es zuerst `source ./start_npu.sh` ausführen. Alle danach gestarteten
Prozesse erben dann die NPU-Variablen.
