#!/usr/bin/env python3
"""Build all 4 parametric J cases (volume source × ventilation area)."""
import sys
sys.path.insert(0, "src")

from pathlib import Path
from harness.case_builder import build_case

CASES = [
    ("configs/cases/parametric_J1_6kW_vent_std.yaml",  "results/parametric_J1"),
    ("configs/cases/parametric_J2_8kW_vent_std.yaml",  "results/parametric_J2"),
    ("configs/cases/parametric_J3_6kW_vent_half.yaml", "results/parametric_J3"),
    ("configs/cases/parametric_J4_8kW_vent_half.yaml", "results/parametric_J4"),
]

for yaml_path, output_dir in CASES:
    print(f"=== Building {yaml_path} -> {output_dir} ===")
    build_case(Path(yaml_path), output_dir=Path(output_dir))
    print(f"    Done: {output_dir}")

print("\nAll 4 cases built.")
