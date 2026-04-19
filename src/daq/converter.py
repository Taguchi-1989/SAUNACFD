"""Unit conversions for sensor data: °C→K, %RH→kg/kg."""

from __future__ import annotations

import math


def celsius_to_kelvin(t_c: float) -> float:
    """Convert temperature from Celsius to Kelvin."""
    return t_c + 273.15


def rh_to_absolute_humidity(
    rh_pct: float, t_kelvin: float, p_atm: float = 101325.0
) -> float:
    """Convert relative humidity to absolute humidity (mixing ratio).

    Args:
        rh_pct: Relative humidity in percent (0-100).
        t_kelvin: Air temperature in Kelvin.
        p_atm: Atmospheric pressure in Pa (default 101325 Pa).

    Returns:
        Absolute humidity w in kg vapor / kg dry air.
        Compatible with KPI K-03 which expects kg/kg.
    """
    if rh_pct <= 0.0:
        return 0.0

    t_c = t_kelvin - 273.15

    # Antoine equation coefficients for water (NIST)
    # Two ranges for better accuracy across sauna temperatures
    if t_c <= 100.0:
        a, b, c = 8.07131, 1730.63, 233.426
    else:
        a, b, c = 8.14019, 1810.94, 244.485

    # Saturation vapor pressure [Pa]
    log_psat = a - b / (c + t_c)
    p_sat_pa = math.pow(10.0, log_psat) * 133.322  # mmHg → Pa

    # Actual vapor pressure
    p_vapor = (rh_pct / 100.0) * p_sat_pa

    # Prevent division by zero / negative denominator
    denom = p_atm - p_vapor
    if denom <= 0.0:
        return 0.0

    # Mixing ratio (mass of vapor per mass of dry air)
    return 0.622 * p_vapor / denom
