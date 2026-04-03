"""Probe output parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProbeData:
    """Parsed data for a single probe and field."""

    probe_name: str
    field: str
    times: list[float]
    values: list[float]


def parse_probe_file(probe_file: Path, probe_names: list[str]) -> list[ProbeData]:
    """Parse an OpenFOAM probe output file.

    OpenFOAM probes function object writes tab/space-separated files like:
        # Probe 0 (x y z)
        # Probe 1 (x y z)
        # Time          0           1
        0               293.15      293.15
        100             350.2       320.1

    Args:
        probe_file: Path to the probe output file (e.g., postProcessing/probes/0/T).
        probe_names: Ordered list of probe names matching column order.

    Returns:
        List of ProbeData, one per probe.
    """
    field_name = probe_file.stem  # e.g. "T" from ".../T"

    times: list[float] = []
    # Each inner list collects values for one probe column
    columns: list[list[float]] = [[] for _ in probe_names]

    text = probe_file.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 1 + len(probe_names):
            continue

        times.append(float(parts[0]))
        for i in range(len(probe_names)):
            columns[i].append(float(parts[1 + i]))

    return [
        ProbeData(
            probe_name=name,
            field=field_name,
            times=list(times),
            values=columns[i],
        )
        for i, name in enumerate(probe_names)
    ]


def get_steady_state_values(probe_data: list[ProbeData]) -> dict[str, float]:
    """Extract the final (steady-state) value for each probe.

    Args:
        probe_data: List of ProbeData from parse_probe_file.

    Returns:
        Dict mapping probe_name to its final value.
    """
    return {
        pd.probe_name: pd.values[-1]
        for pd in probe_data
        if pd.values
    }
