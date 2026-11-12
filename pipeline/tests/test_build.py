"""End-to-end build on synthetic extracts: format checks, provenance, determinism."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.build import build_pack, run_build  # noqa: E402
from agroeco_pipeline.common import PipelineError  # noqa: E402
from agroeco_pipeline.validate import plausibility_problems, provenance_problems, validate_pack  # noqa: E402
from fixtures import BUDGET_LINES, OWNED_LAND_LINE, make_sources_tree, write_budget_csvs  # noqa: E402


def _build(tmp_path: Path) -> dict:
    os.environ["AGROECO_SOURCES_DIR"] = str(make_sources_tree(tmp_path))
    try:
        return build_pack("suwannee")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


def _owned(pack: dict) -> dict:
    return next(t for t in pack["tenure_options"] if t["id"] == "owned")


def test_pack_passes_schema_and_provenance(tmp_path: Path) -> None:
    pack = _build(tmp_path)
    assert validate_pack(pack) == []


def test_every_number_traces_to_a_source(tmp_path: Path) -> None:
    pack = _build(tmp_path)
    assert provenance_problems(pack) == []
    pack["custom_operations"][0].pop("prov")
    pack["custom_operations"][0]["florida_adjustment"].pop("prov")
    problems = provenance_problems(pack)
    assert any("custom_operations[0].rate_usd" in p for p in problems)


def test_content(tmp_path: Path) -> None:
    pack = _build(tmp_path)
    corn = pack["crops"][0]
    assert corn["n_rules"]["default"] == "sl129-plant-population"
    assert [r["n_lb_a"] for r in corn["fertilizer_by_population"]] == [180, 210, 240]
    assert {t["id"] for t in pack["tenure_options"]} == {"owned", "rented"}
    rented = next(t for t in pack["tenure_options"] if t["id"] == "rented")
    assert rented["land_rent_usd_ac"]["value"] == 140.0  # per-acre column E, not whole-farm D
    assert rented["land_rent_usd_ac"]["prov"]["loc"] == "FieldDetails!E20"
    assert rented["benchmark_price_usd_bu"]["value"] == 4.2  # net farm-gate, same as the market
    assert [y["role"] for y in pack["weather_years"]] == ["dry", "median", "wet"]
    assert len(pack["weather_years"][0]["daily"]["et0_mm"]) == 365
    assert {u["dominant_component"]["name"] for u in pack["soil_units"]} == {"Blanton", "Bonneau"}
    assert {f["id"] for f in pack["review_flags"]} >= {"corn-n-rule", "custom-rates-florida-adjustment"}
    market = pack["market_channels"][0]
    assert market["price_basis"] == "net_farm_gate"
    assert market["price_usd_bu"]["value"] == 4.2
    assert market["price_usd_bu"]["prov"]["loc"] == "Marketing!C15"
    assert market["gross_price_usd_bu"]["value"] == 4.5
    assert "hauling_usd_ac" not in market  # already deducted from the net price
    # Buyer charges already inside the net price are carried for reference only.
    deductions = market["included_deductions"]
    assert deductions["drying_fees_usd_ac"]["value"] == 24.6
    assert deductions["hauling_usd_ac"]["value"] == 61.5
    assert deductions["hauling_usd_ac"]["prov"]["loc"] == "Marketing!D13"
    station = pack["weather_station"]
    assert station["prov"]["sources"] == ["fawn-station-locations"]
    assert "location_source" not in station and "location_loc" not in station


def test_crop_insurance_is_a_separate_cited_cost(tmp_path: Path) -> None:
    pack = _build(tmp_path)
    [option] = pack["crop_insurance_options"]
    assert option["id"] == "rp-75"
    assert (option["plan"], option["coverage_level"]) == ("Revenue Protection", 0.75)
    assert option["premium_usd_ac"]["value"] == 12.2
    assert option["premium_usd_ac"]["prov"]["loc"] == "Marketing!D16"
    assert option["default_purchased"] is True
    assert option["proceeds_modelled"] is False
    assert "Revenue Protection, 75%" in option["prov"]["method"]


def test_budget_total_is_read_from_the_marketing_sheet(tmp_path: Path) -> None:
    """The same label on BudgetSummary holds a whole-farm total; the sheet setting avoids it."""
    pack = _build(tmp_path)
    for t in pack["tenure_options"]:
        total = t["budget_total_net_revenue_usd_ac"]
        assert total["value"] == 848.8
        assert total["prov"]["loc"] == "Marketing!D17"


def test_revenue_reconciles_with_the_budget(tmp_path: Path) -> None:
    """205 bu/A x $4.20 - $12.20 premium = $848.80, the budget's own total."""
    pack = json.loads(json.dumps(_build(tmp_path)))
    assert plausibility_problems(pack) == []
    pack["crop_insurance_options"][0]["premium_usd_ac"]["value"] = 0.0
    problems = plausibility_problems(pack)
    assert any("does not reconcile" in p and "861.00" in p and "848.80" in p for p in problems)


def test_missing_insurance_premium_fails_the_build(tmp_path: Path) -> None:
    base = make_sources_tree(tmp_path)
    write_budget_csvs(base / "extracted" / "suwannee",
                      [ln for ln in BUDGET_LINES if ln[0] != "Revenue Protection, 75%"])
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        with pytest.raises(PipelineError, match="crop_insurance_premium_usd_ac"):
            build_pack("suwannee")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


def test_whole_farm_rent_is_rejected(tmp_path: Path) -> None:
    """The bug found in the spot-check: $40,000 whole-farm rent read as $/acre."""
    pack = _build(tmp_path)
    rented = next(t for t in pack["tenure_options"] if t["id"] == "rented")
    rented["land_rent_usd_ac"]["value"] = 40000.0
    problems = plausibility_problems(pack)
    assert any("land_rent_usd_ac = 40000.0" in p and "whole-farm" in p for p in problems)


def test_implausible_price_and_net_above_gross_are_rejected(tmp_path: Path) -> None:
    # Round-trip through JSON (as the written pack is) so shared sub-objects become independent.
    pack = json.loads(json.dumps(_build(tmp_path)))
    pack["tenure_options"][0]["benchmark_price_usd_bu"]["value"] = 861.0
    pack["market_channels"][0]["price_usd_bu"]["value"] = 5.0
    problems = plausibility_problems(pack)
    assert any("benchmark_price_usd_bu = 861.0" in p for p in problems)
    assert any("net price 5.0 exceeds gross price 4.5" in p for p in problems)


def test_owned_land_cost_lines(tmp_path: Path) -> None:
    """Option C: $4.03 tax + $5.97 insurance = the budget's $10.00/A; + $23.96 upkeep = $33.96/A."""
    owned = _owned(_build(tmp_path))
    assert owned["property_tax_usd_ac"]["value"] == 4.03  # $278.63/A x 14.4745 mills / 1,000
    assert owned["property_insurance_usd_ac"]["value"] == 5.97
    assert owned["upkeep_usd_ac"]["value"] == 23.96
    assert owned["owned_land_cost_usd_ac"]["value"] == 33.96
    budget = owned["budget_property_tax_and_insurance_usd_ac"]
    assert (budget["value"], budget["prov"]["loc"]) == (10.0, "FieldDetails!E21")  # per-acre E, not D
    basis = owned["property_tax_basis"]
    assert basis["use_value_usd_ac"]["value"] == 278.63
    assert basis["total_mills"] == 14.4745
    assert [m["mills"] for m in basis["millage"]] == [8.8, 5.405, 0.2695]
    assert basis["review_flag"] == "owned-land-use-value"
    assert set(owned["property_tax_usd_ac"]["prov"]["sources"]) == {
        "fgio-fl-statewide-parcels", "suwannee-bocc-millage-fy2027",
        "suwannee-school-board-millage-fy2027", "srwmd-millage-fy2027",
    }
    assert owned["property_insurance_usd_ac"]["prov"]["sources"] == ["svaec-corn-2026-ct-owned", "agroeco-adjustments"]
    assert owned["upkeep_usd_ac"]["prov"]["sources"] == ["usda-ers-ccr-corn"]
    assert "General farm overhead" in owned["upkeep_usd_ac"]["prov"]["loc"]
    assert "2024" in owned["upkeep_usd_ac"]["prov"]["loc"]


def test_rented_land_has_no_owned_land_costs(tmp_path: Path) -> None:
    rented = next(t for t in _build(tmp_path)["tenure_options"] if t["id"] == "rented")
    for key in ("property_tax_usd_ac", "owned_land_cost_usd_ac", "land_appreciation"):
        assert key not in rented


def test_land_appreciation(tmp_path: Path) -> None:
    """USDA NASS Florida cropland 2022-2026: ($11,100 / $8,340)^(1/4) - 1 = 7.41%/yr."""
    appreciation = _owned(_build(tmp_path))["land_appreciation"]
    assert [(s["year"], s["usd_ac"]) for s in appreciation["series"]] == [
        (2022, 8340.0), (2023, 9290.0), (2024, 10170.0), (2025, 10550.0), (2026, 11100.0),
    ]
    assert appreciation["rate_per_yr"]["value"] == pytest.approx(0.074086, abs=1e-6)
    assert round(appreciation["rate_per_yr"]["value"] * 100, 2) == 7.41
    assert appreciation["rate_per_yr"]["prov"]["sources"] == ["usda-nass-land-values-2026"]
    assert appreciation["review_flag"] == "land-appreciation-method"


def test_owned_budget_without_property_tax_line_fails_the_build(tmp_path: Path) -> None:
    base = make_sources_tree(tmp_path)
    write_budget_csvs(base / "extracted" / "suwannee", owned_lines=[])
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        with pytest.raises(PipelineError, match="property_tax_and_insurance_usd_ac"):
            build_pack("suwannee")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


def test_missing_parcels_extract_explains(tmp_path: Path) -> None:
    base = make_sources_tree(tmp_path)
    (base / "extracted" / "suwannee" / "parcels_summary.json").unlink()
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        with pytest.raises(PipelineError, match="only = parcels"):
            build_pack("suwannee")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


def test_property_tax_above_the_budget_line_fails_the_build(tmp_path: Path) -> None:
    """If tax ($4.03/A) exceeds the budget's 'Property tax and insurance', insurance must not go negative."""
    base = make_sources_tree(tmp_path)
    label, sheet, cell, occ, _ = OWNED_LAND_LINE
    write_budget_csvs(base / "extracted" / "suwannee", owned_lines=[(label, sheet, cell, occ, [["E21", 3.0]])])
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        with pytest.raises(PipelineError, match="property_insurance_usd_ac = -1.03 is negative"):
            run_build("suwannee", tmp_path / "p.json")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


def test_build_is_byte_deterministic(tmp_path: Path) -> None:
    os.environ["AGROECO_SOURCES_DIR"] = str(make_sources_tree(tmp_path))
    try:
        a = run_build("suwannee", tmp_path / "a.json").read_bytes()
        b = run_build("suwannee", tmp_path / "b.json").read_bytes()
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]
    assert a == b
