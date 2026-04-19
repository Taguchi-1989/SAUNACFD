"""Tests for daq.serial_logger with mock serial port."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from daq.serial_logger import RAW_CSV_FIELDS, _parse_json_line, log_session


class MockSerial:
    """Mock serial port that yields pre-defined JSON lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = iter(lines)
        self.closed = False

    def readline(self) -> bytes:
        try:
            line = next(self._lines)
            return (line + "\n").encode("utf-8")
        except StopIteration:
            return b""

    def close(self) -> None:
        self.closed = True


def _make_json_line(
    time_s: float = 0.0,
    temp_c: float = 68.0,
    rh_pct: float = 10.0,
    box_temp_c: float = 25.0,
    status: str = "ok",
) -> str:
    return json.dumps({
        "time_s": time_s,
        "temp_c": temp_c,
        "rh_pct": rh_pct,
        "box_temp_c": box_temp_c,
        "status": status,
    })


class TestLogSession:
    def test_writes_raw_csv(self, tmp_path: Path) -> None:
        lines = [
            _make_json_line(0.0, 68.0, 10.0, 25.0, "ok"),
            _make_json_line(2.0, 68.1, 10.1, 25.1, "ok"),
        ]
        port = MockSerial(lines)
        out = tmp_path / "raw.csv"
        result = log_session(port, duration_s=10, output_path=out)

        assert result == out
        assert out.exists()
        data = np.genfromtxt(out, delimiter=",", names=True, dtype=None, encoding="utf-8")
        data = np.atleast_1d(data)
        assert len(data) == 2
        assert float(data[0]["temp_c"]) == 68.0

    def test_csv_has_correct_headers(self, tmp_path: Path) -> None:
        lines = [_make_json_line()]
        port = MockSerial(lines)
        out = tmp_path / "raw.csv"
        log_session(port, duration_s=10, output_path=out)

        with open(out, encoding="utf-8") as f:
            header = f.readline().strip()
        assert header == ",".join(RAW_CSV_FIELDS)

    def test_stops_on_shutdown(self, tmp_path: Path) -> None:
        lines = [
            _make_json_line(0.0, 68.0, 10.0, 25.0, "ok"),
            _make_json_line(2.0, 68.1, 10.1, 62.0, "shutdown"),
            _make_json_line(4.0, 68.2, 10.2, 63.0, "ok"),  # should not be written
        ]
        port = MockSerial(lines)
        out = tmp_path / "raw.csv"
        log_session(port, duration_s=60, output_path=out)

        data = np.genfromtxt(out, delimiter=",", names=True, dtype=None, encoding="utf-8")
        data = np.atleast_1d(data)
        # shutdown row IS written (the sensor data is valuable), but loop stops after
        assert len(data) == 2

    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        lines = [
            _make_json_line(0.0),
            "not valid json",
            _make_json_line(4.0, 68.2, 10.2, 25.2, "ok"),
        ]
        port = MockSerial(lines)
        out = tmp_path / "raw.csv"
        log_session(port, duration_s=10, output_path=out)

        data = np.genfromtxt(out, delimiter=",", names=True, dtype=None, encoding="utf-8")
        data = np.atleast_1d(data)
        assert len(data) == 2  # invalid line skipped

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        lines = [_make_json_line()]
        port = MockSerial(lines)
        out = tmp_path / "sub" / "dir" / "raw.csv"
        log_session(port, duration_s=10, output_path=out)
        assert out.exists()


class TestParseJsonLine:
    def test_valid_json(self) -> None:
        line = '{"time_s": 0.0, "temp_c": 68.0}'
        result = _parse_json_line(line)
        assert result is not None
        assert result["time_s"] == 0.0

    def test_invalid_json(self) -> None:
        assert _parse_json_line("not json") is None

    def test_empty_string(self) -> None:
        assert _parse_json_line("") is None
