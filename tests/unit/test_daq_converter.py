"""Tests for daq.converter unit conversion functions."""

from __future__ import annotations

import pytest

from daq.converter import celsius_to_kelvin, rh_to_absolute_humidity


class TestCelsiusToKelvin:
    def test_zero(self) -> None:
        assert celsius_to_kelvin(0.0) == 273.15

    def test_boiling(self) -> None:
        assert celsius_to_kelvin(100.0) == 373.15

    def test_negative(self) -> None:
        assert abs(celsius_to_kelvin(-40.0) - 233.15) < 1e-10

    def test_sauna_lower_bench(self) -> None:
        assert celsius_to_kelvin(68.0) == 341.15

    def test_sauna_upper_bench(self) -> None:
        assert celsius_to_kelvin(108.0) == 381.15


class TestRhToAbsoluteHumidity:
    def test_zero_rh_returns_zero(self) -> None:
        assert rh_to_absolute_humidity(0.0, 300.0) == 0.0

    def test_negative_rh_returns_zero(self) -> None:
        assert rh_to_absolute_humidity(-5.0, 300.0) == 0.0

    def test_known_value_25c_50rh(self) -> None:
        # 25°C, 50%RH → ~0.00987 kg/kg (standard psychrometric tables)
        w = rh_to_absolute_humidity(50.0, 298.15)
        assert abs(w - 0.00987) < 0.001

    def test_known_value_20c_60rh(self) -> None:
        # 20°C, 60%RH → ~0.00873 kg/kg
        w = rh_to_absolute_humidity(60.0, 293.15)
        assert abs(w - 0.00873) < 0.001

    def test_high_temp_low_rh_positive(self) -> None:
        # 68°C, 10%RH — typical dry sauna at lower_bench
        w = rh_to_absolute_humidity(10.0, 341.15)
        assert w > 0.0

    def test_high_temp_saturation_pressure_increases(self) -> None:
        # Higher temperature at same RH → higher absolute humidity
        w_low = rh_to_absolute_humidity(50.0, 293.15)  # 20°C
        w_high = rh_to_absolute_humidity(50.0, 333.15)  # 60°C
        assert w_high > w_low

    def test_custom_pressure(self) -> None:
        # Lower pressure → higher mixing ratio at same RH and T
        w_std = rh_to_absolute_humidity(50.0, 298.15, p_atm=101325.0)
        w_low = rh_to_absolute_humidity(50.0, 298.15, p_atm=95000.0)
        assert w_low > w_std

    def test_above_100c_uses_high_range_coefficients(self) -> None:
        # 110°C, 5%RH — should not crash, should return positive
        w = rh_to_absolute_humidity(5.0, 383.15)
        assert w > 0.0
