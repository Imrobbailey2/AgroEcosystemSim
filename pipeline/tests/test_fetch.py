"""Fetch steps with fake transports (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline import fetch  # noqa: E402
from agroeco_pipeline.common import PIPELINE_DIR, PipelineError, read_csv, read_json  # noqa: E402
from fixtures import make_xlsx  # noqa: E402

REGION = read_json(PIPELINE_DIR / "sources" / "regions" / "suwannee.json")
REGISTRY = {s["id"]: s for s in read_json(PIPELINE_DIR / "sources" / "sources.json")["sources"]}


def test_fetch_budgets_writes_cell_references(tmp_path: Path) -> None:
    def fake_get(url: str) -> bytes:
        rows = [["Crop yield (units/acre)", 205], ["Average delivered gross price ($/unit)", 4.5]]
        if "Rented" in url:
            rows.append(["Land rental cost", 140])
        return make_xlsx(rows)

    lock = fetch.Lock()
    fetch.fetch_budgets(REGION, REGISTRY, tmp_path, lock, get=fake_get)
    rented = read_csv(tmp_path / "budget_rented.csv")
    rent = next(r for r in rented if r["label"] == "Land rental cost")
    assert json.loads(rent["values"]) == [["B3", 140.0]]
    assert len(lock.entries) == 2 and all(len(e["sha256"]) == 64 for e in lock.entries)


def test_fetch_budgets_requires_rent_for_rented(tmp_path: Path) -> None:
    def fake_get(url: str) -> bytes:
        return make_xlsx([["Crop yield (units/acre)", 205], ["Average delivered gross price ($/unit)", 4.5]])

    with pytest.raises(PipelineError, match="Land rental cost"):
        fetch.fetch_budgets(REGION, REGISTRY, tmp_path, fetch.Lock(), get=fake_get)


def test_fetch_soils_fails_on_missing_map_unit(tmp_path: Path) -> None:
    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> bytes:
        return json.dumps({"Table": [["areasymbol", "saverest", "mukey", "musym", "muname"],
                                     ["FL121", "v", "1", "13", "Something else"]]}).encode()

    with pytest.raises(PipelineError, match="map units not found"):
        fetch.fetch_soils(REGION, tmp_path, fetch.Lock(), post=fake_post)
    assert not (tmp_path / "sda_mapunits.json").exists()
