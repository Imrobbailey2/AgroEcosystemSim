"""SSURGO query building, parsing and soil-unit construction."""

from __future__ import annotations

import json

import pytest

from agroeco_pipeline import sda
from agroeco_pipeline.common import PipelineError
from agroeco_pipeline.soils import build_soil_units, total_available_water_mm


def test_query_rejects_injection() -> None:
    with pytest.raises(PipelineError):
        sda.mapunit_query("FL121", ["x'; DROP TABLE mapunit; --"])
    with pytest.raises(PipelineError):
        sda.component_query(["1 OR 1=1"])
    q = sda.mapunit_query("FL121", ["Blanton-Alpin-Bonneau complex, 0 to 5 percent slopes"])
    assert "'FL121'" in q and "IN ('Blanton-Alpin-Bonneau complex, 0 to 5 percent slopes')" in q


def test_parse_table() -> None:
    raw = json.dumps({"Table": [["mukey", "muname"], ["1", "A"], ["2", "B"]]}).encode()
    assert sda.parse_table(raw) == [{"mukey": "1", "muname": "A"}, {"mukey": "2", "muname": "B"}]
    assert sda.parse_table(b"") == []
    with pytest.raises(PipelineError):
        sda.parse_table(b"<html>error</html>")


def test_run_query_uses_json_columnname() -> None:
    seen = {}

    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> bytes:
        seen.update(url=url, body=json.loads(body), headers=headers)
        return json.dumps({"Table": [["a"], ["1"]]}).encode()

    _, rows = sda.run_query(fake_post, "SELECT 1 AS a")
    assert rows == [{"a": "1"}]
    assert seen["url"] == sda.SDA_URL
    assert seen["body"]["format"] == "JSON+COLUMNNAME"


MAPUNITS = [{"mukey": "1", "musym": "13", "muname": "Unit A", "saverest": "v"}]
COMPS = [
    {"mukey": "1", "cokey": "10", "compname": "Minor", "comppct_r": "20", "hydgrp": "A"},
    {"mukey": "1", "cokey": "11", "compname": "Blanton", "comppct_r": "50", "hydgrp": "A"},
]
HZ = [
    {"cokey": "11", "chkey": "a", "hzname": "A", "hzdept_r": "0", "hzdepb_r": "50", "wthirdbar_r": "10",
     "wfifteenbar_r": "4", "awc_r": "0.06", "sandtotal_r": "90", "silttotal_r": "5", "claytotal_r": "5",
     "om_r": "1", "dbthirdbar_r": "1.5", "ksat_r": "40", "ph1to1h2o_r": "5.4", "cec7_r": "3"},
    {"cokey": "11", "chkey": "b", "hzname": "Bt", "hzdept_r": "50", "hzdepb_r": "200", "wthirdbar_r": "20",
     "wfifteenbar_r": "10", "awc_r": "0.1", "sandtotal_r": "70", "silttotal_r": "10", "claytotal_r": "20",
     "om_r": "0.2", "dbthirdbar_r": "1.6", "ksat_r": "9", "ph1to1h2o_r": "5.0", "cec7_r": "5"},
]


def test_dominant_component_and_layers() -> None:
    units = build_soil_units([{"id": "f1", "muname": "Unit A"}], MAPUNITS, COMPS, HZ, 150, "ssurgo-fl121", "FL121")
    u = units[0]
    assert u["dominant_component"]["name"] == "Blanton"
    assert [ly["bottom_cm"] for ly in u["layers"]] == [50, 150]
    assert u["layers"][0]["theta_fc"] == 0.10
    # (0.10-0.04)*500 mm + (0.20-0.10)*500 mm = 30 + 50
    assert u["taw_mm_top_100cm"] == 80.0
    assert "mukey=1" in u["prov"]["loc"]


def test_missing_map_unit_and_retention_fail() -> None:
    with pytest.raises(PipelineError):
        build_soil_units([{"id": "f1", "muname": "Nope"}], MAPUNITS, COMPS, HZ, 150, "s", "FL121")
    bad = [dict(HZ[0], wthirdbar_r=None)]
    with pytest.raises(PipelineError):
        build_soil_units([{"id": "f1", "muname": "Unit A"}], MAPUNITS, COMPS, bad, 150, "s", "FL121")


def test_taw_partial_layer() -> None:
    layers = [{"top_cm": 0, "bottom_cm": 200, "theta_fc": 0.2, "theta_wp": 0.1}]
    assert total_available_water_mm(layers, 100) == 100.0
