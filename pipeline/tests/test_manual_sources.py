"""Hand-entered tables match the published sources (spot values) and cite real sources."""

from __future__ import annotations

import math

from agroeco_pipeline.common import PIPELINE_DIR, read_csv, read_json

MANUAL = PIPELINE_DIR / "sources" / "manual"
SOURCES = {s["id"] for s in read_json(PIPELINE_DIR / "sources" / "sources.json")["sources"]}


def test_every_manual_row_cites_a_registered_source() -> None:
    for path in sorted(MANUAL.glob("*.csv")):
        for i, row in enumerate(read_csv(path)):
            assert row.get("source") in SOURCES, f"{path.name} row {i + 2}: {row.get('source')!r}"


def test_sl129_mehlich3_ratings() -> None:
    rows = {(r["nutrient"], r["rating"]): r for r in read_csv(MANUAL / "sl129_ratings.csv")}
    assert rows[("P", "Low")]["le_mg_kg"] == "25"
    assert (rows[("P", "Medium")]["gt_mg_kg"], rows[("P", "Medium")]["le_mg_kg"]) == ("25", "45")
    assert rows[("P", "High")]["gt_mg_kg"] == "45"
    assert rows[("K", "Low")]["le_mg_kg"] == "35"
    assert rows[("K", "High")]["gt_mg_kg"] == "60"
    assert rows[("Mg", "Low")]["le_mg_kg"] == "20"
    assert rows[("Mg", "High")]["gt_mg_kg"] == "40"


def test_sl129_irrigated_corn_rows() -> None:
    rows = {
        int(r["plants_per_acre"]): r
        for r in read_csv(MANUAL / "sl129_corn.csv")
        if r["crop_code"] == "5"
    }
    assert set(rows) == {20000, 25000, 30000}
    assert [rows[p]["n_lb_a"] for p in (20000, 25000, 30000)] == ["180", "210", "240"]
    r30 = rows[30000]
    assert (r30["p2o5_lo"], r30["p2o5_med"], r30["p2o5_hi"]) == ("175", "70", "0")
    assert (r30["k2o_lo"], r30["k2o_med"], r30["k2o_hi"]) == ("175", "70", "0")
    assert all(r["target_ph"] == "6.5" for r in rows.values())


def test_footnote_104_split_adds_up() -> None:
    fn = {r["key"]: r["value"] for r in read_csv(MANUAL / "sl129_footnotes.csv") if r["footnote"] == "104"}
    assert float(fn["preplant_n"]) + float(fn["remaining_n"]) == 210
    assert float(fn["preplant_k2o_fraction"]) + float(fn["sidedress_k2o_fraction"]) == 1.0


def test_interim_n_rule_is_1_37_lb_per_bu() -> None:
    # The published table rounds half up (e.g. 250 x 1.37 = 342.5 -> 343).
    for r in read_csv(MANUAL / "n_interim_yield_goal.csv"):
        assert math.floor(float(r["yield_bu_ac"]) * 1.37 + 0.5 + 1e-9) == int(r["n_lb_ac"])


def test_georgia_custom_rates_spot_values() -> None:
    rows = {r["operation_id"]: r for r in read_csv(MANUAL / "custom_rates_ga2024.csv")}
    assert rows["combine_corn"]["average"] == "58.50"
    assert rows["plant_corn"]["average"] == "27.00"
    assert rows["haul_grain"]["unit"] == "mile"
    for r in rows.values():
        assert float(r["low"]) <= float(r["median"]) <= float(r["high"])
        assert float(r["low"]) <= float(r["average"]) <= float(r["high"])


def test_review_register_default_is_sl129() -> None:
    review = read_json(PIPELINE_DIR / "sources" / "review" / "needs-expert-review.json")
    item = next(i for i in review["items"] if i["id"] == "corn-n-rule")
    assert item["current_default"] == "sl129-plant-population"
    assert {o["id"] for o in item["options"]} == {"sl129-plant-population", "interim-yield-goal"}
