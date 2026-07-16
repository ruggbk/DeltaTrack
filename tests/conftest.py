"""Shared test helpers and fixtures."""

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree, normalize_bill
from diff_bill import NodeDiff, diff_bills

BILLS_DIR = Path(__file__).parent.parent / "bills"

# --- Corpus completeness policy (#167) -----------------------------------------
# The corpus property gates (test_diff_validation, test_corpus_properties,
# test_corpus_tree_properties) parametrize over bill assets that are gitignored and
# fetch-scripted. When an asset is absent the case skips, and pytest emits nothing at
# all for an empty parametrization — so on an unfetched checkout the whole gate runs
# green without executing a single assertion. "Skip" reads as "pass": the fail-open
# pattern. PR #146 merged with a red corpus gate this way (the proof case pinned below).
#
# The deliberate design is that a clean local clone / CI skips the corpus cleanly
# (PRs #62/#64/#66 made the corpus fetch-scripted precisely so it wouldn't be a hard
# dependency). So the policy is NOT "always fail" — it is "never SILENTLY skip where
# completeness is required." REQUIRE_CORPUS=1 opts into the required mode: a pre-PR
# strict run (or CI after running the fetch scripts) sets it, and then a missing
# baseline asset or an empty parametrization is a loud failure instead of a silent skip.
REQUIRE_CORPUS = os.environ.get("REQUIRE_CORPUS") == "1"

# The curated baseline floor: bills whose hand-pinned expectations the corpus gates
# encode (diff-validation class fixtures, _KNOWN_DUPLICATE_COUNTS / _KNOWN_MISSING_APPRO,
# the tree money-drop budgets). In REQUIRE_CORPUS mode every one of these must be on
# disk, else the gate that pins it against a hardcoded baseline skips silently. Paths
# are relative to BILLS_DIR. Not the whole CI corpus (curation is #126) — just the floor
# below which the regression harness is provably inert.
REQUIRED_CORPUS_BILLS = (
    # 118-hr-4366: TestControlledDiff (v1->v2) and TestStructureExpansion (v1->v6).
    "118-hr-4366/1_reported-in-house.xml",
    "118-hr-4366/2_engrossed-in-house.xml",
    "118-hr-4366/4_engrossed-amendment-senate.xml",
    "118-hr-4366/5_engrossed-amendment-house.xml",
    "118-hr-4366/6_enrolled-bill.xml",
    # 115-hr-5895: TestDeadZoneBaseline (v4->v5), the corpus's densest dead-zone case.
    "115-hr-5895/4_engrossed-amendment-senate.xml",
    "115-hr-5895/5_enrolled-bill.xml",
    # 113-hr-3547 enrolled: the #146/#167 proof case (duplicate match_path count).
    "113-hr-3547/6_enrolled-bill.xml",
    # 119-hr-1 reported: the twin-Sec.-10012 collision baseline (#8).
    "119-hr-1/1_reported-in-house.xml",
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
        "Fetch the corpus (fetch_bills.py download ... --format both / "
        "scripts/fetch_test_assets.py) before enforcing the corpus gates."
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
