#!/usr/bin/env bash

set -Eeuo pipefail


set -m

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
PYTHONPATH_VALUE="$PROJECT_ROOT/src"
MODEL_PATH="$PROJECT_ROOT/src/vision/models/yolov8_det.bin"
SHUTDOWN_TIMEOUT_SECONDS=10

declare -a PROCESS_NAMES=()
declare -a PROCESS_PIDS=()
SHUTTING_DOWN=false

start_process() {
    local name="$1"
    local module="$2"
    local needs_sudo="$3"
    local pid

    if [[ "$needs_sudo" == "true" ]]; then
        sudo env PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON" -m "$module" &
    else
        env PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON" -m "$module" &
    fi
    pid=$!

    PROCESS_NAMES+=("$name")
    PROCESS_PIDS+=("$pid")
    echo "Gestartet: $name (PID $pid)"
}

shutdown_processes() {
    local exit_code="$1"
    local deadline
    local has_running_processes
    local index
    local pid

    if [[ "$SHUTTING_DOWN" == "true" ]]; then
        return
    fi
    SHUTTING_DOWN=true
    trap - EXIT INT TERM

    echo
    echo "Beende Safe Cycle ..."
    for ((index=${#PROCESS_PIDS[@]} - 1; index >= 0; index--)); do
        pid="${PROCESS_PIDS[$index]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stoppe ${PROCESS_NAMES[$index]} (PID $pid)"
            kill -INT "$pid" 2>/dev/null || true
        fi
    done

    deadline=$((SECONDS + SHUTDOWN_TIMEOUT_SECONDS))
    while ((SECONDS < deadline)); do
        has_running_processes=false
        for pid in "${PROCESS_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                has_running_processes=true
                break
            fi
        done
        if [[ "$has_running_processes" == "false" ]]; then
            break
        fi
        sleep 0.1
    done

    for ((index=${#PROCESS_PIDS[@]} - 1; index >= 0; index--)); do
        pid="${PROCESS_PIDS[$index]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo "Erzwinge Ende von ${PROCESS_NAMES[$index]} (PID $pid)" >&2
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    for pid in "${PROCESS_PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    echo "Safe Cycle wurde beendet."
    exit "$exit_code"
}

handle_exit() {
    local exit_code="$?"

    if [[ "$SHUTTING_DOWN" == "false" && ${#PROCESS_PIDS[@]} -gt 0 ]]; then
        shutdown_processes "$exit_code"
    fi
}

trap handle_exit EXIT
trap 'shutdown_processes 130' INT
trap 'shutdown_processes 143' TERM

if [[ ! -x "$PYTHON" ]]; then
    echo "Fehler: Python-Umgebung wurde nicht gefunden: $PYTHON" >&2
    exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "Fehler: NPU-Modell wurde nicht gefunden: $MODEL_PATH" >&2
    exit 1
fi

if ! env PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON" -c '
import cv2

gstreamer_lines = [line.strip() for line in cv2.getBuildInformation().splitlines() if "GStreamer" in line]
print(f"OpenCV: {cv2.__file__}")
print(f"OpenCV-Build: {gstreamer_lines[0] if gstreamer_lines else "GStreamer-Angabe fehlt"}")
raise SystemExit(0 if any("YES" in line for line in gstreamer_lines) else 1)
'
then
    echo "Fehler: Das von der .venv geladene OpenCV unterstützt GStreamer nicht." >&2
    echo "Erstelle die Umgebung auf dem Radxa mit --system-site-packages und ohne opencv-python neu." >&2
    exit 1
fi

if ! env PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON" -c \
    'import socket; from shared.config import MQTT_BROKER_IP, MQTT_BROKER_PORT; connection = socket.create_connection((MQTT_BROKER_IP, MQTT_BROKER_PORT), timeout=2); connection.close()'
then
    echo "Fehler: MQTT-Broker unter 127.0.0.1:1883 ist nicht erreichbar." >&2
    echo "Starte ihn zum Beispiel mit: docker compose up -d mqtt" >&2
    exit 1
fi

if ! sudo -v; then
    echo "Fehler: Die Sensoren benötigen sudo-Berechtigung für den Hardwarezugriff." >&2
    exit 1
fi

source "$PROJECT_ROOT/src/vision/start_npu.sh"

echo "Starte Safe Cycle ..."
start_process "Core" "core" false
start_process "GPS" "sensors.gps_node" true
start_process "Radar" "sensors.radar_node" true
start_process "ToF links" "sensors.tof_node_left" true
start_process "ToF rechts" "sensors.tof_node_right" true
start_process "Vision/NPU" "vision" false

echo "Safe Cycle läuft. Mit Ctrl+C werden alle Module sauber beendet."

set +e
wait -n "${PROCESS_PIDS[@]}"
PROCESS_EXIT_CODE=$?
set -e

if [[ "$PROCESS_EXIT_CODE" -eq 0 ]]; then
    PROCESS_EXIT_CODE=1
fi
echo "Ein Safe-Cycle-Modul wurde unerwartet beendet." >&2
shutdown_processes "$PROCESS_EXIT_CODE"
