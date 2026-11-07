"""Agricultural-use (greenbelt) land value per acre from the Florida statewide parcel layer.

The layer is the Florida Department of Revenue parcel GIS joined with the real
property assessment roll (NAL), published by the State of Florida Geographic
Information Office. Only the allow-listed value and land-use fields are ever
requested: owner names, mailing addresses, parcel IDs and geometry are never
downloaded, and only aggregate statistics are written to the repository.
"""

from __future__ import annotations

import json
import statistics
import urllib.parse
from collections import Counter
from collections.abc import Callable
from typing import Any

from agroeco_pipeline.common import PipelineError

SQFT_PER_ACRE = 43560.0
PAGE_SIZE = 2000
MAX_PAGES = 50
# Logical field names the region config must map to layer field names.
FIELD_KEYS = ("county", "use_code", "class_use_assessed", "class_use_just", "land_sqft", "tax_authority", "year")
# Layer fields that must never be requested (personal data or identifiers).
FORBIDDEN_FIELD_PREFIXES = ("OWN_", "FIDU_", "PHY_ADDR", "PARCEL_ID", "S_LEGAL", "ALT_KEY", "STATE_PAR")
STRING_TYPES = {"esriFieldTypeString"}
METHOD = (
    "Agricultural classified-use assessed value (AV_CLASS_USE) / parcel acres (LND_SQFOOT / 43,560) "
    "for parcels with the configured DOR cropland use codes; median and quartiles across parcels. "
    "Parcel acres include any non-classified portion (for example a homesite), so per-acre values are "
    "conservative (low)."
)


def _codes(values: Any, label: str, upper: int) -> list[int]:
    if not isinstance(values, list) or not values:
        raise PipelineError(f"parcels.{label} must be a non-empty list of integer codes")
    out = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= upper:
            raise PipelineError(f"parcels.{label}: {v!r} is not an allowed code (integer 0-{upper})")
        out.append(v)
    return out


def _literal(code: int, field_type: str, width: int) -> str:
    return f"'{code:0{width}d}'" if field_type in STRING_TYPES else str(code)


def check_fields(cfg: dict[str, Any], meta: dict[str, Any]) -> dict[str, str]:
    """Return {layer field name: esri type}; fail with the available names if any are missing."""
    fields = cfg.get("fields") or {}
    missing_keys = [k for k in FIELD_KEYS if not fields.get(k)]
    if missing_keys:
        raise PipelineError(f"parcels.fields is missing {missing_keys}")
    for name in fields.values():
        if any(name.upper().startswith(p) for p in FORBIDDEN_FIELD_PREFIXES):
            raise PipelineError(f"parcels.fields: {name!r} is personal or identifying data and must not be requested")
    if "error" in meta:
        raise PipelineError(f"parcel layer metadata returned an error: {meta['error']}")
    types = {f["name"]: f.get("type", "") for f in meta.get("fields") or [] if "name" in f}
    absent = [n for n in fields.values() if n not in types]
    if absent:
        raise PipelineError(f"parcel layer has no field(s) {absent}; available: {sorted(types)}")
    return types


def where_clause(cfg: dict[str, Any], types: dict[str, str]) -> str:
    f = cfg["fields"]
    county = _codes([cfg.get("county_no")], "county_no", 99)[0]
    uses = _codes(cfg.get("use_codes"), "use_codes", 99)
    c = _literal(county, types[f["county"]], 2)
    u = ", ".join(_literal(x, types[f["use_code"]], 3) for x in uses)
    return f"{f['county']} = {c} AND {f['use_code']} IN ({u})"


def query_params(cfg: dict[str, Any], where: str, oid_field: str, offset: int) -> dict[str, str]:
    return {
        "where": where,
        "outFields": ",".join(cfg["fields"][k] for k in FIELD_KEYS),
        "returnGeometry": "false",
        "orderByFields": f"{oid_field} ASC",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "f": "json",
    }


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _q(values: list[float]) -> dict[str, float]:
    q1, q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"p25": round(q1, 2), "median": round(q2, 2), "p75": round(q3, 2),
            "min": round(min(values), 2), "max": round(max(values), 2)}


def summarize(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Aggregate per-acre classified-use values. Rows are attribute dicts from the layer."""
    f = cfg["fields"]
    exclude = {str(x) for x in cfg.get("exclude_tax_authorities") or []}
    excluded: Counter[str] = Counter()
    used: list[tuple[str, float, float | None]] = []
    years: Counter[str] = Counter()
    authorities: Counter[str] = Counter()
    for r in rows:
        auth = str(r.get(f["tax_authority"]) or "").strip()
        authorities[auth or "(blank)"] += 1
        if auth in exclude:
            excluded["excluded_tax_authority"] += 1
            continue
        av, sqft = _num(r.get(f["class_use_assessed"])), _num(r.get(f["land_sqft"]))
        if av is None or av <= 0:
            excluded["no_classified_use_value"] += 1
            continue
        if sqft is None or sqft <= 0:
            excluded["no_land_area"] += 1
            continue
        acres = sqft / SQFT_PER_ACRE
        jv = _num(r.get(f["class_use_just"]))
        code = str(r.get(f["use_code"])).strip().zfill(3)
        years[str(r.get(f["year"]))] += 1
        used.append((code, av / acres, jv / acres if jv and jv > 0 else None))
    minimum = int(cfg.get("min_parcels", 10))
    if len(used) < max(minimum, 2):
        raise PipelineError(
            f"only {len(used)} usable cropland parcels (need {minimum}); excluded: {dict(excluded)}; "
            f"returned: {len(rows)}. Check parcels.county_no, use_codes and field names."
        )
    by_code: dict[str, dict[str, Any]] = {}
    for code in sorted({c for c, _, _ in used}):
        vals = [v for c, v, _ in used if c == code]
        by_code[code] = {"parcels": len(vals), "median_usd_ac": round(statistics.median(vals), 2)}
    just = [j for _, _, j in used if j is not None]
    return {
        "parcels_returned": len(rows),
        "parcels_used": len(used),
        "excluded": dict(sorted(excluded.items())),
        "assessment_years": dict(sorted(years.items())),
        "tax_authority_counts": dict(sorted(authorities.items())),
        "by_use_code": by_code,
        "classified_use_assessed_usd_ac": _q([v for _, v, _ in used]),
        "classified_use_just_usd_ac": _q(just) if len(just) >= 2 else None,
        "method": METHOD,
    }


def fetch_rows(cfg: dict[str, Any], get: Callable[[str], bytes],
               record: Callable[[str, bytes, str], None]) -> tuple[list[dict[str, Any]], str]:
    """Download layer metadata and all matching rows (allow-listed fields only)."""
    base = cfg["url"].rstrip("/")
    meta_url = f"{base}?f=json"
    raw = get(meta_url)
    record(meta_url, raw, "layer metadata")
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"parcel layer metadata is not JSON: {meta_url}") from exc
    types = check_fields(cfg, meta)
    where = where_clause(cfg, types)
    oid = meta.get("objectIdField") or "OBJECTID"
    rows: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        url = f"{base}/query?" + urllib.parse.urlencode(query_params(cfg, where, oid, page * PAGE_SIZE))
        raw = get(url)
        record(url, raw, f"query page {page + 1}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"parcel query returned non-JSON (page {page + 1})") from exc
        if "error" in data:
            raise PipelineError(f"parcel query error (page {page + 1}): {data['error']}")
        feats = data.get("features") or []
        rows.extend(ft.get("attributes") or {} for ft in feats)
        if len(feats) < PAGE_SIZE and not data.get("exceededTransferLimit"):
            return rows, where
    raise PipelineError(f"parcel query did not finish within {MAX_PAGES} pages")
