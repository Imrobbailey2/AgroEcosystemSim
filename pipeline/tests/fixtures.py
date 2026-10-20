"""Synthetic inputs for offline tests (no network, no copyrighted files)."""

from __future__ import annotations

import io
import json
import math
import shutil
import zipfile
from datetime import date, timedelta
from pathlib import Path

from agroeco_pipeline.common import PIPELINE_DIR, write_csv, write_json
from agroeco_pipeline.weather import DAILY_FIELDS


def make_xlsx(rows: list[list[object]], sheet: str = "Budget") -> bytes:
    """Build a tiny .xlsx with shared strings for text and numbers inline."""
    strings: list[str] = []
    cells_xml = []
    for r, row in enumerate(rows, start=1):
        cs = []
        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if value is None:
                continue
            if isinstance(value, str):
                strings.append(value)
                cs.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
            else:
                cs.append(f'<c r="{ref}"><v>{value}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cs)}</row>')
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    sheet_xml = f'<worksheet xmlns="{m}"><sheetData>{"".join(cells_xml)}</sheetData></worksheet>'
    sst = "".join(f"<si><t>{s.replace('&', '&amp;')}</t></si>" for s in strings)
    files = {
        "xl/workbook.xml": f'<workbook xmlns="{m}" xmlns:r="{r_ns}"><sheets>'
        f'<sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{pkg_ns}">'
        '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst xmlns="{m}">{sst}</sst>',
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def daily_rows(years: list[int], rain_scale: dict[int, float]) -> list[dict[str, object]]:
    rows = []
    for y in years:
        d = date(y, 1, 1)
        while d.year == y:
            doy = d.timetuple().tm_yday
            season = math.sin(math.pi * (doy - 30) / 365)
            rows.append({
                "date": d.isoformat(), "doy": doy,
                "tmax_c": round(22 + 10 * season, 2), "tmin_c": round(10 + 9 * season, 2),
                "rhmax_pct": 95.0, "rhmin_pct": 50.0,
                "rain_mm": round(rain_scale[y] * (3.0 if doy % 4 == 0 else 0.0), 2),
                "solar_mj_m2": round(14 + 8 * season, 3), "wind2m_ms": 2.0,
                "et0_mm": round(2 + 3 * season, 3), "n_obs": 96,
            })
            d += timedelta(days=1)
    return rows


def make_sources_tree(root: Path) -> Path:
    """Copy the real committed sources and add synthetic extracts for 'suwannee'."""
    base = root / "sources"
    for sub in ("manual", "review", "regions"):
        shutil.copytree(PIPELINE_DIR / "sources" / sub, base / sub)
    shutil.copy(PIPELINE_DIR / "sources" / "sources.json", base / "sources.json")
    ex = base / "extracted" / "suwannee"
    ex.mkdir(parents=True)
    region = json.loads((base / "regions" / "suwannee.json").read_text())
    names = [f["muname"] for f in region["soils"]["fields"]]
    write_json(ex / "sda_mapunits.json", [
        {"areasymbol": "FL121", "saverest": "Aug 1 2025", "mukey": "1001", "musym": "13", "muname": names[0]},
        {"areasymbol": "FL121", "saverest": "Aug 1 2025", "mukey": "1002", "musym": "20", "muname": names[1]},
    ])
    write_json(ex / "sda_components.json", [
        {"mukey": "1001", "cokey": "11", "compname": "Blanton", "comppct_r": 45, "majcompflag": "Yes",
         "hydgrp": "A", "drainagecl": "Moderately well drained", "taxclname": "x"},
        {"mukey": "1001", "cokey": "12", "compname": "Alpin", "comppct_r": 30, "majcompflag": "Yes",
         "hydgrp": "A", "drainagecl": "Excessively drained", "taxclname": "x"},
        {"mukey": "1002", "cokey": "21", "compname": "Bonneau", "comppct_r": 50, "majcompflag": "Yes",
         "hydgrp": "B", "drainagecl": "Well drained", "taxclname": "x"},
    ])
    hz = []
    for cokey, fc, wp in (("11", 8.0, 3.0), ("12", 6.0, 2.5), ("21", 14.0, 6.0)):
        for i, (top, bottom) in enumerate(((0, 30), (30, 100), (100, 203))):
            hz.append({"cokey": cokey, "chkey": f"{cokey}{i}", "hzname": f"H{i}", "hzdept_r": top,
                       "hzdepb_r": bottom, "sandtotal_r": 90, "silttotal_r": 5, "claytotal_r": 5,
                       "om_r": 1.0, "dbthirdbar_r": 1.5, "wthirdbar_r": fc, "wfifteenbar_r": wp,
                       "awc_r": 0.06, "ksat_r": 40, "ph1to1h2o_r": 5.5, "cec7_r": 3})
    write_json(ex / "sda_horizons.json", hz)
    # Same column layout as the real 2026 workbooks: per-unit values in C, per-acre
    # hauling in D, and a land-rent row holding the whole-farm total (D) before the
    # per-acre value (E).
    lines = [
        ("Crop yield (units/acre)", [["C10", 205.0]]),
        ("Average delivered gross price ($/unit)", [["C11", 4.5]]),
        ("Net farm-gate crop sales revenue", [["C12", 4.2], ["D12", 861.0]]),
        ("Hauling cost", [["D13", 24.6]]),
        ("Annual interest rate", [["C14", 0.08]]),
    ]
    for tenure in ("owned", "rented"):
        rows = [{"label": lab, "sheet": "Budget", "label_cell": "B1", "occurrence": 0,
                 "values": json.dumps(v)} for lab, v in lines]
        if tenure == "rented":
            rows.append({"label": "Land rental cost", "sheet": "Budget", "label_cell": "B20",
                         "occurrence": 0, "values": json.dumps([["D20", 19600.0], ["E20", 140.0]])})
        write_csv(ex / f"budget_{tenure}.csv", rows, ["label", "sheet", "label_cell", "occurrence", "values"])
    write_json(ex / "station.json", {"latitude": 30.3, "longitude": -82.9, "elevation_m": 50.0,
                                     "station_id": 170, "name": "Live Oak",
                                     "source": "fawn-gapfree-liveoak-170",
                                     "location_source": "fawn-station-locations",
                                     "location_loc": "Live Oak (Station ID 170)"})
    years = [2010, 2011, 2012, 2013, 2014]
    write_csv(ex / "weather_daily.csv",
              daily_rows(years, {2010: 1.0, 2011: 0.5, 2012: 1.5, 2013: 0.9, 2014: 1.2}), DAILY_FIELDS)
    write_json(ex / "fetch-lock.json", {"region": "suwannee", "fetched_at": {"soils": "test"}, "downloads": []})
    return base
