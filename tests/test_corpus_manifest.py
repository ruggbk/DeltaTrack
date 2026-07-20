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
