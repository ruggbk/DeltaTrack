"""ADR 0018 gate: the structural parsers must not read appropriations English.

Structure (account names, anchors, hierarchy) comes from format — glyph size,
position, and the universal legislative tokens `TITLE N` / `SEC. N` / `(a)`.
Appropriations-specific stock phrases (`For necessary expenses of`, `RESCISSION`,
`INCLUDING TRANSFER OF FUNDS`) may interpret dollar amounts, never define a
boundary. See docs/decisions/0018-text-triggers-are-financial-only.md and #114.

This is an ABSENCE assertion, which is the kind that fails open: a detector that
has quietly stopped matching anything looks exactly like a codebase in permanent
compliance. So `test_detector_flags_the_retired_trigger` feeds the detector the
exact source line this gate was written to catch (the retired
`_FOR_NECESSARY_EXPENSES` regex) and fails if it is NOT flagged. Keep that test
passing or the green from the rest of this module means nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "deltatrack"

# Modules that decide bill STRUCTURE. The financial layer (diff_bill, diff_pdf) and
# the committee-report table parser are deliberately absent: reading appropriations
# vocabulary is their job (ADR 0018 "Context" and the 0009 carve-out).
STRUCTURAL_MODULES = (
    SRC / "parsers" / "pdf_anchors.py",
    SRC / "structure_tree.py",
    SRC / "bill_tree.py",
)

# Appropriations-genre vocabulary. Matched case-insensitively against string
# literals only. `increased/reduced by` are financial-layer phrases and are listed
# so that moving one INTO a structural module trips the gate too.
APPROPRIATIONS_VOCABULARY = (
    "necessary expenses",
    "hereby appropriated",
    "to remain available",
    "including transfer",
    "including rescission",
    "rescission",
    "limitation on",
    "salaries and expenses",
    "administrative provisions",
    "increased by",
    "reduced by",
    "decreased by",
)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """id()s of the string Constant nodes that are docstrings, not code.

    Docstrings and comments are prose ABOUT the rule — this module's own header
    names the retired trigger — so only real string literals are evidence.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def find_appropriations_vocabulary(source: str) -> list[tuple[str, str]]:
    """(phrase, literal) for every appropriations phrase in a string literal.

    Comments and docstrings are excluded; a pattern only counts when it can reach
    the matcher at runtime.
    """
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    hits: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in skip:
            continue
        lowered = node.value.lower()
        for phrase in APPROPRIATIONS_VOCABULARY:
            if phrase in lowered:
                hits.append((phrase, node.value))
    return hits


@pytest.mark.parametrize("module", STRUCTURAL_MODULES, ids=lambda p: p.name)
def test_structural_module_reads_no_appropriations_vocabulary(module: Path):
    assert module.exists(), f"{module} moved; update STRUCTURAL_MODULES or this gate guards nothing"
    hits = find_appropriations_vocabulary(module.read_text())
    assert hits == [], (
        f"{module.name} matches appropriations English in a string literal: {hits}. "
        "Structure comes from format (size/position/TITLE/SEC.), not genre vocabulary "
        "— see docs/decisions/0018-text-triggers-are-financial-only.md."
    )


def test_detector_flags_the_retired_trigger():
    """Proves the gate can fail. The sample is the code this rule exists to reject."""
    known_bad = 'import re\n_FOR_NECESSARY_EXPENSES = re.compile(r"^For necessary expenses of\\b", re.IGNORECASE)\n'
    hits = find_appropriations_vocabulary(known_bad)
    assert [phrase for phrase, _ in hits] == ["necessary expenses"]


def test_detector_ignores_prose_about_the_rule():
    """Comments and docstrings may name the phrases; only live literals count.

    Without this the gate would be unusable: explaining WHY the trigger was retired,
    as this repo does in several docstrings, would itself trip it.
    """
    prose = (
        '"""Retired the `For necessary expenses of` trigger (#114)."""\n'
        "# RESCISSION and INCLUDING TRANSFER OF FUNDS are financial-layer vocabulary.\n"
        "PATTERN = 1\n"
    )
    assert find_appropriations_vocabulary(prose) == []
