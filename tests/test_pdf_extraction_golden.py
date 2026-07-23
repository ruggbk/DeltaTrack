"""Golden-snapshot regression guard for PDF text extraction.

The amount-recall and diff-recall suites prove extraction *recall* (expected
content survives). They miss a subtler regression: the cleaner silently changing
what it emits — chrome leaking back into the body, a soft-hyphen path breaking,
or a pypdfium2 upgrade altering glyph handling. This pins the cleaned line output
of a curated set of pages, each chosen to exercise one tricky path, so any such
change fails loudly with a readable diff.

Engine note: extraction is pypdfium2 (PDFium). pdfplumber was dropped after a
full-corpus differential check (numbered-line parity ~99.9%, identical per-pair
diff output). That cross-engine comparison cannot run once pdfplumber is gone, so
this golden is the lasting guard against extraction drift.

To regenerate after an INTENTIONAL extraction change, then review the JSON diff:
    UPDATE_GOLDEN=1 uv run pytest tests/test_pdf_extraction_golden.py

Regeneration MERGES (#296): cases whose fixture is absent keep their recorded
expectations instead of being dropped from the file. See _regenerated_golden.
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

import pytest

from parsers.pdf_text import extract_clean_pages
from tests.conftest import assert_manifest_committed

_ROOT = Path(__file__).parent.parent
_GOLDEN = _ROOT / "test_data" / "pdf" / "extraction_golden.json"

# (key, pdf path relative to repo root, 1-based page, path exercised).
_CASES = [
    (
        "hr4366_reported_p5",
        "bills/118-hr-4366/1_reported-in-house.pdf",
        5,
        "numbered body + soft-hyphen reconstruction across margin lines",
    ),
    (
        "hr4366_pcs_p7",
        "bills/118-hr-4366/3_placed-on-calendar-senate.pdf",
        7,
        "page-boundary hyphen gluing the VerDate footer onto the last body line",
    ),
    (
        "hr2029_reported_p2",
        "bills/114-hr-2029/1_reported-in-house.pdf",
        2,
        "page-boundary hyphen gluing the DSK watermark onto the last body line",
    ),
    (
        "hr8752_title_p1",
        "bills/118-hr-8752/1_reported-in-house.pdf",
        1,
        "title page: soft hyphen joined into one word (no margin numbers)",
    ),
    (
        "crpt198_compare_p220",
        "test_data/CRPT-118srpt198.pdf",
        220,
        "watermarked committee-report comparison table read forward, not reversed",
    ),
]

# The cases whose fixtures are committed, so their absence is a fail-closed error
# (floored by test_manifest_fixtures_committed), never a silent skip — the fail-open
# shape #287 removes. hr8752 v1 was already committed; CRPT-118srpt198 is committed by
# #287 (which also resolves the fetchability half of #296). The other three read large
# omnibus PDFs kept FETCHED-ONLY (not in the #287 committed set), so they skip visibly
# when absent, like the other slow PDF suites (TESTING.md).
_COMMITTED_RELS = frozenset(
    {
        "bills/118-hr-8752/1_reported-in-house.pdf",
        "test_data/CRPT-118srpt198.pdf",
    }
)


class GoldenEntryPreserved(UserWarning):
    """Raised by regeneration when a case's fixture is absent and its entry was kept.

    A warning, not a print: pytest captures stdout for passing tests and this repo runs
    xdist by default (addopts), so a printed notice never reaches the contributor running
    the documented UPDATE_GOLDEN=1 command. Warnings survive both and land in the summary.
    """


def _page_lines(path: Path, page_number: int) -> list[list]:
    """The cleaned page's lines as JSON-friendly [line_number, text] pairs."""
    pages = extract_clean_pages(path)
    page = next((p for p in pages if p.page_number == page_number), None)
    assert page is not None, f"{path} has no page {page_number}"
    return [[ln.line_number, ln.text] for ln in page.lines]


def _present(rel: str) -> bool:
    return (_ROOT / rel).exists()


def test_manifest_fixtures_committed():
    """Fail-closed floor (#287, ADR 0015): a plain, always-collected guard, so a missing
    committed fixture fails HERE naming it, instead of the fail-open shape #287 removes (a
    case silently skipping in CI). hr8752 v1 is in the bills/-layout manifest (checked via
    the shared helper); CRPT-118srpt198 sits outside it (ADR 0015), so it is floored
    directly. The three fetched-only omnibus cases are deliberately NOT floored — they keep
    a visible per-case skip (see _COMMITTED_RELS)."""
    assert_manifest_committed(sorted(_COMMITTED_RELS), "pdf-extraction-golden")
    absent = sorted(rel for rel in _COMMITTED_RELS if not _present(rel))
    assert not absent, f"committed pdf-extraction-golden fixtures absent from checkout: {absent}"


def _regenerated_golden(existing: dict) -> dict:
    """The merged golden: regenerate present cases, PRESERVE entries for absent ones (#296).

    The pre-#296 body rebuilt the file from only the present cases and overwrote, so a
    contributor on a checkout without the fetched-only omnibus PDFs (see _COMMITTED_RELS)
    deleted those cases' expectations as an ordinary-looking diff. A skipped case comes
    back when someone fetches the file; a deleted golden entry does not, and the case then
    fails closed with "no golden entry" for a reason unrelated to what it tests.

    Preservation trades a deletion for a possibly-STALE entry: regenerating after a real
    extraction change on a partial checkout leaves those cases recorded in the old format,
    and CI cannot catch it because they skip when the PDF is absent. So the preserved cases
    are named in a GoldenEntryPreserved warning — the only control for that residue, which
    is why it must not be a print (see that class).

    Fail-closed where it should be: a *committed* fixture being absent means the checkout
    is broken, not that the case is optional, so refuse to write at all rather than
    silently rebuild from a partial set.

    Entries for keys no longer in _CASES are dropped — retiring a case should clean up
    after itself. Output follows _CASES order for a stable, reviewable diff.
    """
    absent_committed = sorted(rel for rel in _COMMITTED_RELS if not _present(rel))
    assert not absent_committed, (
        f"refusing to regenerate: committed fixtures absent from the checkout: {absent_committed}. "
        "Restore them before regenerating (#296)."
    )
    merged: dict[str, list] = {}
    preserved: list[str] = []
    for key, rel, pg, _ in _CASES:
        if _present(rel):
            merged[key] = _page_lines(_ROOT / rel, pg)
        elif key in existing:
            merged[key] = existing[key]
            preserved.append(key)
    if preserved:
        warnings.warn(
            f"[golden] fixture absent, entry preserved not regenerated: {', '.join(preserved)}. "
            "Fetch those PDFs and regenerate again if the extraction change affects them.",
            GoldenEntryPreserved,
            stacklevel=2,
        )
    return merged


@pytest.mark.skipif(os.environ.get("UPDATE_GOLDEN") != "1", reason="not in golden-update mode")
def test_regenerate_golden():
    """Rewrite the golden from current extraction. Skipped unless UPDATE_GOLDEN=1."""
    existing = json.loads(_GOLDEN.read_text()) if _GOLDEN.exists() else {}
    data = _regenerated_golden(existing)
    _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def test_regeneration_preserves_entries_for_absent_fixtures(monkeypatch):
    """#296: regenerating on a checkout missing a fetched-only fixture keeps that case's
    recorded expectations, and NAMES it so the contributor knows the entry may be stale.
    Simulates the absent fixture rather than moving the real PDF, so this runs on any
    checkout."""
    module = sys.modules[__name__]
    absent_rel = "bills/118-hr-4366/1_reported-in-house.pdf"
    monkeypatch.setattr(module, "_present", lambda rel: rel != absent_rel)
    monkeypatch.setattr(module, "_page_lines", lambda path, pg: [[1, "regenerated"]])

    existing = {key: [[1, f"recorded {key}"]] for key, *_ in _CASES}
    with pytest.warns(GoldenEntryPreserved, match="hr4366_reported_p5"):
        merged = _regenerated_golden(existing)

    assert set(merged) == {key for key, *_ in _CASES}, "no case may drop out of the golden"
    assert merged["hr4366_reported_p5"] == [[1, "recorded hr4366_reported_p5"]]
    assert merged["crpt198_compare_p220"] == [[1, "regenerated"]]


def test_regeneration_is_silent_when_every_fixture_is_present(monkeypatch, recwarn):
    """The notice must fire only on a real preservation: a warning on every regeneration
    would be trained past, and then the stale-entry case it exists to flag reads as noise."""
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "_present", lambda rel: True)
    monkeypatch.setattr(module, "_page_lines", lambda path, pg: [[1, "regenerated"]])

    merged = _regenerated_golden({})

    assert set(merged) == {key for key, *_ in _CASES}
    assert not [w for w in recwarn if issubclass(w.category, GoldenEntryPreserved)]


def test_regeneration_refuses_when_a_committed_fixture_is_absent(monkeypatch):
    """#296: a missing committed fixture is a broken checkout, not an optional case, so
    regeneration must not write a partial golden."""
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "_present", lambda rel: rel not in _COMMITTED_RELS)
    monkeypatch.setattr(module, "_page_lines", lambda path, pg: [[1, "regenerated"]])

    with pytest.raises(AssertionError, match="refusing to regenerate"):
        _regenerated_golden({})


@pytest.mark.parametrize("key,rel,page,why", _CASES, ids=[c[0] for c in _CASES])
def test_extraction_matches_golden(key, rel, page, why):
    if os.environ.get("UPDATE_GOLDEN") == "1":
        pytest.skip("golden-update mode")
    # Committed cases (_COMMITTED_RELS) run unconditionally: a missing fixture is a
    # fail-closed error, floored by test_manifest_fixtures_committed. The fetched-only
    # omnibus cases skip visibly when absent (not committed, out of the #287 set).
    if rel not in _COMMITTED_RELS and not _present(rel):
        pytest.skip(f"{rel} not present (fetched-only omnibus PDF)")
    golden = json.loads(_GOLDEN.read_text())
    assert key in golden, f"no golden entry for {key}; regenerate with UPDATE_GOLDEN=1"
    actual = _page_lines(_ROOT / rel, page)
    expected = [[ln, text] for ln, text in golden[key]]
    assert actual == expected, (
        f"extraction drifted for {key} ({why}). If intentional, regenerate the "
        f"golden with UPDATE_GOLDEN=1 and review the diff."
    )
