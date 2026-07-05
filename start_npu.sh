#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Fehler: Dieses Script muss mit 'source' geladen werden." >&2
    echo "Beispiel: source ./start_npu.sh" >&2
    exit 1
fi

SAFE_CYCLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

export QAIRT_VERSION="${QAIRT_VERSION:-2.42.0.251225}"
export PRODUCT_SOC="${PRODUCT_SOC:-6490}"
export DSP_ARCH="${DSP_ARCH:-68}"

QAIRT_DIR="${QAIRT_DIR:-$SAFE_CYCLE_DIR/Qualcomm/qairt/$QAIRT_VERSION}"
APPBUILDER_DIR="${APPBUILDER_DIR:-$SAFE_CYCLE_DIR/Qualcomm/ai-engine-direct-helper}"

if [[ ! -d "$QAIRT_DIR" ]]; then
    echo "Fehler: QAIRT wurde nicht gefunden:" >&2
    echo "$QAIRT_DIR" >&2
    return 1
fi

if [[ ! -f "$QAIRT_DIR/bin/envsetup.sh" ]]; then
    echo "Fehler: QAIRT envsetup.sh wurde nicht gefunden:" >&2
    echo "$QAIRT_DIR/bin/envsetup.sh" >&2
    return 1
fi

if [[ ! -d "$APPBUILDER_DIR" ]]; then
    echo "Fehler: ai-engine-direct-helper wurde nicht gefunden:" >&2
    echo "$APPBUILDER_DIR" >&2
    return 1
fi

source "$QAIRT_DIR/bin/envsetup.sh"

export ADSP_LIBRARY_PATH="$QNN_SDK_ROOT/lib/hexagon-v${DSP_ARCH}/unsigned"
export LD_LIBRARY_PATH="$QNN_SDK_ROOT/lib/aarch64-oe-linux-gcc11.2:${LD_LIBRARY_PATH:-}"

echo "NPU-Umgebung wurde vorbereitet."
echo "QNN_SDK_ROOT=$QNN_SDK_ROOT"
echo "PRODUCT_SOC=$PRODUCT_SOC"
echo "DSP_ARCH=$DSP_ARCH"
echo "ADSP_LIBRARY_PATH=$ADSP_LIBRARY_PATH"
