"""Assemble a region data pack from committed manual tables and fetched extracts.

The build is offline and deterministic: the same inputs give byte-identical
output (sorted keys, no timestamps other than those recorded in the inputs).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agroeco_pipeline import budget, soils, weather
from agroeco_pipeline.common import (
    PipelineError,
    packs_dir,
    read_csv,
    read_json,
    sha256_bytes,
    sources_dir,
    to_float,
    write_json,
)

FORMAT = "agroeco-datapack"
FORMAT_VERSION = 1


def _prov(source: str, loc: str, method: str | None = None) -> dict[str, Any]:
    p: dict[str, Any] = {"sources": [source], "loc": loc}
    if method:
        p["method"] = method
    return p


def _num(row: dict[str, str], key: str) -> float | None:
    v = row.get(key, "")
    return None if v == "" else to_float(v, key)


def soil_test_block(manual: Path) -> dict[str, Any]:
    ratings = [
        {
            "nutrient": r["nutrient"],
            "rating": r["rating"],
            "gt_mg_kg": _num(r, "gt_mg_kg"),
            "le_mg_kg": _num(r, "le_mg_kg"),
            "prov": _prov(r["source"], r["locator"]),
        }
        for r in read_csv(manual / "sl129_ratings.csv")
    ]
    lime = [
        {"key": r["key"], "value": r["value"], "unit": r["unit"], "prov": _prov(r["source"], r["locator"])}
        for r in read_csv(manual / "sl129_lime.csv")
    ]
    return {"extractant": "Mehlich-3", "ratings": ratings, "lime_rules": lime}


def crop_block(manual: Path, review: dict[str, Any]) -> dict[str, Any]:
    rows = read_csv(manual / "sl129_corn.csv")
    pop_rows = [
        {
            "plants_per_acre": int(r["plants_per_acre"]),
            "target_ph": to_float(r["target_ph"], "target_ph"),
            "n_lb_a": to_float(r["n_lb_a"], "n_lb_a"),
            "p2o5_lb_a": {k: to_float(r[f"p2o5_{k}"], "p2o5") for k in ("lo", "med", "hi")},
            "k2o_lb_a": {k: to_float(r[f"k2o_{k}"], "k2o") for k in ("lo", "med", "hi")},
            "footnotes": [int(f) for f in r["footnotes"].split(";")],
            "prov": _prov(r["source"], r["locator"]),
        }
        for r in rows
        if r["irrigated"] == "true"
    ]
    footnotes = [
        {"footnote": int(r["footnote"]), "key": r["key"], "value": r["value"], "unit": r["unit"],
         "prov": _prov(r["source"], r["locator"])}
        for r in read_csv(manual / "sl129_footnotes.csv")
    ]
    interim = [
        {"yield_bu_ac": to_float(r["yield_bu_ac"], "yield"), "n_lb_ac": to_float(r["n_lb_ac"], "n"),
         "prov": _prov(r["source"], r["locator"])}
        for r in read_csv(manual / "n_interim_yield_goal.csv")
    ]
    item = next((i for i in review["items"] if i["id"] == "corn-n-rule"), None)
    if item is None:
        raise PipelineError("review register lacks corn-n-rule")
    return {
        "id": "corn-grain-irrigated",
        "name": "Field corn for grain, irrigated",
        "sl129_crop_code": 5,
        "target_ph": pop_rows[0]["target_ph"],
        "fertilizer_by_population": pop_rows,
        "footnotes": footnotes,
        "n_rules": {
            "default": item["current_default"],
            "review_flag": "corn-n-rule",
            "rules": [
                {"id": "sl129-plant-population", "kind": "table_by_population",
                 "prov": _prov("sl129", "Table 2 crop code 5")},
                {"id": "interim-yield-goal", "kind": "lb_n_per_bu", "lb_n_per_bu": 1.37,
                 "table": interim, "prov": _prov("ufifas-corn-n-interim", "Table 2 and text")},
            ],
        },
        "prov": _prov("sl129", "Table 2 crop code 5"),
    }


def custom_ops_block(manual: Path) -> list[dict[str, Any]]:
    adj = {r["operation_id"]: r for r in read_csv(manual / "custom_rate_fl_adjustment.csv")}
    cross = {r["operation_id"]: r for r in read_csv(manual / "custom_rates_crosscheck.csv")}
    ops = []
    for r in read_csv(manual / "custom_rates_ga2024.csv"):
        a = adj.get(r["operation_id"]) or adj.get("*")
        if a is None:
            raise PipelineError(f"no Florida adjustment row for {r['operation_id']}")
        factor = to_float(a["factor"], "factor")
        avg = to_float(r["average"], "average")
        op: dict[str, Any] = {
            "id": r["operation_id"],
            "label": r["survey_label"],
            "unit": r["unit"],
            "rate_usd": round(avg * factor, 2),
            "survey": {k: to_float(r[k], k) for k in ("average", "median", "high", "low")},
            "florida_adjustment": {"factor": factor, "status": a["status"],
                                   "prov": _prov(a["source"], "custom_rate_fl_adjustment.csv", a["method"])},
            "review_flag": "custom-rates-florida-adjustment",
            "prov": {"sources": [r["source"], a["source"]], "loc": r["locator"],
                     "method": "survey average x Florida adjustment factor"},
        }
        if r["operation_id"] in cross:
            c = cross[r["operation_id"]]
            op["crosscheck"] = {"label": c["survey_label"], "range_low": to_float(c["range_low"], "low"),
                                "range_high": to_float(c["range_high"], "high"),
                                "prov": _prov(c["source"], c["locator"])}
        ops.append(op)
    return ops


def budgets_block(region: dict[str, Any], extracted: Path) -> tuple[dict[str, Any], dict[str, dict]]:
    """Return (budgets, picked fields per tenure)."""
    budgets: dict[str, Any] = {}
    picked: dict[str, dict] = {}
    for b in region["budgets"]:
        lines = read_csv(extracted / b["file"])
        budgets[b["tenure"]] = {
            "source": b["source"],
            "lines": [
                {"label": ln["label"], "sheet": ln["sheet"], "label_cell": ln["label_cell"],
                 "occurrence": int(ln["occurrence"]), "values": ln["values"],
                 "prov": _prov(b["source"], f"{ln['sheet']}!{ln['label_cell']}")}
                for ln in lines
            ],
        }
        fields: dict[str, Any] = {}
        for name, spec in region["budget_fields"].items():
            if b["tenure"] not in spec.get("tenures", [b["tenure"]]):
                continue
            try:
                value, ref = budget.pick_value(lines, spec["label"], spec["col"])
            except PipelineError as exc:
                if spec.get("required", False):
                    raise PipelineError(f"{b['tenure']} budget, field {name}: {exc}") from exc
                continue
            fields[name] = {"value": value, "prov": _prov(b["source"], ref)}
        picked[b["tenure"]] = fields
    return budgets, picked


def tenure_block(picked: dict[str, dict], price_field: str) -> list[dict[str, Any]]:
    """Tenure options; the benchmark price is the same one the market channel pays."""
    out = []
    for tenure in sorted(picked):
        f = picked[tenure]
        entry: dict[str, Any] = {
            "id": tenure,
            "budget": tenure,
            "benchmark_yield_bu_ac": f["yield_bu_ac"],
            "benchmark_price_usd_bu": f[price_field],
        }
        if tenure == "rented":
            entry["land_rent_usd_ac"] = f["land_rent_usd_ac"]
        out.append(entry)
    return out


def market_block(region: dict[str, Any], picked: dict[str, dict], ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    m = region["market_channel"]
    base = picked.get("owned") or next(iter(picked.values()))
    channel: dict[str, Any] = {
        "id": m["id"],
        "name": m["name"],
        "price_basis": m["price_basis"],
        "price_usd_bu": base[m["price_field"]],
        "price_series": None,
        "prov": base[m["price_field"]]["prov"],
    }
    if m.get("gross_price_field") in base:
        channel["gross_price_usd_bu"] = base[m["gross_price_field"]]
    # A net farm-gate price already has hauling and marketing deducted, so hauling
    # is only carried separately when the channel pays a delivered (gross) price.
    if m["price_basis"] == "delivered" and m.get("hauling_field") in base:
        channel["hauling_usd_ac"] = base[m["hauling_field"]]
    haul = next((o for o in ops if o["id"] == m["crosscheck_haul_operation"]), None)
    if haul:
        channel["crosscheck_haul_usd_mile"] = {"value": haul["rate_usd"], "prov": haul["prov"]}
    return [channel]


def weather_block(region: dict[str, Any], extracted: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cfg = region["weather"]
    station = read_json(extracted / "station.json")
    rows = read_csv(extracted / "weather_daily.csv")
    picks = weather.select_years(rows, cfg["season_start"], cfg["season_end"])
    years = []
    cols = [c for c in weather.DAILY_FIELDS if c not in ("date", "n_obs")]
    for role, year, rain in picks:
        yr = [r for r in rows if r["date"].startswith(f"{year}-")]
        years.append(
            {
                "id": f"{cfg['station_id']}-{year}",
                "year": year,
                "role": role,
                "season": {"start": cfg["season_start"], "end": cfg["season_end"], "rain_mm": rain},
                "daily": {c: [float(r[c]) if c != "doy" else int(r[c]) for r in yr] for c in cols},
                "prov": {"sources": [cfg["source"], "fao56"],
                         "loc": f"station {cfg['station_id']}, {year}",
                         "method": "15-min obs aggregated to daily; ET0 by FAO-56 Penman-Monteith (Eq. 6)"},
            }
        )
    loc_source = station.pop("location_source", cfg["source"])
    loc_text = station.pop("location_loc", "station metadata")
    station_out = {**station, "prov": _prov(loc_source, loc_text)}
    return station_out, years


def build_pack(region_id: str) -> dict[str, Any]:
    base = sources_dir()
    manual = base / "manual"
    extracted = base / "extracted" / region_id
    region = read_json(base / "regions" / f"{region_id}.json")
    registry = read_json(base / "sources.json")["sources"]
    review = read_json(base / "review" / "needs-expert-review.json")
    lock_path = extracted / "fetch-lock.json"
    if not lock_path.exists():
        raise PipelineError(
            f"no fetched data for {region_id!r}: run the 'Fetch sources' workflow "
            f"(or `agroeco-pipeline fetch --region {region_id}`) first"
        )
    lock = read_json(lock_path)
    scfg = region["soils"]
    soil_units = soils.build_soil_units(
        scfg["fields"],
        read_json(extracted / "sda_mapunits.json"),
        read_json(extracted / "sda_components.json"),
        read_json(extracted / "sda_horizons.json"),
        scfg["max_depth_cm"],
        scfg["source"],
        scfg["areasymbol"],
    )
    ops = custom_ops_block(manual)
    budgets, picked = budgets_block(region, extracted)
    station, years = weather_block(region, extracted)
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "pack_version": region["pack_version"],
        "region": {"id": region["id"], "name": region["name"]},
        "inputs": {"fetch_lock_sha256": sha256_bytes(lock_path.read_bytes()),
                   "fetched_at": lock.get("fetched_at")},
        "sources": sorted(registry, key=lambda s: s["id"]),
        "review_flags": review["items"],
        "soil_test": soil_test_block(manual),
        "soil_units": soil_units,
        "crops": [crop_block(manual, review)],
        "custom_operations": ops,
        "budgets": budgets,
        "tenure_options": tenure_block(picked, region["market_channel"]["price_field"]),
        "market_channels": market_block(region, picked, ops),
        "weather_station": station,
        "weather_years": years,
    }


def run_build(region_id: str, out: Path | None = None) -> Path:
    from agroeco_pipeline.validate import validate_pack

    pack = build_pack(region_id)
    problems = validate_pack(pack)
    if problems:
        raise PipelineError("data pack failed validation:\n  " + "\n  ".join(problems))
    target = out or packs_dir() / f"{region_id}-v{pack['pack_version']}.json"
    write_json(target, pack)
    return target
