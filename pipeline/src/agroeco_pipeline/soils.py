"""Turn SSURGO map units, components and horizons into game soil units."""

from __future__ import annotations

from typing import Any

from agroeco_pipeline.common import PipelineError, opt_float


def _dominant(components: list[dict[str, Any]], mukey: str) -> dict[str, Any]:
    comps = [c for c in components if str(c["mukey"]) == mukey]
    if not comps:
        raise PipelineError(f"no components for mukey {mukey}")
    return sorted(comps, key=lambda c: (-(opt_float(c["comppct_r"]) or 0), str(c["cokey"])))[0]


def build_layers(horizons: list[dict[str, Any]], cokey: str, max_depth_cm: float) -> list[dict[str, Any]]:
    layers = []
    for h in sorted(
        (h for h in horizons if str(h["cokey"]) == cokey),
        key=lambda h: opt_float(h["hzdept_r"]) or 0,
    ):
        top = opt_float(h["hzdept_r"])
        bottom = opt_float(h["hzdepb_r"])
        if top is None or bottom is None or top >= max_depth_cm:
            continue
        fc = opt_float(h["wthirdbar_r"])
        wp = opt_float(h["wfifteenbar_r"])
        if fc is None or wp is None:
            raise PipelineError(
                f"horizon {h['chkey']} lacks water retention (wthirdbar_r/wfifteenbar_r)"
            )
        layers.append(
            {
                "chkey": str(h["chkey"]),
                "name": h.get("hzname") or "",
                "top_cm": top,
                "bottom_cm": min(bottom, max_depth_cm),
                "theta_fc": round(fc / 100, 4),
                "theta_wp": round(wp / 100, 4),
                "awc_cm_cm": opt_float(h["awc_r"]),
                "sand_pct": opt_float(h["sandtotal_r"]),
                "silt_pct": opt_float(h["silttotal_r"]),
                "clay_pct": opt_float(h["claytotal_r"]),
                "om_pct": opt_float(h["om_r"]),
                "bulk_density_g_cm3": opt_float(h["dbthirdbar_r"]),
                "ksat_um_s": opt_float(h["ksat_r"]),
                "ph_h2o": opt_float(h["ph1to1h2o_r"]),
                "cec_meq_100g": opt_float(h["cec7_r"]),
            }
        )
    if not layers:
        raise PipelineError(f"no usable horizons for component {cokey}")
    return layers


def total_available_water_mm(layers: list[dict[str, Any]], depth_cm: float) -> float:
    """Plant-available water (FC - WP) in mm over the top `depth_cm`."""
    total = 0.0
    for layer in layers:
        top, bottom = layer["top_cm"], min(layer["bottom_cm"], depth_cm)
        if bottom > top:
            total += (layer["theta_fc"] - layer["theta_wp"]) * (bottom - top) * 10
    return round(total, 1)


def build_soil_units(
    fields: list[dict[str, str]],
    mapunits: list[dict[str, Any]],
    components: list[dict[str, Any]],
    horizons: list[dict[str, Any]],
    max_depth_cm: float,
    source_id: str,
    areasymbol: str,
) -> list[dict[str, Any]]:
    units = []
    for field in fields:
        matches = [m for m in mapunits if m["muname"] == field["muname"]]
        if len(matches) != 1:
            raise PipelineError(
                f"expected exactly 1 map unit named {field['muname']!r}, found {len(matches)}"
            )
        mu = matches[0]
        mukey = str(mu["mukey"])
        comp = _dominant(components, mukey)
        cokey = str(comp["cokey"])
        layers = build_layers(horizons, cokey, max_depth_cm)
        units.append(
            {
                "id": field["id"],
                "mukey": mukey,
                "musym": str(mu["musym"]),
                "muname": mu["muname"],
                "survey_version": str(mu.get("saverest") or ""),
                "dominant_component": {
                    "cokey": cokey,
                    "name": comp["compname"],
                    "pct": opt_float(comp["comppct_r"]),
                    "hydrologic_group": comp.get("hydgrp"),
                    "drainage_class": comp.get("drainagecl"),
                    "taxonomic_class": comp.get("taxclname"),
                },
                "layers": layers,
                "taw_mm_top_100cm": total_available_water_mm(layers, 100),
                "prov": {
                    "sources": [source_id],
                    "loc": f"areasymbol={areasymbol}; mukey={mukey}; cokey={cokey}",
                },
            }
        )
    return units
