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

PAGE_SIZE = 1000
MAX_PAGES = 200
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

    Paging advances by the number of features actually returned, so a server
    that returns short pages (``exceededTransferLimit``) is still read in full.
    """
    refuse_forbidden(out_fields)
    base = url.rstrip("/")
    features: list[dict[str, Any]] = []
    offset = 0
    for page in range(MAX_PAGES):
        params = {
            "where": where,
            "outFields": ",".join(out_fields),
            "returnGeometry": "true",
            "outSR": str(out_sr),
            "geometryPrecision": "0",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE_SIZE),
            "f": "json",
        }
        if max_allowable_offset_m:
            params["maxAllowableOffset"] = f"{max_allowable_offset_m:g}"
        if order_by:
            params["orderByFields"] = f"{order_by} ASC"
        query_url = f"{base}/query?" + urllib.parse.urlencode(params)
        raw = get(query_url)
        record(query_url, raw, f"query page {page + 1}")
        data = _json(raw, f"query page {page + 1}")
        batch = data.get("features") or []
        if batch:
            sr = data.get("spatialReference") or {}
            if out_sr not in (sr.get("wkid"), sr.get("latestWkid")):
                raise PipelineError(f"layer returned spatial reference {sr}; expected EPSG:{out_sr}")
        features.extend(batch)
        offset += len(batch)
        if not batch or (len(batch) < PAGE_SIZE and not data.get("exceededTransferLimit")):
            return features
    raise PipelineError(f"query did not finish within {MAX_PAGES} pages: {base}")


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
