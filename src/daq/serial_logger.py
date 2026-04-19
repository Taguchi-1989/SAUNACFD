"""Serial port logger: receive JSON lines from microcontroller, write raw CSV."""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import IO, Protocol

logger = logging.getLogger(__name__)

RAW_CSV_FIELDS = ["time_s", "temp_c", "rh_pct", "box_temp_c", "status"]


class SerialPort(Protocol):
    """Protocol for serial port (allows mocking without pyserial)."""

    def readline(self) -> bytes: ...

    def close(self) -> None: ...


def log_session(
    port: SerialPort,
    duration_s: int,
    output_path: Path,
    flush_interval_s: float = 10.0,
) -> Path:
    """Read JSON lines from serial port and write raw CSV.

    Each line from the microcontroller is expected to be a JSON object:
        {"time_s": 0.0, "temp_c": 68.5, "rh_pct": 12.3, "box_temp_c": 25.1, "status": "ok"}

    Args:
        port: Serial port object with readline() method.
        duration_s: Maximum session duration in seconds.
        output_path: Path for output raw CSV file.
        flush_interval_s: Interval in seconds between forced file flushes.

    Returns:
        Path to the written raw CSV file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()
    last_flush = start_time

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_CSV_FIELDS)
        writer.writeheader()

        while (time.monotonic() - start_time) < duration_s:
            line = _read_line(port)
            if line is None:
                continue

            data = _parse_json_line(line)
            if data is None:
                continue

            row = {field: data.get(field, "") for field in RAW_CSV_FIELDS}
            writer.writerow(row)

            # Check for shutdown
            if data.get("status") == "shutdown":
                logger.warning("Received shutdown status from sensor, stopping")
                break

            # Periodic flush
            now = time.monotonic()
            if (now - last_flush) >= flush_interval_s:
                f.flush()
                last_flush = now

    return output_path


def _read_line(port: SerialPort) -> str | None:
    """Read one line from serial port, return decoded string or None."""
    try:
        raw = port.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").strip()
    except Exception:
        logger.debug("Serial read error", exc_info=True)
        return None


def _parse_json_line(line: str) -> dict | None:
    """Parse a JSON line, return dict or None on failure."""
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON: %s", line)
        return None
