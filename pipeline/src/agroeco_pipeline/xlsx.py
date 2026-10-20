"""Minimal, dependency-free .xlsx cell reader (values only, no formulas).

Reads cached cell values from the Office Open XML package so budget workbooks
can be parsed in CI without third-party libraries.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_REF = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass(frozen=True)
class Cell:
    sheet: str
    ref: str
    row: int
    col: int
    value: str | float


def col_to_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def split_ref(ref: str) -> tuple[int, int]:
    m = _REF.match(ref)
    if not m:
        raise ValueError(f"bad cell reference {ref!r}")
    return int(m.group(2)), col_to_index(m.group(1))


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(t.text or "" for t in el.iter(f"{{{NS['m']}}}t"))


def read_workbook(data: bytes) -> list[Cell]:
    """Return all non-empty cells from every worksheet."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("not an .xlsx file (bad zip)") from exc
    names = set(zf.namelist())
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        shared = [_text(si) for si in root.findall("m:si", NS)]

    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target", "") for r in rels.findall("rel:Relationship", NS)}

    cells: list[Cell] = []
    for sheet in wb.findall("m:sheets/m:sheet", NS):
        name = sheet.get("name", "")
        rid = sheet.get(f"{{{NS['r']}}}id")
        target = targets.get(rid, "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        if path not in names:
            continue
        root = ET.fromstring(zf.read(path))
        for c in root.iter(f"{{{NS['m']}}}c"):
            ref = c.get("r")
            if not ref:
                continue
            kind = c.get("t", "n")
            v = c.find("m:v", NS)
            value: str | float
            if kind == "s" and v is not None and v.text is not None:
                value = shared[int(v.text)]
            elif kind == "inlineStr":
                value = _text(c.find("m:is", NS))
            elif kind in ("str", "e", "b"):
                value = v.text if v is not None and v.text is not None else ""
            elif v is not None and v.text is not None:
                try:
                    value = float(v.text)
                except ValueError:
                    value = v.text
            else:
                continue
            if value == "":
                continue
            row, col = split_ref(ref)
            cells.append(Cell(name, ref, row, col, value))
    return cells


def normalize_label(text: str) -> str:
    return " ".join(text.split()).casefold()
