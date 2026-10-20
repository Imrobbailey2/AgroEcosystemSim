"""FAWN gap-free weather: 15-minute CSV -> daily FAO-56 inputs -> weather years."""

from __future__ import annotations

import csv
import io
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from agroeco_pipeline.common import PipelineError, opt_float
from agroeco_pipeline.et0 import DailyWeather, et0_penman_monteith, wind_at_2m

ROLES = ("time", "temp", "rh", "rain", "solar", "wind")
DAILY_FIELDS = [
    "date", "doy", "tmax_c", "tmin_c", "rhmax_pct", "rhmin_pct",
    "rain_mm", "solar_mj_m2", "wind2m_ms", "et0_mm", "n_obs",
]
MIN_OBS_PER_DAY = 86  # 90% of 96 fifteen-minute observations


@dataclass(frozen=True)
class Column:
    index: int
    header: str
    unit: str


def _norm(header: str) -> str:
    h = header.lower().replace("°", "deg").replace("/", "_per_")
    return "_" + re.sub(r"[^a-z0-9]+", "_", h).strip("_") + "_"


def _unit(role: str, n: str, header: str) -> str:
    if role == "temp":
        if re.search(r"_(c|degc|celsius)_", n):
            return "C"
        if re.search(r"_(f|degf|fahrenheit)_", n):
            return "F"
    elif role == "rain":
        if "_mm_" in n:
            return "mm"
        if re.search(r"_(in|inch|inches)_", n):
            return "in"
    elif role == "wind":
        if re.search(r"_(m_per_s|ms|m_s|mps)_", n):
            return "m/s"
        if "_mph_" in n:
            return "mph"
    elif role == "solar":
        if re.search(r"_(w_per_m2|wm2|w_m2|w_per_m_2)_", n):
            return "W/m2"
    elif role == "rh":
        return "%"
    elif role == "time":
        return "local"
    raise PipelineError(f"cannot determine units for {role} column {header!r}")


def _matches(role: str, n: str) -> bool:
    if role == "time":
        return any(k in n for k in ("_time", "date", "period", "timestamp"))
    if role == "temp":
        return (
            any(k in n for k in ("temp", "tair", "_t_"))
            and re.search(r"_2_?m_", n) is not None
            and not any(k in n for k in ("dew", "soil", "wet", "60cm", "10m", "10_m"))
        )
    if role == "rh":
        return any(k in n for k in ("humid", "_rh_", "_rh"))
    if role == "rain":
        return any(k in n for k in ("rain", "precip"))
    if role == "solar":
        return any(k in n for k in ("solar", "rad", "rfd"))
    if role == "wind":
        return (
            "wind" in n
            and not any(k in n for k in ("dir", "max", "gust"))
        )
    return False


def map_columns(headers: list[str]) -> dict[str, Column]:
    """Identify the needed columns and their units, or fail with the header list."""
    found: dict[str, Column] = {}
    for role in ROLES:
        cands = [(i, h) for i, h in enumerate(headers) if _matches(role, _norm(h))]
        if len(cands) != 1:
            raise PipelineError(
                f"expected exactly one {role} column, found {[h for _, h in cands]} in {headers}"
            )
        i, h = cands[0]
        found[role] = Column(i, h, _unit(role, _norm(h), h))
    return found


_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                 "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")


def parse_day(text: str) -> date:
    t = text.strip().split("+")[0].rstrip("Z")
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise PipelineError(f"unrecognised timestamp {text!r}")


def _convert(role: str, unit: str, v: float) -> float:
    if role == "temp" and unit == "F":
        return (v - 32) * 5 / 9
    if role == "rain" and unit == "in":
        return v * 25.4
    if role == "wind" and unit == "mph":
        return v * 0.44704
    return v


def aggregate_daily(
    csv_text: str, latitude: float, elevation_m: float, wind_height_m: float
) -> list[dict[str, Any]]:
    """Aggregate one station's sub-daily CSV text into daily rows with ET0."""
    reader = csv.reader(io.StringIO(csv_text))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise PipelineError("empty weather file") from exc
    cols = map_columns(headers)
    buckets: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in reader:
        if not row or len(row) < len(headers):
            continue
        day = parse_day(row[cols["time"].index])
        for role in ("temp", "rh", "rain", "solar", "wind"):
            v = opt_float(row[cols[role].index])
            if v is not None:
                buckets[day][role].append(_convert(role, cols[role].unit, v))
    out = []
    for day in sorted(buckets):
        b = buckets[day]
        n = min(len(b[r]) for r in ("temp", "rh", "rain", "solar", "wind"))
        if n < MIN_OBS_PER_DAY:
            continue
        doy = day.timetuple().tm_yday
        w = DailyWeather(
            day_of_year=doy,
            t_max=max(b["temp"]),
            t_min=min(b["temp"]),
            rh_max=min(max(b["rh"]), 100.0),
            rh_min=max(min(b["rh"]), 0.0),
            solar_mj=max(statistics.fmean(b["solar"]), 0.0) * 0.0864,
            wind_2m=wind_at_2m(statistics.fmean(b["wind"]), wind_height_m),
        )
        et0 = et0_penman_monteith(w, latitude, elevation_m).et0_mm
        out.append(
            {
                "date": day.isoformat(),
                "doy": doy,
                "tmax_c": round(w.t_max, 2),
                "tmin_c": round(w.t_min, 2),
                "rhmax_pct": round(w.rh_max, 1),
                "rhmin_pct": round(w.rh_min, 1),
                "rain_mm": round(sum(b["rain"]), 3),  # 0.01 in = 0.254 mm resolution
                "solar_mj_m2": round(w.solar_mj, 3),
                "wind2m_ms": round(w.wind_2m, 3),
                "et0_mm": round(et0, 3),
                "n_obs": n,
            }
        )
    return out


def season_rain(rows: list[dict[str, Any]], year: int, start: str, end: str) -> float:
    lo, hi = f"{year}-{start}", f"{year}-{end}"
    return round(sum(float(r["rain_mm"]) for r in rows if lo <= r["date"] <= hi), 1)


def complete_years(rows: list[dict[str, Any]]) -> list[int]:
    counts: dict[int, int] = defaultdict(int)
    for r in rows:
        counts[int(r["date"][:4])] += 1
    return sorted(y for y, c in counts.items() if c >= 365)


def select_years(
    rows: list[dict[str, Any]], start: str, end: str
) -> list[tuple[str, int, float]]:
    """Pick the driest, median and wettest complete seasons (ties -> earlier year)."""
    years = complete_years(rows)
    if len(years) < 3:
        raise PipelineError(f"need at least 3 complete years, have {years}")
    totals = sorted((season_rain(rows, y, start, end), y) for y in years)
    dry = totals[0]
    wet = totals[-1]
    middle = totals[1:-1]
    med = statistics.median(t for t, _ in totals)
    median = min(middle, key=lambda ty: (abs(ty[0] - med), ty[1]))
    return [("dry", dry[1], dry[0]), ("median", median[1], median[0]), ("wet", wet[1], wet[0])]


def find_station(meta_text: str, station_id: int, station_name: str) -> dict[str, float]:
    """Find latitude, longitude and elevation (m) for a station in a metadata CSV."""
    reader = csv.reader(io.StringIO(meta_text))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise PipelineError("empty station metadata") from exc
    norm = [_norm(h) for h in headers]

    def idx(*keys: str) -> int:
        hits = [i for i, n in enumerate(norm) if any(k in n for k in keys)]
        if not hits:
            raise PipelineError(f"metadata lacks a {keys} column: {headers}")
        return hits[0]

    i_lat, i_lon, i_elev = idx("lat"), idx("lon"), idx("elev", "alt")
    elev_ft = "ft" in norm[i_elev] or "feet" in norm[i_elev]
    for row in reader:
        cells = [c.strip() for c in row]
        if str(station_id) in cells or any(station_name.lower() == c.lower() for c in cells):
            lat, lon, elev = (opt_float(cells[i]) for i in (i_lat, i_lon, i_elev))
            if lat is None or lon is None or elev is None:
                raise PipelineError(f"incomplete station row: {row}")
            return {
                "latitude": lat,
                "longitude": lon,
                "elevation_m": round(elev * 0.3048, 1) if elev_ft else elev,
            }
    raise PipelineError(f"station {station_id} / {station_name} not found in metadata")
