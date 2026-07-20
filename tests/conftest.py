"""Shared test helpers and fixtures."""

import functools
import os
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree, normalize_bill
from diff_bill import NodeDiff, diff_bills

BILLS_DIR = Path(__file__).parent.parent / "bills"

# --- Committed corpus manifest (#217 / ADR 0015) -------------------------------
# The three corpus correctness gates (test_corpus_properties, test_corpus_tree_
# properties, test_diff_validation) parametrize over the COMMITTED fixture set named
# in tests/corpus_manifest.toml — not a `bills/*/…` glob. Every manifested bill is in
# git, so the collected set is byte-identical on every machine and in CI; a missing
# fixture fails the per-module completeness floor (fail closed) instead of vanishing
# from an empty glob (fail open). See docs/decisions/0015-corpus-test-fixtures.md.
#
# CORPUS_SWEEP=1 restores the old broad-glob behavior as an opt-in, non-CI exploratory
# mode: it sweeps every locally-fetched bill (a superset of the manifest), which has
# caught bugs a few clean bills did not (#126, #146). It is exploration, not a gate.
CORPUS_SWEEP = os.environ.get("CORPUS_SWEEP") == "1"
_MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.toml"


@functools.cache
def _manifest_bills() -> tuple[dict, ...]:
    """The [[bill]] entries from corpus_manifest.toml (cached)."""
    return tuple(tomllib.loads(_MANIFEST_PATH.read_text())["bill"])


def _manifest_paths(fmt: str) -> list[Path]:
    """Committed manifest fixture paths of one format ('xml' | 'pdf'), sorted."""
    return sorted(
        BILLS_DIR / bill["id"] / f"{ver['stage']}.{fmt}"
        for bill in _manifest_bills()
        for ver in bill["versions"]
        if fmt in ver["formats"]
    )


def manifest_xml_files() -> list[Path]:
    """XML fixtures the corpus gates parametrize over (manifest, or the full local
    glob under CORPUS_SWEEP)."""
    if CORPUS_SWEEP:
        return sorted(BILLS_DIR.glob("*/[0-9]*_*.xml"))
    return _manifest_paths("xml")


def manifest_pdf_files() -> list[Path]:
    """PDF fixtures the corpus gates parametrize over (manifest, or the full local
    glob under CORPUS_SWEEP)."""
    if CORPUS_SWEEP:
        return sorted(BILLS_DIR.glob("*/[0-9]*_*.pdf"))
    return _manifest_paths("pdf")


def _stage_num(path: Path) -> int:
    """Leading integer of a version filename (``4_engrossed-... -> 4``). Adjacency for
    the diff pairs must sort NUMERICALLY, not lexicographically: a string sort puts
    ``10_`` before ``2_`` and would silently mis-pair a 10+-stage bill. No corpus bill
    reaches stage 10 today, so this is a latent guard, not a live fix."""
    return int(path.name.split("_", 1)[0])


def manifest_version_pairs() -> list[tuple[Path, Path]]:
    """Adjacent committed-XML version pairs within each bill, for the diff smoke.
    Under CORPUS_SWEEP, every adjacent pair across all locally-fetched bills."""
    pairs: list[tuple[Path, Path]] = []
    if CORPUS_SWEEP:
        for bill_dir in sorted(BILLS_DIR.iterdir()):
            if bill_dir.is_dir():
                # Scope to the version-file naming (matches manifest_xml_files) so a stray
                # non-bill XML (e.g. govinfo BILLSTATUS metadata) can't enter the diff pairs.
                versions = sorted(bill_dir.glob("[0-9]*_*.xml"), key=_stage_num)
                pairs += [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]
        return pairs
    for bill in _manifest_bills():
        versions = sorted(
            (BILLS_DIR / bill["id"] / f"{ver['stage']}.xml" for ver in bill["versions"] if "xml" in ver["formats"]),
            key=_stage_num,
        )
        pairs += [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]
    return pairs


def missing_manifest_files() -> list[str]:
    """Manifest fixtures (all formats) absent from the checkout. Must be empty: every
    manifested bill is committed, so absence means an uncommitted fixture (fail closed).
    Checks the manifest set regardless of CORPUS_SWEEP."""
    missing = []
    for bill in _manifest_bills():
        for ver in bill["versions"]:
            for fmt in ver["formats"]:
                if not (BILLS_DIR / bill["id"] / f"{ver['stage']}.{fmt}").exists():
                    missing.append(f"{bill['id']}/{ver['stage']}.{fmt}")
    return missing


def assert_manifest_committed(collected: Sequence, kind: str) -> None:
    """Fail-closed completeness floor for a corpus gate (#217, ADR 0015).

    Called from a plain (non-parametrized) guard test so it always collects and runs —
    with no env var, unlike the retired REQUIRE_CORPUS floor. Fails (not skips) if any
    manifested fixture is absent from the checkout, so a fresh CI checkout that is
    missing a committed fixture goes red instead of silently collecting fewer cases.
    ``kind`` names the gate in the failure message.
    """
    missing = missing_manifest_files()
    assert not missing, (
        f"{kind}: manifest fixtures absent from the checkout (uncommitted?): {missing}. "
        "Every bill in tests/corpus_manifest.toml must be committed to git."
    )
    assert len(collected) > 0, f"{kind}: gate parametrized over zero cases despite a complete manifest."


# --- REQUIRE_CORPUS: narrowed by #220 ------------------------------------------
# No longer a corpus-gate mechanism: #220 put every corpus gate on the committed
# manifest, so they fail closed with no env var. Two non-manifest consumers keep the
# flag alive: test_govinfo_corpus_parity (a live-network gate) and
# test_validate_extraction's fetched-bill floor. Read it now as "I have a fetched
# corpus and a network", not "make the corpus gates strict". Full rationale, and the
# retirement plan, are in ADR 0015 (its #220 amendment) and issue #278.
REQUIRE_CORPUS = os.environ.get("REQUIRE_CORPUS") == "1"

# Paths to commonly used bill versions (118-hr-4366).
HR4366_V1_PATH = BILLS_DIR / "118-hr-4366" / "1_reported-in-house.xml"
HR4366_V4_PATH = BILLS_DIR / "118-hr-4366" / "4_engrossed-amendment-senate.xml"
HR4366_V5_PATH = BILLS_DIR / "118-hr-4366" / "5_engrossed-amendment-house.xml"
HR4366_V6_PATH = BILLS_DIR / "118-hr-4366" / "6_enrolled-bill.xml"

HR4366_V2_PATH = BILLS_DIR / "118-hr-4366" / "2_engrossed-in-house.xml"

HR5895_V4_PATH = BILLS_DIR / "115-hr-5895" / "4_engrossed-amendment-senate.xml"
HR5895_V5_PATH = BILLS_DIR / "115-hr-5895" / "5_enrolled-bill.xml"


# --- Session-scoped cached bill trees ---
# These avoid re-parsing the same large XML files across test classes.
# Safe because BillTree and BillNode are frozen dataclasses.


@pytest.fixture(scope="session")
def hr4366_v1():
    """Parsed 118-hr-4366 reported-in-house (v1)."""
    if not HR4366_V1_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR4366_V1_PATH)


@pytest.fixture(scope="session")
def hr4366_v6():
    """Parsed 118-hr-4366 enrolled-bill (v6)."""
    if not HR4366_V6_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR4366_V6_PATH)


@pytest.fixture(scope="session")
def hr4366_v2():
    """Parsed 118-hr-4366 engrossed-in-house (v2)."""
    if not HR4366_V2_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR4366_V2_PATH)


@pytest.fixture(scope="session")
def hr4366_v4():
    """Parsed 118-hr-4366 engrossed-amendment-senate (v4)."""
    if not HR4366_V4_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR4366_V4_PATH)


@pytest.fixture(scope="session")
def hr4366_v5():
    """Parsed 118-hr-4366 engrossed-amendment-house (v5)."""
    if not HR4366_V5_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR4366_V5_PATH)


@pytest.fixture(scope="session")
def hr4366_v1_v6_diff(hr4366_v1, hr4366_v6):
    """Cached diff of v1 (reported) vs v6 (enrolled) for 118-hr-4366."""
    return diff_bills(hr4366_v1, hr4366_v6)


@pytest.fixture(scope="session")
def hr4366_v1_v2_diff(hr4366_v1, hr4366_v2):
    """Cached diff of v1 (reported) vs v2 (engrossed-in-house) for 118-hr-4366."""
    return diff_bills(hr4366_v1, hr4366_v2)


@pytest.fixture(scope="session")
def hr4366_v4_v5_diff(hr4366_v4, hr4366_v5):
    """Cached diff of v4 vs v5 for 118-hr-4366."""
    return diff_bills(hr4366_v4, hr4366_v5)


@pytest.fixture(scope="session")
def hr5895_v4():
    """Parsed 115-hr-5895 engrossed-amendment-senate (v4)."""
    if not HR5895_V4_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR5895_V4_PATH)


@pytest.fixture(scope="session")
def hr5895_v5():
    """Parsed 115-hr-5895 enrolled-bill (v5)."""
    if not HR5895_V5_PATH.exists():
        pytest.skip("Real XML not present")
    return normalize_bill(HR5895_V5_PATH)


@pytest.fixture(scope="session")
def hr5895_v4_v5_diff(hr5895_v4, hr5895_v5):
    """Cached diff of v4 vs v5 for 115-hr-5895."""
    return diff_bills(hr5895_v4, hr5895_v5)


# --- Session-scoped HR8752 PDF pages (shared across pdf recall tests) ---

HR8752_V1_PDF = BILLS_DIR / "118-hr-8752" / "1_reported-in-house.pdf"
HR8752_V2_PDF = BILLS_DIR / "118-hr-8752" / "2_engrossed-in-house.pdf"


@pytest.fixture(scope="session")
def hr8752_v1_pages():
    if not HR8752_V1_PDF.exists():
        pytest.skip("HR 8752 v1 PDF not present")
    from parsers.pdf_text import extract_clean_pages

    return extract_clean_pages(HR8752_V1_PDF)


@pytest.fixture(scope="session")
def hr8752_v2_pages():
    if not HR8752_V2_PDF.exists():
        pytest.skip("HR 8752 v2 PDF not present")
    from parsers.pdf_text import extract_clean_pages

    return extract_clean_pages(HR8752_V2_PDF)


@pytest.fixture(scope="session")
def hr8752_pdf_diff(hr8752_v1_pages, hr8752_v2_pages):
    from diff_pdf import diff_pdfs

    return diff_pdfs(hr8752_v1_pages, hr8752_v2_pages)


@pytest.fixture
def fast_normalize_diff(monkeypatch, hr4366_v1, hr4366_v2, hr4366_v6, hr4366_v1_v2_diff, hr4366_v1_v6_diff):
    """Monkeypatch diff_bill.normalize_bill and diff_bills to reuse session-cached results
    for the 118-hr-4366 v1/v2/v6 paths used by the CLI tests. Saves ~7s/test."""
    import diff_bill as diff_bill_module

    normalize_orig = diff_bill_module.normalize_bill
    diff_orig = diff_bill_module.diff_bills
    tree_cache = {HR4366_V1_PATH: hr4366_v1, HR4366_V2_PATH: hr4366_v2, HR4366_V6_PATH: hr4366_v6}
    diff_cache = {
        (id(hr4366_v1), id(hr4366_v2)): hr4366_v1_v2_diff,
        (id(hr4366_v1), id(hr4366_v6)): hr4366_v1_v6_diff,
    }

    def _cached_normalize(path):
        return tree_cache.get(path) or normalize_orig(path)

    def _cached_diff(old, new):
        cached = diff_cache.get((id(old), id(new)))
        if cached is not None:
            return cached
        return diff_orig(old, new)

    monkeypatch.setattr(diff_bill_module, "normalize_bill", _cached_normalize)
    monkeypatch.setattr(diff_bill_module, "diff_bills", _cached_diff)


def has_bill_xml() -> bool:
    """Check if real bill XML files are available.

    Matches the corpus version-file naming (`<n>_<stage>.xml`), not any `*.xml`, so a
    directory holding only non-bill XML (e.g. govinfo BILLSTATUS metadata) doesn't
    falsely report the corpus as present.
    """
    return any(BILLS_DIR.glob("*/[0-9]*_*.xml"))


def make_bill_node(
    match_path,
    body_text="text",
    element_id="",
    header_text="",
    tag="appropriations-intermediate",
    division_label="",
):
    """Build a BillNode with defaults for testing."""
    return BillNode(
        match_path=match_path,
        display_path=match_path,
        tag=tag,
        element_id=element_id,
        header_text=header_text,
        body_text=body_text,
        section_number="",
        division_label=division_label,
    )


def make_bill_tree(nodes):
    """Build a BillTree with defaults."""
    return BillTree(congress=118, bill_type="hr", bill_number=4366, version="test", nodes=nodes)


def make_node_diff(change_type, old_path=None, new_path=None, old_text=None, new_text=None):
    """Build a NodeDiff with defaults for testing."""
    return NodeDiff(
        display_path_old=old_path,
        display_path_new=new_path,
        match_path=old_path or new_path or (),
        change_type=change_type,
        old_text=old_text,
        new_text=new_text,
        text_diff=None,
        section_number="",
        element_id_old="old_id" if old_text else "",
        element_id_new="new_id" if new_text else "",
    )


def make_change_dict(*, change_type="modified", path=None, financial=None, index=0):
    """Build a minimal change dict for HTML formatter testing."""
    return {
        "display_path_old": path or ["DEPT", "Section"],
        "display_path_new": path or ["DEPT", "Section"],
        "match_path": [p.lower() for p in (path or ["DEPT", "Section"])],
        "change_type": change_type,
        "old_text": "old",
        "new_text": "new",
        "text_diff": [],
        "section_number": "",
        "element_id_old": f"old-{index}",
        "element_id_new": f"new-{index}",
        **({"financial": financial} if financial else {}),
    }
