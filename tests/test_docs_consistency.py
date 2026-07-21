"""Guardrails that keep the docs from drifting out of sync with how the suite runs.

These are plain text checks over Markdown files, not behavior tests, so they carry
no markers and run in the default fast suite.
"""

import argparse
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Docs that show how to run the tests. The fast/no-setup suite must EXCLUDE the
# browser tests (they need a one-time `playwright install chromium`), so the
# canonical marker is `not slow and not browser`. The bare `not slow` is stale:
# it now also selects the browser tests. See issue #124, fixed across #118/#120/#121.
_DOCS_WITH_RUN_COMMANDS = [
    "README.md",
    "TESTING.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
]

_STALE_MARKERS = ('-m "not slow"', "-m 'not slow'")


def test_docs_use_current_fast_test_marker():
    """No doc should show the stale `-m "not slow"` fast-test command.

    Whenever a new marker is added that should stay out of the fast run, update
    that marker list AND every command below, or this test fails on purpose.
    """
    offenders = []
    for rel in _DOCS_WITH_RUN_COMMANDS:
        path = ROOT / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if any(marker in line for marker in _STALE_MARKERS):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Docs show the stale fast-test marker (now selects browser tests). "
        'Use `-m "not slow and not browser"` instead:\n' + "\n".join(offenders)
    )


# --- CLI surface vs the README command reference (#135) -------------------------
# The product commands are wrapper scripts in the project root, and the README's
# "Command reference" table is where a user finds them. Nothing tied the two
# together, so a new subcommand could ship fully working and undiscoverable.
#
# Each script is introspected for its argparse subcommands rather than listed by
# hand: a hand-maintained list would need the same discipline the table already
# lacked, and would pass while both drifted together.
_WRAPPERS_WITH_PARSERS = ("diff_bill", "diff_pdf", "fetch_bills", "fetch_bill_text_archives")

# fetch_bill_archives runs a hardcoded congress range with no flags and has no
# argparse yet (#10), so the script name itself is the unit to document. `init` is
# deliberately absent: it is sourced to set up the environment, not run, and the
# README says so where it appears.
_WRAPPERS_WITHOUT_PARSERS = ("fetch_bill_archives",)


def _cli_commands() -> dict[str, list[str]]:
    """Every documentable command, keyed by the wrapper script that provides it.

    A parser with subcommands contributes one entry per subcommand (`./fetch_bills
    search`); a parser that takes only options contributes the bare script name,
    which is how the README names it.
    """
    commands: dict[str, list[str]] = {}
    for script in _WRAPPERS_WITH_PARSERS:
        parser = importlib.import_module(script).build_parser()
        subcommands = [
            name
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for name in action.choices
        ]
        commands[script] = [f"./{script} {name}" for name in subcommands] if subcommands else [f"./{script}"]
    for script in _WRAPPERS_WITHOUT_PARSERS:
        commands[script] = [f"./{script}"]
    return commands


def _command_reference_section() -> str:
    """The README's "Command reference" section, up to the next heading."""
    text = (ROOT / "README.md").read_text()
    start = text.index("## Command reference")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_every_cli_command_appears_in_the_readme_command_reference():
    """A command that is not in the table is a command nobody will find.

    Fails when a new subcommand lands undocumented, and equally when a rename
    silently orphans the row that used to describe it.
    """
    section = _command_reference_section()
    missing = [cmd for cmds in _cli_commands().values() for cmd in cmds if cmd not in section]

    assert not missing, (
        "CLI commands missing from the README 'Command reference' table: "
        f"{missing}. Add a row for each, or rename the existing row to match."
    )


def test_the_command_gate_actually_found_commands():
    """Completeness floor for the gate above.

    Introspection reaching into `parser._actions` is the fragile part: if it stopped
    finding subcommands, the gate would have nothing to check and would pass green
    over an entirely undocumented CLI. So assert every wrapper contributed at least
    one command, and that the section it checks against is a real table.
    """
    commands = _cli_commands()
    empty = sorted(script for script, cmds in commands.items() if not cmds)
    assert not empty, f"no commands discovered for {empty} -- introspection is broken, not the docs"

    # fetch_bills is the multi-subcommand script; a bare "./fetch_bills" from it would
    # mean the subparser walk found nothing while still returning a plausible answer.
    assert len(commands["fetch_bills"]) > 1, "fetch_bills subcommands were not discovered"

    section = _command_reference_section()
    assert "| Command | What it does |" in section, "README 'Command reference' table not found"
