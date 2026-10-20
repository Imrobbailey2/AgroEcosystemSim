"""CLI behaviour (offline)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from agroeco_pipeline import __version__  # noqa: E402
from agroeco_pipeline.cli import main  # noqa: E402
from fixtures import make_sources_tree  # noqa: E402


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_unknown_region_rejected() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["build", "--region", "atlantis"])
    assert exc.value.code == 2


def test_build_without_fetch_explains(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = make_sources_tree(tmp_path)
    (base / "extracted" / "suwannee" / "fetch-lock.json").unlink()
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        assert main(["build", "--region", "suwannee", "--out", str(tmp_path / "p.json")]) == 2
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]
    assert "Fetch sources" in capsys.readouterr().err


def test_build_check_and_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = make_sources_tree(tmp_path)
    out = tmp_path / "pack.json"
    os.environ["AGROECO_SOURCES_DIR"] = str(base)
    try:
        assert main(["build", "--region", "suwannee", "--out", str(out)]) == 0
        assert main(["build", "--region", "suwannee", "--out", str(out), "--check"]) == 0
        pack = json.loads(out.read_text())
        pack["soil_units"][0]["prov"]["sources"] = ["no-such-source"]
        out.write_text(json.dumps(pack))
        assert main(["build", "--region", "suwannee", "--out", str(out), "--check"]) == 1
        assert main(["validate", str(out)]) == 1
    finally:
        del os.environ["AGROECO_SOURCES_DIR"]
    assert "unknown source" in capsys.readouterr().err
