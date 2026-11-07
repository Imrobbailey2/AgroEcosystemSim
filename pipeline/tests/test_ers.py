"""ERS Commodity Costs and Returns selection (no network)."""

from __future__ import annotations

import pytest

from agroeco_pipeline import ers
from agroeco_pipeline.common import PipelineError

HEADER = '"Commodity","Category","Item","Units","Size","Region","Country","Year","Value","Survey base year"\n'
CFG = {
    "commodity": "Corn",
    "region": "Southern Seaboard",
    "units": "dollars per planted acre",
    "items": {"taxes_and_insurance": "Taxes and insurance", "general_farm_overhead": "General farm overhead"},
    "years_kept": 3,
}


def _row(item: str, region: str, year: str, value: str, units: str = "dollars per planted acre") -> str:
    return (f'"Corn","Allocated overhead","{item}","{units}","No specific size","{region}",'
            f'"United States",{year},{value},"Base survey of 2021"\n')


def _csv(extra: str = "") -> bytes:
    body = ""
    for year, t, g in [(2020, "10.5", "20.1"), (2021, "11", "21"), (2022, "12", "22"), (2023, "13", "23"),
                       (2024, "14.25", "24.75")]:
        body += _row("Taxes and insurance", "Southern Seaboard", str(year), t)
        body += _row("General farm overhead", "Southern Seaboard", str(year), g)
        body += _row("Taxes and insurance", "Heartland", str(year), "99")
    body += _row("Taxes and insurance", "Southern Seaboard", "2026F", "50")
    body += _row("General farm overhead", "Southern Seaboard", "2026F", "60")
    return (HEADER + body + extra).encode()


def test_latest_actual_year_and_series() -> None:
    s = ers.summarize(ers.parse_rows(_csv()), CFG)
    assert s["latest_year"] == 2024
    t = s["items"]["taxes_and_insurance"]
    assert t["latest_value"] == 14.25
    assert [p["year"] for p in t["series"]] == [2022, 2023, 2024]
    assert s["items"]["general_farm_overhead"]["latest_value"] == 24.75
    assert t["category"] == "Allocated overhead"


def test_unknown_region_lists_available() -> None:
    with pytest.raises(PipelineError, match="Heartland"):
        ers.summarize(ers.parse_rows(_csv()), {**CFG, "region": "Southern Seaboard Region"})


def test_missing_item_lists_items() -> None:
    with pytest.raises(PipelineError, match="General farm overhead"):
        ers.summarize(ers.parse_rows(_csv()), {**CFG, "items": {"x": "Real estate taxes"}})


def test_duplicate_year_rejected() -> None:
    extra = _row("Taxes and insurance", "Southern Seaboard", "2024", "15")
    with pytest.raises(PipelineError, match="more than one"):
        ers.summarize(ers.parse_rows(_csv(extra)), CFG)


def test_missing_columns_rejected() -> None:
    with pytest.raises(PipelineError, match="missing columns"):
        ers.parse_rows(b"Commodity,Item\nCorn,Seed\n")


def test_items_ending_in_different_years_rejected() -> None:
    extra = _row("Taxes and insurance", "Southern Seaboard", "2025", "15")
    with pytest.raises(PipelineError, match="different years"):
        ers.summarize(ers.parse_rows(_csv(extra)), CFG)
