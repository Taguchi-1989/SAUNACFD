"""Tests for KPI calculation module."""

from __future__ import annotations

from harness.kpi import compute_k01, compute_k07, evaluate_phase1_kpis


class TestComputeK01:
    def test_positive_stratification(self) -> None:
        result = compute_k01(upper_temp=353.0, lower_temp=323.0)
        assert result.kpi_id == "K-01"
        assert result.value == 30.0
        assert result.unit == "K"
        assert result.pass_fail == "pass"

    def test_no_stratification(self) -> None:
        result = compute_k01(upper_temp=300.0, lower_temp=300.0)
        assert result.value == 0.0
        assert result.pass_fail == "fail"

    def test_inverted_stratification(self) -> None:
        result = compute_k01(upper_temp=300.0, lower_temp=350.0)
        assert result.value == -50.0
        assert result.pass_fail == "fail"


class TestComputeK07:
    def test_relative_difference(self) -> None:
        result = compute_k07(upper_temp=360.0, lower_temp=320.0)
        assert result.kpi_id == "K-07"
        # (360 - 320) / 340 ≈ 0.1176
        assert abs(result.value - 0.1176) < 0.001
        assert result.unit == "-"
        assert result.pass_fail is None

    def test_equal_temperatures(self) -> None:
        result = compute_k07(upper_temp=300.0, lower_temp=300.0)
        assert result.value == 0.0

    def test_zero_temperatures(self) -> None:
        result = compute_k07(upper_temp=0.0, lower_temp=0.0)
        assert result.value == 0.0


class TestEvaluatePhase1Kpis:
    def test_returns_two_kpis(self) -> None:
        values = {"upper_bench": 358.2, "lower_bench": 327.5}
        results = evaluate_phase1_kpis(values)
        assert len(results) == 2
        assert results[0].kpi_id == "K-01"
        assert results[1].kpi_id == "K-07"

    def test_correct_values(self) -> None:
        values = {"upper_bench": 358.2, "lower_bench": 327.5}
        results = evaluate_phase1_kpis(values)
        assert results[0].value == 30.7  # 358.2 - 327.5
        assert results[0].pass_fail == "pass"

    def test_missing_probes(self) -> None:
        values = {}
        results = evaluate_phase1_kpis(values)
        assert results[0].value == 0.0
        assert results[0].pass_fail == "fail"
