"""Drift guard: content-skip allowlist entries must key on live manifest fixtures (#281).

The content-skip ceiling (#220) allowlists individual corpus-gate cases in
``ALLOWED_CORPUS_SKIPS`` (tests/conftest.py). Each key is a full pytest node id whose
parametrize id — e.g. ``[119-hr-1/1_reported-in-house.xml]`` — is generated from the
committed manifest (tests/corpus_manifest.toml, via ``_xml_id``/``_corpus_id`` =
``<bill>/<stage>.<fmt>``). The same fact ("this fixture version cannot be asserted on")
is therefore spelled out in two files that must agree, and they can drift apart
silently: a fixture that leaves the manifest, or a version renamed, strands an
allowlist entry that quietly widens what the ceiling permits until the case it named
reappears under a new id.

``test_allowlisted_skips_name_real_corpus_gate_modules`` (test_corpus_manifest.py) only
checks the MODULE prefix of each key — by its own docstring it cannot see a
parametrize-id change or a fixture that left the manifest. This guard closes exactly
that gap: every allowlist key that carries a manifest-shaped fixture id must reference a
fixture the manifest still declares, or the entry is flagged as stale by name.

Scope: only entries whose parametrize id is a manifest fixture reference
(``<bill>/<stage>.<fmt>``) are manifest-validated. Gate cases that are not parametrized
over a manifest fixture — the class-based ``test_diff_validation`` gates, the plain
``skipif`` functions in ``test_financial_callout_whole_item`` — have no manifest
coupling to drift, so they are left to the module-prefix guard and the runtime ceiling.

Same rationale as the ceiling's own regression tests: a drift guard that has never been
shown to fire cannot distinguish "nothing drifted" from "the check is broken", so the
guard is a directly-unit-testable function proven to fire on a stranded entry.
"""

from tests import conftest


def manifest_fixture_ids() -> set[str]:
    """Every fixture the manifest declares, as ``<bill>/<stage>.<fmt>`` — the exact form
    the corpus gates use as their parametrize id (``_xml_id``/``_corpus_id``), so it is
    directly comparable to the fixture id embedded in an allowlist key."""
    return {
        f"{bill['id']}/{ver['stage']}.{fmt}"
        for bill in conftest._manifest_bills()
        for ver in bill["versions"]
        for fmt in ver["formats"]
    }


def allowlist_fixture_id(nodeid: str) -> str | None:
    """The manifest fixture id an allowlist key references, or ``None`` if it keys on no
    manifest fixture.

    Returns the parametrize id inside the trailing ``[...]`` when that id is
    fixture-shaped (``<dir>/<name>.xml`` or ``.pdf``, matching ``_xml_id``/``_corpus_id``
    = ``<bill>/<stage>.<fmt>``). A key with no bracket, or a non-fixture parametrize id,
    yields ``None`` — it has no manifest coupling for this guard to validate."""
    if "[" not in nodeid or not nodeid.endswith("]"):
        return None
    param = nodeid[nodeid.index("[") + 1 : -1]
    if "/" in param and param.endswith((".xml", ".pdf")):
        return param
    return None


def stale_allowlist_entries(allowlist: dict[str, str], manifest_ids: set[str]) -> dict[str, str]:
    """Allowlist entries whose fixture id is absent from the manifest (i.e. stale).

    Maps each stale node id to the fixture id it references but the manifest no longer
    declares. Empty on a manifest and allowlist that agree — the clean-tree case."""
    stale = {}
    for nodeid in allowlist:
        fixture = allowlist_fixture_id(nodeid)
        if fixture is not None and fixture not in manifest_ids:
            stale[nodeid] = fixture
    return stale


def test_allowlist_keys_reference_only_live_manifest_fixtures() -> None:
    """The drift guard, run against the real allowlist: every ``ALLOWED_CORPUS_SKIPS``
    key that names a manifest fixture references one the manifest still declares. This is
    the gate that reddens the fast CI run when an allowlist entry and the manifest drift
    apart — the failure mode #281 exists to catch."""
    stale = stale_allowlist_entries(dict(conftest.ALLOWED_CORPUS_SKIPS), manifest_fixture_ids())
    assert stale == {}, (
        f"{len(stale)} content-skip allowlist entry(ies) key on a fixture absent from "
        f"tests/corpus_manifest.toml (stale — the ceiling now silently permits them): "
        f"{stale}. Remove the entry, or restore the fixture to the manifest."
    )


def test_current_allowlist_all_key_on_manifest_fixtures() -> None:
    """Sanity floor for the guard above: the real allowlist is entirely fixture-keyed
    today, so the clean-run assertion is exercising the manifest check on every entry
    (not passing vacuously because nothing was fixture-shaped)."""
    allowlist = dict(conftest.ALLOWED_CORPUS_SKIPS)
    assert allowlist, "ALLOWED_CORPUS_SKIPS is empty — this guard would pass vacuously"
    assert all(allowlist_fixture_id(nodeid) is not None for nodeid in allowlist)


def test_guard_flags_a_fixture_absent_from_the_manifest() -> None:
    """A synthetic entry keyed on a never-manifested fixture is flagged, by name and with
    the offending fixture id — the stranded-entry case, demonstrated to fire."""
    nodeid = "tests/test_corpus_properties.py::test_x[999-hr-9999/1_nonexistent.xml]"
    stale = stale_allowlist_entries({nodeid: "made up"}, manifest_fixture_ids())
    assert stale == {nodeid: "999-hr-9999/1_nonexistent.xml"}


def test_guard_flags_a_real_entry_when_its_fixture_leaves_the_manifest() -> None:
    """The issue's live worked example: take a REAL allowlist entry and drop its fixture
    from the manifest (a version renamed, or a fixture removed under #126 curation). The
    guard flags that exact entry — proving it fires on genuine drift of a live entry, not
    only on a hand-built fake."""
    real_nodeid = next(iter(conftest.ALLOWED_CORPUS_SKIPS))
    fixture = allowlist_fixture_id(real_nodeid)
    assert fixture is not None, "precondition: the sampled entry keys on a fixture"
    manifest_missing_that_fixture = manifest_fixture_ids() - {fixture}
    stale = stale_allowlist_entries(dict(conftest.ALLOWED_CORPUS_SKIPS), manifest_missing_that_fixture)
    assert stale.get(real_nodeid) == fixture


def test_guard_ignores_entries_with_no_manifest_fixture_key() -> None:
    """Entries that key on no manifest fixture — a class-based diff gate, a plain
    ``skipif`` callout function — carry no manifest coupling and must NOT be flagged
    (the false-positive direction: this guard governs manifest drift only)."""
    non_fixture = {
        "tests/test_diff_validation.py::TestControlledDiff::test_added_section": "r",
        "tests/test_financial_callout_whole_item.py::test_sec_20004_callout_nets_to_zero": "r",
    }
    assert stale_allowlist_entries(non_fixture, manifest_fixture_ids()) == {}


def test_allowlist_fixture_id_extracts_only_fixture_shaped_params() -> None:
    """The extractor unit: a manifest-shaped parametrize id is returned; a bare test id,
    or a non-fixture param, yields None."""
    assert (
        allowlist_fixture_id("tests/m.py::test_x[119-hr-1/1_reported-in-house.xml]")
        == "119-hr-1/1_reported-in-house.xml"
    )
    assert allowlist_fixture_id("tests/m.py::test_x[113-hr-3547/4_engrossed-amendment-senate.pdf]") == (
        "113-hr-3547/4_engrossed-amendment-senate.pdf"
    )
    assert allowlist_fixture_id("tests/m.py::TestX::test_y") is None
    assert allowlist_fixture_id("tests/m.py::test_x[serial]") is None
