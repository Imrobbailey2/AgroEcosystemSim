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

# Allowed difference, in $/acre, when the pack's revenue is reconciled with the
# budget's own "Total net farm-gate crop revenue" line.
RECONCILE_TOLERANCE_USD_AC = 0.01

# Owned-land cost lines (Advanced mode); the Basic-mode total must equal their sum.
OWNED_LAND_LINES = ("property_tax_usd_ac", "property_insurance_usd_ac", "upkeep_usd_ac")

# Allowed difference between the stored appreciation rate and the rate recomputed
# from the land value series (the stored rate is rounded to 6 decimals).
APPRECIATION_RATE_TOLERANCE = 1e-6


def _num(node: Any) -> float | None:
    if isinstance(node, dict) and isinstance(node.get("value"), (int, float)):
        return float(node["value"])
    return None


def _default_premium(pack: dict[str, Any]) -> float | None:
    """Premium ($/acre) of the crop insurance option the budget assumes is bought."""
    for option in pack.get("crop_insurance_options") or []:
        if option.get("default_purchased") is True:
            return _num(option.get("premium_usd_ac"))
    return None


def plausibility_problems(pack: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    premium = _default_premium(pack)
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
        # The budget's bottom line is net sales revenue minus the crop insurance
        # premium. If the pack does not reproduce it, a cell is wrong or a deduction
        # is missing.
        total = _num(t.get("budget_total_net_revenue_usd_ac"))
        if total is not None and revenue is not None and premium is not None:
            expected = revenue - premium
            if abs(expected - total) > RECONCILE_TOLERANCE_USD_AC:
                problems.append(
                    f"tenure_options[{tid}]: yield x price - insurance premium = {expected:.2f} "
                    f"does not reconcile with the budget's total net revenue {total:.2f} $/acre"
                )
        problems.extend(owned_land_problems(t))
    for i, m in enumerate(pack.get("market_channels") or []):
        net, gross = _num(m.get("price_usd_bu")), _num(m.get("gross_price_usd_bu"))
        if m.get("price_basis") == "net_farm_gate" and net is not None and gross is not None and net > gross:
            problems.append(f"market_channels[{i}] net price {net} exceeds gross price {gross}")
    return problems


def owned_land_problems(tenure: dict[str, Any]) -> list[str]:
    """Checks for the owned-land cost lines and land appreciation of one tenure option.

    - The Basic total equals the sum of the three Advanced lines (+/- $0.01/A).
    - Option C (2026-11-09): property tax + property insurance equals the owned
      budget's "Property tax and insurance" (+/- $0.01/A), and insurance is not
      negative (property tax above the budget's line must fail, not go negative).
    - The appreciation rate equals the compound growth of the land value series.
    """
    problems: list[str] = []
    tid = tenure.get("id")
    tax, insurance, upkeep = (_num(tenure.get(k)) for k in OWNED_LAND_LINES)
    total = _num(tenure.get("owned_land_cost_usd_ac"))
    if total is not None:
        if None in (tax, insurance, upkeep):
            missing = [k for k in OWNED_LAND_LINES if _num(tenure.get(k)) is None]
            problems.append(f"tenure_options[{tid}]: owned_land_cost_usd_ac is set but {missing} are missing")
        elif abs(tax + insurance + upkeep - total) > RECONCILE_TOLERANCE_USD_AC:
            problems.append(
                f"tenure_options[{tid}]: owned_land_cost_usd_ac = {total:.2f} does not equal the sum of "
                f"property tax, property insurance and upkeep ({tax + insurance + upkeep:.2f})"
            )
    if insurance is not None and insurance < 0:
        problems.append(
            f"tenure_options[{tid}]: property_insurance_usd_ac = {insurance:.2f} is negative; property tax "
            "exceeds the budget's 'Property tax and insurance' line"
        )
    combined = _num(tenure.get("budget_property_tax_and_insurance_usd_ac"))
    if combined is not None and tax is not None and insurance is not None:
        if abs(tax + insurance - combined) > RECONCILE_TOLERANCE_USD_AC:
            problems.append(
                f"tenure_options[{tid}]: property tax + property insurance = {tax + insurance:.2f} does not "
                f"reconcile with the budget's 'Property tax and insurance' {combined:.2f} $/acre"
            )
    appreciation = tenure.get("land_appreciation")
    if isinstance(appreciation, dict):
        problems.extend(_appreciation_problems(tid, appreciation))
    return problems


def _appreciation_problems(tid: Any, appreciation: dict[str, Any]) -> list[str]:
    series = appreciation.get("series") or []
    points = [(s.get("year"), s.get("usd_ac")) for s in series if isinstance(s, dict)]
    years = [y for y, _ in points]
    if len(points) < 2 or any(not isinstance(y, int) for y in years) or years != sorted(set(years)):
        return [f"tenure_options[{tid}].land_appreciation.series needs 2+ distinct years in increasing order"]
    if any(not isinstance(v, (int, float)) or v <= 0 for _, v in points):
        return [f"tenure_options[{tid}].land_appreciation.series has a non-positive land value"]
    (y0, v0), (y1, v1) = points[0], points[-1]
    expected = (v1 / v0) ** (1 / (y1 - y0)) - 1
    rate = _num(appreciation.get("rate_per_yr"))
    if rate is None or abs(rate - expected) > APPRECIATION_RATE_TOLERANCE:
        return [
            f"tenure_options[{tid}].land_appreciation.rate_per_yr = {rate} does not match the series "
            f"compound growth {y0}-{y1} ({expected:.6f})"
        ]
    return []


def validate_pack(pack: dict[str, Any], use_schema: bool = True) -> list[str]:
    problems = provenance_problems(pack)
    problems.extend(plausibility_problems(pack))
    if use_schema:
        problems.extend(schema_problems(pack))
    return problems
