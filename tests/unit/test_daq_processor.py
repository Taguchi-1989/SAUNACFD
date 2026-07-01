"""Tests for daq.processor raw CSV processing and steady-state detection."""

from __future__ import annotations

import numpy as np
import pytest

from daq.processor import detect_steady_state, process_raw


class TestProcessRaw:
    def test_creates_validation_csv(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,25.0,ok\n"
            "2.0,68.1,10.1,25.1,ok\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        result = process_raw(raw, out, probe_name="lower_bench")

        assert result == out
        assert out.exists()
        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        assert "lower_bench" in data.dtype.names
        assert "time" in data.dtype.names

    def test_converts_celsius_to_kelvin(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,25.0,ok\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        process_raw(raw, out, probe_name="lower_bench")
        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        data = np.atleast_1d(data)
        # Index explicitly: NumPy 2.x no longer converts size-1 1-D arrays
        # to Python scalars via float().
        assert abs(float(data["lower_bench"][0]) - 341.15) < 0.01

    def test_filters_shutdown_rows(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,25.0,ok\n"
            "2.0,68.1,10.1,25.1,ok\n"
            "4.0,68.2,10.2,62.0,shutdown\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        process_raw(raw, out)
        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        data = np.atleast_1d(data)
        assert len(data) == 2  # shutdown row excluded

    def test_keeps_warn_rows(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,25.0,ok\n"
            "2.0,68.1,10.1,52.0,warn\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        process_raw(raw, out)
        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        data = np.atleast_1d(data)
        assert len(data) == 2  # warn rows are kept

    def test_custom_probe_name(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,30.0,50.0,25.0,ok\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        process_raw(raw, out, probe_name="floor_level")
        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        assert "floor_level" in data.dtype.names

    def test_all_shutdown_writes_header_only(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,65.0,shutdown\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"
        process_raw(raw, out)
        content = out.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "lower_bench" in lines[0]

    def test_creates_parent_directories(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,68.0,10.0,25.0,ok\n",
            encoding="utf-8",
        )
        out = tmp_path / "sub" / "dir" / "processed.csv"
        process_raw(raw, out)
        assert out.exists()


class TestDetectSteadyState:
    def test_constant_temperature(self) -> None:
        times = np.arange(0, 120, 2.0)
        temps = np.full_like(times, 68.0)
        t_ss = detect_steady_state(times, temps)
        assert t_ss is not None
        assert t_ss <= 60.0

    def test_rising_temperature_detects_late(self) -> None:
        times = np.arange(0, 600, 2.0)
        # Exponential rise: τ=60s, settles around 5τ=300s
        temps = 20.0 + 48.0 * (1 - np.exp(-times / 60.0))
        t_ss = detect_steady_state(times, temps)
        assert t_ss is not None
        assert t_ss > 120.0  # should not detect early

    def test_never_stabilizes(self) -> None:
        times = np.arange(0, 120, 2.0)
        temps = times * 0.5  # constant slope 0.5°C/s = 30°C/min
        t_ss = detect_steady_state(times, temps)
        assert t_ss is None

    def test_short_data_returns_none(self) -> None:
        times = np.array([0.0])
        temps = np.array([68.0])
        assert detect_steady_state(times, temps) is None

    def test_empty_data_returns_none(self) -> None:
        assert detect_steady_state(np.array([]), np.array([])) is None

    def test_step_change_then_steady(self) -> None:
        # Jump from 20 to 68, then stay constant
        t1 = np.arange(0, 10, 2.0)
        t2 = np.arange(10, 200, 2.0)
        times = np.concatenate([t1, t2])
        temps = np.concatenate([np.linspace(20, 68, len(t1)), np.full(len(t2), 68.0)])
        t_ss = detect_steady_state(times, temps)
        assert t_ss is not None
