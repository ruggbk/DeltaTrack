"""Guardrail that pre-commit and CI run the same Ruff (#646).

``pyproject.toml`` pins ``ruff==`` exactly so that a local format matches CI, and CI runs
that pin through ``uv run ruff``. The pre-commit hook does NOT: pre-commit builds an
isolated virtualenv per hook repo (``language: python``, no ``additional_dependencies``),
installing whatever ``ruff==`` release the ``rev`` tag of ruff-pre-commit declares. The tag
therefore *is* the Ruff version, and the two can disagree while both files look correct.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
PRECOMMIT = ROOT / ".pre-commit-config.yaml"
PYPROJECT = ROOT / "pyproject.toml"

RUFF_HOOK_REPO = "https://github.com/astral-sh/ruff-pre-commit"
# `ruff` is the legacy alias for `ruff-check`; both are live, so either spelling counts.
LINT_HOOK_IDS = {"ruff", "ruff-check"}
FORMAT_HOOK_ID = "ruff-format"


def _ruff_hook_entry() -> dict:
    config = yaml.safe_load(PRECOMMIT.read_text(encoding="utf-8"))
    entries = [repo for repo in config.get("repos", []) if repo.get("repo") == RUFF_HOOK_REPO]
    # Failing rather than skipping on a missing entry: every assertion below would pass
    # vacuously against an empty read, which is the shape of gate this file exists to close.
    assert entries, f"no {RUFF_HOOK_REPO} entry found in {PRECOMMIT.name}"
    assert len(entries) == 1, f"expected one {RUFF_HOOK_REPO} entry in {PRECOMMIT.name}, found {len(entries)}"
    return entries[0]


def _pinned_ruff_version() -> str:
    dev_group = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["dependency-groups"]["dev"]
    pins = [m.group(1) for m in (re.fullmatch(r"ruff==([^\s;]+)", spec.strip()) for spec in dev_group) if m]
    assert pins, f"no exact `ruff==` pin found in the dev dependency group of {PYPROJECT.name}"
    assert len(pins) == 1, f"expected one `ruff==` pin in {PYPROJECT.name}, found {pins}"
    return pins[0]


def test_precommit_ruff_matches_the_pinned_ruff() -> None:
    """The hook tag names the same Ruff release CI installs."""
    rev = _ruff_hook_entry()["rev"]
    pinned = _pinned_ruff_version()
    assert rev == f"v{pinned}", (
        f"pre-commit runs Ruff {rev.lstrip('v')} but CI runs {pinned}. "
        f"Set `rev: v{pinned}` in {PRECOMMIT.name}, or move the pin in {PYPROJECT.name} to match."
    )


def test_precommit_actually_runs_both_ruff_hooks() -> None:
    """Keeps the version assertion from going vacuous if the hooks are dropped."""
    ids = {hook.get("id") for hook in _ruff_hook_entry().get("hooks", [])}
    assert ids & LINT_HOOK_IDS, f"no Ruff lint hook ({' or '.join(sorted(LINT_HOOK_IDS))}) in {PRECOMMIT.name}"
    assert FORMAT_HOOK_ID in ids, f"no {FORMAT_HOOK_ID} hook in {PRECOMMIT.name}"
