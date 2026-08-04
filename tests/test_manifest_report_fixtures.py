"""Manifest-driven committee report fixture tests (issue #295).

These tests exercise the committee report reader against ALL manifested report fixtures,
not just the Senate validation jurisdictions. This ensures the parser handles House
report formatting (which renders account tables as images) and detects any
Senate/118th-specific assumptions.

House reports are not expected to yield usable amount data (tables are images), but
they must parse without error and produce a valid document structure. This is a
parser generalization gate, not an amount-validation gate.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from deltatrack.parsers.committee_report import (
    extract_pre_text,
    parse_comparative_statement,
    parse_summary_blocks,
)
from tests.corpus_paths import DATA_DIR


def load_manifest() -> dict:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        return tomllib.load(f)


def extract_report_pkgs(manifest: dict) -> dict[str, list[dict]]:
    """Extract all report package IDs from the manifest, grouped by bill/version."""
    result = {}
    for bill_entry in manifest.get("bill", []):
        bill_id = bill_entry["id"]
        for ver in bill_entry.get("versions", []):
            cr = ver.get("committee_report")
            if cr:
                if isinstance(cr, list):
                    sources = [s for s in cr if s.get("pkg") and s["pkg"] != "none"]
                else:
                    sources = [cr] if cr.get("pkg") and cr["pkg"] != "none" else []
                if sources:
                    key = (bill_id, ver["stage"])
                    result[key] = sources
    return result


# Collect all unique report packages from the manifest
_MANIFEST = load_manifest()
_REPORT_PKGS = extract_report_pkgs(_MANIFEST)
_ALL_REPORT_SOURCES = []
for (bill_id, stage), sources in _REPORT_PKGS.items():
    for src in sources:
        pkg = src["pkg"]
        if pkg not in [s["pkg"] for s in _ALL_REPORT_SOURCES]:
            _ALL_REPORT_SOURCES.append(
                {
                    "pkg": pkg,
                    "citation": src["citation"],
                    "chamber": src["chamber"],
                    "book": src.get("book"),
                    "bill_id": bill_id,
                    "stage": stage,
                }
            )


@pytest.mark.slow
@pytest.mark.parametrize("src", _ALL_REPORT_SOURCES, ids=lambda s: s["pkg"])
def test_committee_report_fixture_parses(src: dict):
    """Every manifested committee report HTML fixture must parse without error.

    This is the primary generalization gate for issue #295: it ensures the
    committee report reader handles both Senate and House formatting. House
    reports render account tables as images, so they produce 0 summary blocks,
    but they must still parse into a valid document structure.

    The test does NOT assert amount validation for House reports — that is
    tracked separately under #5 / #289 (House extraction has no external check).
    """
    pkg = src["pkg"]
    html_path = DATA_DIR / f"{pkg}.htm"

    # Known unavailable fixtures (report exists in BILLSTATUS but full text not yet on govinfo)
    KNOWN_UNAVAILABLE = {
        "CRPT-119hrpt106": "119th Congress report not yet published in full text on govinfo",
        "CRPT-118hrpt364": "Report full text not available on govinfo (BILLSTATUS citation only)",
    }

    if pkg in KNOWN_UNAVAILABLE:
        pytest.skip(KNOWN_UNAVAILABLE[pkg])

    # Completeness floor: every manifested report fixture must be committed
    assert html_path.exists(), (
        f"Committee report fixture {pkg}.htm is referenced in corpus_manifest.toml "
        f"but not committed to tests/data/. Download with scripts/vendor_reports.py."
    )

    # Parse the HTML
    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    pre_text = extract_pre_text(html_content)

    # Basic sanity checks on extracted text
    assert len(pre_text) > 1000, f"{pkg}: extracted text too short ({len(pre_text)} chars)"
    assert "APPROPRIATIONS" in pre_text.upper(), f"{pkg}: doesn't appear to be an appropriations report"

    # Try parsing summary blocks (should work for Senate, yield 0 for House)
    summary_blocks = parse_summary_blocks(pre_text)

    # Try parsing comparative statement (should work for tabular jurisdictions)
    comparative_rows = parse_comparative_statement(pre_text)

    # Assertions based on chamber
    chamber = src["chamber"]
    if chamber == "house":
        # House reports use image-based tables, so summary_blocks and comparative
        # should be empty or near-empty. This is expected, not a bug.
        # The key assertion is that parsing completes without error.
        # We track the count for observability but don't fail on it.
        pass  # Expected: 0 summary blocks for House
    else:
        # Senate reports should yield some summary blocks or comparative rows
        total_parsed = len(summary_blocks) + len(comparative_rows)
        assert total_parsed > 0, (
            f"{pkg} (Senate): expected at least some parsed accounts, "
            f"got {len(summary_blocks)} summary blocks + {len(comparative_rows)} comparative rows"
        )


@pytest.mark.slow
def test_all_manifested_reports_are_committed():
    """Completeness floor: every committee_report pkg in the manifest must have a
    committed HTML fixture in tests/data/.

    This is the analog of test_manifest_fixtures_committed for report fixtures.
    """
    missing = []
    for src in _ALL_REPORT_SOURCES:
        pkg = src["pkg"]
        html_path = DATA_DIR / f"{pkg}.htm"
        if not html_path.exists():
            missing.append(f"{pkg} (for {src['bill_id']} {src['stage']})")

    assert not missing, (
        f"{len(missing)} committee report fixture(s) referenced in corpus_manifest.toml "
        f"are not committed to tests/data/:\n" + "\n".join(f"  {m}" for m in missing)
    )


@pytest.mark.slow
def test_119_hr_1_has_both_books():
    """Regression test for 119-hr-1's two-book report (issue #295).

    H. Rept. 119-106 is published as two physical books (Book 1 and Book 2).
    Both must be present in the manifest. The full-text fixtures are not yet
    available on govinfo (119th Congress), so we only verify the manifest structure.
    """
    # Find 119-hr-1 reported-in-house version
    bill_id = "119-hr-1"
    stage = "1_reported-in-house"

    key = (bill_id, stage)
    assert key in _REPORT_PKGS, f"{bill_id} {stage} missing committee_report in manifest"

    sources = _REPORT_PKGS[key]
    assert len(sources) == 2, (
        f"{bill_id} {stage}: expected 2 report sources (Book 1 and Book 2), "
        f"got {len(sources)}: {[s['citation'] for s in sources]}"
    )

    books = {s.get("book") for s in sources}
    assert "Book 1" in books, "Missing Book 1"
    assert "Book 2" in books, "Missing Book 2"

    # Fixtures not yet available on govinfo (known limitation)
    # When they become available, download with scripts/vendor_reports.py


@pytest.mark.slow
def test_115_hr_5895_enrolled_has_conference_report():
    """Regression test for 115-hr-5895 enrolled conference report (issue #295).

    The enrolled version should pair with both H. Rept. 115-697 (House report)
    and H. Rept. 115-929 (conference report).
    """
    bill_id = "115-hr-5895"
    stage = "5_enrolled-bill"

    key = (bill_id, stage)
    assert key in _REPORT_PKGS, f"{bill_id} {stage} missing committee_report in manifest"

    sources = _REPORT_PKGS[key]
    citations = {s["citation"] for s in sources}

    assert "H. Rept. 115-697" in citations, "Missing House report H. Rept. 115-697"
    assert "H. Rept. 115-929" in citations, "Missing conference report H. Rept. 115-929"

    # Both must be committed fixtures
    for s in sources:
        pkg = s["pkg"]
        html_path = DATA_DIR / f"{pkg}.htm"
        assert html_path.exists(), f"Missing fixture for {pkg}"


@pytest.mark.slow
def test_114_hr_2029_enrolled_has_both_chambers():
    """Regression test for 114-hr-2029 enrolled having both House and Senate reports."""
    bill_id = "114-hr-2029"
    stage = "7_enrolled-bill"

    key = (bill_id, stage)
    assert key in _REPORT_PKGS, f"{bill_id} {stage} missing committee_report in manifest"

    sources = _REPORT_PKGS[key]
    chambers = {s["chamber"] for s in sources}

    assert "house" in chambers, "Missing House report"
    assert "senate" in chambers, "Missing Senate report"
