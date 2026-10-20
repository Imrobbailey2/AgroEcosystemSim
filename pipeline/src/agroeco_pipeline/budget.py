"""Extract labelled budget lines from UF/IFAS budget workbooks."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from difflib import get_close_matches
from typing import Any

from agroeco_pipeline.common import PipelineError
from agroeco_pipeline.xlsx import Cell, normalize_label

FIELDS = ["label", "sheet", "label_cell", "occurrence", "values"]


def extract_lines(
    cells: Iterable[Cell], required: list[str], optional: list[str]
) -> list[dict[str, Any]]:
    """For each label, record every numeric cell to its right on the same row.

    Each occurrence of a label is kept (labels can repeat across sections).
    Raises PipelineError listing close matches if a required label is missing.
    """
    by_row: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    text_cells: list[Cell] = []
    for c in cells:
        by_row[(c.sheet, c.row)].append(c)
        if isinstance(c.value, str):
            text_cells.append(c)

    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for label in [*required, *optional]:
        want = normalize_label(label)
        hits = [c for c in text_cells if normalize_label(str(c.value)) == want]
        hits.sort(key=lambda c: (c.sheet, c.row, c.col))
        if not hits:
            if label in required:
                missing.append(label)
            continue
        for i, hit in enumerate(hits):
            right = sorted(
                (c for c in by_row[(hit.sheet, hit.row)] if c.col > hit.col and isinstance(c.value, float)),
                key=lambda c: c.col,
            )
            rows.append(
                {
                    "label": label,
                    "sheet": hit.sheet,
                    "label_cell": hit.ref,
                    "occurrence": i,
                    "values": json.dumps([[c.ref, c.value] for c in right]),
                }
            )
    if missing:
        all_labels = sorted({str(c.value) for c in text_cells})
        hints = {m: get_close_matches(m, all_labels, n=3, cutoff=0.5) for m in missing}
        raise PipelineError(f"required budget labels not found: {hints}")
    return rows


def pick_value(lines: list[dict[str, str]], label: str, pick: int) -> tuple[float, str]:
    """Return (value, 'sheet!cell') for the first occurrence of `label` with a value."""
    for line in sorted(lines, key=lambda r: int(r["occurrence"])):
        if line["label"] != label:
            continue
        values = json.loads(line["values"])
        if len(values) > pick:
            ref, val = values[pick]
            return float(val), f"{line['sheet']}!{ref}"
    raise PipelineError(f"no numeric value #{pick} for budget label {label!r}")
