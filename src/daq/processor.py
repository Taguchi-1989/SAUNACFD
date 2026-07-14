"""Process raw sensor CSV to validation-compatible format."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from daq.converter import celsius_to_kelvin
from daq.meta import validate_session_meta


@dataclass(frozen=True)
class SensorProcessingMetadata:
    """Processing settings for one physical sensor."""

    sensor_id: str | None
    probe_name: str
    temperature_offset_c: float = 0.0


def load_sensor_processing_metadata(meta_yaml: Path) -> list[SensorProcessingMetadata]:
    """Load processing settings for all sensors in a session metadata file."""
    with open(meta_yaml, encoding="utf-8") as f:
        metadata = yaml.safe_load(f)

    if not isinstance(metadata, dict):
        raise ValueError(f"Session metadata must be a mapping: {meta_yaml}")

    schema_version = metadata.get("schema_version")
    if schema_version is not None:
        if schema_version != "1.0":
            raise ValueError(f"unsupported session metadata schema_version: {schema_version}")
        errors = validate_session_meta(metadata)
        if errors:
            raise ValueError("invalid session metadata: " + "; ".join(errors))

    probe_position = metadata.get("probe_position")
    if isinstance(probe_position, dict):
        calibration = metadata.get("calibration", {})
        if calibration is None:
            calibration = {}
        if not isinstance(calibration, dict):
            raise ValueError("session metadata 'calibration' must be a mapping")
        return [
            _make_sensor_metadata(
                sensor_id=metadata.get("sensor_id"),
                probe_name=probe_position.get("name"),
                offset=calibration.get(
                    "temperature_offset_c", metadata.get("calibration_offset_c", 0.0)
                ),
            )
        ]

    sensors = metadata.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        raise ValueError("session metadata must define probe_position.name or sensors")

    result: list[SensorProcessingMetadata] = []
    for sensor in sensors:
        if not isinstance(sensor, dict):
            raise ValueError("session metadata sensor must be a mapping")
        position = sensor.get("position")
        probe_name = position.get("name") if isinstance(position, dict) else position
        calibration = sensor.get("calibration", {})
        if calibration is None:
            calibration = {}
        if not isinstance(calibration, dict):
            raise ValueError("session metadata sensor calibration must be a mapping")
        result.append(
            _make_sensor_metadata(
                sensor_id=sensor.get("id"),
                probe_name=probe_name,
                offset=calibration.get(
                    "temperature_offset_c", sensor.get("calibration_offset_c", 0.0)
                ),
            )
        )

    if len(result) > 1 and any(sensor.sensor_id is None for sensor in result):
        raise ValueError("each sensor in multi-sensor metadata must define an id")
    if len({sensor.sensor_id for sensor in result}) != len(result):
        raise ValueError("sensor ids in session metadata must be unique")
    if len({sensor.probe_name for sensor in result}) != len(result):
        raise ValueError("probe positions in session metadata must be unique")
    return result


def _make_sensor_metadata(
    sensor_id: object,
    probe_name: object,
    offset: object,
) -> SensorProcessingMetadata:
    if sensor_id is not None and (not isinstance(sensor_id, str) or not sensor_id.strip()):
        raise ValueError("session metadata sensor id must be a non-empty string")
    if not isinstance(probe_name, str) or not probe_name.strip():
        raise ValueError("session metadata must define a non-empty probe_position.name")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)):
        raise ValueError("session metadata temperature offset must be numeric")
    return SensorProcessingMetadata(
        sensor_id=sensor_id.strip() if isinstance(sensor_id, str) else None,
        probe_name=probe_name.strip(),
        temperature_offset_c=float(offset),
    )


def load_processing_metadata(meta_yaml: Path) -> tuple[str, float]:
    """Load the probe name and temperature correction from session metadata.

    Both the metadata emitted by :mod:`daq.meta` and the single-sensor form in
    ``docs/measurement_implementation_plan.md`` are accepted. The correction
    is added to the measured Celsius value before conversion to Kelvin.

    Args:
        meta_yaml: Path to a session metadata YAML file.

    Returns:
        A ``(probe_name, temperature_offset_c)`` tuple.

    Raises:
        ValueError: If the YAML is not a mapping or does not identify exactly
            one usable probe.
    """
    sensors = load_sensor_processing_metadata(meta_yaml)
    if len(sensors) != 1:
        raise ValueError("session metadata must define exactly one sensor for single processing")
    sensor = sensors[0]
    return sensor.probe_name, sensor.temperature_offset_c


def process_raw(
    raw_csv: Path,
    output_csv: Path,
    probe_name: str | None = None,
    meta_yaml: Path | None = None,
) -> Path:
    """Convert raw sensor CSV to validation-compatible CSV.

    Reads raw CSV (time_s, temp_c, rh_pct, box_temp_c, status),
    filters to status=="ok" or "warn" rows, converts °C→K,
    and writes validation-compatible CSV with columns: time, <probe_name>.

    Args:
        raw_csv: Path to raw sensor CSV.
        output_csv: Path for output validation CSV.
        probe_name: Column name for temperature (must match CFD probe name).
            Overrides the name in ``meta_yaml`` when both are supplied.
        meta_yaml: Optional session metadata. Its probe name is used when
            ``probe_name`` is omitted, and its calibration offset is applied.

    Returns:
        Path to the written output CSV.
    """
    processing_sensors: list[SensorProcessingMetadata] = []
    temperature_offset_c = 0.0
    if meta_yaml is not None:
        processing_sensors = load_sensor_processing_metadata(meta_yaml)
        if len(processing_sensors) == 1:
            temperature_offset_c = processing_sensors[0].temperature_offset_c
            if probe_name is None:
                probe_name = processing_sensors[0].probe_name
    # Read raw CSV; status is a string column
    data = np.genfromtxt(
        raw_csv,
        delimiter=",",
        names=True,
        dtype=None,
        encoding="utf-8",
    )
    data = np.atleast_1d(data)

    # Filter: keep "ok" and "warn" rows, exclude "shutdown"
    mask = np.array([s in ("ok", "warn") for s in data["status"]])
    filtered = data[mask]

    field_names = data.dtype.names or ()
    raw_sensor_ids: set[str] = set()
    if "sensor_id" in field_names:
        raw_sensor_ids = {str(value).strip() for value in data["sensor_id"] if str(value).strip()}

    if len(raw_sensor_ids) > 1 and meta_yaml is None:
        raise ValueError("multi-sensor raw data requires session metadata")
    if len(processing_sensors) > 1 and not raw_sensor_ids:
        raise ValueError("multi-sensor metadata requires sensor_id values in raw data")
    if raw_sensor_ids and processing_sensors and (
        len(raw_sensor_ids) > 1 or len(processing_sensors) > 1
    ):
        if probe_name is not None and len(processing_sensors) > 1:
            raise ValueError("probe_name cannot override multi-sensor metadata")
        return _write_multi_sensor_csv(
            filtered,
            output_csv,
            processing_sensors,
            raw_sensor_ids,
        )
    if raw_sensor_ids and processing_sensors:
        expected_sensor_id = processing_sensors[0].sensor_id
        if expected_sensor_id is not None and raw_sensor_ids != {expected_sensor_id}:
            raw_sensor_id = next(iter(raw_sensor_ids))
            raise ValueError(
                f"raw sensor id {raw_sensor_id} does not match metadata id {expected_sensor_id}"
            )

    if probe_name is None:
        probe_name = "lower_bench"

    if len(filtered) == 0:
        # Write header-only file
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8") as f:
            f.write(f"time,{probe_name}\n")
        return output_csv

    times = np.asarray(filtered["time_s"], dtype=float)
    temps_c = np.asarray(filtered["temp_c"], dtype=float) + temperature_offset_c
    temps_k = np.array([celsius_to_kelvin(t) for t in temps_c])

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8") as f:
        f.write(f"time,{probe_name}\n")
        for t, v in zip(times, temps_k, strict=True):
            f.write(f"{t:.1f},{v:.2f}\n")

    return output_csv


def _write_multi_sensor_csv(
    filtered: np.ndarray,
    output_csv: Path,
    sensors: list[SensorProcessingMetadata],
    raw_sensor_ids: set[str],
) -> Path:
    """Pivot sensor-id rows into validation-compatible probe columns."""
    by_id = {sensor.sensor_id: sensor for sensor in sensors if sensor.sensor_id is not None}
    unknown_ids = raw_sensor_ids - by_id.keys()
    if unknown_ids:
        unknown = ", ".join(sorted(unknown_ids))
        raise ValueError(f"raw sensor ids missing from session metadata: {unknown}")

    active_sensors = [sensor for sensor in sensors if sensor.sensor_id in raw_sensor_ids]
    rows: dict[float, dict[str, float]] = {}
    for row in filtered:
        sensor_id = str(row["sensor_id"]).strip()
        if not sensor_id:
            continue
        sensor = by_id[sensor_id]
        time_s = float(row["time_s"])
        corrected_c = float(row["temp_c"]) + sensor.temperature_offset_c
        rows.setdefault(time_s, {})[sensor.probe_name] = celsius_to_kelvin(corrected_c)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["time", *(sensor.probe_name for sensor in active_sensors)]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for time_s in sorted(rows):
            values: dict[str, str] = {"time": f"{time_s:.1f}"}
            values.update({name: f"{value:.2f}" for name, value in rows[time_s].items()})
            writer.writerow(values)

    return output_csv


def detect_steady_state(
    times: np.ndarray,
    temps: np.ndarray,
    window_s: float = 60.0,
    threshold_c_per_min: float = 0.1,
) -> float | None:
    """Detect when temperature reaches steady state.

    Scans the time series with a sliding window. Returns the earliest
    time at which the absolute temperature change rate drops below
    the threshold for the entire window.

    Args:
        times: Array of time values [s].
        temps: Array of temperature values [°C or K].
        window_s: Window size in seconds.
        threshold_c_per_min: Max allowed |dT/dt| in °C/min (or K/min).

    Returns:
        Time [s] at which steady state is first detected, or None if
        the temperature never stabilizes within the data.
    """
    if len(times) < 2:
        return None

    threshold_per_s = threshold_c_per_min / 60.0

    for i in range(len(times)):
        t_start = times[i]
        t_end = t_start + window_s

        # Find all points within the window
        win_mask = (times >= t_start) & (times <= t_end)
        win_times = times[win_mask]
        win_temps = temps[win_mask]

        if len(win_times) < 2:
            continue

        # Check if window spans at least window_s
        if (win_times[-1] - win_times[0]) < window_s * 0.9:
            continue

        # Max absolute rate within the window
        dt = np.diff(win_times)
        dtemp = np.diff(win_temps)
        # Avoid division by zero
        nonzero = dt > 0
        if not np.any(nonzero):
            continue
        rates = np.abs(dtemp[nonzero] / dt[nonzero])

        if np.max(rates) <= threshold_per_s:
            return float(t_start)

    return None
