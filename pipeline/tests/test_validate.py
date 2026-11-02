"""Plausibility checks for picked budget values (validate.plausibility_problems).

These mirror the real spot-check finding: a whole-farm total ($40,000 land rent)
must be rejected when it is read as a per-acre value, the correct per-acre rent
(~$285.71) must pass, and a net farm-gate price above the gross price must be
rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.validate import plausibility_problems  # noqa: E402


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
