# Qualcomm-Dateien für die NPU

Dieser Ordner ist für lokale Qualcomm-Dateien gedacht, die für die NPU auf dem
Radxa Dragon Q6A gebraucht werden.

## Was hier liegen muss

Für die aktuelle YOLOv8-NPU-Integration werden zwei Bestandteile gebraucht:

1. `qairt/2.42.0.251225`

   Das ist die Qualcomm AI Runtime. Sie enthält die QNN-Bibliotheken, die
   HTP-Bibliotheken für die NPU und das Script `bin/envsetup.sh`. Ohne diese
   Runtime kann Python später kein Modell auf der NPU ausführen.

2. `ai-engine-direct-helper`

   Dieser Helper enthält den Python-Zugriff über `qai_appbuilder`, Beispiele
   von Qualcomm und aktuell das getestete YOLOv8-Beispielmodell. Das einfache
   Beispielscript wurde nur benutzt, um zu prüfen, ob die NPU grundsätzlich
   funktioniert. Die spätere Safe-Cycle-Erkennung soll in `src/vision/vision.py`
   integriert werden.

Die erwartete lokale Struktur sieht so aus:

```text
Qualcomm/
├── README.md
├── .gitignore
├── qairt/
│   └── 2.42.0.251225/
└── ai-engine-direct-helper/
```

## NPU-Umgebung laden

Das Script im Projektstamm setzt nur die nötigen Umgebungsvariablen. Es startet
keine Bilderkennung und verarbeitet keine Bilder.

Wichtig: Das Script muss mit `source` geladen werden:

```bash
source ./start_npu.sh
```

Ein normaler Aufruf wie `bash start_npu.sh` reicht nicht aus. Dann würden die
Variablen nur in einem Unterprozess gesetzt und wären danach wieder weg.

Nach dem Laden sind unter anderem diese Variablen gesetzt:

```bash
QNN_SDK_ROOT
PRODUCT_SOC
DSP_ARCH
ADSP_LIBRARY_PATH
LD_LIBRARY_PATH
```

Diese Variablen werden später von `src/vision/vision.py` benötigt, damit die
QNN- und HTP-Bibliotheken gefunden werden.


## Spätere Orchestrierung

Wenn später ein gemeinsames `start.sh` für MQTT, Sensoren, Vision und weitere
Module entsteht, sollte es zuerst die NPU-Umgebung laden:

```bash
source ./start_npu.sh
```

Alle danach gestarteten Prozesse erben diese Variablen automatisch.