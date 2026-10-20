"""FAO-56 worked examples (Allen et al. 1998)."""

from __future__ import annotations

import pytest

from agroeco_pipeline.et0 import (
    DailyWeather,
    et0_penman_monteith,
    extraterrestrial_radiation,
    psychrometric_constant,
    sat_vapour_pressure,
    wind_at_2m,
)


def test_example_8_extraterrestrial_radiation() -> None:
    # 3 September (day 246) at 20°S: Ra = 32.2 MJ m-2 day-1.
    assert extraterrestrial_radiation(-20.0, 246) == pytest.approx(32.2, abs=0.1)


def test_saturation_vapour_pressure_table() -> None:
    # Annex 2 Table 2.3: e°(25 °C) = 3.168 kPa.
    assert sat_vapour_pressure(25.0) == pytest.approx(3.168, abs=0.001)


def test_psychrometric_constant_example_2() -> None:
    # Example 2: elevation 1800 m -> gamma = 0.054 kPa/°C.
    assert psychrometric_constant(1800) == pytest.approx(0.054, abs=0.001)


def test_example_14_wind_conversion() -> None:
    # 3.2 m/s at 10 m -> 2.4 m/s at 2 m.
    assert wind_at_2m(3.2, 10) == pytest.approx(2.4, abs=0.05)


def test_example_18_brussels_6_july() -> None:
    # Brussels, 50°48'N, 100 m, 6 July (day 187): ET0 = 3.9 mm/day.
    w = DailyWeather(
        day_of_year=187,
        t_max=21.5,
        t_min=12.3,
        rh_max=84,
        rh_min=63,
        solar_mj=22.07,
        wind_2m=2.078,
    )
    r = et0_penman_monteith(w, latitude_deg=50.8, elevation_m=100)
    assert r.ra == pytest.approx(41.09, abs=0.1)
    assert r.rn == pytest.approx(13.28, abs=0.1)
    assert r.et0_mm == pytest.approx(3.9, abs=0.05)


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        extraterrestrial_radiation(30, 0)
    with pytest.raises(ValueError):
        wind_at_2m(3, 0)
    with pytest.raises(ValueError):
        et0_penman_monteith(DailyWeather(100, 10, 20, 90, 50, 20, 2), 30, 10)
