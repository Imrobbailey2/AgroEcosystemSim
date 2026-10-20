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
    assert pick_value(str_lines, "Crop yield (units/acre)", "C") == (205.0, "Budget!C2")
    assert pick_value(str_lines, "Crop yield (units/acre)", "d") == (1.0, "Budget!D2")
    with pytest.raises(PipelineError, match=r"column E .*Budget!B4"):
        pick_value(str_lines, "Land rental cost", "E")


def test_pick_by_column_skips_whole_farm_total() -> None:
    """Rented 2026 budget: row 19 has whole-farm rent in D and $/acre in E."""
    lines = [
        {"label": "Land rental cost", "sheet": "FieldDetails", "label_cell": "B19", "occurrence": "0",
         "values": json.dumps([["D19", 40000.0], ["E19", 285.7142857142857]])},
    ]
    assert pick_value(lines, "Land rental cost", "E") == (285.7142857142857, "FieldDetails!E19")


def test_pick_by_column_uses_later_occurrence_when_first_lacks_column() -> None:
    lines = [
        {"label": "Total", "sheet": "A", "label_cell": "B5", "occurrence": "0", "values": "[]"},
        {"label": "Total", "sheet": "B", "label_cell": "B9", "occurrence": "1",
         "values": json.dumps([["C9", 4.72], ["AA9", 1.0]])},
    ]
    assert pick_value(lines, "Total", "C") == (4.72, "B!C9")
    assert pick_value(lines, "Total", "AA") == (1.0, "B!AA9")


def test_missing_required_label_suggests_matches() -> None:
    cells = read_workbook(make_xlsx(ROWS))
    with pytest.raises(PipelineError, match="Crop yield"):
        extract_lines(cells, ["Crop yields (units/acre)"], [])


def test_rejects_non_xlsx() -> None:
    with pytest.raises(ValueError):
        read_workbook(b"not a zip")
