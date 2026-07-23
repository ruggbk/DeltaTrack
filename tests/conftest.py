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


# --- Content-skip ceiling (#220) -----------------------------------------------
# The #217 manifest floor proves fixtures are committed and cases collected, but not
# that any ASSERTION ran. The corpus gates skip per-case on content conditions ("no
# bill body", "no dollar amounts", "no anchors / no offset table"), so a corpus-wide
# parser regression that turned every case into a content-skip would keep CI green
# while asserting nothing — the one structural fail-open left after #217.
#
# This closes that channel: every content-skip in the three corpus gate modules must
# be named in ALLOWED_CORPUS_SKIPS below, AND skip for the reason recorded there. An
# unlisted skip fails the session; so does an allowlisted nodeid that starts skipping
# for a different reason (a bare count, or a nodeid-only match, would miss both — the
# second is precisely a regression on a case already known to be fragile).
#
# Adding an entry is a deliberate act: it records a fixture the gates cannot assert
# on, which is a coverage gap, not a neutral fact. Say why in the comment.
#
# Scope: only the three gates that skip per-case on content. The other corpus modules
# migrated onto the manifest in #220 Part 1 (test_node_join_corpus,
# test_xml_subsection_nodes, test_pdf_subsection_recall) hard-assert denominators
# instead of skipping, so they have no content-skip channel to watch — they are left
# out deliberately rather than by oversight. Add one here if it ever grows a
# content-skip.
CORPUS_GATE_MODULES = (
    "tests/test_corpus_properties.py",
    "tests/test_corpus_tree_properties.py",
    "tests/test_diff_validation.py",
)

ALLOWED_CORPUS_SKIPS = {
    # 119-hr-1 v1 is a reconciliation shell: it carries no <appropriations-*> elements
    # with text at all, so the element->node gate has nothing to assert against. A
    # genuine property of the fixture, not a parser gap.
    "tests/test_corpus_properties.py::test_every_appropriations_element_with_text_produces_node"
    "[119-hr-1/1_reported-in-house.xml]": "No appropriations elements with text",
    # 115-hr-5895 v5 (the ENROLLED print, no GPO margin line numbers) used to live here:
    # its tree comes back empty, so the PDF gate skipped it and this entry recorded why.
    # #262 closed that — the gate now ASSERTS on a zero-anchor document instead of
    # skipping it (_assert_zero_anchor_layout in test_corpus_tree_properties.py), so
    # there is no skip left to allow. The layout reason it used to carry lives in
    # _PDF_NO_ANCHOR_LAYOUTS, next to the assertions that now check it.
    # --- 113-hr-3547 v4 (added to the manifest by #220 Part 1 / #277) -----------
    # 113-hr-3547 v4 is the Senate's FIRST engrossed amendment to what was then a
    # shell bill: a single section extending commercial space-launch liability (2.6 KB,
    # 1 parsed node, no dollar amounts, no appropriations elements). HR 3547 only became
    # the FY2014 omnibus at v5. So both skips are true properties of the document, not
    # a parser gap — and the v4->v5 pair is worth keeping precisely because diffing a
    # one-section shell against a 3 MB omnibus is the amendment-shape extreme.
    "tests/test_corpus_properties.py::test_every_dollar_amount_appears_in_a_node"
    "[113-hr-3547/4_engrossed-amendment-senate.xml]": "No dollar amounts in bill body",
    "tests/test_corpus_properties.py::test_every_appropriations_element_with_text_produces_node"
    "[113-hr-3547/4_engrossed-amendment-senate.xml]": "No appropriations elements with text",
}

# --- The CI slow suite (#288) ---------------------------------------------------
# These @slow modules run against committed fixtures and were named by no CI step, so
# ~95 real assertions passed on any fresh clone in about 20 seconds and never once ran
# in CI. Committing a fixture makes a gate RUNNABLE; only naming its module in the
# workflow makes it RUN — the same distinction #220 called out for the corpus gates.
#
# They are watched here for the same reason the corpus gates are: adding a module to CI
# also adds its skip channel to CI, and a skip asserts nothing. Kept as a SEPARATE
# allowlist from ALLOWED_CORPUS_SKIPS deliberately. Those entries are content
# properties — permanent, correct facts about a fixture. Every entry below is instead a
# fixture this repo does not commit, so each one is a coverage gap that should SHRINK as
# #126 curates the corpus. Merging the two dicts would lose exactly that distinction and
# make the temporary look permanent.
#
# NOTE on blast radius: this tuple is read by pytest_runtest_logreport, which runs in
# EVERY session, not only the slow step that gates these modules. So listing a module
# here also watches its NON-slow cases in the fast run. That is the intended reach (a
# skip asserts nothing wherever it happens), but it means a module's whole skip surface
# has to be declared, not just the part the slow step collects — see the
# test_bill_tree.py entry below, which skips in the fast tier.
CI_SLOW_MODULES = (
    "tests/test_pdf_corpus_smoke.py",
    "tests/test_bill_tree.py",
    "tests/test_structure_tree.py",
    "tests/test_diff_bill.py",
    "tests/test_pdf_compare.py",
    "tests/test_financial_diff.py",
    "tests/test_pipeline_parity.py",
    "tests/test_pdf_xml_amount_recall.py",
    "tests/test_front_matter_parity.py",
    "tests/test_xml_compare.py",
    "tests/test_toc_tree.py",
    "tests/test_format_html.py",
    "tests/test_canonical_tree.py",
    "tests/test_reconcile.py",
    "tests/test_pdf_watermark_recall.py",
    "tests/test_formatters_text_serializer.py",
    "tests/test_validate_extraction.py",
)

ALLOWED_CI_SLOW_SKIPS = {
    # --- Uncommitted fixtures: real coverage gaps, tracked by #126 ---------------
    # Each of these needs a bill version this repo does not commit, so the case cannot
    # assert in CI. Listed (not silently skipped) so the gap is enforced and countable:
    # a NEW skip fails the session, and committing any fixture below should delete its
    # line here. None of these are properties of the documents; they are absences.
    "tests/test_pdf_compare.py::test_compare_api_returns_html": "sample bill PDFs not present (bills/118-hr-4366/)",
    "tests/test_pdf_compare.py::test_compare_pdfs_html_returns_standalone_report": (
        "sample bill PDFs not present (bills/118-hr-4366/)"
    ),
    "tests/test_pdf_compare.py::test_compare_pdfs_returns_valid_canonical": (
        "sample bill PDFs not present (bills/118-hr-4366/)"
    ),
    "tests/test_pipeline_parity.py::test_pipeline_change_parity[115-hr-5895]": "115-hr-5895 v1/v2 not fetched locally",
    "tests/test_pipeline_parity.py::test_pipeline_change_parity[117-hr-4502]": "117-hr-4502 v1/v2 not fetched locally",
    "tests/test_pipeline_parity.py::test_pipeline_change_parity[118-hr-8774]": "118-hr-8774 v1/v2 not fetched locally",
    "tests/test_financial_diff.py::TestCliFinancial::test_financial_flag_filters_output": "Real XML not present",
    "tests/test_financial_diff.py::TestCliFinancial::test_no_financial_flag_no_filtering": "Real XML not present",
    "tests/test_canonical_tree.py::test_pdf_tree_conserves_money_no_overcount_on_real_bill": "sample PDFs absent",
    "tests/test_front_matter_parity.py::test_omnibus_leading_sections_group_under_front_matter": (
        "117-hr-2471 enrolled omnibus not fetched locally"
    ),
    "tests/test_reconcile.py::TestReconcileIntegration::test_udall_sections_moved": (
        "Test XML not found: bills/118-hr-2882/4_engrossed-amendment-senate.xml"
    ),
    "tests/test_structure_tree.py::test_money_conservation_no_overcount_bounded_drops[113-hr-83]": (
        "bill corpus not present (fetch_bills.py)"
    ),
    # Not slow-marked, so this one skips in the FAST tier, not the slow step — the reach
    # noted above. 115-hr-244 is present in a fetched local corpus but not committed, so
    # it is the same kind of gap as the entries around it.
    "tests/test_bill_tree.py::TestFindBillBody::test_amendment_doc_115_hr_244_v5_produces_nodes": (
        "Bill XML not available locally"
    ),
    # The Leg-Branch fixture references five bills this repo does not commit, so the
    # parse floor cannot run. One entry standing for five gaps: the reason enumerates
    # them, so committing ANY of the five changes the message and reddens the session
    # until this line is updated. That is the allowlist working as designed (the gap
    # shrank, so the record of it must change), not a flake — see #126.
    "tests/test_validate_extraction.py::TestLegBranchValidation::test_all_bills_loaded": (
        "5 bill(s) not downloaded: ['113-hr-83', '114-hr-2029', '115-hr-1625', "
        "'115-hr-244', '116-hr-1865']. Run fetch_bills.py download for each (see README)."
    ),
    # --- Environment-gated, not a fixture gap -------------------------------------
    # A third flavour, called out so it is not mistaken for one of the absences above.
    # This floor only asserts under REQUIRE_CORPUS=1 (a fetched corpus + network), which
    # CI deliberately never sets, so it skips on every CI run by construction.
    # Committing fixtures will NOT retire this line; only changing the gate would.
    "tests/test_validate_extraction.py::TestLegBranchValidation::test_fixture_bills_present_when_required": (
        "corpus not required (set REQUIRE_CORPUS=1 to enforce fixture completeness)"
    ),
    # --- Content property, not an absence ----------------------------------------
    # 113-hr-3547 v4 is a one-section shell (see the note in ALLOWED_CORPUS_SKIPS): it
    # genuinely carries no dollar amounts, so there is nothing for the recall case to
    # assert. This one will not go away by committing anything.
    "tests/test_pdf_xml_amount_recall.py::test_xml_amounts_appear_in_pdf"
    "[113-hr-3547/4_engrossed-amendment-senate]": "No amounts in XML (shell / procedural version)",
}

# (label, modules, allowlist) — each group's skips are watched and must be declared.
_SKIP_WATCH_GROUPS = (
    ("corpus content-skip ceiling (#220)", CORPUS_GATE_MODULES, ALLOWED_CORPUS_SKIPS),
    ("CI slow-suite skip ceiling (#288)", CI_SLOW_MODULES, ALLOWED_CI_SLOW_SKIPS),
)

_WATCHED_SKIP_MODULES = CORPUS_GATE_MODULES + CI_SLOW_MODULES

# Populated by pytest_runtest_logreport; read in pytest_sessionfinish.
_observed_corpus_skips: dict[str, str] = {}


def classify_corpus_skips(observed: dict[str, str]) -> dict[str, str]:
    """Corpus-gate skips that are not in the documented allowlist (i.e. failures).

    Matches on nodeid AND reason: an allowlisted case that starts skipping for a
    DIFFERENT reason (e.g. the enrolled PDF stops yielding "no anchors" and starts
    failing to parse) is exactly the regression this gate exists to catch, so it must
    not be waved through just because the nodeid is known.

    Split out from the hooks so it is directly unit-testable — a ceiling that has
    never been shown to fire cannot distinguish "nothing regressed" from "the check
    is broken".
    """
    unexpected = {}
    for nodeid, reason in observed.items():
        for _label, modules, allowed in _SKIP_WATCH_GROUPS:
            if nodeid.startswith(modules):
                if allowed.get(nodeid) != reason:
                    unexpected[nodeid] = reason
                break
    return unexpected


def pytest_runtest_logreport(report) -> None:
    """Record content-skips originating in the corpus gate modules.

    Runs on the xdist controller as well as inline, because xdist re-emits worker
    reports through this hook — so the count aggregates correctly under -n N.
    """
    # xfail is reported as outcome == "skipped" but carries `wasxfail`; it is a tracked
    # known-failure, not a content-skip, so it must not enter the ceiling (else adding a
    # bill to _XFAIL_ZERO_NODES would redden CI on a blank-reason "skip").
    if report.outcome != "skipped" or hasattr(report, "wasxfail"):
        return
    if not report.nodeid.startswith(_WATCHED_SKIP_MODULES):
        return
    reason = ""
    if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
        reason = str(report.longrepr[2]).removeprefix("Skipped: ")
    _observed_corpus_skips[report.nodeid] = reason


def pytest_sessionfinish(session, exitstatus) -> None:
    """Fail the session if any corpus gate content-skipped outside the allowlist."""
    # CORPUS_SWEEP sweeps every locally-fetched bill (a superset of the manifest) as
    # exploration, not a gate; its skips are expected and uncalibrated.
    if CORPUS_SWEEP or hasattr(session.config, "workerinput"):
        return
    # Only escalate a clean run. If the session already failed or was interrupted/
    # aborted, leave its exit code alone — relabeling an INTERRUPTED run as TESTS_FAILED
    # would mask why it actually stopped.
    if exitstatus not in (0, pytest.ExitCode.OK):
        return
    unexpected = classify_corpus_skips(_observed_corpus_skips)
    if not unexpected:
        return
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    reporter.write_sep("=", "undeclared skip ceiling exceeded", red=True, bold=True)
    reporter.write_line(
        f"{len(unexpected)} watched case(s) skipped without being listed in the matching "
        "allowlist (tests/conftest.py). A gate that skips asserts nothing, so this fails "
        "closed rather than passing green:"
    )
    for nodeid, reason in sorted(unexpected.items()):
        group = next((label for label, mods, _ in _SKIP_WATCH_GROUPS if nodeid.startswith(mods)), "?")
        reporter.write_line(f"  {nodeid}\n      reason: {reason}\n      ceiling: {group}")
    reporter.write_line(
        "If this is a regression, fix it. If the case genuinely cannot assert, add it to "
        "ALLOWED_CORPUS_SKIPS (a content property) or ALLOWED_CI_SLOW_SKIPS (an "
        "uncommitted fixture) with a comment saying why."
    )


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
