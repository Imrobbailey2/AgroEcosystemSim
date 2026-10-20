"""Shared paths and helpers for deterministic I/O."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_DIR.parent


class PipelineError(RuntimeError):
    """A user-facing pipeline failure with an actionable message."""


def sources_dir() -> Path:
    """Root of committed source inputs (overridable for tests)."""
    return Path(os.environ.get("AGROECO_SOURCES_DIR", PIPELINE_DIR / "sources"))


def packs_dir() -> Path:
    return Path(os.environ.get("AGROECO_PACKS_DIR", REPO_ROOT / "data" / "packs"))


def schemas_dir() -> Path:
    return REPO_ROOT / "schemas"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    """Write JSON with sorted keys and a trailing newline (byte-stable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    except FileNotFoundError as exc:
        raise PipelineError(f"missing file: {path}") from exc


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def to_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{field}: expected a number, got {value!r}") from exc


def opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
