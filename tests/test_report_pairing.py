"""Direct unit tests for the committee-report pairing rules (issue #295).

These exercise ``get_report_pairing()`` itself, rather than the manifest it wrote.
Both are worth having and they fail for different reasons: a manifest assertion says
the recorded answer is right *today*, while these say the rule that produces it is
right, including for stage/chamber combinations no committed bill happens to have.
A manifest-only gate also cannot distinguish "the rule is correct" from "the rule is
broken and the stored data is stale", because it reads the stored data.

Fast (unmarked) on purpose: pure functions over literals, no fixtures and no network,
so they run in the fast CI step where a broken rule surfaces in seconds.
"""

from __future__ import annotations

import pytest

from scripts.report_pairing import (
    ENROLLED,
    POST_COMMITTEE,
    PRE_COMMITTEE,
    REPORTED,
    ReportSource,
    authoring_chamber,
    get_report_pairing,
    mark_conference_reports,
    stage_class,
)

HOUSE_REPORT = ReportSource(citation="H. Rept. 118-364", chamber="house", number=364)
HOUSE_EARLIER = ReportSource(citation="H. Rept. 115-697", chamber="house", number=697)
HOUSE_CONFERENCE = ReportSource(citation="H. Rept. 115-929", chamber="house", number=929, conference=True)
SENATE_REPORT = ReportSource(citation="S. Rept. 114-57", chamber="senate", number=57)


def citations(pairing) -> set[str]:
    return {s.citation for s in pairing.sources}


# --- stage classification ------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("1_introduced-in-house", PRE_COMMITTEE),
        ("1_reported-in-house", REPORTED),
        ("1_reported-in-senate", REPORTED),
        ("2_engrossed-in-house", POST_COMMITTEE),
        ("3_received-in-senate", POST_COMMITTEE),
        ("4_engrossed-amendment-senate", POST_COMMITTEE),
        ("5_engrossed-amendment-house", POST_COMMITTEE),
        ("7_enrolled-bill", ENROLLED),
    ],
)
def test_stage_class(stage: str, expected: int) -> None:
    """Every stage the corpus uses lands in the intended class."""
    assert stage_class(stage) == expected


def test_stage_class_ignores_the_numeric_prefix() -> None:
    """The prefix numbers a bill's committed versions, so it is not an ordering.

    ``1_introduced-in-house`` and ``1_reported-in-house`` share a prefix and are
    different classes; reading the digit would collapse them.
    """
    assert stage_class("1_introduced-in-house") != stage_class("1_reported-in-house")
    assert stage_class("9_introduced-in-house") == stage_class("1_introduced-in-house")


# --- the cases named in the review --------------------------------------------


def test_introduced_version_predating_the_report_gets_none() -> None:
    """The regression: introduced text predates the report, which is filed at REPORTED.

    118-hr-2882's introduced version took H. Rept. 118-364 purely because both are
    House-authored. The report recommends changing that text; it does not explain it.
    """
    pairing = get_report_pairing([HOUSE_REPORT], "1_introduced-in-house", "hr")

    assert pairing.sources == ()
    assert "predates" in (pairing.reason or ""), f"expected a temporal reason, got {pairing.reason!r}"


def test_reported_house_version_gets_the_house_report() -> None:
    pairing = get_report_pairing([HOUSE_REPORT], "1_reported-in-house", "hr")
    assert citations(pairing) == {"H. Rept. 118-364"}


def test_senate_authored_amendment_gets_the_senate_report() -> None:
    """A Senate substitute is explained by the Senate's report, not the House's."""
    pairing = get_report_pairing([HOUSE_REPORT, SENATE_REPORT], "5_engrossed-amendment-senate", "hr")
    assert citations(pairing) == {"S. Rept. 114-57"}


def test_senate_authored_amendment_without_a_senate_report_is_explicitly_none() -> None:
    """No Senate report means no pairing and a stated reason -- not the House report."""
    pairing = get_report_pairing([HOUSE_REPORT], "4_engrossed-amendment-senate", "hr")

    assert pairing.sources == ()
    assert "senate" in (pairing.reason or "").lower(), f"reason should name the chamber: {pairing.reason!r}"


def test_house_authored_version_after_the_senate_gets_the_house_report() -> None:
    """The House's post-Senate text is back to being explained by the House report."""
    pairing = get_report_pairing([HOUSE_REPORT, SENATE_REPORT], "5_engrossed-amendment-house", "hr")
    assert citations(pairing) == {"H. Rept. 118-364"}


def test_enrolled_version_gets_every_source_including_the_conference_report() -> None:
    """Enrolled text is the agreed product of both chambers; the conference report explains it."""
    pairing = get_report_pairing([HOUSE_EARLIER, HOUSE_CONFERENCE, SENATE_REPORT], "7_enrolled-bill", "hr")
    assert citations(pairing) == {"H. Rept. 115-697", "H. Rept. 115-929", "S. Rept. 114-57"}


def test_conference_report_is_excluded_before_enrollment() -> None:
    """A conference report postdates every pre-conference stage, same chamber or not."""
    for stage in ("1_reported-in-house", "2_engrossed-in-house", "5_engrossed-amendment-house"):
        pairing = get_report_pairing([HOUSE_EARLIER, HOUSE_CONFERENCE], stage, "hr")
        assert citations(pairing) == {"H. Rept. 115-697"}, f"{stage} pulled in the conference report"


def test_a_bill_with_no_reports_pairs_nothing_anywhere() -> None:
    for stage in ("1_introduced-in-house", "1_reported-in-house", "6_enrolled-bill"):
        pairing = get_report_pairing([], stage, "hr")
        assert pairing.sources == ()
        assert pairing.reason


# --- supporting rules ----------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "bill_type", "expected"),
    [
        ("1_reported-in-house", "hr", "house"),
        ("4_engrossed-amendment-senate", "hr", "senate"),
        ("5_engrossed-amendment-house", "hr", "house"),
        # Transit: the receiving chamber has not amended anything, so the text is
        # still the originating chamber's.
        ("3_received-in-senate", "hr", "house"),
        ("3_referred-in-senate", "hr", "house"),
        ("3_placed-on-calendar-senate", "hr", "house"),
        ("1_reported-in-senate", "s", "senate"),
    ],
)
def test_authoring_chamber(stage: str, bill_type: str, expected: str) -> None:
    assert authoring_chamber(stage, bill_type) == expected


def test_conference_marking_needs_two_distinct_numbers_in_one_chamber() -> None:
    """The higher of two same-chamber report numbers is the conference report."""
    marked = mark_conference_reports(
        [
            ReportSource(citation="H. Rept. 115-697", chamber="house", number=697),
            ReportSource(citation="H. Rept. 115-929", chamber="house", number=929),
        ]
    )
    assert {s.citation for s in marked if s.conference} == {"H. Rept. 115-929"}


def test_books_of_one_report_are_not_mistaken_for_a_conference_report() -> None:
    """Two books share a report number, so the higher-number rule must not fire."""
    marked = mark_conference_reports(
        [
            ReportSource(citation="H. Rept. 119-106,Book 1", chamber="house", number=106, book="Book 1"),
            ReportSource(citation="H. Rept. 119-106,Book 2", chamber="house", number=106, book="Book 2"),
        ]
    )
    assert not any(s.conference for s in marked)


def test_one_report_per_chamber_is_never_a_conference_report() -> None:
    marked = mark_conference_reports([HOUSE_REPORT, SENATE_REPORT])
    assert not any(s.conference for s in marked)


# --- package / granule resolution ----------------------------------------------
#
# resolve_pkgs asks govinfo whether a rendition exists, so these stub that one call
# and assert on the decision it drives. The rule under test is what happens with the
# answer, not the HTTP; stubbing keeps the fail-closed branch gated without needing
# the corpus to contain an unpublished report.

from scripts import update_manifest_with_reports as updater  # noqa: E402

BOOK_1 = ReportSource(citation="H. Rept. 119-106,Book 1", chamber="house", number=106, book="Book 1")
BOOK_2 = ReportSource(citation="H. Rept. 119-106,Book 2", chamber="house", number=106, book="Book 2")
PLAIN = ReportSource(citation="H. Rept. 118-364", chamber="house", number=364)


def _stub_resolver(monkeypatch, resolvable: set[str | None]) -> None:
    """Make only the named renditions resolve. ``None`` means the undivided package."""
    monkeypatch.setattr(updater, "rendition_resolves", lambda pkg, granule=None: granule in resolvable)


def test_books_resolve_to_distinct_granules(monkeypatch) -> None:
    """The fix for the collapse: Book N is granule -ptN of the shared parent package."""
    _stub_resolver(monkeypatch, {"CRPT-119hrpt106-pt1", "CRPT-119hrpt106-pt2"})

    resolved = updater.resolve_pkgs([BOOK_1, BOOK_2], congress=119)

    assert [s.pkg for s in resolved] == ["CRPT-119hrpt106", "CRPT-119hrpt106"]
    assert [s.granule for s in resolved] == ["CRPT-119hrpt106-pt1", "CRPT-119hrpt106-pt2"]
    assert all(s.text_available for s in resolved)
    # The property the old model broke: two books, two addressable artifacts.
    assert len({(s.pkg, s.granule) for s in resolved}) == 2


def test_undivided_package_records_no_granule(monkeypatch) -> None:
    _stub_resolver(monkeypatch, {None})
    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)
    assert (resolved.pkg, resolved.granule) == ("CRPT-118hrpt364", None)


def test_parted_package_without_a_cited_book_uses_its_only_granule(monkeypatch) -> None:
    """CRPT-118hrpt364 is served only as -pt1, though BILLSTATUS cites no book."""
    _stub_resolver(monkeypatch, {"CRPT-118hrpt364-pt1"})
    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)
    assert (resolved.pkg, resolved.granule) == ("CRPT-118hrpt364", "CRPT-118hrpt364-pt1")


def test_ambiguous_multipart_package_fails_closed(monkeypatch) -> None:
    """Several parts but no cited book: which one the citation means is unresolved."""
    _stub_resolver(monkeypatch, {"CRPT-118hrpt364-pt1", "CRPT-118hrpt364-pt2"})

    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)

    assert resolved.text_available is False
    assert not resolved.pkg and not resolved.granule
    assert "unresolved" in (resolved.unavailable_reason or "")


def test_nothing_resolving_is_marked_unavailable_with_a_reason(monkeypatch) -> None:
    """Fail closed: an unpublished report is explicit, never a pkg pointing at nothing."""
    _stub_resolver(monkeypatch, set())

    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)

    assert resolved.text_available is False
    assert resolved.pkg is None, "a package ID that resolves to nothing reads as a vendorable fixture"
    assert "CRPT-118hrpt364" in (resolved.unavailable_reason or "")


def test_missing_book_granule_is_marked_unavailable(monkeypatch) -> None:
    """A cited book whose granule does not resolve must not fall back to the package."""
    _stub_resolver(monkeypatch, {None})  # the undivided package resolves, the granule does not

    (resolved,) = updater.resolve_pkgs([BOOK_2], congress=119)

    assert resolved.text_available is False
    assert resolved.pkg is None
    assert "CRPT-119hrpt106-pt2" in (resolved.unavailable_reason or "")


def test_fixture_stem_separates_books_but_not_undivided_packages() -> None:
    from scripts.report_pairing import fixture_stem

    assert fixture_stem("CRPT-119hrpt106", "CRPT-119hrpt106-pt1") == "CRPT-119hrpt106-pt1"
    assert fixture_stem("CRPT-119hrpt106", "CRPT-119hrpt106-pt2") == "CRPT-119hrpt106-pt2"
    assert fixture_stem("CRPT-118hrpt122", None) == "CRPT-118hrpt122"


def test_rendition_url_addresses_a_granule_inside_its_parent_package() -> None:
    """There is no standalone CRPT-...-pt1 package; asking for one lands on the error page."""
    from scripts.report_pairing import rendition_url

    assert rendition_url("CRPT-119hrpt106", "CRPT-119hrpt106-pt1") == (
        "https://www.govinfo.gov/content/pkg/CRPT-119hrpt106/html/CRPT-119hrpt106-pt1.htm"
    )
    assert rendition_url("CRPT-118hrpt122") == (
        "https://www.govinfo.gov/content/pkg/CRPT-118hrpt122/html/CRPT-118hrpt122.htm"
    )
