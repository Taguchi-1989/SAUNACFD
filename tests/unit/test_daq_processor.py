"""Tests for daq.processor raw CSV processing and steady-state detection."""

from __future__ import annotations

import numpy as np
import pytest

from daq.processor import detect_steady_state, load_processing_metadata, process_raw


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

    def test_uses_probe_name_from_session_metadata(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,30.0,50.0,25.0,ok\n",
            encoding="utf-8",
        )
        meta = tmp_path / "meta.yaml"
        meta.write_text(
            "session_id: '001'\n"
            "probe_position:\n"
            "  name: floor_level\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"

        process_raw(raw, out, meta_yaml=meta)

        data = np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        assert "floor_level" in data.dtype.names

    def test_applies_metadata_temperature_offset(self, tmp_path: object) -> None:
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
            "  temperature_offset_c: -0.4\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"

        process_raw(raw, out, meta_yaml=meta)

        data = np.atleast_1d(
            np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        )
        assert float(data["floor_level"][0]) == pytest.approx(302.75)

    def test_explicit_probe_name_overrides_metadata(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,30.0,50.0,25.0,ok\n",
            encoding="utf-8",
        )
        meta = tmp_path / "meta.yaml"
        meta.write_text("probe_position:\n  name: floor_level\n", encoding="utf-8")
        out = tmp_path / "processed.csv"

        process_raw(raw, out, probe_name="upper_bench", meta_yaml=meta)

        assert out.read_text(encoding="utf-8").startswith("time,upper_bench\n")

    def test_pivots_multiple_sensors_to_probe_columns(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,sensor_id,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,SHT45-LOWER,30.0,50.0,25.0,ok\n"
            "0.0,SHT45-UPPER,70.0,20.0,25.0,ok\n"
            "2.0,SHT45-LOWER,30.2,49.8,25.1,ok\n"
            "2.0,SHT45-UPPER,70.4,19.8,25.1,warn\n",
            encoding="utf-8",
        )
        meta = tmp_path / "meta.yaml"
        meta.write_text(
            "sensors:\n"
            "  - id: SHT45-LOWER\n"
            "    position: lower_bench\n"
            "    calibration_offset_c: 0.1\n"
            "  - id: SHT45-UPPER\n"
            "    position: upper_bench\n"
            "    calibration_offset_c: -0.2\n",
            encoding="utf-8",
        )
        out = tmp_path / "processed.csv"

        process_raw(raw, out, meta_yaml=meta)

        data = np.atleast_1d(
            np.genfromtxt(out, delimiter=",", names=True, encoding="utf-8")
        )
        assert data.dtype.names == ("time", "lower_bench", "upper_bench")
        assert len(data) == 2
        assert float(data["lower_bench"][0]) == pytest.approx(303.25)
        assert float(data["upper_bench"][0]) == pytest.approx(342.95)

    def test_multi_sensor_data_requires_metadata(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,sensor_id,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,SHT45-LOWER,30.0,50.0,25.0,ok\n"
            "0.0,SHT45-UPPER,70.0,20.0,25.0,ok\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="metadata"):
            process_raw(raw, tmp_path / "processed.csv")

    def test_single_sensor_id_must_match_metadata(self, tmp_path: object) -> None:
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "time_s,sensor_id,temp_c,rh_pct,box_temp_c,status\n"
            "0.0,SHT45-ACTUAL,30.0,50.0,25.0,ok\n",
            encoding="utf-8",
        )
        meta = tmp_path / "meta.yaml"
        meta.write_text(
            "sensor_id: SHT45-EXPECTED\n"
            "probe_position:\n"
            "  name: lower_bench\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="does not match"):
            process_raw(raw, tmp_path / "processed.csv", meta_yaml=meta)


class TestLoadProcessingMetadata:
    def test_rejects_missing_probe_name(self, tmp_path: object) -> None:
        meta = tmp_path / "meta.yaml"
        meta.write_text("session_id: '001'\n", encoding="utf-8")

        with pytest.raises(ValueError, match="probe_position.name"):
            load_processing_metadata(meta)

    def test_supports_planned_single_sensor_format(self, tmp_path: object) -> None:
        meta = tmp_path / "meta.yaml"
        meta.write_text(
            "sensors:\n"
            "  - id: SHT45-001\n"
            "    position: lower_bench\n"
            "    calibration_offset_c: 0.3\n",
            encoding="utf-8",
        )

        probe_name, offset = load_processing_metadata(meta)

        assert probe_name == "lower_bench"
        assert offset == pytest.approx(0.3)

    def test_single_sensor_loader_rejects_multiple_sensors(self, tmp_path: object) -> None:
        meta = tmp_path / "meta.yaml"
        meta.write_text(
            "sensors:\n"
            "  - id: lower\n"
            "    position: lower_bench\n"
            "  - id: upper\n"
            "    position: upper_bench\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="exactly one sensor"):
            load_processing_metadata(meta)


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
