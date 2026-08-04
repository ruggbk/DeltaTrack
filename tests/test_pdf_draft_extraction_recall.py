"""Extraction recall test for a real draft PDF (no XML twin).

Draft bills circulate as PDF only. This test hand-verifies that key amounts and
clauses survive `extract_clean_pages` + `extract_amounts` on a real introduced/
referred bill PDF. The fixture is a curated list from visual inspection of
114-HR-2029 v3 (Senate referred), a Military Construction/VA appropriations bill.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deltatrack.diff_bill import extract_amounts
from tests.corpus_paths import fixture_path
from tests.pdf_corpus import cached_pages

FIXTURE_PATH = Path(__file__).parent / "data" / "pdf" / "draft_114hr2029_fixture.json"


def _load_fixture() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


FIXTURE = _load_fixture()


def _full_text(pages) -> str:
    return "\n".join(p.text for p in pages)


def _normalized_text(pages) -> str:
    """Text with newlines collapsed for clause matching."""
    return " ".join(p.text.replace("\n", " ") for p in pages)


@pytest.mark.slow
def test_draft_extraction_recall_amounts():
    """Every hand-verified dollar amount must be extractable from the PDF."""
    pdf_path = fixture_path(FIXTURE["bill_id"], FIXTURE["version"] + ".pdf")
    pages = cached_pages(pdf_path)
    text = _full_text(pages)
    extracted = set(extract_amounts(text))

    missing = [amt for amt in FIXTURE["amounts"] if amt not in extracted]
    assert not missing, (
        f"Missing {len(missing)} expected amount(s): {missing[:10]}...\nBill: {FIXTURE['bill_id']} {FIXTURE['version']}"
    )


@pytest.mark.slow
def test_draft_extraction_recall_clauses():
    """Key section headers and clause text must survive extraction."""
    pdf_path = fixture_path(FIXTURE["bill_id"], FIXTURE["version"] + ".pdf")
    pages = cached_pages(pdf_path)
    text = _normalized_text(pages)

    missing = [clause for clause in FIXTURE["clauses"] if clause not in text]
    assert not missing, (
        f"Missing {len(missing)} expected clause(s): {missing[:5]}...\nBill: {FIXTURE['bill_id']} {FIXTURE['version']}"
    )
