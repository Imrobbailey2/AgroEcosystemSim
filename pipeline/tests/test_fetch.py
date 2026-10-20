"""Fetch steps with fake transports (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline import fetch  # noqa: E402
from agroeco_pipeline.common import PIPELINE_DIR, PipelineError, read_csv, read_json  # noqa: E402
from fixtures import make_xlsx  # noqa: E402

REGION = read_json(PIPELINE_DIR / "sources" / "regions" / "suwannee.json")
REGISTRY = {s["id"]: s for s in read_json(PIPELINE_DIR / "sources" / "sources.json")["sources"]}


def test_fetch_budgets_writes_cell_references(tmp_path: Path) -> None:
    def fake_get(url: str) -> bytes:
        rows = [["Crop yield (units/acre)", 205], ["Average delivered gross price ($/unit)", 4.5]]
        if "Rented" in url:
            rows.append(["Land rental cost", 140])
        return make_xlsx(rows)

    lock = fetch.Lock()
    fetch.fetch_budgets(REGION, REGISTRY, tmp_path, lock, get=fake_get)
    rented = read_csv(tmp_path / "budget_rented.csv")
    rent = next(r for r in rented if r["label"] == "Land rental cost")
    assert json.loads(rent["values"]) == [["B3", 140.0]]
    assert len(lock.entries) == 2 and all(len(e["sha256"]) == 64 for e in lock.entries)


def test_fetch_budgets_requires_rent_for_rented(tmp_path: Path) -> None:
    def fake_get(url: str) -> bytes:
        return make_xlsx([["Crop yield (units/acre)", 205], ["Average delivered gross price ($/unit)", 4.5]])

    with pytest.raises(PipelineError, match="Land rental cost"):
        fetch.fetch_budgets(REGION, REGISTRY, tmp_path, fetch.Lock(), get=fake_get)


def test_configured_station_converts_feet_and_validates() -> None:
    loc = REGION["weather"]["station_location"]
    s = fetch.configured_station(loc)
    assert (s["latitude"], s["longitude"], s["elevation_m"]) == (30.305, -82.89876, 50.3)
    assert s["location_source"] == "fawn-station-locations"
    assert loc["source"] in REGISTRY
    with pytest.raises(PipelineError, match="latitude"):
        fetch.configured_station({k: v for k, v in loc.items() if k != "latitude"})
    with pytest.raises(PipelineError, match="elevation"):
        fetch.configured_station({k: v for k, v in loc.items() if k != "elevation_ft"})


def test_fetch_weather_uses_configured_location_without_metadata_file(tmp_path: Path) -> None:
    header = "Period,temp_air_2m_C,rh_2m_pct,rain_2m_mm,rfd_2m_wm2,wind_speed_10m_m/s\n"
    body = "".join(f"2010-06-01 {q // 4:02d}:{q % 4 * 15:02d}:00,25,70,0,300,2\n" for q in range(96))
    article = {"files": [{"name": "170_2010.csv", "download_url": "https://example.test/170_2010.csv"}]}

    def fake_get(url: str) -> bytes:
        return json.dumps(article).encode() if "api.figshare" in url else (header + body).encode()

    # Gets past the station lookup; fails later only because one day is not 3 complete years.
    with pytest.raises(PipelineError, match="need at least 3 complete years"):
        fetch.fetch_weather(REGION, tmp_path, fetch.Lock(), get=fake_get)


def test_fetch_soils_fails_on_missing_map_unit(tmp_path: Path) -> None:
    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> bytes:
        return json.dumps({"Table": [["areasymbol", "saverest", "mukey", "musym", "muname"],
                                     ["FL121", "v", "1", "13", "Something else"]]}).encode()

    with pytest.raises(PipelineError, match="map units not found"):
        fetch.fetch_soils(REGION, tmp_path, fetch.Lock(), post=fake_post)
    assert not (tmp_path / "sda_mapunits.json").exists()
