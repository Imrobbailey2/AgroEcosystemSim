"""Fetch step registry and ordering for the county map steps (offline)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline import cli, fetch  # noqa: E402
from agroeco_pipeline.common import read_json  # noqa: E402
from fixtures import make_sources_tree  # noqa: E402

MAP = ("city_limits", "county_outline", "parcel_shapes")


def test_cli_and_fetch_list_the_same_steps() -> None:
    assert cli.FETCH_STEPS == fetch.STEPS
    assert set(fetch.MAP_STEPS) == set(MAP)


def test_city_limits_and_outline_run_before_parcel_shapes() -> None:
    s = fetch.STEPS
    assert s.index("city_limits") < s.index("parcel_shapes")
    assert s.index("county_outline") < s.index("parcel_shapes")


def test_run_fetch_runs_map_steps_in_order_and_records_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = make_sources_tree(tmp_path)
    monkeypatch.setenv("AGROECO_SOURCES_DIR", str(base))
    calls: list[str] = []

    def fake(step: str) -> Any:
        def run(region: dict[str, Any], out: Path, record: Any, get: Any) -> None:
            calls.append(step)
            record(f"https://example.test/{step}", b"{}", "query page 1")
        return run

    for step in MAP:
        monkeypatch.setitem(fetch.MAP_STEPS, step, fake(step))
    out = fetch.run_fetch("suwannee", ["parcel_shapes", "city_limits"])
    assert calls == ["city_limits", "parcel_shapes"]
    lock = read_json(out / "fetch-lock.json")
    assert {"city_limits", "parcel_shapes"} <= set(lock["fetched_at"])
    sources = {e["step"]: e["source"] for e in lock["downloads"] if e["step"] in MAP}
    assert sources == {"city_limits": "fgdl-city-limits-2021", "parcel_shapes": "fgio-fl-statewide-parcels"}


def test_unknown_step_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGROECO_SOURCES_DIR", str(make_sources_tree(tmp_path)))
    with pytest.raises(fetch.PipelineError, match="unknown fetch steps"):
        fetch.run_fetch("suwannee", ["zoning"])
