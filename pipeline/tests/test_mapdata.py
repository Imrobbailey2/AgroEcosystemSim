"""County map extracts (parcel shapes, city limits, county outline) with fake transports (no network)."""

from __future__ import annotations

import copy
import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from agroeco_pipeline import arcgis, mapdata, mapmeasure
from agroeco_pipeline.common import PIPELINE_DIR, PipelineError, read_json

REGION = read_json(PIPELINE_DIR / "sources" / "regions" / "suwannee.json")
REGISTRY = {s["id"]: s for s in read_json(PIPELINE_DIR / "sources" / "sources.json")["sources"]}
SR = REGION["map"]["crs_epsg"]
FORBIDDEN_TEXT = ("OWN_", "PARCEL_ID", "PHY_ADDR", "ALT_KEY", "S_LEGAL", "OBJECTID")

PARCEL_META = {
    "objectIdField": "OBJECTID",
    "fields": [{"name": n, "type": t} for n, t in [
        ("OBJECTID", "esriFieldTypeOID"), ("CO_NO", "esriFieldTypeSmallInteger"),
        ("DOR_UC", "esriFieldTypeString"), ("LND_SQFOOT", "esriFieldTypeDouble"),
        ("OWN_NAME", "esriFieldTypeString"), ("PARCEL_ID", "esriFieldTypeString"),
    ]],
}
CITY_META = {"objectIdField": "OBJECTID", "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"},
                                                     {"name": "BASENAME", "type": "esriFieldTypeString"},
                                                     {"name": "STATE", "type": "esriFieldTypeString"}]}
COUNTY_META = {"objectIdField": "OBJECTID", "fields": [{"name": "GEOID", "type": "esriFieldTypeString"},
                                                       {"name": "NAME", "type": "esriFieldTypeString"}]}


def square(x: float, y: float, size: float) -> list[list[float]]:
    """Clockwise square ring (Esri outer-boundary orientation)."""
    return [[x, y], [x, y + size], [x + size, y + size], [x + size, y], [x, y]]


def parcel(code: str, x: float, y: float, size_m: float, oid: int) -> dict[str, Any]:
    """A feature as the server returns it, including fields we never asked for."""
    return {
        "attributes": {"OBJECTID": oid, "CO_NO": 71, "DOR_UC": code, "LND_SQFOOT": size_m * size_m * 10.7639,
                       "OWN_NAME": "PRIVATE PERSON", "PARCEL_ID": f"12-34-56-{oid:05d}"},
        "geometry": {"rings": [square(x + 0.4, y + 0.4, size_m)]},
    }


def transport(meta: dict[str, Any], features: list[dict[str, Any]], sr: int = SR) -> tuple[Any, list[str]]:
    """Fake server: layer metadata, an object-ID query, then features by objectIds."""
    seen: list[str] = []
    by_id = {f["attributes"]["OBJECTID"]: f for f in features}

    def get(url: str) -> bytes:
        seen.append(url)
        if url.endswith("?f=json"):
            return json.dumps(meta).encode()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if q.get("returnIdsOnly") == ["true"]:
            return json.dumps({"objectIdFieldName": "OBJECTID", "objectIds": list(by_id)}).encode()
        wanted = [int(i) for i in q["objectIds"][0].split(",")]
        batch = [by_id[i] for i in wanted if i in by_id]
        return json.dumps({"features": batch, "spatialReference": {"wkid": sr}}).encode()

    return get, seen


def no_record(url: str, raw: bytes, note: str) -> None:
    return None


def region_with(min_parcels: int = 1) -> dict[str, Any]:
    region = copy.deepcopy(REGION)
    region["map"]["parcel_shapes"]["min_parcels"] = min_parcels
    return region


def query(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_region_map_config_is_registered() -> None:
    m = REGION["map"]
    assert m["crs_epsg"] == 3086
    for key in ("parcel_shapes", "city_limits", "county_outline"):
        assert m[key]["source"] in REGISTRY
        assert REGISTRY[m[key]["source"]]["url"] == m[key]["url"]
    assert m["parcel_shapes"]["source"] == REGION["parcels"]["source"]
    assert m["parcel_shapes"]["county_no"] == 71
    assert m["agricultural_use_code_range"] == [50, 69] and m["min_selectable_acres"] == 10


def test_parcel_shapes_request_only_allow_listed_fields_and_write_no_identifiers(tmp_path: Path) -> None:
    get, seen = transport(PARCEL_META, [parcel("052", 1000, 1000, 300, 7), parcel("001", 0, 0, 50, 8)])
    mapdata.fetch_parcel_shapes(region_with(), tmp_path, no_record, get)
    assert query(seen[1])["where"] == ["CO_NO = 71"] and query(seen[1])["returnIdsOnly"] == ["true"]
    q = query(seen[2])
    assert sorted(q["outFields"][0].split(",")) == ["CO_NO", "DOR_UC", "LND_SQFOOT"]
    assert q["returnGeometry"] == ["true"] and q["outSR"] == [str(SR)] and q["geometryPrecision"] == ["0"]
    assert q["objectIds"] == ["7,8"]
    text = (tmp_path / mapdata.PARCEL_SHAPES_FILE).read_text(encoding="utf-8")
    assert not any(bad in text for bad in FORBIDDEN_TEXT)
    assert "PRIVATE PERSON" not in text and "12-34-56" not in text
    out = json.loads(text)
    assert out["count"] == 2
    assert {tuple(sorted(p)) for p in out["parcels"]} == {("dor_uc", "land_sqft", "rings")}
    # Coordinates are whole metres.
    assert all(isinstance(c, int) for p in out["parcels"] for r in p["rings"] for pt in r for c in pt)


@pytest.mark.parametrize("key,name", [("use_code", "PARCEL_ID"), ("land_sqft", "OWN_NAME"), ("county", "ALT_KEY")])
def test_personal_fields_cannot_be_configured_and_nothing_is_downloaded(tmp_path: Path, key: str, name: str) -> None:
    region = region_with()
    region["map"]["parcel_shapes"]["fields"][key] = name
    get, seen = transport(PARCEL_META, [])
    with pytest.raises(PipelineError, match="personal or identifying"):
        mapdata.fetch_parcel_shapes(region, tmp_path, no_record, get)
    assert seen == []


def test_features_download_in_object_id_batches_and_ids_are_not_logged(tmp_path: Path) -> None:
    feats = [parcel("052", i * 400, 0, 300, 101 + i) for i in range(5)]
    get, seen = transport(PARCEL_META, feats)
    logged: list[tuple[str, str]] = []
    saved = arcgis.ID_CHUNK
    arcgis.ID_CHUNK = 2
    try:
        mapdata.fetch_parcel_shapes(region_with(), tmp_path, lambda u, r, n: logged.append((u, n)), get)
    finally:
        arcgis.ID_CHUNK = saved
    assert [query(u)["objectIds"][0] for u in seen[2:]] == ["101,102", "103,104", "105"]
    assert [n for _, n in logged] == ["layer metadata", "object IDs", "features batch 1", "features batch 2",
                                      "features batch 3"]
    batch_urls = [u for u, n in logged if n.startswith("features batch")]
    assert [query(u)["objectIds"][0] for u in batch_urls] == ["<2 ids>", "<2 ids>", "<1 ids>"]
    assert not any(str(101 + i) in u for u, _ in logged for i in range(5))
    assert read_json(tmp_path / mapdata.PARCEL_SHAPES_FILE)["count"] == 5


def test_truncated_batch_stops_the_fetch(tmp_path: Path) -> None:
    def get(url: str) -> bytes:
        if url.endswith("?f=json"):
            return json.dumps(PARCEL_META).encode()
        if "returnIdsOnly" in url:
            return json.dumps({"objectIds": [1, 2]}).encode()
        return json.dumps({"features": [parcel("052", 0, 0, 300, 1)], "spatialReference": {"wkid": SR},
                           "exceededTransferLimit": True}).encode()

    with pytest.raises(PipelineError, match="truncated"):
        mapdata.fetch_parcel_shapes(region_with(), tmp_path, no_record, get)


def test_wrong_spatial_reference_stops_the_fetch(tmp_path: Path) -> None:
    get, _ = transport(PARCEL_META, [parcel("052", 0, 0, 300, 1)], sr=4326)
    with pytest.raises(PipelineError, match="spatial reference"):
        mapdata.fetch_parcel_shapes(region_with(), tmp_path, no_record, get)


def test_parcel_without_geometry_is_counted_not_written(tmp_path: Path) -> None:
    empty = {"attributes": {"OBJECTID": 2, "DOR_UC": "052", "LND_SQFOOT": 1.0}, "geometry": None}
    get, _ = transport(PARCEL_META, [parcel("052", 0, 0, 300, 1), empty])
    mapdata.fetch_parcel_shapes(region_with(), tmp_path, no_record, get)
    out = read_json(tmp_path / mapdata.PARCEL_SHAPES_FILE)
    assert out["count"] == 1 and out["excluded"] == {"no_geometry": 1} and out["returned"] == 2


def test_too_few_parcels_fails(tmp_path: Path) -> None:
    get, _ = transport(PARCEL_META, [parcel("052", 0, 0, 300, 1)])
    with pytest.raises(PipelineError, match="parcels with geometry"):
        mapdata.fetch_parcel_shapes(region_with(min_parcels=5), tmp_path, no_record, get)


def test_output_does_not_depend_on_server_order(tmp_path: Path) -> None:
    feats = [parcel("052", i * 500, (i % 3) * 500, 300, i) for i in range(6)]
    a, b = tmp_path / "a", tmp_path / "b"
    mapdata.fetch_parcel_shapes(region_with(), a, no_record, transport(PARCEL_META, feats)[0])
    mapdata.fetch_parcel_shapes(region_with(), b, no_record, transport(PARCEL_META, feats[::-1])[0])
    assert (a / mapdata.PARCEL_SHAPES_FILE).read_bytes() == (b / mapdata.PARCEL_SHAPES_FILE).read_bytes()
    assert (a / mapdata.MEASUREMENTS_FILE).read_bytes() == (b / mapdata.MEASUREMENTS_FILE).read_bytes()


def city(name: str, x: float, y: float, size: float, oid: int = 1) -> dict[str, Any]:
    return {"attributes": {"OBJECTID": oid, "BASENAME": name, "STATE": "12"},
            "geometry": {"rings": [square(x, y, size)]}}


def test_city_limits_writes_configured_cities_in_the_region_state(tmp_path: Path) -> None:
    get, seen = transport(CITY_META, [city("Live Oak", 0, 0, 2000, 1), city("Branford", 9000, 0, 1000, 2)])
    mapdata.fetch_city_limits(REGION, tmp_path, no_record, get)
    assert query(seen[1])["where"] == ["STATE = '12' AND BASENAME IN ('Branford', 'Live Oak')"]
    assert query(seen[2])["outFields"] == ["BASENAME"]
    out = read_json(tmp_path / mapdata.CITY_LIMITS_FILE)
    assert [c["name"] for c in out["cities"]] == ["BRANFORD", "LIVE OAK"]
    assert "OBJECTID" not in json.dumps(out)


def test_city_limits_missing_city_fails(tmp_path: Path) -> None:
    get, _ = transport(CITY_META, [city("Live Oak", 0, 0, 2000)])
    with pytest.raises(PipelineError, match="Branford"):
        mapdata.fetch_city_limits(REGION, tmp_path, no_record, get)


def test_city_limits_state_must_be_a_fips_code(tmp_path: Path) -> None:
    region = copy.deepcopy(REGION)
    region["map"]["city_limits"]["state"] = "FL' OR '1'='1"
    get, seen = transport(CITY_META, [])
    with pytest.raises(PipelineError, match="2-digit state FIPS"):
        mapdata.fetch_city_limits(region, tmp_path, no_record, get)
    assert seen == []


def test_city_names_cannot_inject_sql(tmp_path: Path) -> None:
    region = copy.deepcopy(REGION)
    region["map"]["city_limits"]["names"] = ["X' OR '1'='1"]
    get, _ = transport(CITY_META, [])
    with pytest.raises(PipelineError, match="not an allowed name"):
        mapdata.fetch_city_limits(region, tmp_path, no_record, get)


def test_missing_layer_field_lists_available_names(tmp_path: Path) -> None:
    get, _ = transport({"fields": [{"name": "NAME", "type": "esriFieldTypeString"}]}, [])
    with pytest.raises(PipelineError, match="available"):
        mapdata.fetch_city_limits(REGION, tmp_path, no_record, get)


def test_county_outline_writes_rings(tmp_path: Path) -> None:
    feat = {"attributes": {"OBJECTID": 9, "GEOID": "12121"}, "geometry": {"rings": [square(0, 0, 50000)]}}
    get, seen = transport(COUNTY_META, [feat])
    mapdata.fetch_county_outline(REGION, tmp_path, no_record, get)
    assert query(seen[1])["where"] == ["GEOID = '12121'"]
    out = read_json(tmp_path / mapdata.COUNTY_OUTLINE_FILE)
    assert out["geoid"] == "12121" and len(out["rings"]) == 1


def test_county_outline_not_found_fails(tmp_path: Path) -> None:
    get, _ = transport(COUNTY_META, [])
    with pytest.raises(PipelineError, match="not found"):
        mapdata.fetch_county_outline(REGION, tmp_path, no_record, get)


def test_query_error_is_reported(tmp_path: Path) -> None:
    def get(url: str) -> bytes:
        if url.endswith("?f=json"):
            return json.dumps(PARCEL_META).encode()
        return json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()

    with pytest.raises(PipelineError, match="Invalid query"):
        mapdata.fetch_parcel_shapes(region_with(), tmp_path, no_record, get)


def test_rings_are_rounded_closed_and_degenerate_rings_dropped() -> None:
    feat = {"geometry": {"rings": [[[0.4, 0.4], [0.6, 10.2], [10.0, 10.0], [10.0, 0.0]],  # not closed
                                   [[0, 0], [0.2, 0.1], [0.1, 0.3]]]}}  # collapses to one point
    assert arcgis.rings_of(feat) == [[[0, 0], [1, 10], [10, 10], [10, 0], [0, 0]]]


def test_measure_counts_interim_eligibility_and_sizes() -> None:
    acre_side = 63.6149  # metres per side of a 1-acre square
    parcels = [
        {"dor_uc": "052", "land_sqft": 20 * 43560.0, "rings": [square(10000, 10000, 20 * acre_side)]},  # selectable
        {"dor_uc": "060", "land_sqft": 15 * 43560.0, "rings": [square(100, 100, 15 * acre_side)]},  # in city
        {"dor_uc": "053", "land_sqft": 5 * 43560.0, "rings": [square(20000, 0, 5 * acre_side)]},  # too small
        {"dor_uc": "001", "land_sqft": 1 * 43560.0, "rings": [square(30000, 0, acre_side)]},  # residential
    ]
    cities = [{"name": "LIVE OAK", "rings": [square(0, 0, 5000)]}]
    county = [square(-1000, -1000, 60000)]
    report = mapmeasure.measure(parcels, cities, county, REGION["map"])
    c = report["counts"]
    assert (c["agricultural"], c["agricultural_min_acres"], c["agricultural_in_municipality"]) == (3, 2, 1)
    assert c["selectable_interim"] == 1 and c["in_municipality"] == 1
    assert report["by_use_code"] == {"001": 1, "052": 1, "053": 1, "060": 1}
    sizes = report["sizes_by_tolerance_m"]
    assert set(sizes) == {"2", "5", "10", "20"}
    assert sizes["10"]["all_parcels_bytes"] <= sizes["2"]["all_parcels_bytes"]
    assert sizes["2"]["selectable_only_bytes"] < sizes["2"]["all_parcels_bytes"]
    assert sizes["2"]["all_parcels_fit_budget"] is True and sizes["2"]["county_outline_bytes"] > 0


def test_encode_rings_is_delta_encoded_whole_metres() -> None:
    enc, dropped = mapmeasure.encode_rings([[[100, 200], [100, 300], [250, 300], [250, 200], [100, 200]]], 2)
    assert dropped == 0
    assert enc == [[100, 200, 0, 100, 150, 0, 0, -100, -150, 0]]
