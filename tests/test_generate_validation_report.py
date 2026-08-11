"""Regression tests for scripts/generate_validation_report.py.

The fixtures are committed since ADR 0015, but the script must still degrade
gracefully where one is genuinely absent (a partial checkout) instead of
raising FileNotFoundError (#18).
"""

from pathlib import Path
from unittest import mock

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


def test_main_parses_argv_and_rejects_unknown_argument(monkeypatch, capsys):
    """Wiring: main() must run argv through the parser before writing the report."""
    # Pin the ordering, not just the rejection: SystemExit(2) and "usage:" hold
    # even if the parse is moved to the END of main(), after every jurisdiction
    # has been validated and the committed report already overwritten. Neither
    # may happen. The argv is passed explicitly (no sys.argv monkeypatching, #445)
    # and the destination is an explicit temporary path.
    validate = mock.Mock(side_effect=AssertionError("validate_jurisdiction ran before argv was parsed"))
    monkeypatch.setattr(report, "validate_jurisdiction", validate)
    output = mock.Mock(spec=Path)
    with pytest.raises(SystemExit) as excinfo:
        report.main(["--nope"], output=output)
    assert excinfo.value.code == 2
    assert "usage:" in capsys.readouterr().err
    validate.assert_not_called()
    output.write_text.assert_not_called()


def test_main_requires_an_explicit_output():
    """An in-process caller must choose where the report goes (#445).

    `main()` takes its destination as a required keyword-only argument, so an
    import-and-call cannot silently overwrite the committed report: omitting
    `output` fails loudly instead of writing the tracked file.
    """
    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'output'"):
        report.main([])


def test_committed_output_is_project_root_derived():
    """The intentional CLI regeneration destination is absolute, never CWD-relative (#445)."""
    assert report.COMMITTED_OUTPUT.is_absolute()
    assert report.COMMITTED_OUTPUT.is_relative_to(Path(__file__).resolve().parents[1])
    assert report.COMMITTED_OUTPUT.name == "parser-validation.md"
    assert report.COMMITTED_OUTPUT.parent.name == "docs"
