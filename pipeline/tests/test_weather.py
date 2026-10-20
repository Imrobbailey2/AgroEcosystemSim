"""Weather column mapping, daily aggregation and year selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.common import PipelineError  # noqa: E402
from agroeco_pipeline.weather import (  # noqa: E402
    aggregate_daily,
    find_station,
    map_columns,
    parse_day,
    select_years,
)
from fixtures import daily_rows  # noqa: E402

HEADERS_METRIC = ["StationID", "Period", "temp_air_2m_C", "rh_2m_pct", "rain_2m_mm",
                  "rfd_2m_wm2", "wind_speed_10m_m/s", "wind_direction_10m_deg", "temp_air_60cm_C"]
HEADERS_US = ["Timestamp", "Air Temp 2m (°F)", "Relative Humidity (%)", "Rainfall (in)",
              "Solar Radiation (W/m2)", "Wind Speed 10m (mph)"]


def test_map_columns_metric_and_us() -> None:
    m = map_columns(HEADERS_METRIC)
    assert (m["temp"].header, m["temp"].unit) == ("temp_air_2m_C", "C")
    assert m["wind"].unit == "m/s" and m["rain"].unit == "mm" and m["solar"].unit == "W/m2"
    u = map_columns(HEADERS_US)
    assert (u["temp"].unit, u["rain"].unit, u["wind"].unit) == ("F", "in", "mph")


def test_map_columns_fails_loudly() -> None:
    with pytest.raises(PipelineError, match="temp"):
        map_columns(["Period", "rh_2m_pct", "rain_2m_mm", "rfd_2m_wm2", "wind_speed_10m_m/s"])


def test_parse_day_formats() -> None:
    assert parse_day("2012-05-01 00:15:00").isoformat() == "2012-05-01"
    assert parse_day("05/01/2012 23:45").isoformat() == "2012-05-01"
    with pytest.raises(PipelineError):
        parse_day("yesterday")


def _fifteen_minute_csv(days: int) -> str:
    lines = [",".join(HEADERS_US)]
    for d in range(days):
        for q in range(96):
            hh, mm = divmod(q * 15, 60)
            temp_f = 68 + 18 * (1 if 10 <= hh < 16 else 0)  # 20 °C or 30 °C
            solar = 500 if 8 <= hh < 18 else 0
            rain = 0.01 if q == 0 else 0
            lines.append(f"2012-06-{d + 1:02d} {hh:02d}:{mm:02d}:00,{temp_f},{60 + (hh % 2) * 30},"
                         f"{rain},{solar},{4.4738}")
    return "\n".join(lines) + "\n"


def test_aggregate_daily_units_and_et0() -> None:
    rows = aggregate_daily(_fifteen_minute_csv(2), latitude=30.3, elevation_m=50, wind_height_m=10)
    assert len(rows) == 2
    r = rows[0]
    assert (r["tmax_c"], r["tmin_c"]) == (30.0, 20.0)
    assert r["rain_mm"] == pytest.approx(0.254, abs=1e-3)
    assert r["solar_mj_m2"] == pytest.approx(500 * 40 / 96 * 0.0864, abs=0.01)
    # 4.4738 mph = 2.0 m/s at 10 m; FAO-56 Eq. 47: 2.0 * 4.87 / ln(67.8*10 - 5.42) = 1.496
    assert r["wind2m_ms"] == pytest.approx(1.496, abs=0.001)
    assert 3.0 < r["et0_mm"] < 7.0


def test_incomplete_days_dropped() -> None:
    text = _fifteen_minute_csv(1)
    short = "\n".join(text.splitlines()[:50]) + "\n"
    assert aggregate_daily(short, 30.3, 50, 10) == []


def test_select_years_dry_median_wet() -> None:
    rows = daily_rows([2010, 2011, 2012, 2013, 2014], {2010: 1.0, 2011: 0.5, 2012: 1.5, 2013: 0.9, 2014: 1.2})
    picks = select_years([{k: str(v) for k, v in r.items()} for r in rows], "04-01", "08-31")
    assert [(role, year) for role, year, _ in picks] == [("dry", 2011), ("median", 2010), ("wet", 2012)]
    with pytest.raises(PipelineError):
        select_years([{k: str(v) for k, v in r.items()} for r in daily_rows([2010, 2011], {2010: 1, 2011: 1})],
                     "04-01", "08-31")


def test_find_station() -> None:
    meta = "Station Name,StationID,Latitude,Longitude,Elevation (ft)\nLive Oak,170,30.30,-82.90,164\n"
    s = find_station(meta, 170, "Live Oak")
    assert s == {"latitude": 30.30, "longitude": -82.90, "elevation_m": 50.0}
    with pytest.raises(PipelineError):
        find_station(meta, 999, "Nowhere")
