"""Schreibt abgeschlossene Fahrten in das Dashboard-JSON-Format."""

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import TypeAlias

from shared import RideData

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)


def resolve_ride_output(
    ride_data: RideData,
    output_directory: Path,
) -> tuple[RideData, Path]:
    """Bestimmt eine freie Ride-ID und den zugehörigen JSON-Pfad.

    :param ride_data: Abgeschlossene Fahrt mit der gewünschten Basis-ID.
    :param output_directory: Verzeichnis für abgeschlossene Fahrten.
    :return: Kopie der Fahrt mit eindeutiger ID und passender Zielpfad.
    """
    candidate_ride_id = ride_data.ride_id
    candidate_path = output_directory / f"{candidate_ride_id}.json"
    candidate_lock_path = output_directory / f".{candidate_path.name}.lock"
    suffix = 2

    while candidate_path.exists() or candidate_lock_path.exists():
        candidate_ride_id = f"{ride_data.ride_id}_{suffix}"
        candidate_path = output_directory / f"{candidate_ride_id}.json"
        candidate_lock_path = output_directory / f".{candidate_path.name}.lock"
        suffix += 1

    return replace(ride_data, ride_id=candidate_ride_id), candidate_path


def write_ride_data(ride_data: RideData, output_directory: Path) -> Path:
    """Schreibt eine abgeschlossene Fahrt atomar als JSON-Datei.

    :param ride_data: Vollständige Daten einer abgeschlossenen Fahrt.
    :param output_directory: Verzeichnis für abgeschlossene Fahrten.
    :return: Tatsächlich geschriebener JSON-Pfad.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    resolved_ride_data, output_path, lock_path = _reserve_ride_output(
        ride_data,
        output_directory,
    )
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")

    try:
        json_data = _to_json_value(asdict(resolved_ride_data))
        json_text = (
            json.dumps(json_data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        temporary_path.write_text(json_text, encoding="utf-8")
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        lock_path.unlink(missing_ok=True)

    return output_path


def _reserve_ride_output(
    ride_data: RideData,
    output_directory: Path,
) -> tuple[RideData, Path, Path]:
    """Reserviert eine freie Ride-ID atomar für den aktuellen Writer."""
    suffix = 1

    while True:
        candidate_ride_id = ride_data.ride_id
        if suffix > 1:
            candidate_ride_id = f"{candidate_ride_id}_{suffix}"
        candidate_path = output_directory / f"{candidate_ride_id}.json"
        lock_path = output_directory / f".{candidate_path.name}.lock"

        try:
            file_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            suffix += 1
            continue

        try:
            os.close(file_descriptor)
            if candidate_path.exists():
                lock_path.unlink(missing_ok=True)
                suffix += 1
                continue
        except Exception:
            lock_path.unlink(missing_ok=True)
            raise

        return replace(ride_data, ride_id=candidate_ride_id), candidate_path, lock_path


def _to_json_value(value: object) -> JsonValue:
    """Konvertiert Dataclass-Inhalte in unterstützte JSON-Werte."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        if value.is_absolute():
            raise ValueError("Bildpfade müssen relativ zum Fahrtverzeichnis sein.")
        return value.as_posix()
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    raise TypeError(f"Nicht unterstützter JSON-Wert: {type(value).__name__}")
