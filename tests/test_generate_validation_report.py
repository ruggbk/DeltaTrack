"""Regression tests for scripts/generate_validation_report.py.

The script reads gitignored, fetch-scripted fixtures, so it must degrade
gracefully on a clean clone instead of raising FileNotFoundError (#18).
"""

import scripts.generate_validation_report as report
from tests.corpus_paths import DATA_DIR


def test_leg_branch_summary_degrades_when_fixture_absent(monkeypatch):
    monkeypatch.setattr(report, "LEG_BRANCH_FIXTURE", DATA_DIR / "_does_not_exist.json")
    summary = report._leg_branch_summary()
    assert "not fetched" in summary
    assert "Legislative Branch" in summary
