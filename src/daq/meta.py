"""Session metadata generation for DAQ measurements."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema
import yaml

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "configs"
    / "schemas"
    / "session_meta_schema.json"
)


def validate_session_meta(data: dict) -> list[str]:
    """Validate canonical session metadata against the v1 JSON Schema."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)
    return errors


def load_and_validate_session_meta(path: Path) -> tuple[dict, list[str]]:
    """Load a canonical session metadata YAML file and return data and errors."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}, ["session metadata must be a mapping"]
    return data, validate_session_meta(data)


def generate_session_meta_v1(
    session_id: str,
    sensor_type: str = "DHT22",
    probe_name: str = "lower_bench",
    probe_x: float = 1.5,
    probe_y: float = 0.8,
    probe_z: float = 1.25,
    cable_length_m: float = 0.3,
    sensor_id: str = "DHT22-001",
    atmospheric_pressure_pa: float = 101325.0,
    sampling_interval_s: float = 2.0,
    measures: list[str] | None = None,
    steady_state_reached_s: float | None = None,
    calibration: dict | None = None,
    notes: str = "",
) -> dict:
    """Generate canonical v1 metadata for a single-sensor DAQ session."""
    session: dict = {
        "id": session_id,
        "started_at": datetime.now(tz=ZoneInfo("Asia/Tokyo")).isoformat(),
        "timezone": "Asia/Tokyo",
        "sampling_interval_s": sampling_interval_s,
        "notes": notes,
    }
    if steady_state_reached_s is not None:
        session["steady_state_reached_s"] = steady_state_reached_s

    sensor: dict = {
        "id": sensor_id,
        "type": sensor_type,
        "measures": measures or ["temperature", "relative_humidity"],
        "position": {
            "name": probe_name,
            "x_m": probe_x,
            "y_m": probe_y,
            "z_m": probe_z,
        },
        "cable_length_m": cable_length_m,
    }
    if calibration:
        sensor["calibration"] = calibration

    return {
        "schema_version": "1.0",
        "session": session,
        "environment": {"atmospheric_pressure_pa": atmospheric_pressure_pa},
        "sensors": [sensor],
        "events": [],
        "processing": {
            "steady_state_window_s": 60.0,
            "steady_state_threshold_c_per_min": 0.1,
            "missing_value_policy": "preserve",
        },
    }


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
    now = datetime.now(tz=UTC)
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
