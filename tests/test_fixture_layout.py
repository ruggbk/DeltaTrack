"""The fixture-layout invariants the two-tree split rests on (#308).

Splitting committed fixtures (``tests/corpus/``) from the downloaded working corpus
(``bills/``) removed the ``.gitignore`` re-admit list, and with it the failure that list
caused. It also created three new ways to be quietly wrong, none of which any existing
gate would notice, because each fails by making a test *read the wrong tree* rather than
by raising:

1. **A stale ``bills/<id>`` path for a committed fixture.** It resolves on a developer
   machine that has downloaded that bill, and is simply absent in CI — where the test
   skips (most of these guards are skip-if-absent) and the run stays green.
2. **A sweep that no longer spans both trees.** ``CORPUS_SWEEP=1`` is exploratory, so
   nothing asserts its case count; narrowing it to one tree loses coverage silently.
3. **A fixture written into ``tests/corpus/`` but never staged.** The manifest floor
   catches manifested bills; the golden modules pin files the manifest does not name.

Each test below therefore also proves it can fire, against a synthetic bad input — a
layout gate that has never once gone red cannot distinguish "the layout is right" from
"the check is broken".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from corpus_paths import DOWNLOADS_DIR, FIXTURES_DIR, PROJECT_ROOT, sweep_bill_dirs
from tests.conftest import _git_tracked_paths

# Modules that legitimately name ``bills/``: they are about the DOWNLOAD tier itself
# (the fetchers and their tests, the live parity gate) or they pin a bill nobody has
# committed. Each entry is a deliberate exception, not a waiver — see the comment.
_DOWNLOAD_TIER_FILES = {
    # The fetchers: bills/ is their output directory, which is the point.
    "fetch_bills.py",
    "fetch_bill_archives.py",
    "fetch_bill_text_archives.py",
    "tests/test_fetch_bills.py",
    "tests/test_fetch_bill_archives.py",
    "tests/test_fetch_bill_archives_extract.py",
    "tests/test_fetch_bill_text_archives.py",
    "tests/test_fetch_govinfo.py",
    # Live-network gate over whatever is downloaded locally.
    "tests/test_govinfo_corpus_parity.py",
    # This file: the patterns below are the thing under test.
    "tests/test_fixture_layout.py",
}

# Bill ids referenced from tests but deliberately NOT committed. A path under bills/ is
# correct for these; the tests that use them skip when the bill is not downloaded.
# Keep the reason with the id — an entry here records a gate that cannot run in CI.
_DOWNLOAD_ONLY_BILLS = {
    # Amendment-doc class whose appropriations tags the body extraction does not surface
    # (#11). Withheld rather than allowlisted as a content-skip, per #330.
    "115-hr-244",
    # Cross-bill recall probes over large omnibus prints; too big to commit for the value.
    "116-hr-133",
    "117-hr-4432",
    "118-hr-4820",
}

# Both spellings of "reach into the download tree for this bill": the literal path, and
# the constant. The second matters more now — DOWNLOADS_DIR is the form a contributor
# will reach for, and it reads as deliberate even when it is a mistake.
_BILLS_PATH_RES = (
    re.compile(r"""bills/(\d{3}-[a-z]+-\d+)"""),
    re.compile(r"""DOWNLOADS_DIR\s*/\s*["'](\d{3}-[a-z]+-\d+)["']"""),
)


def _python_sources() -> list[Path]:
    roots = [PROJECT_ROOT / "tests", PROJECT_ROOT / "scripts"]
    files = [f for r in roots for f in r.rglob("*.py")]
    files += sorted(PROJECT_ROOT.glob("*.py"))
    return files


def find_stale_fixture_paths(sources: dict[str, str], download_only: set[str]) -> dict[str, list[str]]:
    """``{relative path: [offending bill ids]}`` for sources that reach into ``bills/``
    for a bill that is not download-only.

    Takes its input as a dict so the rule is testable on synthetic sources rather than
    only on the tree it polices.
    """
    offenders: dict[str, list[str]] = {}
    for rel, text in sources.items():
        if rel in _DOWNLOAD_TIER_FILES:
            continue
        found = {m for rx in _BILLS_PATH_RES for m in rx.findall(text)}
        bad = sorted(m for m in found if m not in download_only)
        if bad:
            offenders[rel] = bad
    return offenders


def test_no_source_reaches_into_bills_for_a_committed_fixture() -> None:
    """Failure mode 1: a committed fixture addressed through the download tree.

    ``bills/`` is disposable scratch that CI never populates, so such a path resolves
    only where someone has downloaded that bill. The test then skips in CI and the run
    reports green — the exact fail-open shape ADR 0015 exists to remove.
    """
    sources = {str(f.relative_to(PROJECT_ROOT)): f.read_text() for f in _python_sources()}
    offenders = find_stale_fixture_paths(sources, _DOWNLOAD_ONLY_BILLS)
    assert not offenders, (
        f"{len(offenders)} source file(s) address a bill through bills/ that is not "
        f"download-only: {offenders}. Committed fixtures live in tests/corpus/ — use "
        "corpus_paths.fixture_path(). If the bill genuinely is not committed, add its id "
        "to _DOWNLOAD_ONLY_BILLS here with the reason it stays downloaded."
    )


def test_stale_fixture_path_rule_can_fire() -> None:
    """The rule above, proven against a known-bad source (and a known-good one)."""
    bad = {"tests/test_thing.py": 'X = Path("bills/118-hr-4366/1_reported-in-house.xml")'}
    assert find_stale_fixture_paths(bad, _DOWNLOAD_ONLY_BILLS) == {"tests/test_thing.py": ["118-hr-4366"]}

    good = {"tests/test_thing.py": 'X = fixture_path("118-hr-4366", "1_reported-in-house.xml")'}
    assert find_stale_fixture_paths(good, _DOWNLOAD_ONLY_BILLS) == {}

    # A download-only bill under bills/ is correct, not an offence.
    allowed = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / "115-hr-244" / "5_engrossed-amendment-house.xml"'}
    assert find_stale_fixture_paths(allowed, _DOWNLOAD_ONLY_BILLS) == {}

    # ...but the same constant pointed at a COMMITTED bill is caught, which the literal
    # path pattern alone would miss.
    via_const = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / "118-hr-4366" / "6_enrolled-bill.xml"'}
    assert find_stale_fixture_paths(via_const, _DOWNLOAD_ONLY_BILLS) == {"tests/test_thing.py": ["118-hr-4366"]}

    # An exempt module may name bills/ freely.
    exempt = {"fetch_bills.py": 'default = Path("bills/118-hr-4366")'}
    assert find_stale_fixture_paths(exempt, _DOWNLOAD_ONLY_BILLS) == {}


def test_sweep_spans_both_trees() -> None:
    """Failure mode 2: ``CORPUS_SWEEP=1`` narrowed to one tree.

    Nothing asserts the sweep's case count (it is exploration, not a gate), so dropping
    the committed fixtures from it would go unnoticed. Every fixture bill must appear.
    """
    swept = {d.name for d in sweep_bill_dirs()}
    fixtures = {d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()}
    assert fixtures, "precondition: tests/corpus/ holds bill directories"
    assert fixtures <= swept, f"sweep dropped committed fixture bills: {sorted(fixtures - swept)}"


def test_sweep_prefers_the_committed_copy(tmp_path, monkeypatch) -> None:
    """A downloaded copy of a fixture bill must not shadow the committed bytes, and the
    bill must appear once, not twice. Proven on a synthetic pair of trees."""
    fixtures, downloads = tmp_path / "corpus", tmp_path / "bills"
    (fixtures / "118-hr-4366").mkdir(parents=True)
    (downloads / "118-hr-4366").mkdir(parents=True)
    (downloads / "999-hr-9").mkdir(parents=True)
    monkeypatch.setattr("corpus_paths.FIXTURES_DIR", fixtures)
    monkeypatch.setattr("corpus_paths.DOWNLOADS_DIR", downloads)

    swept = sweep_bill_dirs()
    assert [d.name for d in swept] == ["118-hr-4366", "999-hr-9"], "one entry per bill id"
    assert swept[0].parent == fixtures, "the committed copy wins over the downloaded one"


def test_every_fixture_file_is_tracked_by_git() -> None:
    """Failure mode 3: a fixture written into tests/corpus/ but never staged.

    The manifest floor covers manifested bills; the golden modules pin files the manifest
    does not name (ADR 0015 keeps it bill-layout only), so those would otherwise have no
    committed-ness check at all.
    """
    tracked = _git_tracked_paths(PROJECT_ROOT, "tests/corpus")
    if tracked is None:
        pytest.skip("not a git work tree — git cannot answer whether fixtures are tracked")
    on_disk = {str(f.relative_to(PROJECT_ROOT)) for f in FIXTURES_DIR.rglob("*") if f.is_file()}
    untracked = sorted(on_disk - tracked)
    assert not untracked, (
        f"{len(untracked)} file(s) under tests/corpus/ are not tracked by git: {untracked}. "
        "A fixture that is not staged passes locally and is simply absent in CI."
    )


def test_fixture_tree_is_not_gitignored() -> None:
    """The split is only real while git actually stores the fixture tree.

    A future ignore rule (a broad ``*.pdf``, a stray ``corpus`` entry) would put the
    project straight back into the silent-``git add`` failure #308 removed. Ask git
    rather than parsing .gitignore, and confirm the probe can fire by checking a path
    that IS ignored.
    """
    probe = FIXTURES_DIR / "118-hr-4366" / "1_reported-in-house.xml"
    assert probe.exists(), "precondition: the probed fixture exists"
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", str(probe)],
        capture_output=True,
    )
    assert result.returncode == 1, f"{probe} is gitignored — committed fixtures must be storable"

    ignored = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", str(DOWNLOADS_DIR / "118-hr-4366" / "x.xml")],
        capture_output=True,
    )
    assert ignored.returncode == 0, "probe is broken: bills/ should be ignored, so a real result is meaningful"
