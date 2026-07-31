"""Regression tests for scripts/generate_validation_report.py.

The script reads gitignored, fetch-scripted fixtures, so it must degrade
gracefully on a clean clone instead of raising FileNotFoundError (#18).
"""

import pytest

import scripts.generate_validation_report as report
from tests.corpus_paths import DATA_DIR


def test_leg_branch_summary_degrades_when_fixture_absent(monkeypatch):
    monkeypatch.setattr(report, "LEG_BRANCH_FIXTURE", DATA_DIR / "_does_not_exist.json")
    summary = report._leg_branch_summary()
    assert "not fetched" in summary
    assert "Legislative Branch" in summary


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        report.build_parser().parse_args(["--help"])
    assert excinfo.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_unknown_argument_exits_two_with_usage(capsys):
    with pytest.raises(SystemExit) as excinfo:
        report.build_parser().parse_args(["--nope"])
    assert excinfo.value.code == 2
    assert "usage:" in capsys.readouterr().err
