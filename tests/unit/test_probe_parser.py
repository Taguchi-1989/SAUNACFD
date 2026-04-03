"""Tests for probe_parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.probe_parser import get_steady_state_values, parse_probe_file

SAMPLE_PROBE_OUTPUT = """\
# Probe 0 (1.5 2.0 1.25)
# Probe 1 (1.5 0.8 1.25)
# Probe 2 (1.5 0.1 1.25)
#        Time            0               1               2
0               293.15          293.15          293.15
100             340.5           315.2           298.7
200             355.8           325.1           302.3
300             358.2           327.5           303.1
"""

PROBE_NAMES = ["upper_bench", "lower_bench", "floor_level"]


class TestParseProbeFile:
    def test_parses_correct_count(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        assert len(result) == 3

    def test_probe_names(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        assert result[0].probe_name == "upper_bench"
        assert result[1].probe_name == "lower_bench"
        assert result[2].probe_name == "floor_level"

    def test_field_name(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        assert all(p.field == "T" for p in result)

    def test_time_values(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        assert result[0].times == [0.0, 100.0, 200.0, 300.0]

    def test_probe_values(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        # Upper bench values
        assert result[0].values == [293.15, 340.5, 355.8, 358.2]
        # Floor level final value
        assert result[2].values[-1] == 303.1

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text("", encoding="utf-8")
        result = parse_probe_file(f, PROBE_NAMES)
        assert all(p.values == [] for p in result)

    def test_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_probe_file(Path("/nonexistent/T"), PROBE_NAMES)


class TestGetSteadyStateValues:
    def test_returns_last_values(self, tmp_path: Path) -> None:
        f = tmp_path / "T"
        f.write_text(SAMPLE_PROBE_OUTPUT, encoding="utf-8")
        data = parse_probe_file(f, PROBE_NAMES)
        values = get_steady_state_values(data)
        assert values["upper_bench"] == 358.2
        assert values["lower_bench"] == 327.5
        assert values["floor_level"] == 303.1

    def test_empty_data(self) -> None:
        from harness.probe_parser import ProbeData

        data = [ProbeData("test", "T", [], [])]
        values = get_steady_state_values(data)
        assert values == {}
