"""Tests für die Prozessverwaltung des Safe-Cycle-Startskripts."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = PROJECT_ROOT / "run_safe_cycle.sh"


def wait_for_process_ids(pid_file: Path, expected_count: int) -> list[int]:
    """Wartet kurz, bis alle Testprozesse ihre PID eingetragen haben."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pid_file.exists():
            process_ids = [int(line) for line in pid_file.read_text().splitlines()]
            if len(process_ids) == expected_count:
                return process_ids
        time.sleep(0.05)
    raise AssertionError("Die Sensor-Testprozesse wurden nicht vollständig gestartet.")


@pytest.mark.parametrize("control_message", ["stop\n", None], ids=["stop-command", "closed-control-pipe"])
def test_sensor_supervisor_stops_all_sensor_processes(
    tmp_path: Path,
    control_message: str | None,
) -> None:
    """Beendet alle Sensoren per Stoppbefehl oder geschlossener Steuerleitung."""
    project_root = tmp_path / "safe-cycle"
    python_path = project_root / ".venv" / "bin" / "python"
    pid_file = project_root / "sensor-pids.txt"
    stop_file = project_root / "stopped-pids.txt"
    project_root.mkdir()
    python_path.parent.mkdir(parents=True)
    shutil.copy2(START_SCRIPT, project_root / START_SCRIPT.name)
    python_path.write_text(
        "#!/usr/bin/env bash\n"
        "trap 'printf \"%s\\n\" \"$$\" >> \"$STOP_FILE\"; exit 0' INT TERM\n"
        "printf '%s\\n' \"$$\" >> \"$PID_FILE\"\n"
        "while true; do sleep 0.05; done\n"
    )
    python_path.chmod(0o755)

    environment = os.environ.copy()
    environment["PID_FILE"] = str(pid_file)
    environment["STOP_FILE"] = str(stop_file)
    process = subprocess.Popen(
        ["bash", str(project_root / START_SCRIPT.name), "--sensor-supervisor"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=environment,
    )

    try:
        process_ids = wait_for_process_ids(pid_file, expected_count=4)
        assert process.stdin is not None
        if control_message is not None:
            process.stdin.write(control_message)
            process.stdin.flush()
        process.stdin.close()
        return_code = process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert return_code == 0
    stopped_process_ids = {int(line) for line in stop_file.read_text().splitlines()}
    assert stopped_process_ids == set(process_ids)
