"""FAO-56 Penman-Monteith reference evapotranspiration (daily time step).

Equation numbers refer to Allen, Pereira, Raes and Smith (1998), *Crop
evapotranspiration*, FAO Irrigation and Drainage Paper 56.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SOLAR_CONSTANT = 0.0820  # MJ m-2 min-1
STEFAN_BOLTZMANN = 4.903e-9  # MJ K-4 m-2 day-1
ALBEDO = 0.23


def sat_vapour_pressure(t_c: float) -> float:
    """Saturation vapour pressure e°(T) in kPa (Eq. 11)."""
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def slope_vapour_pressure(t_mean_c: float) -> float:
    """Slope of the saturation vapour pressure curve, kPa/°C (Eq. 13)."""
    return 4098.0 * sat_vapour_pressure(t_mean_c) / (t_mean_c + 237.3) ** 2


def psychrometric_constant(elevation_m: float) -> float:
    """Psychrometric constant γ in kPa/°C (Eqs. 7 and 8)."""
    pressure = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    return 0.665e-3 * pressure


def wind_at_2m(speed_ms: float, height_m: float) -> float:
    """Convert wind speed measured at `height_m` to 2 m (Eq. 47)."""
    if height_m <= 0:
        raise ValueError("wind measurement height must be positive")
    return speed_ms * 4.87 / math.log(67.8 * height_m - 5.42)


def extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    """Daily extraterrestrial radiation Ra in MJ m-2 day-1 (Eqs. 21-25)."""
    if not 1 <= day_of_year <= 366:
        raise ValueError(f"day_of_year out of range: {day_of_year}")
    phi = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return (
        24 * 60 / math.pi * SOLAR_CONSTANT * dr
        * (ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))
    )


@dataclass(frozen=True)
class DailyWeather:
    """Daily inputs for ET0. Units: °C, %, MJ m-2 day-1, m/s at 2 m."""

    day_of_year: int
    t_max: float
    t_min: float
    rh_max: float
    rh_min: float
    solar_mj: float
    wind_2m: float


@dataclass(frozen=True)
class Et0Result:
    et0_mm: float
    ra: float
    rso: float
    rn: float


def et0_penman_monteith(w: DailyWeather, latitude_deg: float, elevation_m: float) -> Et0Result:
    """Daily FAO-56 Penman-Monteith ET0 (Eq. 6), with G = 0 for daily steps."""
    if w.t_max < w.t_min:
        raise ValueError("t_max must be >= t_min")
    t_mean = (w.t_max + w.t_min) / 2
    es = (sat_vapour_pressure(w.t_max) + sat_vapour_pressure(w.t_min)) / 2  # Eq. 12
    ea = (
        sat_vapour_pressure(w.t_min) * w.rh_max / 100
        + sat_vapour_pressure(w.t_max) * w.rh_min / 100
    ) / 2  # Eq. 17
    ra = extraterrestrial_radiation(latitude_deg, w.day_of_year)
    rso = (0.75 + 2e-5 * elevation_m) * ra  # Eq. 37
    rns = (1 - ALBEDO) * w.solar_mj  # Eq. 38
    ratio = min(w.solar_mj / rso, 1.0) if rso > 0 else 0.0
    rnl = (
        STEFAN_BOLTZMANN
        * ((w.t_max + 273.16) ** 4 + (w.t_min + 273.16) ** 4) / 2
        * (0.34 - 0.14 * math.sqrt(max(ea, 0.0)))
        * (1.35 * ratio - 0.35)
    )  # Eq. 39
    rn = rns - rnl
    delta = slope_vapour_pressure(t_mean)
    gamma = psychrometric_constant(elevation_m)
    et0 = (0.408 * delta * rn + gamma * 900 / (t_mean + 273) * w.wind_2m * (es - ea)) / (
        delta + gamma * (1 + 0.34 * w.wind_2m)
    )
    return Et0Result(et0_mm=max(et0, 0.0), ra=ra, rso=rso, rn=rn)
