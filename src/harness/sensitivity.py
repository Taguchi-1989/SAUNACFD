"""Parameter sensitivity and uncertainty propagation for the two-zone ROM.

Addresses review item C10: stop reporting KPIs as single point values when the
underlying parameters (heater power, wall conductivity, wall thickness, ...) are
themselves uncertain. This module perturbs YAML-exposed parameters, re-runs the
two-zone solver, and reports:

  - local sensitivity coefficients (how strongly each KPI responds to each
    parameter), both absolute (dKPI/dp) and normalised (elasticity), and
  - a linear-propagated uncertainty band on each KPI given per-parameter
    uncertainties: sigma_KPI = sqrt( sum_i (dKPI/dp_i * sigma_p_i)^2 ).

Only parameters exposed in the case YAML can be varied here. Hard-coded model
constants (the convective fraction f_conv, the base wall HTC) are not yet
configurable; making them tunable is noted as future work.
"""

from __future__ import annotations

import copy
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import math

import yaml

from harness.schema import load_yaml
from harness.simple_solver import SimpleSolverResult, solve_two_zone

# A KPI extractor maps a solver result to a single scalar of interest.
KPIFn = Callable[[SimpleSolverResult], float]


def kpi_upper_temp_c(r: SimpleSolverResult) -> float:
    """Upper-layer temperature [°C]."""
    return r.upper_layer_temp - 273.15


def kpi_stratification_k(r: SimpleSolverResult) -> float:
    """Upper minus lower layer temperature [K] (K-01)."""
    return r.upper_layer_temp - r.lower_layer_temp


DEFAULT_KPIS: dict[str, KPIFn] = {
    "upper_temp_c": kpi_upper_temp_c,
    "stratification_k": kpi_stratification_k,
}


@dataclass
class ParamSpec:
    """A YAML-exposed parameter to vary.

    Attributes:
        path: dotted path into the case dict, e.g.
            "boundary_conditions.heater.power_kw".
        rel_sigma: 1-sigma relative uncertainty (fraction) for propagation.
    """

    path: str
    rel_sigma: float = 0.10


@dataclass
class Sensitivity:
    """Local sensitivity of one KPI to one parameter."""

    param: str
    kpi: str
    nominal_param: float
    nominal_kpi: float
    d_kpi_d_param: float   # absolute derivative
    elasticity: float      # normalised: (dKPI/KPI) / (dp/p)


@dataclass
class UncertaintyBand:
    """Linear-propagated uncertainty on one KPI."""

    kpi: str
    nominal: float
    sigma: float
    lo_2sigma: float = field(init=False)
    hi_2sigma: float = field(init=False)

    def __post_init__(self) -> None:
        self.lo_2sigma = self.nominal - 2.0 * self.sigma
        self.hi_2sigma = self.nominal + 2.0 * self.sigma


def _get_dotted(data: dict, path: str) -> float:
    node: object = data
    for key in path.split("."):
        node = node[key]  # type: ignore[index]
    return float(node)  # type: ignore[arg-type]


def _set_dotted(data: dict, path: str, value: float) -> None:
    keys = path.split(".")
    node: dict = data
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value


def _run_with_overrides(
    base_data: dict, overrides: dict[str, float], max_iter: int, n_profile: int,
) -> SimpleSolverResult:
    """Write a perturbed copy of the case to a temp YAML and solve it."""
    data = copy.deepcopy(base_data)
    for path, value in overrides.items():
        _set_dotted(data, path, value)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8",
    ) as f:
        yaml.safe_dump(data, f)
        tmp_path = Path(f.name)
    try:
        return solve_two_zone(tmp_path, max_iter=max_iter, n_profile=n_profile)
    finally:
        tmp_path.unlink(missing_ok=True)


def local_sensitivities(
    case_yaml: Path,
    specs: list[ParamSpec],
    kpis: dict[str, KPIFn] | None = None,
    rel_delta: float = 0.05,
    max_iter: int = 4000,
    n_profile: int = 40,
) -> list[Sensitivity]:
    """Central-difference local sensitivity of each KPI to each parameter.

    For each parameter p with nominal p0, perturbs by ±rel_delta·p0 and forms
    the central difference dKPI/dp, plus the dimensionless elasticity
    (dKPI/KPI)/(dp/p) so parameters with different units are comparable.
    """
    kpis = kpis or DEFAULT_KPIS
    base_data = load_yaml(case_yaml)
    base = solve_two_zone(case_yaml, max_iter=max_iter, n_profile=n_profile)
    base_kpi = {name: fn(base) for name, fn in kpis.items()}

    out: list[Sensitivity] = []
    for spec in specs:
        p0 = _get_dotted(base_data, spec.path)
        dp = rel_delta * p0 if p0 != 0 else rel_delta
        r_hi = _run_with_overrides(base_data, {spec.path: p0 + dp}, max_iter, n_profile)
        r_lo = _run_with_overrides(base_data, {spec.path: p0 - dp}, max_iter, n_profile)
        for name, fn in kpis.items():
            deriv = (fn(r_hi) - fn(r_lo)) / (2.0 * dp)
            k0 = base_kpi[name]
            elasticity = deriv * p0 / k0 if k0 != 0 else float("nan")
            out.append(Sensitivity(
                param=spec.path,
                kpi=name,
                nominal_param=p0,
                nominal_kpi=k0,
                d_kpi_d_param=deriv,
                elasticity=elasticity,
            ))
    return out


def propagate_uncertainty(
    case_yaml: Path,
    specs: list[ParamSpec],
    kpis: dict[str, KPIFn] | None = None,
    rel_delta: float = 0.05,
    max_iter: int = 4000,
    n_profile: int = 40,
    sens: list[Sensitivity] | None = None,
) -> list[UncertaintyBand]:
    """First-order (linear) propagation of parameter uncertainty to each KPI.

    sigma_KPI = sqrt( sum_i ( dKPI/dp_i * sigma_p_i )^2 ),  sigma_p_i = rel_sigma_i * p_i.
    Assumes independent parameters and local linearity — adequate for a
    PoC-level error band, not a full nonlinear/correlated propagation.

    Pass ``sens`` (from a prior ``local_sensitivities`` call with the same specs
    and kpis) to avoid re-running the solver; otherwise it is computed here.
    """
    kpis = kpis or DEFAULT_KPIS
    if sens is None:
        sens = local_sensitivities(case_yaml, specs, kpis, rel_delta, max_iter, n_profile)
    base_data = load_yaml(case_yaml)

    bands: list[UncertaintyBand] = []
    for name, _ in kpis.items():
        nominal = next(s.nominal_kpi for s in sens if s.kpi == name)
        var = 0.0
        for spec in specs:
            s = next(x for x in sens if x.kpi == name and x.param == spec.path)
            sigma_p = spec.rel_sigma * _get_dotted(base_data, spec.path)
            var += (s.d_kpi_d_param * sigma_p) ** 2
        bands.append(UncertaintyBand(kpi=name, nominal=nominal, sigma=math.sqrt(var)))
    return bands


def sensitivity_report_markdown(
    sens: list[Sensitivity], bands: list[UncertaintyBand],
) -> str:
    """Render sensitivities + uncertainty bands as Markdown."""
    lines = [
        "## Parameter Sensitivity & Uncertainty",
        "",
        "### Local sensitivities (elasticity = % KPI change per % parameter change)",
        "",
        "| Parameter | KPI | dKPI/dp | Elasticity |",
        "| --------- | --- | ------- | ---------- |",
    ]
    for s in sens:
        lines.append(
            f"| {s.param} | {s.kpi} | {s.d_kpi_d_param:+.4g} | {s.elasticity:+.3f} |"
        )
    lines.extend([
        "",
        "### KPI uncertainty bands (±2σ, linear propagation)",
        "",
        "| KPI | Nominal | σ | 95% band |",
        "| --- | ------- | - | -------- |",
    ])
    for b in bands:
        lines.append(
            f"| {b.kpi} | {b.nominal:.2f} | {b.sigma:.2f} | "
            f"[{b.lo_2sigma:.2f}, {b.hi_2sigma:.2f}] |"
        )
    lines.append("")
    return "\n".join(lines)
