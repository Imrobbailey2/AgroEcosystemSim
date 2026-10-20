"""Tests for the forbidden-path data guard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_forbidden as cf  # noqa: E402

PATTERNS = cf.load_patterns()


def test_patterns_load() -> None:
    assert len(PATTERNS) >= 5


def test_blocks_uf_validation_paths() -> None:
    bad = [
        "uf-validation/dummy.csv",
        "pipeline/data/UF_Validation/yields.xlsx",
        "game/uf-validation-2025.csv",
        "data/private/notes.txt",
        "calibration-private/dssat/out.csv",
        "pipeline/raw/trial.ufdata.csv",
        "uf_data/x.json",
    ]
    hits = {p for p, _ in cf.find_violations(bad, PATTERNS)}
    assert hits == set(bad)


def test_allows_normal_paths() -> None:
    ok = [
        "README.md",
        "game/src/App.tsx",
        "game/src/engine/buffer_validation.ts",
        "pipeline/src/agroeco_pipeline/cli.py",
        "schemas/README.md",
        "scripts/check_forbidden.py",
    ]
    assert cf.find_violations(ok, PATTERNS) == []


def test_main_exit_codes() -> None:
    assert cf.main(["README.md"]) == 0
    assert cf.main(["uf-validation/dummy.csv"]) == 1


def test_repository_is_clean() -> None:
    assert cf.find_violations(cf.tracked_files(), PATTERNS) == []
