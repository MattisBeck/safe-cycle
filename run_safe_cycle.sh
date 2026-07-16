#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
PYTHONPATH_VALUE="$PROJECT_ROOT/src"
MODEL_PATH="$PROJECT_ROOT/src/vision/models/yolov8_det.bin"
SHUTDOWN_TIMEOUT_SECONDS=10
SENSOR_SUPERVISOR_ARGUMENT="--sensor-supervisor"

declare -a PROCESS_NAMES=()
declare -a PROCESS_PIDS=()
SHUTTING_DOWN=false
SENSOR_SUPERVISOR_PID=""
SENSOR_CONTROL_FD=""

start_process() {
    local name="$1"
    local module="$2"
    local pid

    set -m
    env PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON" -m "$module" &
    pid=$!
    set +m

    PROCESS_NAMES+=("$name")
    PROCESS_PIDS+=("$pid")
    echo "Gestartet: $name (PID $pid)"
}

run_sensor_supervisor() {
    local -a sensor_names=("GPS" "Radar" "ToF links" "ToF rechts")
    local -a sensor_modules=(
        "sensors.gps_node"
        "sensors.radar_node"
        "sensors.tof_node_left"
        "sensors.tof_node_right"
    )
    local -a sensor_pids=()
    local control_pid=""
    local finished_pid=""
    local index
    local wait_status

    cleanup_sensor_supervisor() {
        local deadline
        local pid

        trap - EXIT INT TERM

        if [[ -n "$control_pid" ]]; then
            kill -TERM "$control_pid" 2>/dev/null || true
        fi

        for ((index=${#sensor_pids[@]} - 1; index >= 0; index--)); do
            pid="${sensor_pids[$index]}"
            if kill -0 "$pid" 2>/dev/null; then
                echo "Stoppe ${sensor_names[$index]} (PID $pid)"
                kill -INT "$pid" 2>/dev/null || true
            fi
        done

        deadline=$((SECONDS + SHUTDOWN_TIMEOUT_SECONDS))
        while ((SECONDS < deadline)); do
            for pid in "${sensor_pids[@]}"; do
                if kill -0 "$pid" 2>/dev/null; then
                    sleep 0.1
                    continue 2
                fi
            done
            break
        done

        for ((index=${#sensor_pids[@]} - 1; index >= 0; index--)); do
            pid="${sensor_pids[$index]}"
            if kill -0 "$pid" 2>/dev/null; then
                echo "Erzwinge Ende von ${sensor_names[$index]} (PID $pid)" >&2
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done

        sleep 0.2
        for pid in "${sensor_pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null || true
            else
                wait "$pid" 2>/dev/null || true
            fi
        done
    }

    trap cleanup_sensor_supervisor EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    set -m
    for index in "${!sensor_modules[@]}"; do
        env PYTHONPATH="$PYTHONPATH_VALUE" \
            "$PYTHON" -m "${sensor_modules[$index]}" &
        sensor_pids+=("$!")
        echo "Gestartet: ${sensor_names[$index]} (PID $!)"
    done

    # Das Ende der Steuerleitung stoppt die Sensoren auch bei einem harten
    # Abbruch des unprivilegierten Hauptskripts.
    IFS= read -r _ &
    control_pid=$!

    set +e
    wait -n -p finished_pid "$control_pid" "${sensor_pids[@]}"
    wait_status=$?
    set -e

    if [[ "$finished_pid" == "$control_pid" ]]; then
        exit 0
    fi

    echo "Das Sensormodul mit PID $finished_pid wurde unerwartet beendet." >&2
    if [[ "$wait_status" -eq 0 ]]; then
        exit 1
    fi
    exit "$wait_status"
}

start_sensor_supervisor() {
    local sensor_output_fd

    coproc SAFE_CYCLE_SENSORS {
        sudo -n env \
            PYTHONPATH="$PYTHONPATH_VALUE" \
            bash "$PROJECT_ROOT/run_safe_cycle.sh" \
            "$SENSOR_SUPERVISOR_ARGUMENT" >&2
    }

    SENSOR_SUPERVISOR_PID="$SAFE_CYCLE_SENSORS_PID"
    SENSOR_CONTROL_FD="${SAFE_CYCLE_SENSORS[1]}"
    sensor_output_fd="${SAFE_CYCLE_SENSORS[0]}"
    exec {sensor_output_fd}<&-
}

stop_sensor_supervisor() {
    if [[ -n "$SENSOR_CONTROL_FD" ]]; then
        printf 'stop\n' >&"$SENSOR_CONTROL_FD" 2>/dev/null || true
        exec {SENSOR_CONTROL_FD}>&-
    fi
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
    stop_sensor_supervisor
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
        for pid in "${PROCESS_PIDS[@]}" "$SENSOR_SUPERVISOR_PID"; do
            if [[ -z "$pid" ]]; then
                continue
            fi
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
    if [[ -n "$SENSOR_SUPERVISOR_PID" ]]; then
        wait "$SENSOR_SUPERVISOR_PID" 2>/dev/null || true
    fi

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

if [[ "${1:-}" == "$SENSOR_SUPERVISOR_ARGUMENT" ]]; then
    run_sensor_supervisor
fi

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
start_process "Core" "core"
start_sensor_supervisor
start_process "Vision/NPU" "vision"

echo "Safe Cycle läuft. Mit Ctrl+C werden alle Module sauber beendet."

set +e
wait -n "${PROCESS_PIDS[@]}" "$SENSOR_SUPERVISOR_PID"
PROCESS_EXIT_CODE=$?
set -e

if [[ "$PROCESS_EXIT_CODE" -eq 0 ]]; then
    PROCESS_EXIT_CODE=1
fi
echo "Ein Safe-Cycle-Modul wurde unerwartet beendet." >&2
shutdown_processes "$PROCESS_EXIT_CODE"
