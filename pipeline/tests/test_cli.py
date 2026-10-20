"""Smoke tests for the pipeline CLI stub."""

from __future__ import annotations

import pytest

from agroeco_pipeline import __version__
from agroeco_pipeline.cli import EXIT_NOT_IMPLEMENTED, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_build_stub_reports_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "--region", "suwannee"]) == EXIT_NOT_IMPLEMENTED
    assert "not implemented" in capsys.readouterr().err


def test_unknown_region_rejected() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["build", "--region", "atlantis"])
    assert exc.value.code == 2
