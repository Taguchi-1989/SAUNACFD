"""Process raw sensor CSV to validation-compatible format."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from daq.converter import celsius_to_kelvin


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
    with open(meta_yaml, encoding="utf-8") as f:
        metadata = yaml.safe_load(f)

    if not isinstance(metadata, dict):
        raise ValueError(f"Session metadata must be a mapping: {meta_yaml}")

    probe_position = metadata.get("probe_position")
    if isinstance(probe_position, dict):
        probe_name = probe_position.get("name")
        calibration = metadata.get("calibration", {})
        if calibration is None:
            calibration = {}
        if not isinstance(calibration, dict):
            raise ValueError("session metadata 'calibration' must be a mapping")
        offset = calibration.get(
            "temperature_offset_c", metadata.get("calibration_offset_c", 0.0)
        )
    else:
        sensors = metadata.get("sensors")
        if not isinstance(sensors, list) or len(sensors) != 1:
            raise ValueError(
                "session metadata must define probe_position.name or exactly one sensor"
            )
        sensor: Any = sensors[0]
        if not isinstance(sensor, dict):
            raise ValueError("session metadata sensor must be a mapping")
        probe_name = sensor.get("position")
        offset = sensor.get("calibration_offset_c", 0.0)

    if not isinstance(probe_name, str) or not probe_name.strip():
        raise ValueError("session metadata must define a non-empty probe_position.name")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)):
        raise ValueError("session metadata temperature offset must be numeric")

    return probe_name.strip(), float(offset)


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
    temperature_offset_c = 0.0
    if meta_yaml is not None:
        metadata_probe_name, temperature_offset_c = load_processing_metadata(meta_yaml)
        if probe_name is None:
            probe_name = metadata_probe_name
    if probe_name is None:
        probe_name = "lower_bench"

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
