"""Shared test helpers and fixtures."""

import functools
import os
import re
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from corpus_paths import FIXTURES_DIR, PROJECT_ROOT, fixture_path, sweep_bill_dirs
from deltatrack.bill_tree import BillNode, BillTree, normalize_bill
from deltatrack.diff_bill import NodeDiff, diff_bills

# --- Committed corpus manifest (#217 / ADR 0015) -------------------------------
# The three corpus correctness gates (test_corpus_properties, test_corpus_tree_
# properties, test_diff_validation) parametrize over the COMMITTED fixture set named
# in tests/corpus_manifest.toml — not a filesystem glob. Every manifested bill lives
# in tests/corpus/ and is tracked in git, so the collected set is byte-identical on
# every machine and in CI; a missing
# fixture fails the per-module completeness floor (fail closed) instead of vanishing
# from an empty glob (fail open). See docs/decisions/0015-corpus-test-fixtures.md.
#
# CORPUS_SWEEP=1 restores the old broad-glob behavior as an opt-in, non-CI exploratory
# mode: it sweeps both trees — the committed fixtures AND every locally-downloaded
# bill under bills/ (a superset of the manifest), which has caught bugs a few clean
# bills did not (#126, #146). It is exploration, not a gate. See corpus_paths.py.
CORPUS_SWEEP = os.environ.get("CORPUS_SWEEP") == "1"
_MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.toml"


@functools.cache
def _manifest_bills() -> tuple[dict, ...]:
    """The [[bill]] entries from corpus_manifest.toml (cached)."""
    return tuple(tomllib.loads(_MANIFEST_PATH.read_text())["bill"])


def manifest_bill_ids() -> list[str]:
    """Every bill id the manifest names (``118-hr-4366``, ...), sorted.

    For gates that key on the bill DIRECTORY rather than individual fixture files — the
    govinfo filename parity gate derives its completeness floor from this, so the floor
    tracks the committed set instead of pinning a count (#342)."""
    return sorted(bill["id"] for bill in _manifest_bills())


def _manifest_paths(fmt: str) -> list[Path]:
    """Committed manifest fixture paths of one format ('xml' | 'pdf'), sorted."""
    return sorted(
        FIXTURES_DIR / bill["id"] / f"{ver['stage']}.{fmt}"
        for bill in _manifest_bills()
        for ver in bill["versions"]
        if fmt in ver["formats"]
    )


def manifest_xml_files() -> list[Path]:
    """XML fixtures the corpus gates parametrize over (manifest, or the full local
    glob under CORPUS_SWEEP)."""
    if CORPUS_SWEEP:
        return sorted(f for d in sweep_bill_dirs() for f in d.glob("[0-9]*_*.xml"))
    return _manifest_paths("xml")


def manifest_pdf_files() -> list[Path]:
    """PDF fixtures the corpus gates parametrize over (manifest, or the full local
    glob under CORPUS_SWEEP)."""
    if CORPUS_SWEEP:
        return sorted(f for d in sweep_bill_dirs() for f in d.glob("[0-9]*_*.pdf"))
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
        for bill_dir in sweep_bill_dirs():
            if bill_dir.is_dir():
                # Scope to the version-file naming (matches manifest_xml_files) so a stray
                # non-bill XML (e.g. govinfo BILLSTATUS metadata) can't enter the diff pairs.
                versions = sorted(bill_dir.glob("[0-9]*_*.xml"), key=_stage_num)
                pairs += [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]
        return pairs
    for bill in _manifest_bills():
        versions = sorted(
            (FIXTURES_DIR / bill["id"] / f"{ver['stage']}.xml" for ver in bill["versions"] if "xml" in ver["formats"]),
            key=_stage_num,
        )
        pairs += [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]
    return pairs


def _git_tracked_paths(repo: Path, subdir: str) -> frozenset[str] | None:
    """POSIX paths (relative to ``repo``) that git tracks under ``subdir``, or ``None``
    if ``repo`` is not a git work tree. One ``git ls-files`` call.

    Split out from ``_tracked_bills`` / ``missing_manifest_files`` so the git query is
    directly unit-testable against a throwaway repo (a floor that has never been shown
    to fire on an untracked-but-present file cannot distinguish "committed" from "the
    check is broken"). ``None`` — a repo with no ``.git`` — is distinct from an empty
    set — a valid repo tracking nothing under ``subdir``: the first means "git cannot
    answer", the second means "git answered: nothing tracked here"."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", subdir],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return frozenset(p for p in out.stdout.split("\0") if p)


@functools.cache
def _tracked_bills() -> frozenset[str] | None:
    """``tests/corpus/…`` paths git tracks (cached), or ``None`` outside a work tree.
    The corpus does not change mid-session, so one ``git ls-files`` serves every gate's
    floor."""
    return _git_tracked_paths(PROJECT_ROOT, "tests/corpus")


def uncommitted_bill_files(rel_paths: Iterable[str]) -> list[str]:
    """Of the given fixture-relative paths (``<id>/<stage>.<fmt>``), those not committed
    to git under ``tests/corpus/``, sorted.

    A fixture counts as committed only if git TRACKS it *and* it is on disk — not merely
    that it exists. Splitting the trees (#308) removed the failure this was written for
    (a forgotten ``bills/`` ``.gitignore`` re-admit line, which made ``git add`` a silent
    no-op), but not the need for the check: a fixture can still be written into
    ``tests/corpus/`` and left unstaged, and a bare ``Path.exists()`` passes on that
    author's machine while a fresh CI checkout quietly collects fewer cases (fail-open).
    Asking git fails on the author's machine, before the push.

    Outside a git work tree (e.g. tests run from an unpacked sdist) git cannot answer, so
    we fall back to the presence check alone — the untracked-fixture failure mode only
    exists inside a working checkout.

    Takes a caller-supplied path list rather than reading the manifest, because two
    different sets need the same committed-ness semantics: the manifest fixtures
    (``missing_manifest_files``) and the bill versions the Legislative Branch validation
    fixture references (#278), which is derived from
    ``test_data/validation_leg_branch.json`` and is not a manifest question. Both sets
    now live under ``tests/corpus/`` (#308)."""
    tracked = _tracked_bills()
    missing = []
    for rel in sorted(set(rel_paths)):
        on_disk = (FIXTURES_DIR / rel).exists()
        is_tracked = tracked is None or f"tests/corpus/{rel}" in tracked
        if not (on_disk and is_tracked):
            missing.append(rel)
    return missing


def missing_manifest_files() -> list[str]:
    """Manifest fixtures (all formats) that are not committed to git. Must be empty.

    Committed-ness semantics (and why git, not ``Path.exists``) are in
    ``uncommitted_bill_files``. Checks the manifest set regardless of CORPUS_SWEEP."""
    return uncommitted_bill_files(
        f"{bill['id']}/{ver['stage']}.{fmt}"
        for bill in _manifest_bills()
        for ver in bill["versions"]
        for fmt in ver["formats"]
    )


def assert_manifest_committed(collected: Sequence, kind: str) -> None:
    """Fail-closed completeness floor for a corpus gate (#217, ADR 0015).

    Called from a plain (non-parametrized) guard test so it always collects and runs —
    with no env var, unlike the retired REQUIRE_CORPUS floor. Fails (not skips) if any
    manifested fixture is not committed to git — missing on disk OR present-but-unstaged
    under tests/corpus/ (#308) — so the gap goes red on the author's machine before the
    push, not silently on a fresh CI checkout that collects fewer cases. ``kind`` names
    the gate in the failure message.
    """
    missing = missing_manifest_files()
    assert not missing, (
        f"{kind}: manifest fixtures not committed to git (missing on disk or untracked): "
        f"{missing}. Every bill in tests/corpus_manifest.toml must live under tests/corpus/ "
        "and be `git add`ed — a fixture present on your disk but untracked passes locally "
        "and then silently skips in CI (#308)."
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
# Scope: the three gates that skip per-case on content, plus
# test_financial_callout_whole_item, whose channel is fixture ABSENCE rather than
# content: its three XML cases carry skipif(not (_V1.exists() and _V2.exists())). That
# skip used to be routine, because v2 was uncommitted; now that both versions are
# committed and manifested, an absent fixture means someone deleted it, and the #86
# headline gate going quiet is exactly what this ceiling exists to catch. It is not a
# manifest-parametrized module, so the #217 fixture floor does not cover it.
#
# The other corpus modules migrated onto the manifest in #220 Part 1
# (test_node_join_corpus, test_xml_subsection_nodes, test_pdf_subsection_recall)
# hard-assert denominators instead of skipping, so they have no content-skip channel to
# watch — they are left out deliberately rather than by oversight. Add one here if it
# ever grows a content-skip.
CORPUS_GATE_MODULES = (
    "tests/test_corpus_properties.py",
    "tests/test_corpus_tree_properties.py",
    "tests/test_diff_validation.py",
    "tests/test_financial_callout_whole_item.py",
)

ALLOWED_CORPUS_SKIPS = {
    # 119-hr-1 v1 is a reconciliation shell: it carries no <appropriations-*> elements
    # with text at all, so the element->node gate has nothing to assert against. A
    # genuine property of the fixture, not a parser gap.
    "tests/test_corpus_properties.py::test_every_appropriations_element_with_text_produces_node"
    "[119-hr-1/1_reported-in-house.xml]": "No appropriations elements with text",
    # 119-hr-1 v2 is the same reconciliation shell one stage on: the file contains zero
    # <appropriations-*> elements of any kind (verified by grep on the committed
    # fixture), so this gate again has nothing to assert. Its money lives in provision
    # body text, which the DOLLAR gate above does cover on this fixture -- v2 is not
    # uncovered, only outside this one gate's channel.
    "tests/test_corpus_properties.py::test_every_appropriations_element_with_text_produces_node"
    "[119-hr-1/2_engrossed-in-house.xml]": "No appropriations elements with text",
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
    # 118-hr-2882 v4 is a 4 KB engrossed Senate amendment that strikes and inserts a
    # short procedural passage: it carries zero <appropriations-*> elements and no
    # dollar amounts (verified on the committed fixture). A genuine property of the
    # document, committed as the v4->v5 base for test_reconcile's Udall-move case.
    "tests/test_corpus_properties.py::test_every_appropriations_element_with_text_produces_node"
    "[118-hr-2882/4_engrossed-amendment-senate.xml]": "No appropriations elements with text",
    "tests/test_corpus_properties.py::test_every_dollar_amount_appears_in_a_node"
    "[118-hr-2882/4_engrossed-amendment-senate.xml]": "No dollar amounts in bill body",
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
    # Named in its own CI step (the packaging gate, #398) rather than the slow-suite step,
    # but the convention keys on being named by SOME CI slow step, not on which one.
    # Deliberately carries NO entry in the allowlist below: its only skip channel is `uv`
    # missing from PATH, and that is not a content gap to declare as normal -- it means the
    # gate did not run, which is exactly what this ceiling exists to redden. Anyone who can
    # run this suite has uv, since `source ./init` is `uv sync`.
    "tests/test_engine_installs.py",
)

ALLOWED_CI_SLOW_SKIPS = {
    # --- Deliberately withheld fixture: a gap kept open on purpose ----------------
    # Not slow-marked, so this one skips in the FAST tier, not the slow step — the reach
    # noted above.
    # 115-hr-244 v5 is an engrossed-amendment-house doc whose appropriations are not
    # surfaced by the corpus gate's body extraction (the #11 amendment-doc class), so
    # committing it would force allowlisting a known-bug skip — declaring a parser gap as
    # documented-normal. Left uncommitted for that reason (#322/#330); this bill_tree case
    # asserts against the fetched copy locally and is declared here. Note the bill's v6
    # (enrolled) IS committed as part of the Leg-Branch validation set (#278) — the
    # withheld fixture is the v5 amendment doc specifically, not the bill.
    "tests/test_bill_tree.py::TestFindBillBody::test_amendment_doc_115_hr_244_v5_produces_nodes": (
        "Bill XML not available locally"
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

# --- Cases CI can never collect ------------------------------------------------
# Every watched module parametrizes over the committed manifest EXCEPT these two, which
# glob bills/ directly (tests/pdf_corpus.py: dual_format_versions, adjacent_pdf_pairs).
# Their case list therefore grows with whatever a machine has fetched: 6 and 30 cases in
# CI, 90 and 432 on a full working checkout.
#
# That breaks the assumption the allowlist rests on. An allowlist calibrated against the
# committed corpus cannot name cases that only exist on one developer's disk, so those
# skips read as undeclared and the session fails — locally red while CI is green, on a
# branch where nothing is wrong. A ceiling that cries wolf on every maintainer's machine
# gets muted, which costs more than the channel it guards.
#
# So for these two modules a case is watched only if the manifest declares every FILE the
# case reads. A case CI cannot collect cannot regress in CI, and there is nothing
# meaningful to declare about it. Cases that ARE manifested stay watched exactly as
# before, so the channel is narrowed to what CI runs, not switched off. This is the same
# reasoning that already exempts CORPUS_SWEEP: a superset sweep is uncalibrated by
# construction.
#
# Format matters, and collapsing it is the trap here. The manifest declares (bill, stage,
# FORMAT), and a stage is often committed in one format only -- 113-hr-3547 v1 is
# pdf-only. The amount-recall gate reads the xml AND the pdf of a stage, so a pdf-only
# stage yields no case in CI even though the manifest names it. Each module therefore
# declares which formats its cases actually need.
_CORPUS_EXPANDING_MODULES = {
    # adjacent_pdf_pairs(): consecutive PDFs within a bill.
    "tests/test_pdf_corpus_smoke.py": ("pdf",),
    # dual_format_versions(): a stage present in BOTH formats.
    "tests/test_pdf_xml_amount_recall.py": ("xml", "pdf"),
}

# The two id shapes these modules generate: "<bill>/<stem>" and, for a pair case,
# "<bill>/<stem>-><stem>" -- the second stem carries no bill prefix, so it is resolved
# against the one most recently seen.
_BILL_STEM = re.compile(r"(\d+-[a-z]+-\d+)/(.+)")
_VERSION_SUFFIX = re.compile(r"\.(xml|pdf)$")


@functools.cache
def _manifest_case_refs() -> frozenset[str]:
    """Every "<bill>/<stage>.<fmt>" the manifest declares, for membership tests."""
    return frozenset(
        f"{bill['id']}/{ver['stage']}.{fmt}"
        for bill in _manifest_bills()
        for ver in bill["versions"]
        for fmt in ver["formats"]
    )


def _referenced_versions(param: str) -> list[tuple[str, str]]:
    """(bill, stem) for each version a parametrize id names, left to right."""
    out: list[tuple[str, str]] = []
    bill = None
    for chunk in param.split("->"):
        match = _BILL_STEM.search(chunk)
        if match:
            bill, stem = match.group(1), match.group(2)
        else:
            stem = chunk
        stem = _VERSION_SUFFIX.sub("", stem.strip())
        if bill and stem:
            out.append((bill, stem))
    return out


def is_watched_case(nodeid: str) -> bool:
    """Whether a skip in a watched module is one CI could also produce.

    True for everything outside the two corpus-expanding modules — those parametrize
    over the manifest, so their case list is identical everywhere and every skip is
    calibrated. Also true when a nodeid carries no recognizable version reference, so an
    id shape this does not understand fails CLOSED (watched) rather than silently
    escaping the ceiling.
    """
    formats = next((f for mod, f in _CORPUS_EXPANDING_MODULES.items() if nodeid.startswith(mod)), None)
    if formats is None:
        return True
    _, _, param = nodeid.partition("[")
    referenced = _referenced_versions(param.rstrip("]"))
    if not referenced:
        return True
    manifested = _manifest_case_refs()
    return all(f"{bill}/{stem}.{fmt}" in manifested for bill, stem in referenced for fmt in formats)


# Populated by pytest_runtest_logreport; read in pytest_sessionfinish.
_observed_corpus_skips: dict[str, str] = {}


def classify_corpus_skips(observed: dict[str, str]) -> dict[str, str]:
    """Corpus-gate skips that are not in the documented allowlist (i.e. failures).

    Matches on nodeid AND reason: an allowlisted case that starts skipping for a
    DIFFERENT reason (e.g. the enrolled PDF stops yielding "no anchors" and starts
    failing to parse) is exactly the regression this gate exists to catch, so it must
    not be waved through just because the nodeid is known.

    Cases the committed corpus cannot produce are ignored (see is_watched_case): they
    exist only on a machine with a fetched corpus, so no allowlist could name them.

    Split out from the hooks so it is directly unit-testable — a ceiling that has
    never been shown to fire cannot distinguish "nothing regressed" from "the check
    is broken".
    """
    unexpected = {}
    for nodeid, reason in observed.items():
        if not is_watched_case(nodeid):
            continue
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


# --- Live-network opt-in (#278) ------------------------------------------------
# REQUIRE_CORPUS used to live here. #220 put every corpus correctness gate on the
# committed manifest and #278 committed the Legislative Branch validation set, so the
# only requirement left that a fixture cannot satisfy is a NETWORK: test_govinfo_corpus
# _parity fetches live BILLSTATUS per bill to confirm the on-disk filenames are still
# what govinfo enumeration produces today. That is a real requirement, so it gets a
# marker that says so rather than an env var whose name described neither consumer.
#
# The marker alone does not deselect: `-m slow` (what CI runs) would select the parity
# gate right along with everything else, so the requirement has to be enforced at
# collection, not by marker expression. `--run-network` opts in; `-m "not network"`
# still deselects outright.
#
# It is kept out of the PR gates deliberately: a pull request should not go red because a
# third-party service is down, and a naming change on govinfo's side is not something a
# contributor's PR caused or can fix. #342 runs it on a weekly schedule instead, over the
# committed fixtures, where a failure is real news rather than a merge blocker.


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests marked `network` (live external fetches). They are skipped by default.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip_network = pytest.mark.skip(reason="needs a live network (run with --run-network)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


# Paths to commonly used bill versions (118-hr-4366).
HR4366_V1_PATH = fixture_path("118-hr-4366", "1_reported-in-house.xml")
HR4366_V4_PATH = fixture_path("118-hr-4366", "4_engrossed-amendment-senate.xml")
HR4366_V5_PATH = fixture_path("118-hr-4366", "5_engrossed-amendment-house.xml")
HR4366_V6_PATH = fixture_path("118-hr-4366", "6_enrolled-bill.xml")

HR4366_V2_PATH = fixture_path("118-hr-4366", "2_engrossed-in-house.xml")

HR5895_V4_PATH = fixture_path("115-hr-5895", "4_engrossed-amendment-senate.xml")
HR5895_V5_PATH = fixture_path("115-hr-5895", "5_enrolled-bill.xml")


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

HR8752_V1_PDF = fixture_path("118-hr-8752", "1_reported-in-house.pdf")
HR8752_V2_PDF = fixture_path("118-hr-8752", "2_engrossed-in-house.pdf")


@pytest.fixture(scope="session")
def hr8752_v1_pages():
    if not HR8752_V1_PDF.exists():
        pytest.skip("HR 8752 v1 PDF not present")
    from tests.pdf_corpus import cached_pages

    return cached_pages(HR8752_V1_PDF)


@pytest.fixture(scope="session")
def hr8752_v2_pages():
    if not HR8752_V2_PDF.exists():
        pytest.skip("HR 8752 v2 PDF not present")
    from tests.pdf_corpus import cached_pages

    return cached_pages(HR8752_V2_PDF)


@pytest.fixture(scope="session")
def hr8752_pdf_diff(hr8752_v1_pages, hr8752_v2_pages):
    from deltatrack.diff_pdf import diff_pdfs

    return diff_pdfs(hr8752_v1_pages, hr8752_v2_pages)


@pytest.fixture
def fast_normalize_diff(monkeypatch, hr4366_v1, hr4366_v2, hr4366_v6, hr4366_v1_v2_diff, hr4366_v1_v6_diff):
    """Monkeypatch diff_bill.normalize_bill and diff_bills to reuse session-cached results
    for the 118-hr-4366 v1/v2/v6 paths used by the CLI tests. Saves ~7s/test."""
    import deltatrack.diff_bill as diff_bill_module

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


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the server's per-IP rate-limit counters (#64) between tests.

    The limiter's in-memory storage hangs off the module-level app, so it
    outlives every TestClient instance and one test's requests would otherwise
    bleed into the next test's budget — the burst test would then pass or fail
    depending on suite order. getattr-guarded so tests that never import the
    server pay nothing."""
    import sys

    limiter = getattr(sys.modules.get("web.app"), "limiter", None)
    if limiter is not None:
        limiter.reset()
    yield


def has_bill_xml() -> bool:
    """Check if real bill XML files are available.

    Matches the corpus version-file naming (`<n>_<stage>.xml`), not any `*.xml`, so a
    directory holding only non-bill XML (e.g. govinfo BILLSTATUS metadata) doesn't
    falsely report the corpus as present.
    """
    return any(f for d in sweep_bill_dirs() for f in d.glob("[0-9]*_*.xml"))


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
