"""Plausibility checks for picked budget values (validate.plausibility_problems).

These mirror the real spot-check findings: a whole-farm total ($40,000 land rent)
must be rejected when it is read as a per-acre value, the correct per-acre rent
(~$285.71) must pass, a net farm-gate price above the gross price must be
rejected, and the pack's revenue must reconcile with the budget's own total
(205 bu/A x $4.78/bu - $12.20/A crop insurance premium = $967.70/A).

Owned-land costs (option C, 2026-11-09): property tax $4.03 + property insurance
$5.97 = the owned budget's "Property tax and insurance" $10.00/A; plus upkeep
$23.96 = the Basic total $33.96/A; land appreciation 7.41%/yr from the NASS series.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.validate import owned_land_problems, plausibility_problems  # noqa: E402


def _num(value: float) -> dict:
    """A picked value as it appears in the pack: a dict with a numeric 'value'."""
    return {"value": value, "prov": {"loc": "x", "sources": ["svaec-corn-2026-ct-rented"]}}


def _rented(rent: float) -> dict:
    """A rented tenure option with a 205 bu/A x $5.20 revenue and the given rent."""
    return {
        "id": "rented",
        "benchmark_yield_bu_ac": _num(205.0),
        "benchmark_price_usd_bu": _num(5.2),
        "land_rent_usd_ac": _num(rent),
    }


def _reconcile_pack(total: float, premium: float = 12.2, purchased: bool = True) -> dict:
    """The real 2026 values: 205 bu/A at the $4.78/bu net farm-gate price."""
    return {
        "tenure_options": [
            {
                "id": "owned",
                "benchmark_yield_bu_ac": _num(205.0),
                "benchmark_price_usd_bu": _num(4.78),
                "budget_total_net_revenue_usd_ac": _num(total),
            }
        ],
        "crop_insurance_options": [
            {"id": "rp-75", "premium_usd_ac": _num(premium), "default_purchased": purchased},
        ],
    }


NASS_FL_CROPLAND = [(2022, 8340.0), (2023, 9290.0), (2024, 10170.0), (2025, 10550.0), (2026, 11100.0)]


def _owned(
    tax: float = 4.03,
    insurance: float = 5.97,
    upkeep: float = 23.96,
    total: float = 33.96,
    budget: float = 10.0,
    rate: float = 0.074086,
    series: list[tuple[int, float]] | None = None,
) -> dict:
    """An owned tenure option with the real 2026 owned-land values (option C)."""
    points = NASS_FL_CROPLAND if series is None else series
    return {
        "id": "owned",
        "benchmark_yield_bu_ac": _num(205.0),
        "benchmark_price_usd_bu": _num(4.78),
        "property_tax_usd_ac": _num(tax),
        "property_insurance_usd_ac": _num(insurance),
        "upkeep_usd_ac": _num(upkeep),
        "owned_land_cost_usd_ac": _num(total),
        "budget_property_tax_and_insurance_usd_ac": _num(budget),
        "land_appreciation": {
            "series": [{"year": y, "usd_ac": v, "prov": {"loc": "x", "sources": ["s"]}} for y, v in points],
            "rate_per_yr": _num(rate),
        },
    }


def test_whole_farm_rent_is_flagged() -> None:
    """$40,000/acre is a whole-farm total read as $/acre; it must be flagged."""
    pack = {"tenure_options": [_rented(40000.0)]}
    problems = plausibility_problems(pack)
    assert any(
        "land_rent_usd_ac = 40000.0" in p and "whole-farm" in p for p in problems
    )


def test_per_acre_rent_is_not_flagged() -> None:
    """The correct per-acre rent (~$285.71 from FieldDetails!E19) must pass."""
    pack = {"tenure_options": [_rented(285.7142857142857)]}
    assert plausibility_problems(pack) == []


def test_net_price_above_gross_is_flagged() -> None:
    """A net farm-gate price above the gross price must be flagged."""
    pack = {
        "market_channels": [
            {
                "price_basis": "net_farm_gate",
                "price_usd_bu": _num(5.0),
                "gross_price_usd_bu": _num(4.78),
            }
        ]
    }
    problems = plausibility_problems(pack)
    assert any("net price 5.0 exceeds gross price 4.78" in p for p in problems)


def test_net_price_below_gross_is_not_flagged() -> None:
    """The real net ($4.78) below the gross ($5.20) must pass."""
    pack = {
        "market_channels": [
            {
                "price_basis": "net_farm_gate",
                "price_usd_bu": _num(4.78),
                "gross_price_usd_bu": _num(5.2),
            }
        ]
    }
    assert plausibility_problems(pack) == []


def test_implausible_yield_and_price_are_flagged() -> None:
    """A benchmark yield and price outside the plausible bounds must be flagged."""
    pack = {
        "tenure_options": [
            {
                "id": "owned",
                "benchmark_yield_bu_ac": _num(5000.0),
                "benchmark_price_usd_bu": _num(861.0),
            }
        ]
    }
    problems = plausibility_problems(pack)
    assert any("benchmark_yield_bu_ac = 5000.0" in p for p in problems)
    assert any("benchmark_price_usd_bu = 861.0" in p for p in problems)


def test_real_budget_reconciles() -> None:
    """$979.90 - $12.20 = $967.70 (Marketing!D39 is stored as 967.6999999999999)."""
    assert plausibility_problems(_reconcile_pack(967.6999999999999)) == []


def test_missing_premium_deduction_is_flagged() -> None:
    """Paying C39 ($4.72) as a price or forgetting the premium must not pass silently."""
    problems = plausibility_problems(_reconcile_pack(967.7, premium=0.0))
    assert any("does not reconcile" in p and "979.90" in p and "967.70" in p for p in problems)


def test_reconcile_skipped_without_a_default_insurance_option() -> None:
    """With no option marked as purchased there is no premium to reconcile."""
    assert plausibility_problems(_reconcile_pack(967.7, premium=0.0, purchased=False)) == []


def test_real_owned_land_costs_pass() -> None:
    """$4.03 + $5.97 + $23.96 = $33.96/A; $4.03 + $5.97 = $10.00/A; 7.41%/yr."""
    assert plausibility_problems({"tenure_options": [_owned()]}) == []


def test_basic_total_must_equal_the_sum_of_the_lines() -> None:
    problems = owned_land_problems(_owned(total=34.00))
    assert any("owned_land_cost_usd_ac = 34.00 does not equal the sum" in p and "33.96" in p for p in problems)


def test_basic_total_within_one_cent_passes() -> None:
    assert owned_land_problems(_owned(total=33.965)) == []


def test_basic_total_without_its_lines_is_flagged() -> None:
    owned = _owned()
    del owned["upkeep_usd_ac"]
    problems = owned_land_problems(owned)
    assert any("'upkeep_usd_ac'" in p and "missing" in p for p in problems)


def test_tax_and_insurance_must_reconcile_with_the_budget() -> None:
    """Option B ($4.03 tax + ERS $17.02) would be $11.05/A above the budget's $10.00/A."""
    problems = owned_land_problems(_owned(insurance=17.02, total=45.01))
    assert any("21.05 does not reconcile" in p and "10.00" in p for p in problems)


def test_negative_property_insurance_is_flagged() -> None:
    """Property tax above the budget's line must fail rather than give negative insurance."""
    problems = owned_land_problems(_owned(tax=12.0, insurance=-2.0, total=33.96, budget=10.0))
    assert any("property_insurance_usd_ac = -2.00 is negative" in p for p in problems)


def test_appreciation_rate_must_match_the_series() -> None:
    """Using a year-on-year change (2026: +5.2%) instead of the 2022-2026 compound rate is caught."""
    problems = owned_land_problems(_owned(rate=0.052))
    assert any("rate_per_yr = 0.052 does not match" in p and "0.074086" in p for p in problems)


def test_appreciation_series_must_be_increasing_years() -> None:
    problems = owned_land_problems(_owned(series=[(2026, 11100.0), (2022, 8340.0)]))
    assert any("increasing order" in p for p in problems)


def test_appreciation_series_rejects_non_positive_values() -> None:
    problems = owned_land_problems(_owned(series=[(2022, 0.0), (2026, 11100.0)]))
    assert any("non-positive" in p for p in problems)
