"""Map size and interim-eligibility measurements for the county map (Increment 3, step 1).

Estimates how large the map pack would be at several simplification
tolerances, so the project owner can choose the tolerance and whether the map
draws every parcel before the map-pack format is fixed (step 2). The estimate
uses the planned encoding: per-ring Douglas-Peucker simplification, whole-metre
coordinates, delta-encoded and written as compact JSON, plus each parcel's
attribute record.
"""

from __future__ import annotations

import json
from typing import Any

import shapely

from agroeco_pipeline.common import PipelineError

SQFT_PER_ACRE = 43560.0
SQM_PER_ACRE = 4046.8564224
METHOD = (
    "Per-ring Douglas-Peucker simplification (shapely, preserve_topology=False) at each tolerance; "
    "coordinates rounded to whole metres; consecutive duplicates removed; rings with fewer than 4 points "
    "dropped; rings delta-encoded and written as compact JSON; each parcel adds its attribute record "
    "(id, acres, dor_uc, zoning, in_municipality, bbox). Interim eligibility: DOR land-use code in the "
    "agricultural range, at least the minimum acres (LND_SQFOOT / 43,560), representative point not inside "
    "a configured city limit."
)


def _geom(rings: list[list[list[int]]]) -> Any:
    """Polygon(s) from Esri rings: clockwise rings are outer boundaries, counter-clockwise are holes."""
    outers, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        poly = shapely.Polygon(r)
        if not poly.is_valid:
            poly = poly.buffer(0)
        (holes if shapely.LinearRing(r).is_ccw else outers).append(poly)
    if not outers:  # orientation not as expected: treat every ring as an outer boundary
        outers, holes = holes, []
    geom = shapely.unary_union(outers)
    return geom.difference(shapely.unary_union(holes)) if holes else geom


def encode_rings(rings: list[list[list[int]]], tolerance_m: float) -> tuple[list[list[int]], int]:
    """Simplify, round and delta-encode rings; return (encoded rings, rings dropped)."""
    encoded: list[list[int]] = []
    dropped = 0
    for ring in rings:
        if tolerance_m:
            coords = list(shapely.LineString(ring).simplify(tolerance_m, preserve_topology=False).coords)
        else:
            coords = ring
        pts: list[tuple[int, int]] = []
        for x, y in coords:
            p = (round(x), round(y))
            if not pts or p != pts[-1]:
                pts.append(p)
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) < 4:
            dropped += 1
            continue
        flat = [pts[0][0], pts[0][1]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
            flat.extend((x1 - x0, y1 - y0))
        encoded.append(flat)
    return encoded, dropped


def _json_len(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _code(dor_uc: str) -> int | None:
    return int(dor_uc) if dor_uc.isdigit() else None


def measure(
    parcels: list[dict[str, Any]],
    cities: list[dict[str, Any]] | None,
    county_rings: list[list[list[int]]] | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Counts by eligibility and estimated map-pack bytes per simplification tolerance."""
    try:
        lo, hi = cfg["agricultural_use_code_range"]
        min_acres = float(cfg["min_selectable_acres"])
        tolerances = [float(t) for t in cfg["measure_tolerances_m"]]
        budget = int(cfg["size_budget_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError(f"map config is missing or has a bad value: {exc}") from exc

    city_geom = shapely.unary_union([_geom(c["rings"]) for c in cities]) if cities else None
    by_code: dict[str, int] = {}
    counts = {"agricultural": 0, "agricultural_min_acres": 0, "agricultural_in_municipality": 0,
              "selectable_interim": 0, "in_municipality": 0, "unknown_use_code": 0}
    records: list[tuple[dict[str, Any], bool]] = []
    vertices_raw = 0
    for i, p in enumerate(parcels):
        by_code[p["dor_uc"] or "(blank)"] = by_code.get(p["dor_uc"] or "(blank)", 0) + 1
        vertices_raw += sum(len(r) for r in p["rings"])
        geom = _geom(p["rings"])
        acres = p["land_sqft"] / SQFT_PER_ACRE if p.get("land_sqft") else geom.area / SQM_PER_ACRE
        code = _code(p["dor_uc"])
        if code is None:
            counts["unknown_use_code"] += 1
        in_city = bool(city_geom is not None and not geom.is_empty and city_geom.contains(geom.representative_point()))
        ag = code is not None and lo <= code <= hi
        selectable = ag and acres >= min_acres and not in_city
        counts["in_municipality"] += in_city
        counts["agricultural"] += ag
        counts["agricultural_min_acres"] += ag and acres >= min_acres
        counts["agricultural_in_municipality"] += ag and in_city
        counts["selectable_interim"] += selectable
        xs = [q[0] for r in p["rings"] for q in r]
        ys = [q[1] for r in p["rings"] for q in r]
        attrs = {"id": f"P{i + 1:05d}", "acres": round(acres, 2), "dor_uc": p["dor_uc"], "zoning": "unknown",
                 "in_municipality": in_city, "bbox": [min(xs), min(ys), max(xs), max(ys)], "rings": []}
        records.append((attrs, selectable))

    sizes: dict[str, Any] = {}
    for tol in tolerances:
        all_bytes = sel_bytes = vertices = dropped = 0
        for (attrs, selectable), p in zip(records, parcels, strict=True):
            enc, d = encode_rings(p["rings"], tol)
            dropped += d
            vertices += sum(len(r) // 2 for r in enc)
            n = _json_len({**attrs, "rings": enc}) + 1  # +1 for the separating comma
            all_bytes += n
            if selectable:
                sel_bytes += n
        outline = _json_len(encode_rings(county_rings, tol)[0]) if county_rings else 0
        key = f"{tol:g}"
        sizes[key] = {
            "all_parcels_bytes": all_bytes + outline,
            "selectable_only_bytes": sel_bytes + outline,
            "county_outline_bytes": outline,
            "vertices": vertices,
            "rings_dropped": dropped,
            "all_parcels_fit_budget": all_bytes + outline <= budget,
            "selectable_only_fit_budget": sel_bytes + outline <= budget,
        }
    return {
        "method": METHOD,
        "parcels_total": len(parcels),
        "vertices_raw": vertices_raw,
        "counts": counts,
        "by_use_code": dict(sorted(by_code.items())),
        "agricultural_use_code_range": [lo, hi],
        "min_selectable_acres": min_acres,
        "city_limits_used": city_geom is not None,
        "county_outline_used": bool(county_rings),
        "size_budget_bytes": budget,
        "sizes_by_tolerance_m": sizes,
    }
