"""USDA ERS Commodity Costs and Returns: pick cited cost lines from a commodity CSV.

The ERS file is a long table with the columns Commodity, Category, Item, Units,
Size, Region, Country, Year, Value and Survey base year. This module keeps only
the configured commodity, region, units and items, for the most recent
``years_kept`` actual (non-forecast) years, and records the latest value of
each item. Every kept row carries its year and survey base year so the pack can
cite it.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from agroeco_pipeline.common import PipelineError

COLUMNS = ("Commodity", "Category", "Item", "Units", "Size", "Region", "Country", "Year", "Value",
           "Survey base year")


def parse_rows(raw: bytes) -> list[dict[str, str]]:
    """Parse the ERS CSV and check that the expected columns are present."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise PipelineError(f"ERS CSV is missing columns {missing}; found {header}")
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _year(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _value(value: str, where: str) -> float:
    try:
        return float(value.replace(",", ""))
    except ValueError as exc:
        raise PipelineError(f"ERS value is not a number at {where}: {value!r}") from exc


def summarize(rows: list[dict[str, str]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Select the configured items and return per-item series plus the latest actual year."""
    commodity, region, units = cfg["commodity"], cfg["region"], cfg["units"]
    keep = int(cfg.get("years_kept", 5))
    if keep < 1:
        raise PipelineError("ers.years_kept must be at least 1")
    crop = [r for r in rows if r["Commodity"] == commodity]
    if not crop:
        found = sorted({r["Commodity"] for r in rows})
        raise PipelineError(f"ERS commodity {commodity!r} not found; available: {found}")
    in_region = [r for r in crop if r["Region"] == region]
    if not in_region:
        found = sorted({r["Region"] for r in crop})
        raise PipelineError(f"ERS region {region!r} not found for {commodity}; available: {found}")
    items: dict[str, Any] = {}
    for key, label in cfg["items"].items():
        matches = [r for r in in_region if r["Item"] == label and r["Units"].lower() == units.lower()]
        series: dict[int, tuple[float, str, str]] = {}
        for r in matches:
            year = _year(r["Year"])
            if year is None:
                continue  # forecast rows such as "2026F" are not actual estimates
            if year in series:
                raise PipelineError(f"ERS has more than one {label!r} row for {region} {year}")
            series[year] = (_value(r["Value"], f"{label} {region} {year}"), r["Survey base year"], r["Category"])
        if not series:
            found = sorted({r["Item"] for r in in_region})
            raise PipelineError(f"ERS item {label!r} ({units}) not found for {region}; items: {found}")
        years = sorted(series)[-keep:]
        latest = years[-1]
        items[key] = {
            "item": label,
            "category": series[latest][2],
            "units": units,
            "series": [{"year": y, "value": series[y][0], "survey_base_year": series[y][1]} for y in years],
            "latest_year": latest,
            "latest_value": series[latest][0],
        }
    ends = {k: v["latest_year"] for k, v in items.items()}
    if len(set(ends.values())) != 1:
        raise PipelineError(f"ERS items end in different years: {ends}")
    return {"commodity": commodity, "region": region, "units": units, "items": items,
            "latest_year": next(iter(ends.values()))}
