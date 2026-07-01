"""Tests for two-zone plume model solver."""

from __future__ import annotations

from pathlib import Path

import yaml

from harness.simple_solver import (
    ENERGY_CLOSURE_TOL,
    TransientResult,
    _clamp_active,
    _compute_view_factors,
    _radiant_distribution,
    _energy_balance,
    _evaporation_rate,
    _perceived_temperature,
    _plume_entrainment,
    _q_rad_body,
    _ventilation_flow,
    solve_transient,
    solve_two_zone,
)


def _write_case_yaml(tmp_path: Path, **overrides) -> Path:
    """Helper to create a temporary case YAML."""
    data = {
        "case": {"name": "test", "description": "test", "type": "steady"},
        "geometry": {
            "dimensions": {"x": 3.0, "y": 2.5, "z": 2.5},
            "mesh_level": "M0",
        },
        "boundary_conditions": {
            "walls": {"temperature": 293.15, "type": "mixed"},
            "heater": {
                "power_kw": 9.0,
                "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                "width": 0.6,
                "height": 0.5,
            },
        },
        "solver": {
            "name": "buoyantPimpleFoam",
            "end_time": 300,
            "write_interval": 10,
            "delta_t": 0.05,
            "averaging_start": 150,
        },
        "probes": [
            {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
            {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
            {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
        ],
    }
    # Apply overrides
    for key, val in overrides.items():
        if key == "power_kw":
            data["boundary_conditions"]["heater"]["power_kw"] = val
        elif key == "t_wall":
            data["boundary_conditions"]["walls"]["temperature"] = val
    path = tmp_path / "case.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


class TestPlumeEntrainment:
    def test_zero_height_returns_ambient(self) -> None:
        m, t = _plume_entrainment(9000.0, 0.0, 293.15)
        assert m == 0.0
        assert t == 293.15  # no plume at zero height = ambient

    def test_mass_flow_increases_with_height(self) -> None:
        m1, _ = _plume_entrainment(9000.0, 1.0, 293.15)
        m2, _ = _plume_entrainment(9000.0, 2.0, 293.15)
        assert m2 > m1

    def test_plume_temp_decreases_with_height(self) -> None:
        _, t1 = _plume_entrainment(9000.0, 0.5, 293.15)
        _, t2 = _plume_entrainment(9000.0, 2.0, 293.15)
        assert t1 > t2  # more entrainment dilutes plume

    def test_higher_power_increases_temp(self) -> None:
        _, t1 = _plume_entrainment(5000.0, 1.0, 293.15)
        _, t2 = _plume_entrainment(15000.0, 1.0, 293.15)
        assert t2 > t1

    def test_zero_power(self) -> None:
        m, t = _plume_entrainment(0.0, 1.0, 293.15)
        assert m == 0.0

    def test_temp_bounded_for_tiny_mass_flow(self) -> None:
        """Near-source (tiny m_dot) plume temperature must stay bounded.

        The raw energy balance diverges as m_dot -> 0; the solver floors the
        denominator at 0.01 kg/s, so the excess temperature can never exceed
        q / (0.01 * cp).
        """
        q = 500.0
        _, t = _plume_entrainment(q, 0.02, 293.15, heater_diameter=0.05)
        assert t - 293.15 <= q / (0.01 * 1005.0) + 1e-9


class TestSolveTwoZone:
    def test_converges(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.converged is True

    def test_thermal_stratification(self, tmp_path: Path) -> None:
        """Upper bench must be hotter than lower bench."""
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.probe_values["upper_bench"] > result.probe_values["lower_bench"]

    def test_interface_within_room(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert 0 < result.interface_height < 2.5

    def test_upper_layer_hotter_than_lower(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.upper_layer_temp > result.lower_layer_temp

    def test_plume_mass_flow_positive(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.plume_mass_flow > 0

    def test_higher_power_higher_temps(self, tmp_path: Path) -> None:
        (tmp_path / "lo").mkdir()
        (tmp_path / "hi").mkdir()
        path_lo = _write_case_yaml(tmp_path / "lo", power_kw=5.0)
        path_hi = _write_case_yaml(tmp_path / "hi", power_kw=15.0)
        r_lo = solve_two_zone(path_lo, max_iter=10000)
        r_hi = solve_two_zone(path_hi, max_iter=10000)
        assert r_hi.upper_layer_temp > r_lo.upper_layer_temp

    def test_profile_length_matches_n_profile(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, n_profile=40, max_iter=5000)
        assert len(result.y_positions) == 40
        assert len(result.temperatures) == 40

    def test_all_probes_present(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=5000)
        assert "upper_bench" in result.probe_values
        assert "lower_bench" in result.probe_values
        assert "floor_level" in result.probe_values

    def test_residual_history_populated(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=5000)
        assert len(result.residual_history) > 0
        # Residuals should generally decrease
        assert result.residual_history[-1] < result.residual_history[0]


class TestSelfDiagnostics:
    """Energy-closure and clamp self-diagnostics (Roadmap A)."""

    def test_energy_in_equals_heater_power(self, tmp_path: Path) -> None:
        """All heater power enters the system, so energy_in == power_w."""
        path = _write_case_yaml(tmp_path, power_kw=9.0)
        r = solve_two_zone(path, max_iter=10000)
        assert abs(r.energy_in_w - 9000.0) < 1e-6

    def test_energy_residual_is_in_minus_out(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        r = solve_two_zone(path, max_iter=10000)
        assert abs(r.energy_residual_w - (r.energy_in_w - r.energy_out_w)) < 1e-6

    def test_energy_closure_is_out_over_in(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        r = solve_two_zone(path, max_iter=10000)
        assert abs(r.energy_closure - r.energy_out_w / r.energy_in_w) < 1e-9

    def test_physically_converged_invariant(self, tmp_path: Path) -> None:
        """physical convergence == numerical AND energy closed AND no clamp.

        This invariant must hold regardless of the model's current closure, so
        it stays valid even after the energy balance is later improved.
        """
        path = _write_case_yaml(tmp_path)
        r = solve_two_zone(path, max_iter=10000)
        expected = (
            r.converged
            and abs(1.0 - r.energy_closure) <= ENERGY_CLOSURE_TOL
            and not r.clamp_active
        )
        assert r.physically_converged is expected

    def test_numerical_convergence_can_hide_energy_imbalance(self, tmp_path: Path) -> None:
        """The default case meets the residual but does NOT close energy.

        Documents the central validity finding (review C2): a passing numerical
        residual is not evidence of a physical steady state. If a future model
        change actually closes the balance, this test should be updated.
        """
        path = _write_case_yaml(tmp_path, power_kw=9.0)
        r = solve_two_zone(path, max_iter=10000)
        assert r.converged is True
        assert abs(1.0 - r.energy_closure) > ENERGY_CLOSURE_TOL
        assert r.physically_converged is False

    def test_transient_exposes_diagnostics(self, tmp_path: Path) -> None:
        path = _write_case_yaml(tmp_path)
        r = solve_transient(path, end_time=200.0, physical_dt=1.0, record_interval=10.0)
        s = r.steady_result
        assert abs(s.energy_in_w - 9000.0) < 1e-6
        assert s.energy_out_w >= 0.0

    def test_clamp_active_detects_interface_floor(self) -> None:
        """A z_int resting on the lower clamp bound is flagged."""
        assert _clamp_active(
            z_int=0.05 * 2.5, t_upper=350.0, t_lower=320.0,
            height=2.5, t_wall_inner=300.0, t_wall=293.15,
        ) is True

    def test_clamp_active_false_for_interior_state(self) -> None:
        assert _clamp_active(
            z_int=1.2, t_upper=360.0, t_lower=320.0,
            height=2.5, t_wall_inner=300.0, t_wall=293.15,
        ) is False

    def test_energy_balance_lumped_uses_conduction(self) -> None:
        """Lumped wall: q_ext is conduction to outside, independent of h_wall."""
        eb = _energy_balance(
            power_w=9000.0, wall_cfg="lumped", wall_lambda=0.12,
            wall_thickness=0.015, a_wall_total=42.5, a_wall_upper=20.0,
            a_wall_lower=22.5, h_wall=8.0, t_upper=360.0, t_lower=330.0,
            t_wall_inner=330.0, t_wall=293.15, m_vent=0.0, cp_eff=1005.0,
            t_ambient_vent=293.15,
        )
        expected = 0.12 / 0.015 * 42.5 * (330.0 - 293.15)
        assert abs(eb["energy_out_w"] - expected) < 1e-6
        assert eb["energy_in_w"] == 9000.0


def _write_loyly_yaml(tmp_path: Path, water_ml: float = 100, **overrides) -> Path:
    """Helper to create a case YAML with löyly parameters."""
    data = {
        "case": {"name": "loyly_test", "description": "test", "type": "transient"},
        "geometry": {
            "dimensions": {"x": 3.0, "y": 2.5, "z": 2.5},
            "mesh_level": "M0",
        },
        "boundary_conditions": {
            "walls": {"temperature": 293.15, "type": "mixed"},
            "heater": {
                "power_kw": 9.0,
                "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                "width": 0.6,
                "height": 0.5,
            },
        },
        "solver": {
            "name": "buoyantPimpleFoam",
            "end_time": 300,
            "write_interval": 10,
            "delta_t": 0.05,
            "averaging_start": 150,
        },
        "loyly": {
            "water_ml": water_ml,
            "time": 0.0,
            "tau_evap": 5.0,
        },
        "probes": [
            {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
            {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
            {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
        ],
    }
    for key, val in overrides.items():
        if key == "power_kw":
            data["boundary_conditions"]["heater"]["power_kw"] = val
        elif key == "steam_temp_c":
            data["loyly"]["steam_temp_c"] = val
    path = tmp_path / "loyly_case.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


def _write_aufguss_yaml(tmp_path: Path, beta_aug: float = 0.5,
                         start_time: float = 0.0,
                         duration: float = 1000.0) -> Path:
    """Helper to create a case YAML with aufguss parameters."""
    data = {
        "case": {"name": "aufguss_test", "description": "test", "type": "steady"},
        "geometry": {
            "dimensions": {"x": 3.0, "y": 2.5, "z": 2.5},
            "mesh_level": "M0",
        },
        "boundary_conditions": {
            "walls": {"temperature": 293.15, "type": "mixed"},
            "heater": {
                "power_kw": 9.0,
                "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                "width": 0.6,
                "height": 0.5,
            },
        },
        "solver": {
            "name": "buoyantPimpleFoam",
            "end_time": 300,
            "write_interval": 10,
            "delta_t": 0.05,
            "averaging_start": 150,
        },
        "aufguss": {
            "beta_aug": beta_aug,
            "start_time": start_time,
            "duration": duration,
        },
        "probes": [
            {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
            {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
            {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
        ],
    }
    path = tmp_path / "aufguss_case.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


class TestSteamPhysics:
    def test_evaporation_rate_basic(self) -> None:
        """Rate is positive at t=0 and decays over time."""
        rate_0 = _evaporation_rate(0.1, 0.0)
        rate_5 = _evaporation_rate(0.1, 5.0)
        rate_20 = _evaporation_rate(0.1, 20.0)
        assert rate_0 > 0
        assert rate_5 < rate_0  # decays
        assert rate_20 < rate_5  # continues decaying

    def test_evaporation_rate_zero_water(self) -> None:
        """Zero water mass gives zero rate."""
        assert _evaporation_rate(0.0, 0.0) == 0.0
        assert _evaporation_rate(0.0, 5.0) == 0.0
        assert _evaporation_rate(-1.0, 0.0) == 0.0

    def test_loyly_changes_humidity_and_properties(self, tmp_path: Path) -> None:
        """Löyly steam adds humidity which changes air properties.

        Latent heat comes from stones (not air), so T_upper is NOT boosted.
        Instead, humidity affects cp_mix and h_wall_eff, altering the
        pseudo-steady equilibrium. The key assertion is that humidity is
        positive and perceived temperature changes.
        """
        (tmp_path / "dry").mkdir()
        (tmp_path / "wet").mkdir()
        dry_path = _write_case_yaml(tmp_path / "dry")
        wet_path = _write_loyly_yaml(tmp_path / "wet", water_ml=500)
        dry_result = solve_two_zone(dry_path, max_iter=10000)
        wet_result = solve_two_zone(wet_path, max_iter=10000)
        # Humidity should be positive with steam
        assert wet_result.humidity_ratio > 0.0
        # Perceived temperature should differ due to humidity effects
        assert wet_result.perceived_temp_upper != dry_result.perceived_temp_upper

    def test_steam_fields_in_result(self, tmp_path: Path) -> None:
        """New steam fields exist and are non-negative."""
        path = _write_loyly_yaml(tmp_path, water_ml=100)
        result = solve_two_zone(path, max_iter=10000)
        assert result.steam_mass_flow >= 0.0
        assert result.total_steam_generated >= 0.0
        # With 100mL of water, should have positive steam
        assert result.steam_mass_flow > 0.0
        assert result.total_steam_generated > 0.0


class TestLoylySensibleHeat:
    """C3: löyly steam carries sensible heat into the air (dry-bulb peak)."""

    def test_steam_adds_dry_bulb_heat_vs_dry(self, tmp_path: Path) -> None:
        """During the löyly window, wet T_upper exceeds the dry case.

        The hot steam deposits sensible enthalpy on top of the humidity rise,
        producing the dry-bulb bump that K-02/K-04 are meant to capture.
        """
        (tmp_path / "dry").mkdir()
        (tmp_path / "wet").mkdir()
        dry_path = _write_case_yaml(tmp_path / "dry")
        wet_path = _write_loyly_yaml(tmp_path / "wet", water_ml=200)
        dry = solve_transient(dry_path, end_time=60.0, physical_dt=0.5, record_interval=1.0)
        wet = solve_transient(wet_path, end_time=60.0, physical_dt=0.5, record_interval=1.0)
        # In the first 30 s (löyly burst), wet must rise above dry somewhere.
        early = wet.time <= 30.0
        max_excess = float((wet.t_upper_series[early] - dry.t_upper_series[early]).max())
        assert max_excess > 0.0, f"steam should add sensible heat, excess={max_excess:.3f}"

    def test_hotter_steam_gives_higher_peak(self, tmp_path: Path) -> None:
        """Higher steam injection temperature deposits more sensible heat."""
        (tmp_path / "cool").mkdir()
        (tmp_path / "hot").mkdir()
        cool = _write_loyly_yaml(tmp_path / "cool", water_ml=300)
        hot = _write_loyly_yaml(tmp_path / "hot", water_ml=300, steam_temp_c=300.0)
        r_cool = solve_transient(cool, end_time=60.0, physical_dt=0.5, record_interval=1.0)
        r_hot = solve_transient(hot, end_time=60.0, physical_dt=0.5, record_interval=1.0)
        # The steam-temperature effect acts only during the brief injection
        # burst; the global max is dominated by ongoing room warming, so compare
        # within the löyly window where the sensible term actually differs.
        early = r_cool.time <= 25.0
        assert float(r_hot.t_upper_series[early].max()) > float(r_cool.t_upper_series[early].max())

    def test_latent_heat_not_double_counted(self, tmp_path: Path) -> None:
        """Sensible bump stays bounded — steam does not dump latent heat into air.

        A 200 mL löyly should not raise the peak by more than a few K above the
        dry case; the latent heat comes from the stones, only the modest steam
        sensible term enters the air.
        """
        (tmp_path / "dry").mkdir()
        (tmp_path / "wet").mkdir()
        dry = solve_transient(_write_case_yaml(tmp_path / "dry"),
                              end_time=60.0, physical_dt=0.5, record_interval=1.0)
        wet = solve_transient(_write_loyly_yaml(tmp_path / "wet", water_ml=200),
                              end_time=60.0, physical_dt=0.5, record_interval=1.0)
        excess = float(wet.t_upper_series.max() - dry.t_upper_series.max())
        assert excess < 15.0, f"sensible bump implausibly large ({excess:.1f} K) — latent leak?"


class TestRadiationModel:
    """C9/C4: lumped is the default; radiation never heats air directly."""

    def _case(self, tmp_path: Path, model: str | None) -> Path:
        path = _write_case_yaml(tmp_path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if model is None:
            data["boundary_conditions"]["walls"].pop("model", None)
        else:
            data["boundary_conditions"]["walls"]["model"] = model
        path.write_text(yaml.dump(data), encoding="utf-8")
        return path

    def test_default_wall_model_is_lumped(self, tmp_path: Path) -> None:
        """A case omitting walls.model behaves like explicit lumped, not fixed."""
        (tmp_path / "def").mkdir()
        (tmp_path / "lump").mkdir()
        (tmp_path / "fix").mkdir()
        r_default = solve_two_zone(self._case(tmp_path / "def", None), max_iter=4000)
        r_lumped = solve_two_zone(self._case(tmp_path / "lump", "lumped"), max_iter=4000)
        r_fixed = solve_two_zone(self._case(tmp_path / "fix", "fixed"), max_iter=4000)
        assert abs(r_default.upper_layer_temp - r_lumped.upper_layer_temp) < 1e-6
        assert abs(r_default.upper_layer_temp - r_fixed.upper_layer_temp) > 1.0

    def test_fixed_mode_has_no_radiant_air_heating(self, tmp_path: Path) -> None:
        """Fixed (constant-T) walls lose the radiant fraction, so the room is
        cooler than the lumped model where walls re-warm the air."""
        (tmp_path / "lump").mkdir()
        (tmp_path / "fix").mkdir()
        r_lumped = solve_two_zone(self._case(tmp_path / "lump", "lumped"), max_iter=4000)
        r_fixed = solve_two_zone(self._case(tmp_path / "fix", "fixed"), max_iter=4000)
        assert r_fixed.upper_layer_temp < r_lumped.upper_layer_temp

    def test_radiant_distribution_alias_and_closure(self) -> None:
        assert _compute_view_factors is _radiant_distribution
        d = _radiant_distribution(3.0, 2.5, 2.5, 0.1, 0.5, 0.6)
        assert "body" in d
        assert 0.8 <= sum(d.values()) <= 1.2  # closure (not reciprocity)


class TestParameterization:
    """Newly YAML-exposed model constants: convective_fraction, h_natural."""

    def _case(self, tmp_path: Path, **walls_heater) -> Path:
        path = _write_case_yaml(tmp_path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["boundary_conditions"]["walls"]["model"] = "lumped"
        for key in ("convective_fraction",):
            if key in walls_heater:
                data["boundary_conditions"]["heater"][key] = walls_heater[key]
        for key in ("h_natural",):
            if key in walls_heater:
                data["boundary_conditions"]["walls"][key] = walls_heater[key]
        path.write_text(yaml.dump(data), encoding="utf-8")
        return path

    def test_default_matches_explicit_nominal(self, tmp_path: Path) -> None:
        """Omitting the keys equals setting them to the historical defaults."""
        (tmp_path / "d").mkdir()
        (tmp_path / "e").mkdir()
        r_default = solve_two_zone(self._case(tmp_path / "d"), max_iter=3000)
        r_explicit = solve_two_zone(
            self._case(tmp_path / "e", convective_fraction=0.7, h_natural=8.0),
            max_iter=3000,
        )
        assert abs(r_default.upper_layer_temp - r_explicit.upper_layer_temp) < 1e-6

    def test_higher_convective_fraction_warms_air(self, tmp_path: Path) -> None:
        (tmp_path / "lo").mkdir()
        (tmp_path / "hi").mkdir()
        r_lo = solve_two_zone(self._case(tmp_path / "lo", convective_fraction=0.5), max_iter=3000)
        r_hi = solve_two_zone(self._case(tmp_path / "hi", convective_fraction=0.9), max_iter=3000)
        assert r_hi.upper_layer_temp > r_lo.upper_layer_temp

    def test_higher_h_natural_cools_air(self, tmp_path: Path) -> None:
        (tmp_path / "lo").mkdir()
        (tmp_path / "hi").mkdir()
        r_lo = solve_two_zone(self._case(tmp_path / "lo", h_natural=6.0), max_iter=3000)
        r_hi = solve_two_zone(self._case(tmp_path / "hi", h_natural=16.0), max_iter=3000)
        assert r_hi.upper_layer_temp < r_lo.upper_layer_temp

    def test_humid_air_h_wall_base_scales_htc(self) -> None:
        from harness.simple_solver import _humid_air_properties
        p8 = _humid_air_properties(350.0, 0.0, h_wall_base=8.0)
        p16 = _humid_air_properties(350.0, 0.0, h_wall_base=16.0)
        # Dry air: h_ratio == 1, so h_wall_eff == h_wall_base.
        assert abs(p8["h_wall_eff"] - 8.0) < 1e-9
        assert abs(p16["h_wall_eff"] - 16.0) < 1e-9


class TestSteadyAufgussWarning:
    """C5: Aufguss is transient; the steady solver warns it is a surrogate."""

    def test_steady_aufguss_warns(self, tmp_path: Path) -> None:
        import warnings as _w
        path = _write_aufguss_yaml(tmp_path, beta_aug=0.5)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            solve_two_zone(path, max_iter=2000)
        assert any("Aufguss" in str(c.message) for c in caught)

    def test_no_warning_without_aufguss(self, tmp_path: Path) -> None:
        import warnings as _w
        path = _write_case_yaml(tmp_path)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            solve_two_zone(path, max_iter=2000)
        assert not any("Aufguss" in str(c.message) for c in caught)

    def test_aufguss_face_velocity_populated(self, tmp_path: Path) -> None:
        """K-05 free-jet face velocity is set when Aufguss is active, else 0."""
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            r_aug = solve_two_zone(_write_aufguss_yaml(tmp_path, beta_aug=0.5), max_iter=2000)
        # defaults jet_velocity=2.0, d0=0.15, x=1.0 -> 2.0*6.2*0.15/1.0 = 1.86
        assert abs(r_aug.aufguss_face_velocity - 1.86) < 1e-6
        (tmp_path / "dry").mkdir()
        r_dry = solve_two_zone(_write_case_yaml(tmp_path / "dry"), max_iter=2000)
        assert r_dry.aufguss_face_velocity == 0.0


class TestViewFactors:
    def test_view_factors_sum_reasonable(self) -> None:
        """All view factors positive and sum approximately 1.0."""
        vf = _compute_view_factors(3.0, 2.5, 2.5, 0.1, 0.5, 0.6)
        assert all(v > 0 for v in vf.values())
        assert "body" in vf
        total = sum(vf.values())
        assert 0.8 <= total <= 1.2  # approximately 1.0

    def test_view_factors_heater_low(self) -> None:
        """Heater near floor should have higher floor factor."""
        vf_low = _compute_view_factors(3.0, 2.5, 2.5, 0.05, 0.3, 0.6)
        vf_high = _compute_view_factors(3.0, 2.5, 2.5, 1.5, 0.3, 0.6)
        assert vf_low["floor"] > vf_high["floor"]

    def test_view_factors_heater_high(self) -> None:
        """Heater near ceiling should have higher ceiling factor."""
        vf_low = _compute_view_factors(3.0, 2.5, 2.5, 0.05, 0.3, 0.6)
        vf_high = _compute_view_factors(3.0, 2.5, 2.5, 1.8, 0.3, 0.6)
        assert vf_high["ceiling"] > vf_low["ceiling"]

    def test_view_factor_replaces_fixed(self, tmp_path: Path) -> None:
        """Solver with view factors still converges."""
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.converged is True
        assert result.upper_layer_temp > result.lower_layer_temp


class TestPerceivedTemperature:
    def test_dry_hot_air_above_skin_temp(self) -> None:
        """At 80C dry air, perceived temp should exceed skin temperature."""
        t_eq = _perceived_temperature(80.0, 0.0)
        assert t_eq > 36.0

    def test_increases_with_humidity(self) -> None:
        """Higher humidity at same temperature should raise perceived temp."""
        t_dry = _perceived_temperature(80.0, 0.1)
        t_humid = _perceived_temperature(80.0, 0.6)
        assert t_humid > t_dry

    def test_sauna_range_reasonable(self) -> None:
        """At 80C / 20% RH (typical dry sauna), perceived temp in a sensible range."""
        t_eq = _perceived_temperature(80.0, 0.2)
        # Should be above air temp (convective + evap suppression heating)
        # but not absurdly high
        assert 40.0 < t_eq < 200.0

    def test_increases_with_radiation(self) -> None:
        """Direct radiation should raise perceived temperature."""
        t_no_rad = _perceived_temperature(80.0, 0.2, q_rad_body=0.0)
        t_with_rad = _perceived_temperature(80.0, 0.2, q_rad_body=200.0)
        assert t_with_rad > t_no_rad

    def test_below_skin_temp_feels_cool(self) -> None:
        """At 20C dry air, perceived temp should be below skin temperature."""
        t_eq = _perceived_temperature(20.0, 0.3)
        assert t_eq < 36.0

    def test_condensation_at_extreme_humidity(self) -> None:
        """At 100C / 100% RH, condensation should raise perceived temp significantly."""
        t_low_rh = _perceived_temperature(100.0, 0.1)
        t_high_rh = _perceived_temperature(100.0, 1.0)
        assert t_high_rh > t_low_rh


class TestQRadBody:
    def test_positive_flux(self) -> None:
        """Radiative flux from a hot heater to body should be positive."""
        q = _q_rad_body(9000.0, 0.7, 0.03, 0.6, 0.5, 350.0)
        assert q > 0.0

    def test_increases_with_power(self) -> None:
        """Higher heater power should give higher radiative flux."""
        q_lo = _q_rad_body(5000.0, 0.7, 0.03, 0.6, 0.5, 350.0)
        q_hi = _q_rad_body(15000.0, 0.7, 0.03, 0.6, 0.5, 350.0)
        assert q_hi > q_lo

    def test_increases_with_view_factor(self) -> None:
        """Larger view factor means more radiation reaches the body."""
        q_lo = _q_rad_body(9000.0, 0.7, 0.01, 0.6, 0.5, 350.0)
        q_hi = _q_rad_body(9000.0, 0.7, 0.08, 0.6, 0.5, 350.0)
        assert q_hi > q_lo


class TestBetaAug:
    def test_no_aufguss_default(self, tmp_path: Path) -> None:
        """Standard case without aufguss key should have beta_aug_applied == 0.0."""
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.beta_aug_applied == 0.0

    def test_aufguss_reduces_stratification(self, tmp_path: Path) -> None:
        """With aufguss, upper-lower temp difference should be smaller than dry case."""
        (tmp_path / "dry").mkdir()
        (tmp_path / "aug").mkdir()
        path_dry = _write_case_yaml(tmp_path / "dry")
        path_aug = _write_aufguss_yaml(tmp_path / "aug", beta_aug=0.5)

        r_dry = solve_two_zone(path_dry, max_iter=10000)
        r_aug = solve_two_zone(path_aug, max_iter=10000)

        strat_dry = r_dry.upper_layer_temp - r_dry.lower_layer_temp
        strat_aug = r_aug.upper_layer_temp - r_aug.lower_layer_temp

        assert strat_aug < strat_dry, (
            f"Aufguss should reduce stratification: dry={strat_dry:.2f}, aug={strat_aug:.2f}"
        )

    def test_aufguss_energy_conservation(self, tmp_path: Path) -> None:
        """With aufguss, total energy should be approximately conserved.

        The mixing transfers heat from upper to lower but does not create energy.
        Compare total thermal energy (m*cp*T) between aufguss and dry cases:
        they should be similar since aufguss only redistributes, not adds, heat.
        """
        (tmp_path / "dry").mkdir()
        (tmp_path / "aug").mkdir()
        path_dry = _write_case_yaml(tmp_path / "dry")
        path_aug = _write_aufguss_yaml(tmp_path / "aug", beta_aug=0.5)

        r_dry = solve_two_zone(path_dry, max_iter=10000)
        r_aug = solve_two_zone(path_aug, max_iter=10000)

        # Approximate total energy as average temperature across the profile
        avg_t_dry = float(r_dry.temperatures.mean())
        avg_t_aug = float(r_aug.temperatures.mean())

        # They should be within a few degrees — mixing redistributes, not creates
        assert abs(avg_t_aug - avg_t_dry) < 10.0, (
            f"Aufguss should conserve energy: dry_avg={avg_t_dry:.2f}, aug_avg={avg_t_aug:.2f}"
        )


class TestTransientSolver:
    def test_transient_returns_time_series(self, tmp_path: Path) -> None:
        """Transient solver on dry case returns arrays of correct length."""
        path = _write_case_yaml(tmp_path)
        result = solve_transient(path, end_time=50.0, physical_dt=1.0, record_interval=1.0)
        assert isinstance(result, TransientResult)
        # Should have ~51 records (t=0, 1, 2, ..., 50)
        expected_len = int(50.0 / 1.0) + 1
        assert len(result.time) == expected_len
        assert len(result.t_upper_series) == expected_len
        assert len(result.t_lower_series) == expected_len
        assert len(result.z_int_series) == expected_len
        assert len(result.humidity_series) == expected_len
        assert len(result.wall_temp_series) == expected_len
        assert len(result.perceived_upper_series) == expected_len
        # Time should be monotonically increasing
        assert all(result.time[i] < result.time[i + 1] for i in range(len(result.time) - 1))

    def test_transient_loyly_peak(self, tmp_path: Path) -> None:
        """Loyly transient should show T_upper peak above dry steady-state T_upper."""
        (tmp_path / "dry").mkdir()
        (tmp_path / "wet").mkdir()
        dry_path = _write_case_yaml(tmp_path / "dry")
        wet_path = _write_loyly_yaml(tmp_path / "wet", water_ml=2000)

        # Get dry steady-state reference
        dry_steady = solve_two_zone(dry_path, max_iter=10000)

        # Run transient with loyly
        wet_trans = solve_transient(wet_path, end_time=150.0, physical_dt=0.5, record_interval=1.0)

        # The peak T_upper during transient should exceed the dry steady-state value
        peak_t_upper = float(wet_trans.t_upper_series.max())
        assert peak_t_upper > dry_steady.upper_layer_temp, (
            f"Loyly peak {peak_t_upper:.1f} K should exceed dry steady {dry_steady.upper_layer_temp:.1f} K"
        )

    def test_transient_aufguss_mixing(self, tmp_path: Path) -> None:
        """Aufguss should reduce stratification during its active window."""
        path = _write_aufguss_yaml(
            tmp_path, beta_aug=0.5, start_time=30.0, duration=40.0,
        )
        result = solve_transient(path, end_time=100.0, physical_dt=1.0, record_interval=1.0)

        # Stratification = T_upper - T_lower
        strat = result.t_upper_series - result.t_lower_series

        # Find stratification just before aufguss starts and during aufguss
        idx_before = int(25.0 / 1.0)  # t=25s, before aufguss
        idx_during = int(60.0 / 1.0)  # t=60s, during aufguss

        assert strat[idx_during] < strat[idx_before], (
            f"Aufguss should reduce stratification: before={strat[idx_before]:.2f}, "
            f"during={strat[idx_during]:.2f}"
        )

    def test_transient_matches_steady(self, tmp_path: Path) -> None:
        """After long enough transient, final state should approach steady-state."""
        path = _write_case_yaml(tmp_path)
        steady = solve_two_zone(path, max_iter=10000)
        trans = solve_transient(path, end_time=2000.0, physical_dt=1.0, record_interval=10.0)

        # Final transient T_upper should be close to steady-state T_upper
        final_t_upper = float(trans.t_upper_series[-1])
        assert abs(final_t_upper - steady.upper_layer_temp) < 5.0, (
            f"Transient final {final_t_upper:.1f} K vs steady {steady.upper_layer_temp:.1f} K"
        )


def _write_vent_yaml(tmp_path: Path, **overrides) -> Path:
    """Helper to create a case YAML with natural ventilation."""
    data = {
        "case": {"name": "vent_test", "description": "test", "type": "steady"},
        "geometry": {
            "dimensions": {"x": 3.0, "y": 2.5, "z": 2.5},
            "mesh_level": "M0",
        },
        "boundary_conditions": {
            "walls": {"temperature": 293.15, "type": "mixed"},
            "heater": {
                "power_kw": 9.0,
                "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                "width": 0.6,
                "height": 0.5,
            },
        },
        "solver": {
            "name": "buoyantPimpleFoam",
            "end_time": 300,
            "write_interval": 10,
            "delta_t": 0.05,
            "averaging_start": 150,
        },
        "ventilation": {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.02, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.02, "Cd": 0.6},
            "T_ambient": 293.15,
            "w_ambient": 0.005,
        },
        "probes": [
            {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
            {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
            {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
        ],
    }
    for key, val in overrides.items():
        if key == "vent_area":
            data["ventilation"]["supply"]["area"] = val
            data["ventilation"]["exhaust"]["area"] = val
    path = tmp_path / "vent_case.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


class TestVentilationFlow:
    def test_zero_delta_t_gives_zero_flow(self) -> None:
        """When interior equals ambient, no stack-driven flow."""
        cfg = {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.02, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.02, "Cd": 0.6},
            "T_ambient": 350.0,
        }
        m = _ventilation_flow(350.0, 350.0, 1.5, cfg)
        assert m == 0.0

    def test_positive_flow_when_hot(self) -> None:
        """Stack effect drives positive flow when interior is hotter."""
        cfg = {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.02, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.02, "Cd": 0.6},
            "T_ambient": 293.15,
        }
        m = _ventilation_flow(370.0, 320.0, 1.5, cfg)
        assert m > 0.0

    def test_higher_temp_more_flow(self) -> None:
        """Higher interior temperature should drive more ventilation flow."""
        cfg = {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.02, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.02, "Cd": 0.6},
            "T_ambient": 293.15,
        }
        m_lo = _ventilation_flow(340.0, 310.0, 1.5, cfg)
        m_hi = _ventilation_flow(400.0, 340.0, 1.5, cfg)
        assert m_hi > m_lo

    def test_larger_area_more_flow(self) -> None:
        """Larger vent area should increase flow rate."""
        cfg_small = {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.01, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.01, "Cd": 0.6},
            "T_ambient": 293.15,
        }
        cfg_large = {
            "model": "natural",
            "supply": {"height": 0.3, "area": 0.04, "Cd": 0.6},
            "exhaust": {"height": 2.0, "area": 0.04, "Cd": 0.6},
            "T_ambient": 293.15,
        }
        m_small = _ventilation_flow(370.0, 320.0, 1.5, cfg_small)
        m_large = _ventilation_flow(370.0, 320.0, 1.5, cfg_large)
        assert m_large > m_small

    def test_inverted_vents_zero_flow(self) -> None:
        """Exhaust below supply gives zero flow."""
        cfg = {
            "model": "natural",
            "supply": {"height": 2.0, "area": 0.02, "Cd": 0.6},
            "exhaust": {"height": 0.3, "area": 0.02, "Cd": 0.6},
            "T_ambient": 293.15,
        }
        m = _ventilation_flow(370.0, 320.0, 1.5, cfg)
        assert m == 0.0


class TestVentilationIntegration:
    def test_vent_converges(self, tmp_path: Path) -> None:
        """Solver with ventilation should converge."""
        path = _write_vent_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.converged is True

    def test_vent_reduces_upper_temp(self, tmp_path: Path) -> None:
        """Ventilation should cool the upper layer compared to sealed case."""
        (tmp_path / "sealed").mkdir()
        (tmp_path / "vent").mkdir()
        path_sealed = _write_case_yaml(tmp_path / "sealed")
        path_vent = _write_vent_yaml(tmp_path / "vent")

        r_sealed = solve_two_zone(path_sealed, max_iter=10000)
        r_vent = solve_two_zone(path_vent, max_iter=10000)

        assert r_vent.upper_layer_temp < r_sealed.upper_layer_temp, (
            f"Ventilation should cool: sealed={r_sealed.upper_layer_temp:.1f} K, "
            f"vent={r_vent.upper_layer_temp:.1f} K"
        )

    def test_vent_mass_flow_positive(self, tmp_path: Path) -> None:
        """Ventilation mass flow rate should be positive in the result."""
        path = _write_vent_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.vent_mass_flow > 0.0

    def test_no_vent_default(self, tmp_path: Path) -> None:
        """Standard case without ventilation key should have zero vent flow."""
        path = _write_case_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.vent_mass_flow == 0.0

    def test_vent_none_model_disabled(self, tmp_path: Path) -> None:
        """Ventilation with model='none' should behave as sealed."""
        data = {
            "case": {"name": "test", "description": "test", "type": "steady"},
            "geometry": {
                "dimensions": {"x": 3.0, "y": 2.5, "z": 2.5},
                "mesh_level": "M0",
            },
            "boundary_conditions": {
                "walls": {"temperature": 293.15, "type": "mixed"},
                "heater": {
                    "power_kw": 9.0,
                    "position": {"x": 0.0, "y": 0.1, "z": 1.25},
                    "width": 0.6,
                    "height": 0.5,
                },
            },
            "solver": {
                "name": "buoyantPimpleFoam",
                "end_time": 300,
                "write_interval": 10,
                "delta_t": 0.05,
                "averaging_start": 150,
            },
            "ventilation": {"model": "none"},
            "probes": [
                {"name": "upper_bench", "position": {"x": 1.5, "y": 2.0, "z": 1.25}},
                {"name": "lower_bench", "position": {"x": 1.5, "y": 0.8, "z": 1.25}},
                {"name": "floor_level", "position": {"x": 1.5, "y": 0.1, "z": 1.25}},
            ],
        }
        path = tmp_path / "vent_none.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        result = solve_two_zone(path, max_iter=10000)
        assert result.vent_mass_flow == 0.0

    def test_vent_stratification_preserved(self, tmp_path: Path) -> None:
        """Even with ventilation, upper layer should still be hotter than lower."""
        path = _write_vent_yaml(tmp_path)
        result = solve_two_zone(path, max_iter=10000)
        assert result.upper_layer_temp > result.lower_layer_temp

    def test_transient_vent_cools(self, tmp_path: Path) -> None:
        """Transient solver with ventilation should also show cooling effect."""
        (tmp_path / "sealed").mkdir()
        (tmp_path / "vent").mkdir()
        path_sealed = _write_case_yaml(tmp_path / "sealed")
        path_vent = _write_vent_yaml(tmp_path / "vent")

        r_sealed = solve_transient(path_sealed, end_time=500.0, physical_dt=1.0, record_interval=10.0)
        r_vent = solve_transient(path_vent, end_time=500.0, physical_dt=1.0, record_interval=10.0)

        # Final upper temp with vent should be lower
        assert float(r_vent.t_upper_series[-1]) < float(r_sealed.t_upper_series[-1]), (
            f"Ventilation transient should cool: sealed={float(r_sealed.t_upper_series[-1]):.1f} K, "
            f"vent={float(r_vent.t_upper_series[-1]):.1f} K"
        )
