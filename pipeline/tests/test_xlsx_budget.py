"""Workbook reader and budget-line extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline.budget import extract_lines, pick_value  # noqa: E402
from agroeco_pipeline.common import PipelineError  # noqa: E402
from agroeco_pipeline.xlsx import read_workbook  # noqa: E402
from fixtures import make_xlsx  # noqa: E402

ROWS = [
    ["NORTH FLORIDA FIELD CORN CROP BUDGET"],
    ["Crop yield (units/acre)", None, 205, 1.0],
    ["Average delivered gross price ($/unit)", "bu", 4.5],
    ["Land  rental cost", 140],
    ["Fertilizers & lime", 210.25, 0.3],
]


def test_reads_strings_and_numbers() -> None:
    cells = read_workbook(make_xlsx(ROWS))
    by_ref = {c.ref: c.value for c in cells}
    assert by_ref["A2"] == "Crop yield (units/acre)"
    assert by_ref["C2"] == 205.0
    assert by_ref["A5"] == "Fertilizers & lime"


def test_extracts_numeric_cells_right_of_label() -> None:
    cells = read_workbook(make_xlsx(ROWS))
    lines = extract_lines(
        cells,
        ["Crop yield (units/acre)", "Average delivered gross price ($/unit)", "Land rental cost"],
        ["Fertilizers & lime", "Not in workbook"],
    )
    got = {ln["label"]: json.loads(ln["values"]) for ln in lines}
    assert got["Crop yield (units/acre)"] == [["C2", 205.0], ["D2", 1.0]]
    assert got["Average delivered gross price ($/unit)"] == [["C3", 4.5]]
    assert got["Land rental cost"] == [["B4", 140.0]]  # whitespace-normalised match
    assert "Not in workbook" not in got
    str_lines = [{k: str(v) for k, v in ln.items()} for ln in lines]
    assert pick_value(str_lines, "Crop yield (units/acre)", 0) == (205.0, "Budget!C2")
    assert pick_value(str_lines, "Crop yield (units/acre)", 1) == (1.0, "Budget!D2")
    with pytest.raises(PipelineError):
        pick_value(str_lines, "Land rental cost", 1)


def test_missing_required_label_suggests_matches() -> None:
    cells = read_workbook(make_xlsx(ROWS))
    with pytest.raises(PipelineError, match="Crop yield"):
        extract_lines(cells, ["Crop yields (units/acre)"], [])


def test_rejects_non_xlsx() -> None:
    with pytest.raises(ValueError):
        read_workbook(b"not a zip")
