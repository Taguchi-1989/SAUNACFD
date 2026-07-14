"""Tests for the SaunaFlow DAQ command-line interface."""

from __future__ import annotations

import numpy as np
import yaml
from click.testing import CliRunner

from daq.cli import daq


def test_process_uses_session_metadata(tmp_path: object) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "time_s,temp_c,rh_pct,box_temp_c,status\n"
        "0.0,30.0,50.0,25.0,ok\n",
        encoding="utf-8",
    )
    meta = tmp_path / "meta.yaml"
    meta.write_text(
        "probe_position:\n"
        "  name: floor_level\n"
        "calibration:\n"
        "  temperature_offset_c: 0.5\n",
        encoding="utf-8",
    )
    output = tmp_path / "processed.csv"

    result = CliRunner().invoke(
        daq,
        ["process", str(raw), "--meta", str(meta), "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    data = np.atleast_1d(
        np.genfromtxt(output, delimiter=",", names=True, encoding="utf-8")
    )
    assert "floor_level" in data.dtype.names
    assert float(data["floor_level"][0]) == 303.65


def test_process_reports_steady_state_per_sensor(tmp_path: object) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "time_s,sensor_id,temp_c,rh_pct,box_temp_c,status\n"
        "0.0,lower,30.0,50.0,25.0,ok\n"
        "0.0,upper,70.0,20.0,25.0,ok\n",
        encoding="utf-8",
    )
    meta = tmp_path / "meta.yaml"
    meta.write_text(
        "sensors:\n"
        "  - id: lower\n"
        "    position: lower_bench\n"
        "  - id: upper\n"
        "    position: upper_bench\n",
        encoding="utf-8",
    )
    output = tmp_path / "processed.csv"

    result = CliRunner().invoke(
        daq,
        ["process", str(raw), "--meta", str(meta), "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert "Steady state for sensor lower not detected" in result.output
    assert "Steady state for sensor upper not detected" in result.output


def test_steady_state_command_supports_custom_window(tmp_path: object) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "time_s,temp_c,rh_pct,box_temp_c,status\n"
        "0.0,68.0,10.0,25.0,ok\n"
        "10.0,68.0,10.0,25.0,ok\n"
        "20.0,68.0,10.0,25.0,ok\n"
        "30.0,68.0,10.0,25.0,ok\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        daq,
        ["steady-state", str(raw), "--window", "30"],
    )

    assert result.exit_code == 0, result.output
    assert "Steady state detected at t=0.0s" in result.output


def test_validate_meta_command_accepts_v1_contract(tmp_path: object) -> None:
    meta = tmp_path / "session_meta.yaml"
    meta.write_text(
        "schema_version: '1.0'\n"
        "session:\n"
        "  id: session-001\n"
        "  started_at: '2026-07-14T14:00:00+09:00'\n"
        "  sampling_interval_s: 2\n"
        "environment: {atmospheric_pressure_pa: 100800}\n"
        "sensors:\n"
        "  - id: SHT45-LOWER\n"
        "    type: SHT45\n"
        "    measures: [temperature]\n"
        "    position: {name: lower_bench}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(daq, ["validate-meta", str(meta)])

    assert result.exit_code == 0, result.output
    assert "schema v1.0" in result.output


def test_meta_command_writes_canonical_v1(tmp_path: object) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "time_s,temp_c,rh_pct,box_temp_c,status\n"
        "0.0,68.0,10.0,25.0,ok\n",
        encoding="utf-8",
    )
    output = tmp_path / "session_meta.yaml"

    result = CliRunner().invoke(
        daq,
        [
            "meta",
            str(raw),
            "--session-id",
            "session-001",
            "--sensor-id",
            "SHT45-LOWER",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    loaded = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "1.0"
    assert loaded["session"]["id"] == "session-001"
