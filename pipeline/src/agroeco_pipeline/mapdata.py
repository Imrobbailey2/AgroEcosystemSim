"""County map extracts (Increment 3): parcel shapes, city limits and county outline.

Fetch steps ``city_limits``, ``county_outline`` and ``parcel_shapes``. Geometry is
projected by the server to the region's map CRS (EPSG:3086, metres) and rounded
to whole metres. For parcels only the land-use code (DOR_UC) and land area
(LND_SQFOOT) are requested with the shape: owner names, addresses, legal
descriptions, parcel IDs, alternate keys and object IDs are never requested or
written (project-owner decision 2026-11-16, option A: real boundaries,
anonymized).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agroeco_pipeline import arcgis
from agroeco_pipeline.common import PipelineError, read_json, write_json, write_json_compact

PARCEL_FIELD_KEYS = ("county", "use_code", "land_sqft")
CITY_LIMITS_FILE = "city_limits.json"
COUNTY_OUTLINE_FILE = "county_outline.json"
PARCEL_SHAPES_FILE = "parcel_shapes.json"
MEASUREMENTS_FILE = "map_measurements.json"


def map_cfg(region: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    """The region's ``map`` block, or one of its sub-blocks."""
    block = region.get("map")
    if not isinstance(block, dict):
        raise PipelineError("region config has no 'map' block")
    if key is None:
        return block
    sub = block.get(key)
    if not isinstance(sub, dict):
        raise PipelineError(f"region config has no map.{key} block")
    return sub


def _out_sr(region: dict[str, Any]) -> int:
    sr = map_cfg(region).get("crs_epsg")
    if isinstance(sr, bool) or not isinstance(sr, int):
        raise PipelineError("map.crs_epsg must be an integer EPSG code")
    return sr


def _bbox(rings: list[list[list[int]]]) -> list[int]:
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return [min(xs), min(ys), max(xs), max(ys)]


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_city_limits(region: dict[str, Any], out: Path, record: arcgis.Record, get: arcgis.Get) -> None:
    """City-limit polygons for the configured municipalities (excluded from selection)."""
    cfg = map_cfg(region, "city_limits")
    sr = _out_sr(region)
    name_field = cfg["name_field"]
    names = cfg.get("names") or []
    if not names:
        raise PipelineError("map.city_limits.names must list at least one city")
    arcgis.refuse_forbidden([name_field])
    meta = arcgis.layer_meta(cfg["url"], get, record)
    arcgis.field_types(meta, [name_field])
    literals = ", ".join(arcgis.text_literal(n, "map.city_limits.names") for n in names)
    where = f"{name_field} IN ({literals})"
    feats = arcgis.query_features(cfg["url"], where, [name_field], get, record, sr,
                                  cfg.get("max_allowable_offset_m"), meta.get("objectIdField"))
    by_name: dict[str, list[list[list[int]]]] = {}
    for f in feats:
        name = str(arcgis.keep_attributes(f, [name_field]).get(name_field) or "").strip().upper()
        by_name.setdefault(name, []).extend(arcgis.rings_of(f))
    missing = [n for n in names if not by_name.get(n.upper())]
    if missing:
        raise PipelineError(f"city limits not found for {missing}; names returned: {sorted(by_name)}")
    cities = [{"name": n.upper(), "rings": sorted(by_name[n.upper()])} for n in sorted(names)]
    write_json_compact(out / CITY_LIMITS_FILE, {
        "source": cfg["source"], "layer": cfg["url"], "where": where, "crs": f"EPSG:{sr}", "cities": cities,
    })


def fetch_county_outline(region: dict[str, Any], out: Path, record: arcgis.Record, get: arcgis.Get) -> None:
    """County boundary polygon (map background and extent)."""
    cfg = map_cfg(region, "county_outline")
    sr = _out_sr(region)
    field = cfg["geoid_field"]
    geoid = cfg["geoid"]
    if not isinstance(geoid, str) or not geoid.isdigit() or len(geoid) != 5:
        raise PipelineError(f"map.county_outline.geoid must be a 5-digit county FIPS code, got {geoid!r}")
    arcgis.refuse_forbidden([field])
    meta = arcgis.layer_meta(cfg["url"], get, record)
    arcgis.field_types(meta, [field])
    where = f"{field} = '{geoid}'"
    feats = arcgis.query_features(cfg["url"], where, [field], get, record, sr,
                                  cfg.get("max_allowable_offset_m"), meta.get("objectIdField"))
    rings = sorted(r for f in feats for r in arcgis.rings_of(f))
    if not rings:
        raise PipelineError(f"county outline not found for {field} = {geoid}")
    write_json_compact(out / COUNTY_OUTLINE_FILE, {
        "source": cfg["source"], "layer": cfg["url"], "where": where, "crs": f"EPSG:{sr}",
        "geoid": geoid, "rings": rings,
    })


def parcel_where(cfg: dict[str, Any], types: dict[str, str]) -> str:
    f = cfg["fields"]
    county = arcgis.code_literal(cfg.get("county_no"), types[f["county"]], 2, "map.parcel_shapes.county_no")
    return f"{f['county']} = {county}"


def parcel_records(feats: list[dict[str, Any]], fields: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Reduce features to {dor_uc, land_sqft, rings}, sorted by position (no identifiers)."""
    keep = [fields[k] for k in PARCEL_FIELD_KEYS]
    excluded: dict[str, int] = {}
    parcels: list[dict[str, Any]] = []
    for feat in feats:
        attrs = arcgis.keep_attributes(feat, keep)
        rings = arcgis.rings_of(feat)
        if not rings:
            excluded["no_geometry"] = excluded.get("no_geometry", 0) + 1
            continue
        raw_code = attrs.get(fields["use_code"])
        code = str(raw_code).strip().zfill(3) if raw_code not in (None, "") else ""
        sqft = _num(attrs.get(fields["land_sqft"]))
        parcels.append({"dor_uc": code, "land_sqft": round(sqft, 1) if sqft is not None else None, "rings": rings})
    parcels.sort(key=lambda p: (_bbox(p["rings"]), p["dor_uc"], p["land_sqft"] or 0.0, p["rings"]))
    return parcels, dict(sorted(excluded.items()))


def fetch_parcel_shapes(region: dict[str, Any], out: Path, record: arcgis.Record, get: arcgis.Get) -> None:
    """All parcel shapes in the county with land-use code and land area only."""
    cfg = map_cfg(region, "parcel_shapes")
    sr = _out_sr(region)
    fields = cfg.get("fields") or {}
    missing = [k for k in PARCEL_FIELD_KEYS if not fields.get(k)]
    if missing:
        raise PipelineError(f"map.parcel_shapes.fields is missing {missing}")
    names = [fields[k] for k in PARCEL_FIELD_KEYS]
    arcgis.refuse_forbidden(names)
    meta = arcgis.layer_meta(cfg["url"], get, record)
    types = arcgis.field_types(meta, names)
    where = parcel_where(cfg, types)
    offset = cfg.get("max_allowable_offset_m", 1)
    feats = arcgis.query_features(cfg["url"], where, names, get, record, sr, offset,
                                  meta.get("objectIdField") or "OBJECTID")
    parcels, excluded = parcel_records(feats, fields)
    minimum = int(cfg.get("min_parcels", 1))
    if len(parcels) < minimum:
        raise PipelineError(
            f"only {len(parcels)} parcels with geometry (need {minimum}); excluded: {excluded}; "
            f"returned: {len(feats)}. Check map.parcel_shapes.county_no and field names."
        )
    write_json_compact(out / PARCEL_SHAPES_FILE, {
        "source": cfg["source"], "layer": cfg["url"], "where": where, "crs": f"EPSG:{sr}",
        "max_allowable_offset_m": offset, "returned": len(feats), "excluded": excluded,
        "count": len(parcels), "parcels": parcels,
    })
    write_measurements(region, out)


def write_measurements(region: dict[str, Any], out: Path) -> None:
    """Size and eligibility report for the step 1 decisions (uses any city/county extracts present)."""
    from agroeco_pipeline import mapmeasure

    shapes = read_json(out / PARCEL_SHAPES_FILE)
    cities = read_json(out / CITY_LIMITS_FILE)["cities"] if (out / CITY_LIMITS_FILE).exists() else None
    county = read_json(out / COUNTY_OUTLINE_FILE)["rings"] if (out / COUNTY_OUTLINE_FILE).exists() else None
    report = mapmeasure.measure(shapes["parcels"], cities, county, map_cfg(region))
    report["excluded_at_fetch"] = shapes.get("excluded", {})
    write_json(out / MEASUREMENTS_FILE, report)
