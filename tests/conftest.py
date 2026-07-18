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


def manifest_version_pairs() -> list[tuple[Path, Path]]:
    """Adjacent committed-XML version pairs within each bill, for the diff smoke.
    Under CORPUS_SWEEP, every adjacent pair across all locally-fetched bills."""
    pairs: list[tuple[Path, Path]] = []
    if CORPUS_SWEEP:
        for bill_dir in sorted(BILLS_DIR.iterdir()):
            if bill_dir.is_dir():
                # Scope to the version-file naming (matches manifest_xml_files) so a stray
                # non-bill XML (e.g. govinfo BILLSTATUS metadata) can't enter the diff pairs.
                versions = sorted(bill_dir.glob("[0-9]*_*.xml"))
                pairs += [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]
        return pairs
    for bill in _manifest_bills():
        versions = sorted(
            BILLS_DIR / bill["id"] / f"{ver['stage']}.xml" for ver in bill["versions"] if "xml" in ver["formats"]
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


# --- Legacy corpus completeness policy (#167) ----------------------------------
# REQUIRE_CORPUS predates the committed manifest. The three corpus gates above no
# longer use it — they parametrize over the committed manifest and fail closed via
# assert_manifest_committed. It survives only as the presence floor for the corpus
# modules still parametrized over fetched (uncommitted) bills — test_node_join_corpus,
# test_xml_subsection_nodes, test_pdf_subsection_recall — pending their migration to
# the manifest. Those bills (e.g. the large 114-hr-2029 omnibus) are not yet in the
# committed set, so REQUIRE_CORPUS=1 remains their opt-in strict mode: a missing
# baseline asset or empty parametrization is a loud failure instead of a silent skip.
REQUIRE_CORPUS = os.environ.get("REQUIRE_CORPUS") == "1"

# The curated baseline floor for the REQUIRE_CORPUS modules above: the bills those
# modules hand-pin that are NOT in the committed manifest, so they are absent on an
# unfetched checkout. In REQUIRE_CORPUS mode every one must be on disk, else the module
# that pins it against a hardcoded baseline skips silently. Paths are relative to
# BILLS_DIR. (Manifest bills those modules also use — 118-hr-8752, 119-hr-1 v1 — are
# always committed, so they are not the floor here; only the uncommitted bills are.)
# Deliberately over-inclusive across the three modules: it is a shared floor, so a
# missing bill any module needs fails loudly rather than passing green on a partial
# fetch. Migrating these modules onto the manifest is tracked in #220.
REQUIRED_CORPUS_BILLS = (
    # test_xml_subsection_nodes / test_pdf_subsection_recall: 117-hr-4502 is a CLEAN
    # convergence bill (exact-parity assertions); both XML and PDF are pinned.
    "117-hr-4502/1_reported-in-house.xml",
    "117-hr-4502/1_reported-in-house.pdf",
    # test_node_join_corpus: 114-hr-2029 (OMNIBUS_PAIR / span-geometry) and 113-hr-3547
    # stages 4-5 (the amendment-shape XML pairs). v6 of 113-hr-3547 is committed, but
    # these earlier stages are not.
    "114-hr-2029/5_engrossed-amendment-senate.xml",
    "114-hr-2029/6_engrossed-amendment-house.xml",
    "113-hr-3547/4_engrossed-amendment-senate.xml",
    "113-hr-3547/5_engrossed-amendment-house.xml",
    # test_node_join_corpus PDF pairs: their own floor (test_pdf_corpus_present_when_
    # required) only asserts >0 discovered, so a single missing PDF would silently drop
    # one pair to zero cases. Pinning each file here makes missing_required_corpus name
    # it. (114-hr-2029 v4 is the post-#10 govinfo name reported-in-senate, was
    # reported-to-senate under the API source.)
    "114-hr-2029/3_referred-in-senate.pdf",
    "114-hr-2029/4_reported-in-senate.pdf",
    "113-hr-3547/3_received-in-senate.pdf",
    "113-hr-3547/4_engrossed-amendment-senate.pdf",
    "113-hr-3547/1_introduced-in-house.pdf",
    "113-hr-3547/2_engrossed-in-house.pdf",
)


def missing_required_corpus() -> list[str]:
    """Baseline bills (relative paths) absent from BILLS_DIR."""
    return [rel for rel in REQUIRED_CORPUS_BILLS if not (BILLS_DIR / rel).exists()]


def require_corpus_or_skip(discovered: Sequence, kind: str) -> None:
    """Completeness floor for a corpus property gate (#167).

    Call from a plain (non-parametrized) guard test so it always collects and runs.
    Outside REQUIRE_CORPUS mode it skips, preserving clean-clone behavior. In
    REQUIRE_CORPUS mode it asserts the pinned baseline assets are present AND that the
    module actually discovered at least one parametrized case — turning a silently
    inert suite into a loud failure.

    ``discovered`` is the module's parametrization source (the file list or the pair
    list); ``kind`` names the gate in failure messages.
    """
    if not REQUIRE_CORPUS:
        pytest.skip("corpus not required (set REQUIRE_CORPUS=1 to enforce completeness)")
    missing = missing_required_corpus()
    assert not missing, (
        f"REQUIRE_CORPUS=1 but pinned baseline assets are missing: {missing}. "
        "Fetch them (fetch_bills.py download ... --format both / "
        "scripts/fetch_test_assets.py) before enforcing this module in strict mode."
    )
    assert len(discovered) > 0, (
        f"REQUIRE_CORPUS=1 but the {kind} gate discovered zero cases under {BILLS_DIR} — "
        "the gate would run green without asserting anything (fail-open, #167)."
    )


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
