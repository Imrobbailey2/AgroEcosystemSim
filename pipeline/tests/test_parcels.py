"""Parcel (greenbelt use value) fetch with a fake transport (no network)."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pytest

from agroeco_pipeline import parcels
from agroeco_pipeline.common import PipelineError

CFG: dict[str, Any] = {
    "source": "fgio-fl-statewide-parcels",
    "url": "https://example.test/FeatureServer/0",
    "county_no": 71,
    "use_codes": [51, 52, 53],
    "fields": {
        "county": "CO_NO", "use_code": "DOR_UC", "class_use_assessed": "AV_CLASS_U",
        "class_use_just": "JV_CLASS_U", "land_sqft": "LND_SQFOOT", "tax_authority": "TAX_AUTH_C",
        "year": "ASMNT_YR",
    },
    "exclude_tax_authorities": [],
    "min_parcels": 3,
}
META = {
    "objectIdField": "OBJECTID",
    "fields": [{"name": n, "type": t} for n, t in [
        ("OBJECTID", "esriFieldTypeOID"), ("CO_NO", "esriFieldTypeSmallInteger"),
        ("DOR_UC", "esriFieldTypeString"), ("AV_CLASS_U", "esriFieldTypeDouble"),
        ("JV_CLASS_U", "esriFieldTypeDouble"), ("LND_SQFOOT", "esriFieldTypeDouble"),
        ("TAX_AUTH_C", "esriFieldTypeString"), ("ASMNT_YR", "esriFieldTypeSmallInteger"),
        ("OWN_NAME", "esriFieldTypeString"),
    ]],
}
ACRE = parcels.SQFT_PER_ACRE


def row(code: str, av: float, acres: float, auth: str = "1", jv: float | None = None) -> dict[str, Any]:
    return {"CO_NO": 71, "DOR_UC": code, "AV_CLASS_U": av, "JV_CLASS_U": jv, "LND_SQFOOT": acres * ACRE,
            "TAX_AUTH_C": auth, "ASMNT_YR": 2026}


def fake_transport(pages: list[list[dict[str, Any]]], meta: dict[str, Any] = META):
    seen: list[str] = []

    def get(url: str) -> bytes:
        seen.append(url)
        if url.endswith("?f=json"):
            return json.dumps(meta).encode()
        offset = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["resultOffset"][0])
        page = pages[offset // parcels.PAGE_SIZE] if offset // parcels.PAGE_SIZE < len(pages) else []
        return json.dumps({"features": [{"attributes": a} for a in page]}).encode()

    return get, seen


def test_where_clause_quotes_string_codes_and_not_numbers() -> None:
    types = parcels.check_fields(CFG, META)
    assert parcels.where_clause(CFG, types) == "CO_NO = 71 AND DOR_UC IN ('051', '052', '053')"
    numeric = {**types, "DOR_UC": "esriFieldTypeSmallInteger"}
    assert parcels.where_clause(CFG, numeric) == "CO_NO = 71 AND DOR_UC IN (51, 52, 53)"


def test_codes_are_allow_listed_integers() -> None:
    types = parcels.check_fields(CFG, META)
    with pytest.raises(PipelineError, match="not an allowed code"):
        parcels.where_clause({**CFG, "use_codes": ["51 OR 1=1"]}, types)


def test_only_allow_listed_fields_are_requested() -> None:
    get, seen = fake_transport([[row("052", 300, 10), row("052", 400, 10), row("051", 500, 10)]])
    parcels.fetch_rows(CFG, get, lambda u, r, n: None)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(seen[1]).query)
    out = query["outFields"][0].split(",")
    assert "OWN_NAME" not in out and not any(f.startswith(("OWN_", "PARCEL_ID", "PHY_ADDR")) for f in out)
    assert query["returnGeometry"] == ["false"]


def test_personal_fields_cannot_be_configured() -> None:
    bad = {**CFG, "fields": {**CFG["fields"], "year": "OWN_NAME"}}
    with pytest.raises(PipelineError, match="personal or identifying"):
        parcels.check_fields(bad, META)


def test_missing_layer_field_lists_available_names() -> None:
    meta = {**META, "fields": [f for f in META["fields"] if f["name"] != "AV_CLASS_U"]}
    with pytest.raises(PipelineError, match="available"):
        parcels.check_fields(CFG, meta)


def test_pages_until_short_page_and_records_every_download() -> None:
    full = [row("052", 300, 10)] * parcels.PAGE_SIZE
    get, seen = fake_transport([full, [row("052", 300, 10)]])
    recorded: list[str] = []
    rows, _ = parcels.fetch_rows(CFG, get, lambda u, r, n: recorded.append(n))
    assert len(rows) == parcels.PAGE_SIZE + 1
    assert recorded == ["layer metadata", "query page 1", "query page 2"]


def test_query_error_stops_the_fetch() -> None:
    def get(url: str) -> bytes:
        if url.endswith("?f=json"):
            return json.dumps(META).encode()
        return json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()

    with pytest.raises(PipelineError, match="Invalid query"):
        parcels.fetch_rows(CFG, get, lambda u, r, n: None)


def test_summary_per_acre_quartiles_and_exclusions() -> None:
    rows = [
        row("052", 2000, 10, jv=20000),   # $200/ac
        row("052", 3000, 10, jv=30000),   # $300/ac
        row("053", 4000, 10),             # $400/ac
        row("051", 5000, 10),             # $500/ac
        row("052", 0, 10),                # no classified use value
        row("052", 1000, 0),              # no land area
        row("052", 9000, 10, auth="LO"),  # municipal, excluded by config
    ]
    s = parcels.summarize(rows, {**CFG, "exclude_tax_authorities": ["LO"]})
    assert s["parcels_returned"] == 7 and s["parcels_used"] == 4
    assert s["excluded"] == {"excluded_tax_authority": 1, "no_classified_use_value": 1, "no_land_area": 1}
    q = s["classified_use_assessed_usd_ac"]
    assert (q["min"], q["p25"], q["median"], q["p75"], q["max"]) == (200.0, 275.0, 350.0, 425.0, 500.0)
    assert s["by_use_code"]["052"] == {"parcels": 2, "median_usd_ac": 250.0}
    assert s["classified_use_just_usd_ac"]["median"] == 2500.0
    assert s["tax_authority_counts"] == {"1": 6, "LO": 1}
    assert s["assessment_years"] == {"2026": 4}


def test_summary_needs_enough_parcels() -> None:
    with pytest.raises(PipelineError, match="usable cropland parcels"):
        parcels.summarize([row("052", 3000, 10)], CFG)
