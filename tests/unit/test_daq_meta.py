"""Tests for daq.meta session metadata generation."""

from __future__ import annotations

import yaml

from daq.meta import (
    generate_meta,
    generate_session_meta_v1,
    load_and_validate_session_meta,
    save_meta,
    validate_session_meta,
)


def _canonical_meta() -> dict:
    return {
        "schema_version": "1.0",
        "session": {
            "id": "20260714-001",
            "started_at": "2026-07-14T14:00:00+09:00",
            "sampling_interval_s": 2.0,
        },
        "environment": {"atmospheric_pressure_pa": 100800},
        "sensors": [
            {
                "id": "SHT45-LOWER",
                "type": "SHT45",
                "measures": ["temperature", "relative_humidity"],
                "position": {"name": "lower_bench", "y_m": 0.8},
                "calibration": {"temperature_offset_c": 0.1},
            }
        ],
    }


class TestGenerateMeta:
    def test_contains_required_fields(self) -> None:
        meta = generate_meta(session_id="001")
        assert meta["session_id"] == "001"
        assert "date" in meta
        assert "start_time_utc" in meta
        assert meta["sensor_type"] == "DHT22"
        assert meta["atmospheric_pressure_pa"] == 101325.0

    def test_probe_position(self) -> None:
        meta = generate_meta(session_id="001", probe_name="lower_bench")
        pos = meta["probe_position"]
        assert pos["name"] == "lower_bench"
        assert pos["x"] == 1.5
        assert pos["y"] == 0.8
        assert pos["z"] == 1.25

    def test_custom_probe_position(self) -> None:
        meta = generate_meta(
            session_id="002",
            probe_name="floor_level",
            probe_y=0.1,
        )
        assert meta["probe_position"]["name"] == "floor_level"
        assert meta["probe_position"]["y"] == 0.1

    def test_steady_state_included_when_set(self) -> None:
        meta = generate_meta(session_id="001", steady_state_reached_s=580.0)
        assert meta["steady_state_reached_s"] == 580.0

    def test_steady_state_excluded_when_none(self) -> None:
        meta = generate_meta(session_id="001")
        assert "steady_state_reached_s" not in meta

    def test_calibration_data(self) -> None:
        cal = {"ice_point_offset_c": -0.3, "reference_check_c": 65.0}
        meta = generate_meta(session_id="001", calibration=cal)
        assert meta["calibration"]["ice_point_offset_c"] == -0.3

    def test_notes(self) -> None:
        meta = generate_meta(session_id="001", notes="bench test")
        assert meta["notes"] == "bench test"


class TestSaveMeta:
    def test_writes_yaml_file(self, tmp_path: object) -> None:
        meta = generate_meta(session_id="001")
        out = tmp_path / "meta.yaml"
        result = save_meta(meta, out)
        assert result == out
        assert out.exists()

    def test_yaml_is_valid(self, tmp_path: object) -> None:
        meta = generate_meta(session_id="001", notes="test session")
        out = tmp_path / "meta.yaml"
        save_meta(meta, out)
        with open(out, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["session_id"] == "001"
        assert loaded["notes"] == "test session"

    def test_creates_parent_directories(self, tmp_path: object) -> None:
        meta = generate_meta(session_id="001")
        out = tmp_path / "sub" / "dir" / "meta.yaml"
        save_meta(meta, out)
        assert out.exists()


class TestValidateSessionMeta:
    def test_accepts_canonical_v1_metadata(self) -> None:
        assert validate_session_meta(_canonical_meta()) == []

    def test_rejects_unknown_measurement_type(self) -> None:
        meta = _canonical_meta()
        meta["sensors"][0]["measures"] = ["radiant_temperature"]

        errors = validate_session_meta(meta)

        assert any("radiant_temperature" in error for error in errors)

    def test_loads_and_validates_yaml(self, tmp_path: object) -> None:
        out = tmp_path / "session_meta.yaml"
        out.write_text(yaml.safe_dump(_canonical_meta()), encoding="utf-8")

        loaded, errors = load_and_validate_session_meta(out)

        assert errors == []
        assert loaded["schema_version"] == "1.0"

    def test_generated_v1_metadata_matches_schema(self) -> None:
        meta = generate_session_meta_v1(
            session_id="session-001",
            sensor_id="SHT45-LOWER",
            sensor_type="SHT45",
            steady_state_reached_s=620.0,
        )

        assert validate_session_meta(meta) == []
        assert meta["session"]["steady_state_reached_s"] == 620.0
        assert meta["sensors"][0]["position"]["name"] == "lower_bench"
