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
# Both the wrapper roster and each script's subcommands are discovered, never
# listed by hand: a hand-maintained roster would need the same discipline the table
# already lacked, and would pass while both drifted together. Discovering it also
# covers the larger version of the failure -- a whole new wrapper script shipping
# undocumented, which a fixed list would not have looked at.


def _wrapper_scripts() -> list[str]:
    """Every product command wrapper: the symlinks in the project root.

    `init` is absent for free -- it is a regular file, sourced to set up the
    environment rather than run, and the README says so where it appears.
    """
    return sorted(p.name for p in ROOT.iterdir() if p.is_symlink())


def _cli_commands() -> dict[str, list[str]]:
    """Every documentable command, keyed by the wrapper script that provides it.

    A parser with subcommands contributes one entry per subcommand (`./fetch_bills
    search`); a parser that takes only options contributes the bare script name,
    which is how the README names it. A wrapper with no `build_parser` at all
    (fetch_bill_archives runs a hardcoded congress range with no flags and has no
    argparse yet, #10) contributes the bare script name for the same reason.
    """
    commands: dict[str, list[str]] = {}
    for script in _wrapper_scripts():
        build_parser = getattr(importlib.import_module(script), "build_parser", None)
        if build_parser is None:
            commands[script] = [f"./{script}"]
            continue
        parser = build_parser()
        subcommands = [
            name
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for name in action.choices
        ]
        commands[script] = [f"./{script} {name}" for name in subcommands] if subcommands else [f"./{script}"]
    return commands


def _command_reference_section() -> str:
    """The README's "Command reference" section, up to the next heading."""
    text = (ROOT / "README.md").read_text()
    start = text.index("## Command reference")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def _documented_commands() -> list[str]:
    """The command each "Command reference" row documents, from its leading cell.

    A row reads ``| `./fetch_bills download <congress> …` | What it does |``, so the
    first backticked span of the first cell is the command plus its arguments.
    """
    return [line.split("`")[1] for line in _command_reference_section().splitlines() if line.startswith("| `./")]


def _is_documented(command: str, rows: list[str]) -> bool:
    """Whether a row documents `command` -- matched on a whole-token boundary.

    Never a bare substring. `./fetch_bills download` is a prefix of the
    `download-all` row, so a plain `in` test reports the download row as present
    after it has been deleted -- the same defect this change removes from the money
    assertions (#264), which this gate must not reintroduce. Requiring the row to be
    the command exactly, or the command followed by a space, is what makes it able
    to fail.
    """
    return any(row == command or row.startswith(command + " ") for row in rows)


def test_every_cli_command_appears_in_the_readme_command_reference():
    """A command that is not in the table is a command nobody will find.

    Fails when a new subcommand lands undocumented, and equally when a rename
    silently orphans the row that used to describe it.
    """
    rows = _documented_commands()
    missing = [cmd for cmds in _cli_commands().values() for cmd in cmds if not _is_documented(cmd, rows)]

    assert not missing, (
        "CLI commands missing from the README 'Command reference' table: "
        f"{missing}. Add a row for each, or rename the existing row to match."
    )


def test_the_command_gate_actually_found_commands():
    """Completeness floor for the gate above.

    Every step above is discovery, and discovery that quietly finds nothing makes the
    gate pass green over an entirely undocumented CLI. So floor each step: the wrapper
    roster, the subcommand walk through `parser._actions`, and the row parse the
    commands are matched against.

    Deliberately floors rather than pins exact rosters or counts -- a pinned list is
    the hand-maintained thing this gate replaced, and would fail on every legitimate
    new command.
    """
    scripts = _wrapper_scripts()
    # Named wrappers, not a count: a count passes while discovery returns the wrong set.
    for expected in ("fetch_bills", "diff_bill", "fetch_bill_archives"):
        assert expected in scripts, f"wrapper discovery missed {expected!r} -- found {scripts}"

    commands = _cli_commands()
    empty = sorted(script for script, cmds in commands.items() if not cmds)
    assert not empty, f"no commands discovered for {empty} -- introspection is broken, not the docs"

    # fetch_bills is the multi-subcommand script; a bare "./fetch_bills" from it would
    # mean the subparser walk found nothing while still returning a plausible answer.
    assert len(commands["fetch_bills"]) > 1, "fetch_bills subcommands were not discovered"

    # The row parse feeds every match; if it returned [] the gate would report every
    # command missing, but if it silently under-parsed it would report none.
    rows = _documented_commands()
    assert len(rows) >= len(scripts), f"parsed only {len(rows)} command rows for {len(scripts)} wrappers"

    section = _command_reference_section()
    assert "| Command | What it does |" in section, "README 'Command reference' table not found"
