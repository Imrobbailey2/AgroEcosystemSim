"""Format checks for data packs: JSON Schema plus provenance tracing."""

from __future__ import annotations

from typing import Any

from agroeco_pipeline.common import read_json, schemas_dir

# Top-level sections that describe the pack itself rather than data values.
EXEMPT_TOP = {"format", "format_version", "pack_version", "region", "inputs", "sources", "review_flags"}


def _walk(node: Any, path: str, covered: bool, known: set[str], problems: list[str]) -> None:
    if isinstance(node, dict):
        prov = node.get("prov")
        if prov is not None:
            ids = prov.get("sources") if isinstance(prov, dict) else None
            if not ids:
                problems.append(f"{path}.prov has no sources")
            else:
                for sid in ids:
                    if sid not in known:
                        problems.append(f"{path}.prov cites unknown source {sid!r}")
            if not isinstance(prov, dict) or not prov.get("loc"):
                problems.append(f"{path}.prov has no locator")
            covered = True
        for key, value in node.items():
            if key == "prov":
                continue
            _walk(value, f"{path}.{key}", covered, known, problems)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", covered, known, problems)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        if not covered:
            problems.append(f"{path} = {node} has no source (no prov on it or any parent)")


def provenance_problems(pack: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    sources = pack.get("sources") or []
    known = set()
    for s in sources:
        sid = s.get("id")
        known.add(sid)
        for field in ("title", "url", "license", "accessed"):
            if not s.get(field):
                problems.append(f"source {sid!r} lacks {field}")
    for key, value in pack.items():
        if key in EXEMPT_TOP:
            continue
        _walk(value, key, False, known, problems)
    flag_ids = {f["id"] for f in pack.get("review_flags", [])}
    _check_flags(pack, flag_ids, problems)
    return problems


def _check_flags(node: Any, flag_ids: set[str], problems: list[str], path: str = "") -> None:
    if isinstance(node, dict):
        flag = node.get("review_flag")
        if flag is not None and flag not in flag_ids:
            problems.append(f"{path}.review_flag {flag!r} is not in review_flags")
        for k, v in node.items():
            _check_flags(v, flag_ids, problems, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_flags(v, flag_ids, problems, f"{path}[{i}]")


def schema_problems(pack: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a declared dependency
        return ["jsonschema is not installed; run `pip install -e ./pipeline[dev]`"]
    schema = read_json(schemas_dir() / "datapack.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"schema: {'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(pack), key=lambda e: list(map(str, e.absolute_path)))
    ]


# Broad plausibility bounds for picked budget values. They exist to catch a wrong
# workbook cell (for example a whole-farm total read as a per-acre value), not to
# judge whether a budget assumption is realistic.
PLAUSIBLE = {
    "benchmark_yield_bu_ac": (50.0, 400.0),
    "benchmark_price_usd_bu": (1.0, 20.0),
}


def _num(node: Any) -> float | None:
    if isinstance(node, dict) and isinstance(node.get("value"), (int, float)):
        return float(node["value"])
    return None


def plausibility_problems(pack: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for t in pack.get("tenure_options") or []:
        tid = t.get("id")
        for key, (lo, hi) in PLAUSIBLE.items():
            v = _num(t.get(key))
            if v is not None and not lo <= v <= hi:
                problems.append(f"tenure_options[{tid}].{key} = {v} is outside {lo}-{hi}; check the budget cell")
        y, p = _num(t.get("benchmark_yield_bu_ac")), _num(t.get("benchmark_price_usd_bu"))
        revenue = y * p if y is not None and p is not None else None
        for key, node in t.items():
            v = _num(node)
            if key.endswith("_usd_ac") and v is not None and revenue is not None and not 0 <= v <= revenue:
                problems.append(
                    f"tenure_options[{tid}].{key} = {v} is not between 0 and revenue per acre "
                    f"({revenue:.2f}); is it a whole-farm total? check the budget cell"
                )
    for i, m in enumerate(pack.get("market_channels") or []):
        net, gross = _num(m.get("price_usd_bu")), _num(m.get("gross_price_usd_bu"))
        if m.get("price_basis") == "net_farm_gate" and net is not None and gross is not None and net > gross:
            problems.append(f"market_channels[{i}] net price {net} exceeds gross price {gross}")
    return problems


def validate_pack(pack: dict[str, Any], use_schema: bool = True) -> list[str]:
    problems = provenance_problems(pack)
    problems.extend(plausibility_problems(pack))
    if use_schema:
        problems.extend(schema_problems(pack))
    return problems
