"""Tests for parameter sensitivity & uncertainty propagation."""

from __future__ import annotations

from pathlib import Path

import yaml

from harness.sensitivity import (
    ParamSpec,
    UncertaintyBand,
    _get_dotted,
    _set_dotted,
    kpi_stratification_k,
    kpi_upper_temp_c,
    local_sensitivities,
    propagate_uncertainty,
    sensitivity_report_markdown,
)


def _write_case(tmp_path: Path, power_kw: float = 9.0) -> Path:
    data = {
        "case": {"name": "sens", "description": "t", "type": "steady"},
        "geometry": {"dimensions": {"x": 3.0, "y": 2.5, "z": 2.5}, "mesh_level": "M0"},
        "boundary_conditions": {
            "walls": {"temperature": 293.15, "type": "mixed", "model": "lumped",
                      "thickness": 0.05, "conductivity": 0.12},
            "heater": {"power_kw": power_kw, "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                       "width": 0.6, "height": 0.5},
        },
        "solver": {"name": "buoyantPimpleFoam", "end_time": 300, "write_interval": 10,
                   "delta_t": 0.05, "averaging_start": 150},
        "probes": [
            {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
            {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
            {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
        ],
    }
    p = tmp_path / "case.yaml"
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return p


class TestDottedHelpers:
    def test_get_set_roundtrip(self) -> None:
        d = {"a": {"b": {"c": 1.0}}}
        assert _get_dotted(d, "a.b.c") == 1.0
        _set_dotted(d, "a.b.c", 5.0)
        assert d["a"]["b"]["c"] == 5.0


class TestLocalSensitivities:
    def test_power_increases_upper_temp(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path)
        sens = local_sensitivities(
            case,
            [ParamSpec("boundary_conditions.heater.power_kw", rel_sigma=0.1)],
            kpis={"upper_temp_c": kpi_upper_temp_c},
            max_iter=2000,
        )
        s = sens[0]
        # More heater power must raise the upper-layer temperature.
        assert s.d_kpi_d_param > 0.0
        assert s.elasticity > 0.0

    def test_conductivity_lowers_temp(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path)
        sens = local_sensitivities(
            case,
            [ParamSpec("boundary_conditions.walls.conductivity")],
            kpis={"upper_temp_c": kpi_upper_temp_c},
            max_iter=2000,
        )
        # Higher wall conductivity => more loss => cooler room (negative sensitivity).
        assert sens[0].d_kpi_d_param < 0.0


class TestUncertaintyPropagation:
    def test_band_orders_and_positive_sigma(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path)
        bands = propagate_uncertainty(
            case,
            [
                ParamSpec("boundary_conditions.heater.power_kw", rel_sigma=0.1),
                ParamSpec("boundary_conditions.walls.conductivity", rel_sigma=0.2),
            ],
            kpis={"upper_temp_c": kpi_upper_temp_c},
            max_iter=2000,
        )
        b = bands[0]
        assert isinstance(b, UncertaintyBand)
        assert b.sigma > 0.0
        assert b.lo_2sigma < b.nominal < b.hi_2sigma

    def test_report_renders(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path)
        specs = [ParamSpec("boundary_conditions.heater.power_kw", rel_sigma=0.1)]
        kpis = {"upper_temp_c": kpi_upper_temp_c, "stratification_k": kpi_stratification_k}
        sens = local_sensitivities(case, specs, kpis=kpis, max_iter=2000)
        bands = propagate_uncertainty(case, specs, kpis=kpis, max_iter=2000)
        md = sensitivity_report_markdown(sens, bands)
        assert "Parameter Sensitivity" in md
        assert "Elasticity" in md
        assert "95% band" in md
