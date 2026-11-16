"""The Fetch sources workflow's forgiving 'only' input (scripts/normalize-only.sh)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "normalize-only.sh"


def run(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), text], capture_output=True, text=True, check=False)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", []),
        ("all", []),
        ("Budgets, Soil", ["soils", "budgets"]),
        ("parcels ers", ["parcels", "ers"]),
        ("parcel_shapes city_limits county_outline", ["city_limits", "county_outline", "parcel_shapes"]),
        ("parcel shapes", ["parcel_shapes"]),
        ("map", ["city_limits", "county_outline", "parcel_shapes"]),
        ("map, budgets", ["budgets", "city_limits", "county_outline", "parcel_shapes"]),
        ("parcels parcel_shapes", ["parcels", "parcel_shapes"]),
        ("'cities' and 'outline'", ["city_limits", "county_outline"]),
    ],
)
def test_normalizes_steps(text: str, expected: list[str]) -> None:
    result = run(text)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == expected


def test_unknown_word_lists_choices() -> None:
    result = run("zoning")
    assert result.returncode == 2
    assert "'zoning' is not a fetch step" in result.stderr and "parcel_shapes" in result.stderr
