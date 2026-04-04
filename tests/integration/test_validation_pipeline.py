"""Integration tests for the validation pipeline (Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from harness.kpi import evaluate_all_kpis
from harness.reporting import report_to_dict, report_to_json, report_to_markdown
from harness.simple_solver import solve_transient, solve_two_zone
from harness.validation import compare_probes, load_experimental_csv, time_average


class TestSteadyStateValidation:
    """Test: run steady solver -> compare with experimental CSV -> report."""

    def test_full_pipeline(self, tmp_path: Path) -> None:
        # 1. Run solver
        case_yaml = Path("configs/cases/dry_sauna_steady.yaml")
        result = solve_two_zone(case_yaml, n_profile=80, max_iter=50000)
        assert result.converged or result.iterations > 5000

        # 2. Load experimental data
        csv_path = Path("experiments/processed/dry_sauna_sample.csv")
        exp_data = load_experimental_csv(csv_path)
        assert "upper_bench" in exp_data

        # 3. Time-average experimental data (use last time point as steady-state proxy)
        exp_steady: dict[str, float] = {}
        for name in ["upper_bench", "lower_bench", "floor_level"]:
            if name in exp_data:
                exp_steady[name] = float(exp_data[name][-1])

        # 4. Compare
        report = compare_probes(
            sim_values=result.probe_values,
            exp_values=exp_steady,
            default_tol=30.0,  # generous tolerance for sample data
        )
        report.case_name = "dry_sauna_steady"
        assert len(report.points) > 0

        # 5. Generate reports
        md = report_to_markdown(report, tmp_path / "report.md")
        assert "dry_sauna_steady" in md
        assert (tmp_path / "report.md").exists()

        json_str = report_to_json(report, tmp_path / "report.json")
        parsed = json.loads(json_str)
        assert parsed["case_name"] == "dry_sauna_steady"
        assert (tmp_path / "report.json").exists()

    def test_kpis_from_solver(self) -> None:
        """Run solver and compute all available KPIs."""
        case_yaml = Path("configs/cases/dry_sauna_steady.yaml")
        result = solve_two_zone(case_yaml, n_profile=80, max_iter=50000)

        kpis = evaluate_all_kpis(
            probe_values=result.probe_values,
            perceived_temp_c=result.perceived_temp_upper,
        )
        ids = [k.kpi_id for k in kpis]
        assert "K-01" in ids
        assert "K-06" in ids
        assert "K-07" in ids


class TestTransientValidation:
    """Test: run transient solver -> extract time-series KPIs."""

    def test_loyly_transient_kpis(self) -> None:
        case_yaml = Path("configs/cases/loyly_test.yaml")
        tr = solve_transient(case_yaml, physical_dt=1.0, end_time=60.0)

        assert len(tr.time) > 10
        assert len(tr.t_upper_series) == len(tr.time)

        # Compute time-series KPIs
        kpis = evaluate_all_kpis(
            probe_values=tr.steady_result.probe_values,
            t_upper_series=list(tr.t_upper_series),
            humidity_series=list(tr.humidity_series),
            time_series=list(tr.time),
            baseline_temp=float(tr.t_upper_series[0]),
            event_time=0.0,
            perceived_temp_c=tr.steady_result.perceived_temp_upper,
        )
        ids = [k.kpi_id for k in kpis]
        assert "K-02" in ids  # peak temp rise
        assert "K-03" in ids  # peak humidity
        assert "K-04" in ids  # arrival time

    def test_aufguss_transient_kpis(self) -> None:
        case_yaml = Path("configs/cases/aufguss_test.yaml")
        tr = solve_transient(case_yaml, physical_dt=1.0, end_time=60.0)

        kpis = evaluate_all_kpis(
            probe_values=tr.steady_result.probe_values,
            t_upper_series=list(tr.t_upper_series),
            time_series=list(tr.time),
            baseline_temp=float(tr.t_upper_series[0]),
            beta_aug=tr.steady_result.beta_aug_applied,
            perceived_temp_c=tr.steady_result.perceived_temp_upper,
        )
        ids = [k.kpi_id for k in kpis]
        assert "K-05" in ids  # wind speed proxy


class TestBatchComparison:
    """Test: run multiple cases and compare results."""

    def test_three_cases_produce_different_results(self) -> None:
        cases = [
            "configs/cases/dry_sauna_steady.yaml",
            "configs/cases/loyly_test.yaml",
            "configs/cases/aufguss_test.yaml",
        ]
        results = {}
        for case in cases:
            name = Path(case).stem
            r = solve_two_zone(Path(case), n_profile=40, max_iter=20000)
            results[name] = r

        # Aufguss should have lower stratification
        dry_strat = (
            results["dry_sauna_steady"].upper_layer_temp
            - results["dry_sauna_steady"].lower_layer_temp
        )
        aug_strat = (
            results["aufguss_test"].upper_layer_temp
            - results["aufguss_test"].lower_layer_temp
        )
        assert aug_strat < dry_strat

        # All should have positive stratification
        for name, r in results.items():
            assert r.upper_layer_temp > r.lower_layer_temp, (
                f"{name} has no stratification"
            )
