"""USDA-NRCS Soil Data Access (SDA) queries for SSURGO map units."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from agroeco_pipeline.common import PipelineError

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
_SAFE = re.compile(r"^[A-Za-z0-9 ,.\-()]+$")

PostFn = Callable[[str, bytes, dict[str, str]], bytes]


def _quote(value: str) -> str:
    """Quote a literal for T-SQL after a strict allow-list check."""
    if not _SAFE.match(value):
        raise PipelineError(f"unsafe characters in SDA query value: {value!r}")
    return "'" + value.replace("'", "''") + "'"


def _ints(values: list[str]) -> str:
    out = []
    for v in values:
        if not str(v).isdigit():
            raise PipelineError(f"expected numeric key, got {v!r}")
        out.append(str(int(v)))
    if not out:
        raise PipelineError("empty key list for SDA query")
    return ",".join(out)


def mapunit_query(areasymbol: str, munames: list[str]) -> str:
    names = ",".join(_quote(n) for n in munames)
    return (
        "SELECT l.areasymbol, sc.saverest, mu.mukey, mu.musym, mu.muname "
        "FROM legend l "
        "INNER JOIN mapunit mu ON mu.lkey = l.lkey "
        "INNER JOIN sacatalog sc ON sc.areasymbol = l.areasymbol "
        f"WHERE l.areasymbol = {_quote(areasymbol)} AND mu.muname IN ({names}) "
        "ORDER BY mu.mukey"
    )


def component_query(mukeys: list[str]) -> str:
    return (
        "SELECT c.mukey, c.cokey, c.compname, c.comppct_r, c.majcompflag, "
        "c.hydgrp, c.drainagecl, c.taxclname "
        f"FROM component c WHERE c.mukey IN ({_ints(mukeys)}) "
        "ORDER BY c.mukey, c.comppct_r DESC, c.cokey"
    )


def horizon_query(cokeys: list[str]) -> str:
    return (
        "SELECT ch.cokey, ch.chkey, ch.hzname, ch.hzdept_r, ch.hzdepb_r, "
        "ch.sandtotal_r, ch.silttotal_r, ch.claytotal_r, ch.om_r, ch.dbthirdbar_r, "
        "ch.wthirdbar_r, ch.wfifteenbar_r, ch.awc_r, ch.ksat_r, ch.ph1to1h2o_r, ch.cec7_r "
        f"FROM chorizon ch WHERE ch.cokey IN ({_ints(cokeys)}) "
        "ORDER BY ch.cokey, ch.hzdept_r, ch.chkey"
    )


def parse_table(raw: bytes) -> list[dict[str, Any]]:
    """Parse an SDA 'JSON+COLUMNNAME' response into a list of dicts."""
    if not raw.strip():
        return []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"SDA returned non-JSON: {raw[:200]!r}") from exc
    table = doc.get("Table") if isinstance(doc, dict) else None
    if not table:
        return []
    header, *rows = table
    for row in rows:
        if len(row) != len(header):
            raise PipelineError(f"SDA row has {len(row)} values for {len(header)} columns")
    return [dict(zip(header, row, strict=True)) for row in rows]


def run_query(post: PostFn, sql: str) -> tuple[bytes, list[dict[str, Any]]]:
    body = json.dumps({"query": sql, "format": "JSON+COLUMNNAME"}).encode()
    raw = post(SDA_URL, body, {"Content-Type": "application/json"})
    return raw, parse_table(raw)
