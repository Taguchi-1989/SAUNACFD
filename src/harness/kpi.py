"""KPI calculation (peak T, humidity, wind speed, arrival time)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KPIResult:
    """Result of a single KPI computation."""

    kpi_id: str
    name: str
    value: float
    unit: str
    pass_fail: str | None = None  # "pass", "fail", or None


def compute_k01(upper_temp: float, lower_temp: float) -> KPIResult:
    """K-01: Steady-state temperature differential (upper - lower bench).

    A positive value indicates thermal stratification (hot air rises).
    """
    diff = upper_temp - lower_temp
    return KPIResult(
        kpi_id="K-01",
        name="Steady-state temperature differential",
        value=round(diff, 2),
        unit="K",
        pass_fail="pass" if diff > 0 else "fail",
    )


def compute_k07(upper_temp: float, lower_temp: float) -> KPIResult:
    """K-07: Upper/lower relative difference.

    Computed as (upper - lower) / mean_temperature.
    """
    mean = (upper_temp + lower_temp) / 2
    rel_diff = (upper_temp - lower_temp) / mean if mean != 0 else 0.0
    return KPIResult(
        kpi_id="K-07",
        name="Upper/lower relative difference",
        value=round(rel_diff, 4),
        unit="-",
        pass_fail=None,
    )


def evaluate_phase1_kpis(probe_values: dict[str, float]) -> list[KPIResult]:
    """Compute all Phase 1 KPIs from probe steady-state values.

    Expects probe_values to contain 'upper_bench' and 'lower_bench' keys.
    """
    upper = probe_values.get("upper_bench", 0.0)
    lower = probe_values.get("lower_bench", 0.0)

    return [
        compute_k01(upper, lower),
        compute_k07(upper, lower),
    ]
