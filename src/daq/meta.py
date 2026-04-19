"""Session metadata generation for DAQ measurements."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def generate_meta(
    session_id: str,
    sensor_type: str = "DHT22",
    probe_name: str = "lower_bench",
    probe_x: float = 1.5,
    probe_y: float = 0.8,
    probe_z: float = 1.25,
    cable_length_m: float = 0.3,
    sensor_id: str = "DHT22-001",
    atmospheric_pressure_pa: float = 101325.0,
    steady_state_reached_s: float | None = None,
    calibration: dict | None = None,
    notes: str = "",
) -> dict:
    """Generate session metadata dictionary.

    Args:
        session_id: Unique session identifier (e.g. "001").
        sensor_type: Sensor model name.
        probe_name: CFD probe name this sensor corresponds to.
        probe_x: Probe x-coordinate [m].
        probe_y: Probe y-coordinate [m] (height).
        probe_z: Probe z-coordinate [m].
        cable_length_m: Cable extension length [m].
        sensor_id: Individual sensor identifier.
        atmospheric_pressure_pa: Atmospheric pressure [Pa].
        steady_state_reached_s: Time when steady state was detected [s].
        calibration: Calibration data dict.
        notes: Free-text notes.

    Returns:
        Metadata dictionary ready for YAML serialization.
    """
    now = datetime.now(tz=timezone.utc)
    meta: dict = {
        "session_id": session_id,
        "date": now.strftime("%Y-%m-%d"),
        "start_time_utc": now.isoformat(),
        "sensor_type": sensor_type,
        "sensor_id": sensor_id,
        "cable_length_m": cable_length_m,
        "probe_position": {
            "name": probe_name,
            "x": probe_x,
            "y": probe_y,
            "z": probe_z,
        },
        "atmospheric_pressure_pa": atmospheric_pressure_pa,
    }
    if steady_state_reached_s is not None:
        meta["steady_state_reached_s"] = steady_state_reached_s
    if calibration:
        meta["calibration"] = calibration
    meta["notes"] = notes
    return meta


def save_meta(meta: dict, output_path: Path) -> Path:
    """Save metadata dictionary to YAML file.

    Args:
        meta: Metadata dictionary.
        output_path: Path for output YAML file.

    Returns:
        Path to the written file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return output_path
