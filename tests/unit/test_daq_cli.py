"""Tests for the SaunaFlow DAQ command-line interface."""

from __future__ import annotations

import numpy as np
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
