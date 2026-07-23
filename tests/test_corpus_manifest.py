"""Guards for the committed corpus manifest and its fail-closed floor (#217).

These are fast (non-slow) on purpose, for two reasons:

1. The committed-fixture guarantee is checked on *every* CI run, not only in the
   slow corpus-gate step -- an uncommitted manifest fixture goes red in the fast
   job too, and cheaply.
2. The fail-closed guardrail itself (`assert_manifest_committed` /
   `missing_manifest_files`) gets a regression test. #217 exists to turn a missing
   fixture into a red build; a future refactor that quietly made that helper always
   pass would silently revert the gates to fail-open, and without these tests
   nothing would catch it.
"""

import pytest

from tests import conftest


def test_manifest_parses_and_is_nonempty() -> None:
    """corpus_manifest.toml loads and every entry is well-formed."""
    bills = conftest._manifest_bills()
    assert bills, "corpus_manifest.toml has no [[bill]] entries"
    for b in bills:
        assert b["id"] and b["versions"], f"manifest entry missing id/versions: {b}"
        for v in b["versions"]:
            assert v["stage"] and v["formats"], f"{b['id']} version missing stage/formats"
            for fmt in v["formats"]:
                assert fmt in {"xml", "pdf"}, f"{b['id']}/{v['stage']}: unknown format {fmt!r}"


def test_manifest_helpers_match_declared_counts() -> None:
    """The derived file/pair lists have exactly one entry per declared (bill, version,
    format) in the raw TOML. This is ADR 0015's "count derived from the manifest"
    completeness check, made INDEPENDENT of the collection the gates consume: it counts
    the raw manifest directly and compares against the path-building helpers, so a helper
    that silently dropped or deduped entries (leaving the gates asserting over fewer cases
    than the manifest declares) is caught here rather than passing green. Not slow, and
    unaffected by CORPUS_SWEEP (the env var is not set in the default fast run)."""
    bills = conftest._manifest_bills()
    raw_xml = sum(1 for b in bills for v in b["versions"] if "xml" in v["formats"])
    raw_pdf = sum(1 for b in bills for v in b["versions"] if "pdf" in v["formats"])
    raw_pairs = sum(max(0, sum(1 for v in b["versions"] if "xml" in v["formats"]) - 1) for b in bills)
    assert len(conftest.manifest_xml_files()) == raw_xml
    assert len(conftest.manifest_pdf_files()) == raw_pdf
    assert len(conftest.manifest_version_pairs()) == raw_pairs


def test_real_manifest_fixtures_all_committed() -> None:
    """The fail-closed guarantee in the fast tier: every bill the manifest names is
    present in the checkout. Red here on a fresh CI checkout = an uncommitted fixture
    (the same thing the slow gates' test_manifest_fixtures_committed floor enforces)."""
    assert conftest.missing_manifest_files() == []


_FAKE_MANIFEST = ({"id": "999-hr-9999", "versions": [{"stage": "1_nonexistent", "formats": ["xml"]}]},)


def test_missing_manifest_files_detects_absent(monkeypatch) -> None:
    """missing_manifest_files reports a manifested-but-absent fixture (the fail-closed core)."""
    monkeypatch.setattr(conftest, "_manifest_bills", lambda: _FAKE_MANIFEST)
    assert conftest.missing_manifest_files() == ["999-hr-9999/1_nonexistent.xml"]


def test_assert_manifest_committed_fails_closed_on_absent(monkeypatch) -> None:
    """An absent manifested fixture raises (does not skip) -- the fail-open case #217 closes."""
    monkeypatch.setattr(conftest, "_manifest_bills", lambda: _FAKE_MANIFEST)
    with pytest.raises(AssertionError, match="absent from the checkout"):
        conftest.assert_manifest_committed(["a case"], "unit")


def test_assert_manifest_committed_fails_closed_on_zero_cases(monkeypatch) -> None:
    """Even with all fixtures present, zero collected cases is a fail-open and must raise."""
    monkeypatch.setattr(conftest, "missing_manifest_files", lambda: [])
    with pytest.raises(AssertionError, match="zero cases"):
        conftest.assert_manifest_committed([], "unit")


def _manifest_rel_paths() -> set[str]:
    """Every fixture the manifest declares, as ``<id>/<stage>.<fmt>`` strings."""
    return {
        f"{bill['id']}/{ver['stage']}.{fmt}"
        for bill in conftest._manifest_bills()
        for ver in bill["versions"]
        for fmt in ver["formats"]
    }


def test_migrated_modules_pin_only_manifested_fixtures() -> None:
    """The #220 modules' fail-closed floor calls ``assert_manifest_committed``, which
    checks the manifest GLOBALLY, not the specific files the module pins. That is sound
    only while every pinned fixture is IN the manifest -- otherwise a module could pin a
    fetched-but-unmanifested bill, its floor would stay green (the rest of the manifest
    is present), and the parametrized test would ``FileNotFoundError`` on a clean
    checkout. This test locks the coupling the floor assumes: every fixture the three
    migrated modules pin must be manifested. (Caught by review of #220.)"""
    from tests import test_node_join_corpus as nj
    from tests import test_pdf_subsection_recall as pr

    manifest = _manifest_rel_paths()

    pinned: set[str] = set()
    # node-join: (bill, v1_stem, v2_stem) pairs, XML or PDF by which list they live in.
    for bill, v1, v2 in nj.XML_PAIRS + nj.OMNIBUS_PAIR:
        pinned |= {f"{bill}/{v1}.xml", f"{bill}/{v2}.xml"}
    for bill, v1, v2 in nj._ALL_PDF_PAIRS:
        pinned |= {f"{bill}/{v1}.pdf", f"{bill}/{v2}.pdf"}
    # subsection gates: (bill, pdf_rel, xml_rel), already relative paths.
    for _bill, pdf_rel, xml_rel in pr.FIXTURES:
        pinned |= {pdf_rel, xml_rel}

    unmanifested = sorted(pinned - manifest)
    assert not unmanifested, (
        f"{len(unmanifested)} fixture(s) pinned by a migrated corpus module but NOT in "
        f"tests/corpus_manifest.toml: {unmanifested}. The module's fail-closed floor "
        "checks the manifest globally, so an unmanifested pin fails open (its floor stays "
        "green while the test FileNotFoundErrors on a clean checkout). Add it to the "
        "manifest and .gitignore, or stop pinning it."
    )


# --- Content-skip ceiling (#220) -----------------------------------------------
# Same rationale as the #217 helper tests above: the ceiling exists to turn a
# corpus-wide content-skip regression into a red build, so the classifier itself gets
# a regression test. A refactor that made it always return {} would silently reopen
# the fail-open channel #220 closed, and nothing else would catch it.


def test_classify_corpus_skips_passes_the_documented_allowlist() -> None:
    """Every allowlisted skip is accepted -- the ceiling does not fire on a clean run."""
    assert conftest.classify_corpus_skips(dict(conftest.ALLOWED_CORPUS_SKIPS)) == {}


def test_classify_corpus_skips_flags_an_unlisted_skip() -> None:
    """An unlisted content-skip is reported (the regression case the ceiling exists for)."""
    observed = {"tests/test_corpus_properties.py::test_x[118-hr-4366/1_reported-in-house.xml]": "No bill body found"}
    assert conftest.classify_corpus_skips(observed) == observed


def test_classify_corpus_skips_flags_a_different_case_at_constant_total() -> None:
    """A bare skip COUNT would miss this: one allowlisted case stops skipping while a
    different case starts, leaving the total unchanged. Keying on nodeid catches it."""
    allowed = list(conftest.ALLOWED_CORPUS_SKIPS)
    observed = dict(conftest.ALLOWED_CORPUS_SKIPS)
    observed.pop(allowed[0])
    observed["tests/test_diff_validation.py::test_y[118-hr-4366/1_reported-in-house.xml]"] = "No bill body found"
    assert len(observed) == len(conftest.ALLOWED_CORPUS_SKIPS)
    assert list(conftest.classify_corpus_skips(observed)) == [
        "tests/test_diff_validation.py::test_y[118-hr-4366/1_reported-in-house.xml]"
    ]


def test_classify_corpus_skips_flags_an_allowlisted_nodeid_with_a_new_reason() -> None:
    """The regression that a nodeid-only allowlist would wave through: a case that is
    allowlisted for reason A starts skipping for reason B (e.g. the enrolled PDF stops
    yielding "no anchors" because the parser broke on it). Matching on reason catches
    it; the entry is not a blanket exemption for that nodeid."""
    nodeid, orig_reason = next(iter(conftest.ALLOWED_CORPUS_SKIPS.items()))
    observed = {nodeid: orig_reason + " -- PARSER REGRESSION"}
    assert conftest.classify_corpus_skips(observed) == observed


def test_allowlisted_skips_name_real_corpus_gate_modules() -> None:
    """Each allowlist key targets one of the gate MODULES the hook actually watches.

    This catches a module rename/move that stranded an entry — NOT a test rename or a
    parametrize-id change (those leave the module prefix intact and are not detectable
    here; a stranded such entry silently widens the allowlist until the case it named
    reappears with a new id). A full stale-entry check would require collecting the
    gates, which this fast-tier guard deliberately does not do."""
    for nodeid in conftest.ALLOWED_CORPUS_SKIPS:
        assert nodeid.startswith(conftest.CORPUS_GATE_MODULES), f"stale allowlist entry: {nodeid}"


def test_ci_slow_allowlisted_skips_name_watched_modules() -> None:
    """Same guard for the #288 allowlist: every key targets a watched module.

    A stranded key here fails CLOSED (its real skip becomes undeclared and reddens the
    session), so this is not covering a fail-open channel — it names the cause at the
    point of the rename instead of surfacing it as an unexplained ceiling hit later."""
    for nodeid in conftest.ALLOWED_CI_SLOW_SKIPS:
        assert nodeid.startswith(conftest.CI_SLOW_MODULES), f"stale allowlist entry: {nodeid}"


def test_skip_watch_groups_do_not_overlap() -> None:
    """No module belongs to two watch groups.

    classify_corpus_skips ``break``s on the first group whose prefix matches, so a module
    in both would be judged against one allowlist and silently exempt from the other."""
    seen: set[str] = set()
    for _label, modules, _allowed in conftest._SKIP_WATCH_GROUPS:
        overlap = seen & set(modules)
        assert not overlap, f"module watched by two ceilings: {sorted(overlap)}"
        seen |= set(modules)


# --- End-to-end hook behavior (#220) -------------------------------------------
# The unit tests above cover classify_corpus_skips (a dict comprehension). The parts
# that can fail OPEN — the skipped-outcome/xfail filter, the longrepr extraction, the
# session.exitstatus mutation, xdist aggregation — live in the pytest hooks, which a
# unit test cannot exercise. These run a real child pytest session that re-registers the
# actual hooks (imported from tests.conftest, so a regression in them is caught here) and
# assert on the child's PROCESS EXIT CODE, which is the thing that ultimately reddens CI.

_CHILD_CONFTEST = """
import sys
sys.path.insert(0, {repo!r})
from tests.conftest import pytest_runtest_logreport, pytest_sessionfinish  # noqa: F401
"""


def _run_child_session(tmp_path, test_body: str, *, xdist: bool, module: str = "test_corpus_properties.py"):
    """Write a one-file gate-module test under tmp_path/tests and run a child pytest.

    `module` names the file, which is what puts the nodeid under a watched prefix —
    test_corpus_properties.py for the content-skip ceiling, test_pipeline_parity.py for
    the CI slow-suite ceiling. Runs in a subprocess (fresh _observed_corpus_skips, real
    exit code). Returns the CompletedProcess."""
    import subprocess
    import sys
    from pathlib import Path

    repo = str(Path(conftest.__file__).parent.parent)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_text(_CHILD_CONFTEST.format(repo=repo))
    (tests_dir / module).write_text(test_body)
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    cmd = [sys.executable, "-m", "pytest", "-p", "no:randomly", "-q"]
    if xdist:
        cmd += ["-n", "2"]
    return subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.parametrize("xdist", [False, True], ids=["serial", "xdist"])
def test_ceiling_fails_session_on_unlisted_skip_end_to_end(tmp_path, xdist) -> None:
    """An unlisted content-skip in a gate module fails the child session (exit 1) and
    prints the banner — verified for both serial and xdist, since the xdist controller
    must aggregate a worker's skip for the gate to work at all."""
    body = "import pytest\ndef test_x():\n    pytest.skip('No bill body found')\n"
    r = _run_child_session(tmp_path, body, xdist=xdist)
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "undeclared skip ceiling exceeded" in r.stdout, r.stdout
    assert "corpus content-skip ceiling (#220)" in r.stdout, f"wrong ceiling named\n{r.stdout}"


@pytest.mark.parametrize("xdist", [False, True], ids=["serial", "xdist"])
def test_ci_slow_ceiling_fails_session_on_unlisted_skip_end_to_end(tmp_path, xdist) -> None:
    """The CI slow-suite ceiling (#288) fails the child session on an undeclared skip.

    The modules added to CI bring their skip channels with them, and a skip asserts
    nothing — so this ceiling is what stops the new step being a fresh fail-open surface.
    A ceiling that has never been shown to fire cannot distinguish "nothing regressed"
    from "the check is broken", so it gets the same end-to-end proof as the #220 one,
    including under xdist (the controller must aggregate a worker's skip).
    """
    body = "import pytest\ndef test_x():\n    pytest.skip('118-hr-9999 v1/v2 not fetched locally')\n"
    r = _run_child_session(tmp_path, body, xdist=xdist, module="test_pipeline_parity.py")
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "undeclared skip ceiling exceeded" in r.stdout, r.stdout
    assert "CI slow-suite skip ceiling (#288)" in r.stdout, f"wrong ceiling named\n{r.stdout}"


def test_ci_slow_ceiling_allows_a_declared_skip_end_to_end(tmp_path) -> None:
    """The complement: a skip that IS declared, with its recorded reason, exits 0.

    Without this, the test above would also pass if the ceiling reddened on every skip,
    which would make the allowlist meaningless and the CI step unusable.
    """
    # An UNparametrized entry, so the generated function's nodeid reproduces the key
    # exactly. Picking the first entry blindly would silently break the day a
    # parametrized one sorts first, since `def test_x[a]()` is not valid Python.
    nodeid, reason = next(
        (n, r) for n, r in sorted(conftest.ALLOWED_CI_SLOW_SKIPS.items()) if "[" not in n and "::" in n
    )
    # The nodeid may be module::test OR module::Class::test, and the class segment is
    # part of the key — emitting a bare function for the latter produces a DIFFERENT
    # nodeid, which then reads as an undeclared skip and reddens the child for the wrong
    # reason (i.e. this test would fail while the ceiling was working correctly).
    path, *parts = nodeid.split("::")
    assert len(parts) in (1, 2), f"unhandled nodeid shape: {nodeid}"
    skip = f"pytest.skip({reason!r})"
    if len(parts) == 2:
        cls, func = parts
        body = f"import pytest\n\n\nclass {cls}:\n    def {func}(self):\n        {skip}\n"
    else:
        body = f"import pytest\n\n\ndef {parts[0]}():\n    {skip}\n"
    r = _run_child_session(tmp_path, body, xdist=False, module=path.split("/")[-1])
    assert r.returncode == 0, f"declared skip wrongly reddened the session\n{r.stdout}\n{r.stderr}"


def test_ceiling_ignores_xfail_end_to_end(tmp_path) -> None:
    """pytest.xfail() reports outcome=='skipped' but is a tracked known-failure, not a
    content-skip. The child session must exit 0, not redden on a blank-reason skip."""
    body = "import pytest\ndef test_x():\n    pytest.xfail('Known 0-node issue')\n"
    r = _run_child_session(tmp_path, body, xdist=False)
    assert r.returncode == 0, f"xfail wrongly treated as content-skip\n{r.stdout}\n{r.stderr}"


def test_ceiling_stays_green_on_a_passing_gate_end_to_end(tmp_path) -> None:
    """A gate module with no content-skips does not fire the ceiling (guards against the
    hook reddening a clean run — the false-positive direction)."""
    body = "def test_x():\n    assert True\n"
    r = _run_child_session(tmp_path, body, xdist=False)
    assert r.returncode == 0, f"ceiling fired on a clean gate run\n{r.stdout}\n{r.stderr}"
