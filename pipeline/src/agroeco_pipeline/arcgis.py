"""Minimal ArcGIS REST feature-layer client for the county map extracts.

Every request names its output fields explicitly. Field names that carry
personal or identifying data (owner, address, legal description, parcel ID,
alternate key) are refused before any request is made, and only the requested
attributes are kept from each response.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Iterable
from typing import Any

from agroeco_pipeline.common import PipelineError
from agroeco_pipeline.parcels import FORBIDDEN_FIELD_PREFIXES

Get = Callable[[str], bytes]
Record = Callable[[str, bytes, str], None]

# Features are downloaded in batches of object IDs (Esri's recommended pattern for
# large results: returnIdsOnly, then subsets of objectIds) rather than by
# resultOffset, which hosted layers can reject deep into a result set.
ID_CHUNK = 250
MAX_IDS = 500_000
STRING_TYPES = {"esriFieldTypeString"}
# Text values allowed in a where clause (place names): letters, spaces and . ' -
SAFE_TEXT = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,59}$")


def refuse_forbidden(names: Iterable[str]) -> None:
    """Fail if any field name is personal or identifying data."""
    for name in names:
        if any(str(name).upper().startswith(p) for p in FORBIDDEN_FIELD_PREFIXES):
            raise PipelineError(f"field {name!r} is personal or identifying data and must not be requested")


def _json(raw: bytes, what: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{what} is not JSON") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"{what} is not a JSON object")
    if "error" in data:
        raise PipelineError(f"{what} returned an error: {data['error']}")
    return data


def layer_meta(url: str, get: Get, record: Record) -> dict[str, Any]:
    """Download and record the layer description (fields, object-ID field)."""
    meta_url = f"{url.rstrip('/')}?f=json"
    raw = get(meta_url)
    record(meta_url, raw, "layer metadata")
    return _json(raw, f"layer metadata {meta_url}")


def field_types(meta: dict[str, Any], names: Iterable[str]) -> dict[str, str]:
    """Return {field name: esri type}; fail with the available names if any are missing."""
    types = {f["name"]: f.get("type", "") for f in meta.get("fields") or [] if "name" in f}
    absent = [n for n in names if n not in types]
    if absent:
        raise PipelineError(f"layer has no field(s) {absent}; available: {sorted(types)}")
    return types


def code_literal(code: Any, field_type: str, width: int, label: str) -> str:
    """SQL literal for an integer code (zero-padded and quoted for string fields)."""
    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code < 10**width:
        raise PipelineError(f"{label}: {code!r} is not an allowed code (integer 0-{10**width - 1})")
    return f"'{code:0{width}d}'" if field_type in STRING_TYPES else str(code)


def text_literal(value: Any, label: str) -> str:
    """SQL literal for a place name; only letters, spaces and . ' - are allowed."""
    if not isinstance(value, str) or not SAFE_TEXT.match(value):
        raise PipelineError(f"{label}: {value!r} is not an allowed name (letters, spaces and . ' - only)")
    return "'" + value.replace("'", "''") + "'"


def query_features(
    url: str,
    where: str,
    out_fields: list[str],
    get: Get,
    record: Record,
    out_sr: int,
    max_allowable_offset_m: float | None = None,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    """Download every matching feature with geometry projected to ``out_sr`` (whole units).

    First asks for the matching object IDs (``returnIdsOnly``), then downloads the
    features in batches of ``ID_CHUNK`` IDs, in ascending ID order. Object IDs are
    internal row numbers that could be joined back to the source layer, so the
    URLs passed to ``record`` (and so the lock file) show only how many IDs a
    batch asked for, never the IDs themselves. ``order_by`` is accepted for
    compatibility and not needed: batches are already in ID order.
    """
    refuse_forbidden(out_fields)
    base = url.rstrip("/")
    ids_params = {"where": where, "returnIdsOnly": "true", "f": "json"}
    ids_url = f"{base}/query?" + urllib.parse.urlencode(ids_params)
    raw = get(ids_url)
    record(ids_url, raw, "object IDs")
    data = _json(raw, "object ID query")
    ids = data.get("objectIds") or []
    if not isinstance(ids, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        raise PipelineError("object ID query did not return a list of integer IDs")
    if len(ids) > MAX_IDS:
        raise PipelineError(f"query matches {len(ids)} features (limit {MAX_IDS}); narrow the where clause")
    ids = sorted(set(ids))
    features: list[dict[str, Any]] = []
    for n, start in enumerate(range(0, len(ids), ID_CHUNK), start=1):
        chunk = ids[start:start + ID_CHUNK]
        params = {
            "objectIds": ",".join(str(i) for i in chunk),
            "outFields": ",".join(out_fields),
            "returnGeometry": "true",
            "outSR": str(out_sr),
            "geometryPrecision": "0",
            "f": "json",
        }
        if max_allowable_offset_m:
            params["maxAllowableOffset"] = f"{max_allowable_offset_m:g}"
        query_url = f"{base}/query?" + urllib.parse.urlencode(params)
        logged_url = f"{base}/query?" + urllib.parse.urlencode({**params, "objectIds": f"<{len(chunk)} ids>"})
        raw = get(query_url)
        record(logged_url, raw, f"features batch {n}")
        page = _json(raw, f"features batch {n}")
        batch = page.get("features") or []
        if batch:
            sr = page.get("spatialReference") or {}
            if out_sr not in (sr.get("wkid"), sr.get("latestWkid")):
                raise PipelineError(f"layer returned spatial reference {sr}; expected EPSG:{out_sr}")
        if len(batch) > len(chunk):
            raise PipelineError(f"features batch {n} returned {len(batch)} features for {len(chunk)} IDs")
        if page.get("exceededTransferLimit"):
            raise PipelineError(
                f"features batch {n} was truncated by the server (exceededTransferLimit); lower arcgis.ID_CHUNK"
            )
        features.extend(batch)
    return features


def keep_attributes(feature: dict[str, Any], allowed: Iterable[str]) -> dict[str, Any]:
    """Only the requested attributes; anything else the server sends is dropped."""
    attrs = feature.get("attributes") or {}
    return {k: attrs[k] for k in allowed if k in attrs}


def rings_of(feature: dict[str, Any]) -> list[list[list[int]]]:
    """Polygon rings as whole-unit integer coordinates; degenerate rings are dropped."""
    geom = feature.get("geometry") or {}
    out: list[list[list[int]]] = []
    for ring in geom.get("rings") or []:
        pts: list[list[int]] = []
        for pt in ring:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            p = [round(float(pt[0])), round(float(pt[1]))]
            if not pts or p != pts[-1]:
                pts.append(p)
        if pts and pts[0] != pts[-1]:
            pts.append(list(pts[0]))
        if len(pts) >= 4:
            out.append(pts)
    return out
