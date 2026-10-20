"""End-to-end build on synthetic extracts: format checks, provenance, determinism."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.build import build_pack, run_build  # noqa: E402
from agroeco_pipeline.validate import provenance_problems, validate_pack  # noqa: E402
from fixtures import make_sources_tree  # noqa: E402


def _build(tmp_path: Path) -> dict:
    os.environ["AGROECO_SOURCES_DIR"] = str(make_sources_tree(tmp_path))
    try:
        return build_pack("suwannee")
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]


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
    assert rented["land_rent_usd_ac"]["value"] == 140.0
    assert [y["role"] for y in pack["weather_years"]] == ["dry", "median", "wet"]
    assert len(pack["weather_years"][0]["daily"]["et0_mm"]) == 365
    assert {u["dominant_component"]["name"] for u in pack["soil_units"]} == {"Blanton", "Bonneau"}
    assert {f["id"] for f in pack["review_flags"]} >= {"corn-n-rule", "custom-rates-florida-adjustment"}
    assert pack["market_channels"][0]["price_usd_bu"]["value"] == 4.5


def test_build_is_byte_deterministic(tmp_path: Path) -> None:
    os.environ["AGROECO_SOURCES_DIR"] = str(make_sources_tree(tmp_path))
    try:
        a = run_build("suwannee", tmp_path / "a.json").read_bytes()
        b = run_build("suwannee", tmp_path / "b.json").read_bytes()
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]
    assert a == b
