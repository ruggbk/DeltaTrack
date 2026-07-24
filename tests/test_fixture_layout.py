"""The fixture-layout invariants the two-tree split rests on (#308).

Splitting committed fixtures (``tests/corpus/``) from the downloaded working corpus
(``bills/``) removed the ``.gitignore`` re-admit list, and with it the failure that list
caused. It also created three new ways to be quietly wrong, none of which any existing
gate would notice, because each fails by making a test *read the wrong tree* rather than
by raising:

1. **A stale ``bills/<id>`` path for a committed fixture.** It resolves on a developer
   machine that has downloaded that bill, and is simply absent in CI — where the test
   skips (most of these guards are skip-if-absent) and the run stays green. This comes
   in two spellings, and the second is the one that bites: the bill id beside the word
   ``bills``, and a download ROOT bound once and composed with a bill id far away
   (``_BILLS = _ROOT / "bills"``). Only the first is greppable per bill, so each has its
   own rule.
2. **A sweep that no longer spans both trees.** ``CORPUS_SWEEP=1`` is exploratory, so
   nothing asserts its case count; narrowing it to one tree loses coverage silently.
3. **A fixture written into ``tests/corpus/`` but never staged.** The manifest floor
   catches manifested bills; the golden modules pin files the manifest does not name.

The judgement throughout is per VERSION, not per bill: a bill is routinely committed for
the stages a gate pins and download-only for the rest, so a bill-level waiver silently
waives its committed siblings too.

Each rule below also proves it can fire, against a synthetic bad input — a layout gate
that has never once gone red cannot distinguish "the layout is right" from "the check is
broken". ``test_every_fixture_file_is_tracked_by_git`` is the exception: its fault has to
be injected on disk (an unstaged file), so it is verified by hand rather than in-process.
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

_BILL_ID = r"\d{3}-[a-z]+-\d+"

# "Reach into the download tree for THIS bill", where the bill is spelled out beside the
# path. The filename is captured when present, because the question is per-VERSION (see
# committed_fixture_refs).
#
# The broader rule below already rejects every DOWNLOADS_DIR use outside corpus_paths.py,
# so these two patterns are not the last line of defence. They stay because they can name
# the offending fixture in the failure message — "115-hr-244/6_enrolled-bill.xml is
# committed" is a far more actionable error than "you named the download tree".
_BILLS_PATH_RES = (
    re.compile(rf"""bills/({_BILL_ID})(?:/([\w.\-]+))?"""),
    re.compile(rf"""DOWNLOADS_DIR\s*/\s*["']({_BILL_ID})["'](?:\s*/\s*["']([\w.\-]+)["'])?"""),
)

# Naming the download tree at all, rather than a specific bill under it. The patterns
# above need the bill id spelled as a literal right beside the path, which the most
# idiomatic forms in a per-bill parametrized suite do not do:
#
#     DOWNLOADS_DIR / bill / "1_reported-in-house.xml"   # id in a variable
#     DOWNLOADS_DIR / "118-hr-4366/1_reported-in-house.xml"   # id and file in one string
#     Path(f"bills/{bill}/1_reported-in-house.xml")      # interpolated
#     os.path.join("bills", bill, stem)                  # no / operator
#     _BILLS = _ROOT / "bills"                           # root bound once, used far away
#
# The last is how scripts/build_similarity_labels.py came through the #308 move still
# pointing at the download tree and stopped resolving. So the rule is the policy itself:
# outside corpus_paths.py and the fetchers, no module names the download tree — it goes
# through fixture_path() (committed) or resolve_bill_file() (mixed per version).
#
# Deliberately NOT "any 'bills' string literal": that flags a JSON key (``{"bills": []}``
# in tests/test_shared_http.py) and the legitimate download-only paths in
# tests/smoke_test_matching.py and tests/test_pdf_anchor_golden.py, which name bills
# nobody has committed. Each pattern below is narrower than that and currently flags
# nothing in the tree.
_DOWNLOAD_TREE_NAME_RES = (
    # The constant itself, in any composition. No non-exempt module uses it today, and
    # both sanctioned helpers cover the legitimate cases, so this costs nothing.
    re.compile(r"\bDOWNLOADS_DIR\b"),
    # The directory name as a path segment: Path("bills"), x / "bills", join("bills", …).
    re.compile(r"""(?:Path\(\s*["']bills["']\s*\)|/\s*["']bills["']|join\(\s*["']bills["'])"""),
    # A "bills/…" literal whose bill id is interpolated or concatenated in.
    re.compile(r"""["']bills/(?:\{|%|['"]\s*[+%])"""),
)


def committed_fixture_refs() -> set[str]:
    """``"<bill id>/<filename>"`` for every file committed under ``tests/corpus/``.

    Derived from the tree rather than from a hand-kept exemption list. An id-granular
    list cannot express the real shape of the corpus, where a bill is routinely committed
    for the stages a gate pins and download-only for the rest (``115-hr-244`` is
    manifested for its enrolled text while its engrossed-amendment doc is deliberately
    withheld, #11/#322) — so an id-level waiver for that bill silently waives its
    committed fixture too, which is failure mode 1 exactly.
    """
    if not FIXTURES_DIR.is_dir():
        return set()
    return {f"{f.parent.name}/{f.name}" for f in FIXTURES_DIR.rglob("*") if f.is_file()}


def _python_sources() -> list[Path]:
    """Every module the rules police.

    Beyond ``tests/`` and ``scripts/``, the package directories are included even though
    they hold no bill paths today: a helper imported *by* a test is exactly where a stale
    path would hide from a scan limited to test files. ``docs/research/`` is deliberately
    out — those probes are download-tier scratch, like the fetchers.
    """
    roots = [PROJECT_ROOT / d for d in ("tests", "scripts", "parsers", "formatters", "shared", "server", "bill_index")]
    files = [f for r in roots if r.is_dir() for f in r.rglob("*.py")]
    files += sorted(PROJECT_ROOT.glob("*.py"))
    return files


def find_stale_fixture_paths(sources: dict[str, str], committed: set[str]) -> dict[str, list[str]]:
    """``{relative path: [offending "<id>/<file>" refs]}`` for sources that address a
    COMMITTED fixture through ``bills/``.

    ``committed`` is the set :func:`committed_fixture_refs` returns. The judgement is
    per version, not per bill: ``bills/115-hr-244/5_engrossed-amendment-house.xml`` is
    correct (that doc is deliberately withheld) while
    ``bills/115-hr-244/6_enrolled-bill.xml`` is an offence (that one is committed).

    A reference naming a bill but no file is ambiguous, so it fails CLOSED whenever the
    bill has any committed file at all.

    Lines mentioning ``tmp_path`` are skipped, as in :func:`find_download_tree_names`: a
    synthetic tree built under a temp dir is not the real download directory, and a test
    is entitled to name a real bill id inside one.

    Takes its input as a dict so the rule is testable on synthetic sources rather than
    only on the tree it polices.
    """
    committed_ids = {ref.split("/", 1)[0] for ref in committed}
    offenders: dict[str, list[str]] = {}
    for rel, text in sources.items():
        if rel in _DOWNLOAD_TIER_FILES:
            continue
        bad: set[str] = set()
        for line in text.splitlines():
            if "tmp_path" in line:
                continue
            for rx in _BILLS_PATH_RES:
                for bill, filename in rx.findall(line):
                    if filename:
                        if f"{bill}/{filename}" in committed:
                            bad.add(f"{bill}/{filename}")
                    elif bill in committed_ids:
                        bad.add(bill)
        if bad:
            offenders[rel] = sorted(bad)
    return offenders


def find_download_tree_names(sources: dict[str, str]) -> dict[str, list[int]]:
    """``{relative path: [line numbers]}`` for sources that name the download tree.

    Catches every composition the per-bill patterns structurally cannot see, because the
    bill id is not spelled as a literal beside the path::

        _BILLS = _ROOT / "bills"
        normalize_bill(_BILLS / bill / version)   # ...300 lines later

    That is not hypothetical: it is how ``scripts/build_similarity_labels.py`` came
    through the #308 move still pointing at the download tree, raising FileNotFoundError
    on four bills that had just become committed fixtures. ``corpus_paths`` is the one
    home for these names, so everything outside it imports rather than respells.

    Lines mentioning ``tmp_path`` are skipped: a synthetic ``tmp_path / "bills"`` tree in
    a test is not the real directory.
    """
    offenders: dict[str, list[int]] = {}
    for rel, text in sources.items():
        if rel in _DOWNLOAD_TIER_FILES or rel == "corpus_paths.py":
            continue
        lines = [
            n
            for n, line in enumerate(text.splitlines(), 1)
            if any(rx.search(line) for rx in _DOWNLOAD_TREE_NAME_RES) and "tmp_path" not in line
        ]
        if lines:
            offenders[rel] = lines
    return offenders


def test_no_source_reaches_into_bills_for_a_committed_fixture() -> None:
    """Failure mode 1: a committed fixture addressed through the download tree.

    ``bills/`` is disposable scratch that CI never populates, so such a path resolves
    only where someone has downloaded that bill. The test then skips in CI and the run
    reports green — the exact fail-open shape ADR 0015 exists to remove.
    """
    sources = {str(f.relative_to(PROJECT_ROOT)): f.read_text() for f in _python_sources()}
    offenders = find_stale_fixture_paths(sources, committed_fixture_refs())
    assert not offenders, (
        f"{len(offenders)} source file(s) address a COMMITTED fixture through bills/: "
        f"{offenders}. Committed fixtures live in tests/corpus/ — use "
        "corpus_paths.fixture_path(). For a version that genuinely is not committed, "
        "bills/ is correct, or use corpus_paths.resolve_bill_file()."
    )


def test_no_source_names_the_download_tree() -> None:
    """Every composed form of failure mode 1, which the per-bill patterns cannot see."""
    sources = {str(f.relative_to(PROJECT_ROOT)): f.read_text() for f in _python_sources()}
    offenders = find_download_tree_names(sources)
    assert not offenders, (
        f"{len(offenders)} source file(s) name the download tree: {offenders}. Reach a "
        "committed fixture with corpus_paths.fixture_path(), a per-version mix with "
        "resolve_bill_file(), and both trees with sweep_bill_dirs(). Composing the path "
        "yourself puts the bill id out of this guard's sight (#345)."
    )


def test_stale_fixture_path_rule_can_fire() -> None:
    """The rule above, proven against known-bad sources (and known-good ones)."""
    committed = {"118-hr-4366/1_reported-in-house.xml", "115-hr-244/6_enrolled-bill.xml"}

    bad = {"tests/test_thing.py": 'X = Path("bills/118-hr-4366/1_reported-in-house.xml")'}
    expect = {"tests/test_thing.py": ["118-hr-4366/1_reported-in-house.xml"]}
    assert find_stale_fixture_paths(bad, committed) == expect

    good = {"tests/test_thing.py": 'X = fixture_path("118-hr-4366", "1_reported-in-house.xml")'}
    assert find_stale_fixture_paths(good, committed) == {}

    # A download-only VERSION under bills/ is correct, even though its bill is committed
    # for another stage. The id-granular rule this replaced could not express that, and
    # waived the committed sibling along with it.
    allowed = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / "115-hr-244" / "5_engrossed-amendment-house.xml"'}
    assert find_stale_fixture_paths(allowed, committed) == {}

    # ...while the COMMITTED version of that same bill is caught.
    sibling = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / "115-hr-244" / "6_enrolled-bill.xml"'}
    assert find_stale_fixture_paths(sibling, committed) == {"tests/test_thing.py": ["115-hr-244/6_enrolled-bill.xml"]}

    # A bare bill directory is ambiguous, so it fails closed when anything is committed.
    bare = {"tests/test_thing.py": 'X = Path("bills/118-hr-4366")'}
    assert find_stale_fixture_paths(bare, committed) == {"tests/test_thing.py": ["118-hr-4366"]}

    # A bill with nothing committed is free to live under bills/.
    uncommitted = {"tests/test_thing.py": 'X = Path("bills/116-hr-133/1_introduced-in-house.xml")'}
    assert find_stale_fixture_paths(uncommitted, committed) == {}

    # An exempt module may name bills/ freely.
    exempt = {"fetch_bills.py": 'default = Path("bills/118-hr-4366")'}
    assert find_stale_fixture_paths(exempt, committed) == {}

    # A synthetic tree under a temp dir may name a real committed bill: it is not the
    # download directory. (This rule used to scan whole-file, so the tmp_path exemption
    # that find_download_tree_names had did not apply here — #345 review.)
    synthetic = {"tests/test_thing.py": 'p = tmp_path / "bills/118-hr-4366/1_reported-in-house.xml"'}
    assert find_stale_fixture_paths(synthetic, committed) == {}


def test_download_tree_name_rule_can_fire() -> None:
    """The rule proven on every bypass an adversarial review of #345 demonstrated.

    Each of these reached a committed fixture through the download tree while the
    per-bill patterns stayed green, so each is a regression test for a real hole.
    """
    # The shape that actually shipped broken (scripts/build_similarity_labels.py).
    composed = {"scripts/thing.py": '_BILLS = _ROOT / "bills"\nX = _BILLS / bill / version'}
    assert find_download_tree_names(composed) == {"scripts/thing.py": [1]}

    glob_form = {"scripts/thing.py": 'for x in (repo / "bills").glob("*/*.xml"):\n    pass'}
    assert find_download_tree_names(glob_form) == {"scripts/thing.py": [1]}

    bare_path = {"scripts/thing.py": 'D = Path("bills")'}
    assert find_download_tree_names(bare_path) == {"scripts/thing.py": [1]}

    # Bill id in a variable — the most idiomatic form in a parametrized suite, and the
    # one the DOWNLOADS_DIR pattern missed because it demands a quoted literal id.
    via_var = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / bill / "1_reported-in-house.xml"'}
    assert find_download_tree_names(via_var) == {"tests/test_thing.py": [1]}

    # Id and filename in one string, so the id is not followed by a closing quote.
    one_string = {"tests/test_thing.py": 'X = DOWNLOADS_DIR / "118-hr-4366/1_reported-in-house.xml"'}
    assert find_download_tree_names(one_string) == {"tests/test_thing.py": [1]}

    # An import alias defeats a name-based regex on the use site, but not on the import.
    aliased = {"tests/test_thing.py": "from corpus_paths import DOWNLOADS_DIR as DL\nX = DL / bill"}
    assert find_download_tree_names(aliased) == {"tests/test_thing.py": [1]}

    interpolated = {"tests/test_thing.py": 'X = Path(f"bills/{bill}/1_reported-in-house.xml")'}
    assert find_download_tree_names(interpolated) == {"tests/test_thing.py": [1]}

    joined = {"tests/test_thing.py": 'X = os.path.join("bills", bill, stem)'}
    assert find_download_tree_names(joined) == {"tests/test_thing.py": [1]}

    # A synthetic tree in a temp dir is not the real download directory.
    synthetic = {"tests/test_thing.py": 'downloads = tmp_path / "bills"'}
    assert find_download_tree_names(synthetic) == {}

    # The sanctioned doors.
    for src in (
        'X = fixture_path("118-hr-4366", "1_reported-in-house.xml")',
        'X = resolve_bill_file("115-hr-5895", "3_placed-on-calendar-senate.pdf")',
        "for d in sweep_bill_dirs():\n    pass",
    ):
        assert find_download_tree_names({"tests/test_thing.py": src}) == {}

    # Not flagged: a JSON key, and download-only bills named as plain literals — the
    # shapes a blunter "any 'bills' literal" rule would have broken (real code, #345).
    for src in (
        'resp = httpx.Response(200, json={"bills": []})',
        '    "bills/116-hr-133",  # Consolidated Appropriations Act, 2021',
        '        ("117-hr-4432", "bills/117-hr-4432", None),',
    ):
        assert find_download_tree_names({"tests/test_thing.py": src}) == {}

    # corpus_paths.py itself defines them, and the fetchers own the directory.
    assert find_download_tree_names({"corpus_paths.py": 'DOWNLOADS_DIR = PROJECT_ROOT / "bills"'}) == {}
    assert find_download_tree_names({"fetch_bills.py": 'default=Path("bills")'}) == {}


def test_download_only_versions_are_genuinely_uncommitted() -> None:
    """The rule's own input, checked: every ``bills/`` reference the guard tolerates must
    name a version that really is absent from ``tests/corpus/``.

    Without this, the guard could be satisfied by a committed set that quietly shrank.
    """
    sources = {str(f.relative_to(PROJECT_ROOT)): f.read_text() for f in _python_sources()}
    committed = committed_fixture_refs()
    tolerated: set[str] = set()
    for rel, text in sources.items():
        if rel in _DOWNLOAD_TIER_FILES:
            continue
        for rx in _BILLS_PATH_RES:
            for bill, filename in rx.findall(text):
                if filename:
                    tolerated.add(f"{bill}/{filename}")
    still_committed = sorted(ref for ref in tolerated if ref in committed)
    assert not still_committed, f"tolerated bills/ refs that ARE committed: {still_committed}"


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

    # git check-ignore answers 0 (ignored) / 1 (not ignored), but 128 for "not a git
    # work tree" — which tests run from an unpacked sdist would hit. That is git
    # declining to answer, not a verdict, so skip as the tracking gate above does
    # rather than reporting a layout failure the checkout cannot possibly have.
    ignored = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", str(DOWNLOADS_DIR / "118-hr-4366" / "x.xml")],
        capture_output=True,
    )
    if ignored.returncode not in (0, 1):
        pytest.skip("not a git work tree — git cannot answer whether a path is ignored")
    assert ignored.returncode == 0, "probe is broken: bills/ should be ignored, so a real result is meaningful"

    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", str(probe)],
        capture_output=True,
    )
    assert result.returncode == 1, f"{probe} is gitignored — committed fixtures must be storable"
