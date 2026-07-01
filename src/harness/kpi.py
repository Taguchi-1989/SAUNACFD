"""KPI calculation (peak T, humidity, wind speed, arrival time)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class KPIResult:
    """Result of a single KPI computation."""

    kpi_id: str
    name: str
    value: float
    unit: str
    pass_fail: str | None = None  # "pass", "fail", or None
    note: str | None = None  # caveat: proxy/tautology/assumptions, surfaced honestly


# Plausible steady-state upper/lower stratification band for a sauna [K].
# Below MIN the room is essentially well-mixed (no meaningful stratification);
# above MAX the differential is physically implausible and usually signals a
# non-converged or runaway solution. A bare ``diff > 0`` test is tautological —
# any trace of stratification passes — so K-01 checks the band instead.
K01_STRATIFICATION_MIN_K = 2.0
K01_STRATIFICATION_MAX_K = 80.0


def compute_k01(upper_temp: float, lower_temp: float) -> KPIResult:
    """K-01: Steady-state temperature differential (upper - lower bench).

    A positive value indicates thermal stratification (hot air rises). The
    pass band requires the differential to be both non-trivial and physically
    plausible (``2 K <= diff <= 80 K``), not merely positive.
    """
    diff = upper_temp - lower_temp
    in_band = K01_STRATIFICATION_MIN_K <= diff <= K01_STRATIFICATION_MAX_K
    note = None
    if not in_band:
        if diff <= 0:
            note = "no/inverted stratification"
        elif diff < K01_STRATIFICATION_MIN_K:
            note = f"below {K01_STRATIFICATION_MIN_K:g} K — effectively well-mixed"
        else:
            note = f"above {K01_STRATIFICATION_MAX_K:g} K — implausible, suspect non-convergence"
    return KPIResult(
        kpi_id="K-01",
        name="Steady-state temperature differential",
        value=round(diff, 2),
        unit="K",
        pass_fail="pass" if in_band else "fail",
        note=note,
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


def compute_k02(
    t_upper_series: list[float] | np.ndarray, baseline_temp: float
) -> KPIResult:
    """K-02: Post-Löyly peak temperature rise above baseline [K]."""
    peak = max(t_upper_series) if len(t_upper_series) > 0 else baseline_temp
    rise = peak - baseline_temp
    return KPIResult(
        kpi_id="K-02",
        name="Post-Löyly peak temperature rise",
        value=round(rise, 2),
        unit="K",
        pass_fail="pass" if rise > 0.5 else "fail",
    )


def compute_k03(humidity_series: list[float] | np.ndarray) -> KPIResult:
    """K-03: Post-Löyly peak absolute humidity [g/kg]."""
    peak_kg = max(humidity_series) if len(humidity_series) > 0 else 0.0
    peak_gkg = peak_kg * 1000  # convert to g/kg for readability
    return KPIResult(
        kpi_id="K-03",
        name="Post-Löyly peak humidity",
        value=round(peak_gkg, 2),
        unit="g/kg",
        pass_fail=None,
    )


def compute_k04(
    time_series: list[float] | np.ndarray,
    t_upper_series: list[float] | np.ndarray,
    event_time: float = 0.0,
) -> KPIResult:
    """K-04: Time from event (Löyly) to peak temperature [s].

    Only samples at/after ``event_time`` are searched: a pre-event maximum
    (e.g. warm-up overshoot before the Löyly pour) is not the post-event peak
    this KPI is defined on.
    """
    times = np.asarray(time_series, dtype=float)
    temps = np.asarray(t_upper_series, dtype=float)
    n = min(times.size, temps.size)
    times, temps = times[:n], temps[:n]
    mask = times >= event_time
    if n == 0 or not np.any(mask):
        return KPIResult(
            kpi_id="K-04",
            name="Peak arrival time",
            value=0.0,
            unit="s",
            pass_fail=None,
            note="no samples at/after event_time" if n > 0 else None,
        )
    peak_idx = int(np.argmax(temps[mask]))
    arrival = float(times[mask][peak_idx]) - event_time
    return KPIResult(
        kpi_id="K-04",
        name="Peak arrival time",
        value=round(max(arrival, 0.0), 1),
        unit="s",
        pass_fail=None,
    )


# Face air speed [m/s] above which an Aufguss gust is clearly perceptible.
K05_PERCEPTIBLE_MPS = 0.2


def compute_k05(
    beta_aug: float,
    face_velocity: float | None = None,
    rho: float = 0.9,
    a_face: float = 0.05,
) -> KPIResult:
    """K-05: Face-level wind speed during Aufguss.

    Preferred: ``face_velocity`` from the free-jet centerline model
    (``harness.jet.free_jet_face_velocity`` — exit velocity, source size, and
    distance to the face). This is a physics-based estimate, so it gets a
    perceptibility pass/fail (>= 0.2 m/s = clearly felt).

    Fallback: if no jet-derived velocity is available, an order-of-magnitude
    proxy ``v ~ beta_aug / (rho * A_face)`` is reported with no pass/fail and a
    note — this is just a rescale of the mixing coefficient, not a prediction.
    """
    if face_velocity is not None and face_velocity > 0.0:
        return KPIResult(
            kpi_id="K-05",
            name="Face-level wind speed (free-jet)",
            value=round(face_velocity, 2),
            unit="m/s",
            pass_fail="pass" if face_velocity >= K05_PERCEPTIBLE_MPS else "fail",
            note="round free-jet centerline decay (U0, d0, distance)",
        )

    v_proxy = beta_aug / (rho * a_face) if beta_aug > 0 else 0.0
    return KPIResult(
        kpi_id="K-05",
        name="Face-level wind speed (proxy)",
        value=round(v_proxy, 2),
        unit="m/s",
        pass_fail=None,
        note=(
            f"order-of-magnitude proxy: linear in beta_aug "
            f"(rho={rho:g}, A_face={a_face:g} m^2 assumed); not a jet model. "
            f"Provide aufguss.jet_velocity/jet_diameter/face_distance for the "
            f"free-jet estimate."
        ),
    )


def compute_k06(perceived_temp_c: float) -> KPIResult:
    """K-06: Simplified thermal stress index.

    Based on perceived temperature (includes humidity effect).
    Categories: <60C comfortable, 60-80C moderate, 80-100C intense, >100C extreme.
    """
    if perceived_temp_c < 60:
        category = "comfortable"
    elif perceived_temp_c < 80:
        category = "moderate"
    elif perceived_temp_c < 100:
        category = "intense"
    else:
        category = "extreme"
    return KPIResult(
        kpi_id="K-06",
        name=f"Thermal stress index ({category})",
        value=round(perceived_temp_c, 1),
        unit="C",
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


def evaluate_all_kpis(
    probe_values: dict[str, float],
    t_upper_series: list[float] | np.ndarray | None = None,
    humidity_series: list[float] | np.ndarray | None = None,
    time_series: list[float] | np.ndarray | None = None,
    baseline_temp: float = 0.0,
    event_time: float = 0.0,
    beta_aug: float = 0.0,
    perceived_temp_c: float = 0.0,
    aufguss_face_velocity: float = 0.0,
) -> list[KPIResult]:
    """Compute all available KPIs."""
    upper = probe_values.get("upper_bench", 0.0)
    lower = probe_values.get("lower_bench", 0.0)

    results = [
        compute_k01(upper, lower),
        compute_k07(upper, lower),
    ]

    if t_upper_series is not None and len(t_upper_series) > 0:
        results.append(compute_k02(t_upper_series, baseline_temp))
    if humidity_series is not None and len(humidity_series) > 0:
        results.append(compute_k03(humidity_series))
    if time_series is not None and t_upper_series is not None:
        results.append(compute_k04(time_series, t_upper_series, event_time))
    if beta_aug > 0 or aufguss_face_velocity > 0:
        face_vel = aufguss_face_velocity if aufguss_face_velocity > 0 else None
        results.append(compute_k05(beta_aug, face_velocity=face_vel))
    if perceived_temp_c > 0:
        results.append(compute_k06(perceived_temp_c))

    return results
