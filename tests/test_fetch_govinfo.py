"""Tests for the govinfo bulk-data access layer (issue #10).

Unit tests are hermetic (synthetic in-memory ZIPs, no network). One integration
test asserts govinfo BILLS bytes are identical to the curated Congress.gov-
sourced corpus -- #10's regression guard -- and skips when the local bulk ZIPs
or the curated bill are absent (e.g. clean CI checkout).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import fetch_bill_text_archives as fbt
import fetch_govinfo as gi

REPO = Path(__file__).resolve().parent.parent


# ---- version-code resolution ------------------------------------------------


def test_resolve_code_exact():
    assert gi.resolve_code("rh") == ("Reported in House", 3)
    assert gi.resolve_code("enr") == ("Enrolled Bill", 5)


def test_resolve_code_suffixed_variant_inherits_base_tier():
    # eas2/rfs2/eh1s are re-engrossment / repeat-referral variants govinfo emits;
    # they must inherit the base code's tier, not fall to tier 0 (which would sort
    # a late amendment before the introduced version).
    assert gi.resolve_code("eas2") == ("Engrossed Amendment Senate", 4)
    assert gi.resolve_code("rfs2") == ("Referred in Senate", 2)
    assert gi.resolve_code("eh1s")[1] == 4


def test_resolve_code_unknown_is_tier_zero():
    name, tier = gi.resolve_code("zzq")
    assert tier == 0 and name == "zzq"


def test_name_to_code_roundtrip():
    # Every code's sanitized name maps back to a code (derived reverse table).
    assert gi.NAME_TO_CODE["reported-in-senate"] == "rs"
    assert gi.NAME_TO_CODE["enrolled-bill"] == "enr"


# ---- URL builders -----------------------------------------------------------


def test_url_builders():
    assert gi.bills_zip_url(119, 1, "hr") == ("https://www.govinfo.gov/bulkdata/BILLS/119/1/hr/BILLS-119-1-hr.zip")
    assert gi.bill_xml_url(118, 2, "s", 4690, "rs").endswith("/BILLS-118s4690rs.xml")
    assert gi.billstatus_url(119, "hr", 1).endswith("/BILLSTATUS-119hr1.xml")


# ---- order_versions: the shared ordering primitive --------------------------


def test_order_versions_sorts_by_date_over_tier():
    # Dates deliberately CONTRADICT tier rank: eh (tier 4) is dated first, ih
    # (tier 1) last. Date-primary yields [eh, rh, ih]; a tier-primary sort (or one
    # that ignored the date argument) would give [ih, rh, eh]. Proves the date is
    # the primary key.
    ordered = gi.order_versions([("eh", "2025-01-01"), ("rh", "2025-02-01"), ("ih", "2025-03-01")])
    assert [code for code, _d, _t in ordered] == ["eh", "rh", "ih"]


def test_order_versions_undated_sorts_to_max_date_last():
    # enr has no date -> null->max places it at the bill's latest date, and its
    # tier (5) then puts it last rather than first (the enrolled-bill trap).
    ordered = gi.order_versions([("enr", ""), ("ih", "2025-01-01"), ("rh", "2025-02-01")])
    assert [code for code, _d, _t in ordered] == ["ih", "rh", "enr"]


def test_order_versions_truncates_datetime_to_date_for_tie_break():
    # A BILLSTATUS full datetime and a bare date on the same day must compare equal
    # (both truncate to YYYY-MM-DD) and fall through to the tier tie-break, not sort
    # by string length. es (tier 4) before pap (tier 5) on the shared day.
    ordered = gi.order_versions([("pap", "2025-03-20"), ("es", "2025-03-20T04:00:00Z")])
    assert [code for code, _d, _t in ordered] == ["es", "pap"]


def test_order_versions_same_date_and_tier_breaks_by_code():
    # eas and eas2 share slug and tier; a same-date pair stays deterministic by code.
    ordered = gi.order_versions([("eas2", "2025-07-01"), ("eas", "2025-07-01")])
    assert [code for code, _d, _t in ordered] == ["eas", "eas2"]


def test_order_versions_empty_input():
    assert gi.order_versions([]) == []


# ---- conversion: BILLSTATUS-only ordering + min_versions filter -------------
#
# Ordering authority is the BILLSTATUS date alone (gi.order_versions); the
# version's own dc:date in the downloaded bytes is not read. So every ordering
# test supplies dates via a BILLSTATUS ZIP, never via _member. _member's optional
# govinfo_date exists only to prove dc:date is *ignored* (the disagreement test).


def _member(congress, btype, num, code, govinfo_date=None):
    """One fake BILLS-*.xml member (name, bytes).

    ``govinfo_date`` embeds a dc:date that convert_archives no longer reads for
    ordering; pass it only to assert BILLSTATUS overrides it.
    """
    date_el = f"<dublinCore><dc:date>{govinfo_date}</dc:date></dublinCore>" if govinfo_date else ""
    body = f"<bill>{date_el}<text>{code}</text></bill>".encode()
    return f"BILLS-{congress}{btype}{num}{code}.xml", body


def _write_zip(path: Path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)


def _billstatus_zip(path: Path, congress, btype, num, versions):
    """One BILLSTATUS ZIP for a bill; versions = [(type_name, date, code), ...].

    Each item carries a format URL embedding the version code, mirroring real
    BILLSTATUS: the date index keys off that code, not the display <type>.
    """
    items = "".join(
        f"<item><type>{t}</type><date>{d}</date><formats><item>"
        f"<url>https://www.govinfo.gov/content/pkg/BILLS-{congress}{btype}{num}{code}"
        f"/xml/BILLS-{congress}{btype}{num}{code}.xml</url>"
        f"</item></formats></item>"
        for t, d, code in versions
    )
    xml = (
        f"<billStatus><bill><congress>{congress}</congress><type>{btype.upper()}</type>"
        f"<number>{num}</number><textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()
    _write_zip(path, [(f"BILLSTATUS-{congress}{btype}{num}.xml", xml)])


def test_convert_orders_by_date_and_places_undated_last(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    # 999hr1: ih, rh, eas2 dated in BILLSTATUS; enr absent -> undated -> sorts last
    # via max_date + tier.
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 1, "rh"),
            _member(999, "hr", 1, "ih"),
            _member(999, "hr", 1, "enr"),
            _member(999, "hr", 1, "eas2"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        1,
        [
            ("Introduced in House", "2025-01-01", "ih"),
            ("Reported in House", "2025-02-01", "rh"),
            ("Engrossed Amendment Senate", "2025-03-01", "eas2"),
        ],
    )
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert stats["bills_written"] == 1
    names = sorted(p.name for p in (out / "999-hr-1").glob("*.xml"))
    assert names == [
        "1_introduced-in-house.xml",
        "2_reported-in-house.xml",
        "3_engrossed-amendment-senate.xml",  # eas2 resolved to base slug
        "4_enrolled-bill.xml",  # undated (absent from BILLSTATUS), sorted last
    ]


def test_convert_orders_by_billstatus_not_govinfo_date(tmp_path):
    # The split-brain guard: the version's own dc:date must NOT influence ordering.
    # Here dc:date says rh (2025-01-01) precedes ih (2025-06-01), but BILLSTATUS
    # says the opposite. BILLSTATUS wins, so ih sorts first. (Real 118-hr-2 case:
    # dc:date-primary sorted pcs before ih; BILLSTATUS orders ih, eh, pcs.)
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 11, "rh", govinfo_date="2025-01-01"),
            _member(999, "hr", 11, "ih", govinfo_date="2025-06-01"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        11,
        [("Introduced in House", "2025-02-01", "ih"), ("Reported in House", "2025-05-01", "rh")],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    # BILLSTATUS order (ih 2025-02 < rh 2025-05), not dc:date order (rh 2025-01 first).
    assert sorted(p.name for p in (out / "999-hr-11").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_reported-in-house.xml",
    ]


def test_convert_min_versions_filter(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 2, "ih"),  # single version
            _member(999, "hr", 3, "ih"),
            _member(999, "hr", 3, "eh"),  # two versions
        ],
    )
    # min_versions=1 keeps both bills (the general fetch #10 wants)...
    out1 = tmp_path / "b1"
    s1 = fbt.convert_archives(zip_dir, out1, min_versions=1, billstatus_dir=None)
    assert s1["bills_written"] == 2
    # ...min_versions=2 keeps only the matchable one (the #170 corpus).
    out2 = tmp_path / "b2"
    s2 = fbt.convert_archives(zip_dir, out2, min_versions=2, billstatus_dir=None)
    assert s2["bills_written"] == 1
    assert (out2 / "999-hr-3").exists() and not (out2 / "999-hr-2").exists()


def test_convert_skips_existing_dirs(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [_member(999, "hr", 4, "ih"), _member(999, "hr", 4, "eh")],
    )
    out = tmp_path / "bills"
    (out / "999-hr-4").mkdir(parents=True)  # pre-existing (curated) dir
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats.get("existing_dir_skipped") == 1
    assert stats.get("bills_written", 0) == 0


def test_billstatus_date_places_engrossed_before_placed_on_calendar(tmp_path):
    # The real 119-hr-1 shape: engrossed-in-house's date puts it mid-sequence.
    # Without BILLSTATUS (no date at all) it would sort last by tier alone, after
    # placed-on-calendar-senate -- so BILLSTATUS is load-bearing, not cosmetic.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 5, "ih"),
            _member(999, "hr", 5, "eh"),
            _member(999, "hr", 5, "pcs"),
        ],
    )
    # No billstatus_dir: every version is undated -> tier order puts eh (4) last.
    out_none = tmp_path / "none"
    fbt.convert_archives(zip_dir, out_none, min_versions=2, billstatus_dir=None)
    names_none = sorted(p.name for p in (out_none / "999-hr-5").glob("*.xml"))
    assert names_none.index("3_engrossed-in-house.xml") > names_none.index("2_placed-on-calendar-senate.xml")

    # With BILLSTATUS dates, eh (2025-05-22) sorts between ih and pcs.
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        5,
        [
            ("Introduced in House", "2025-05-20", "ih"),
            ("Engrossed in House", "2025-05-22", "eh"),
            ("Placed on Calendar Senate", "2025-06-28", "pcs"),
        ],
    )
    out = tmp_path / "with"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-hr-5").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_engrossed-in-house.xml",
        "3_placed-on-calendar-senate.xml",
    ]


def test_billstatus_join_survives_type_name_divergence(tmp_path):
    # BILLSTATUS spells rs "Reported to Senate" while VERSION_CODES says "Reported
    # in Senate". Keying the date join by the version code from the URL (shared
    # verbatim) -- not the display name -- keeps rs at its true date.
    #
    # rs is deliberately dated AFTER es so the working code-join and a broken
    # name-join produce DIFFERENT orders (else tier alone reproduces the result
    # and the test proves nothing): a working join dates rs 2025-03-20, sorting it
    # last (is, es, rs); a name-join leaves rs dateless -> null->max at 2025-02-05,
    # where its tier 3 lands it BEFORE es tier 4 (is, rs, es). The assertion fails
    # if the join regresses to matching on the divergent display name.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 8, "is"),
            _member(999, "s", 8, "rs"),
            _member(999, "s", 8, "es"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # rs's display name diverges; the code in its URL is still "rs".
    _billstatus_zip(
        bs_dir / "999-s.zip",
        999,
        "s",
        8,
        [
            ("Introduced in Senate", "2025-01-10", "is"),
            ("Engrossed in Senate", "2025-02-05", "es"),
            ("Reported to Senate", "2025-03-20", "rs"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    # Working code-join: rs's own date (2025-03-20) puts it last.
    assert sorted(p.name for p in (out / "999-s-8").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_engrossed-in-senate.xml",
        "3_reported-in-senate.xml",
    ]


def test_convert_same_day_versions_break_tie_by_tier(tmp_path):
    # es (engrossed) and pap (printed-as-passed) share a calendar day. BILLSTATUS
    # gives es a full datetime, pap a bare date; both truncate to YYYY-MM-DD so the
    # tie breaks by tier (es=4 before pap=5), not by the datetime string's length.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 9, "is"),
            _member(999, "s", 9, "es"),
            _member(999, "s", 9, "pap"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-s.zip",
        999,
        "s",
        9,
        [
            ("Introduced in Senate", "2025-01-05", "is"),
            ("Engrossed in Senate", "2025-03-20T04:00:00Z", "es"),
            ("Printed as Passed", "2025-03-20", "pap"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-s-9").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_engrossed-in-senate.xml",  # tier 4, before printed-as-passed on the same day
        "3_printed-as-passed.xml",  # tier 5
    ]


def test_billstatus_urlless_item_falls_back_to_name(tmp_path):
    # Some BILLSTATUS items carry a <type> + <date> but no format URL (govinfo
    # hasn't published one). The code must still be recovered from the display
    # name, or engrossed-in-house -- which relies on this fallback -- would drop
    # out of the index and sort last. Real cases: 117-hr-5705, 119-hr-6703.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 10, "ih"),
            _member(999, "hr", 10, "eh"),
            _member(999, "hr", 10, "rfs"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # ih and rfs carry URLs; the eh item has a date but NO format URL -> its code is
    # recovered from the display name so it still lands in the date index.
    items = (
        "<item><type>Introduced in House</type><date>2025-01-03T05:00:00Z</date><formats><item>"
        "<url>https://www.govinfo.gov/content/pkg/BILLS-999hr10ih/xml/BILLS-999hr10ih.xml</url>"
        "</item></formats></item>"
        "<item><type>Engrossed in House</type><date>2025-02-10T05:00:00Z</date></item>"
        "<item><type>Referred in Senate</type><date>2025-04-01T05:00:00Z</date><formats><item>"
        "<url>https://www.govinfo.gov/content/pkg/BILLS-999hr10rfs/xml/BILLS-999hr10rfs.xml</url>"
        "</item></formats></item>"
    )
    xml = (
        f"<billStatus><bill><congress>999</congress><type>HR</type><number>10</number>"
        f"<textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()
    _write_zip(bs_dir / "999-hr.zip", [("BILLSTATUS-999hr10.xml", xml)])

    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-hr-10").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_engrossed-in-house.xml",  # placed by name-fallback date, not sorted last
        "3_referred-in-senate.xml",
    ]


def test_convert_skips_corrupt_zip_without_aborting(tmp_path):
    # A truncated/garbage ZIP alongside good ones (e.g. an interrupted prior run)
    # must be skipped, not abort the whole conversion.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [_member(999, "hr", 7, "ih"), _member(999, "hr", 7, "eh")],
    )
    (zip_dir / "BILLS-999-2-hr.zip").write_bytes(b"not a real zip file")
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats["corrupt_zip_skipped"] == 1
    assert stats["bills_written"] == 1
    assert (out / "999-hr-7").exists()


def test_convert_repeated_type_ordered_by_billstatus_date(tmp_path):
    # eas and eas2 both resolve to "Engrossed Amendment Senate"; they must stay
    # ordered by their BILLSTATUS dates, not collapse to an arbitrary order.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 6, "ih"),
            _member(999, "hr", 6, "eas2"),
            _member(999, "hr", 6, "eas"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # eas2 is dated EARLIER than eas, so the BILLSTATUS date -- not the code
    # tiebreak -- must decide their order. A date-blind sort would fall back to the
    # code tiebreak ("eas" < "eas2") and put eas first, failing the assertion.
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        6,
        [
            ("Introduced in House", "2025-01-01", "ih"),
            ("Engrossed Amendment Senate", "2025-07-02", "eas"),
            ("Engrossed Amendment Senate", "2025-07-01", "eas2"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    d = out / "999-hr-6"
    # Both share the slug; the earlier-dated eas2 gets the lower index despite
    # sorting after eas under the code tiebreak.
    assert b">eas2<" in (d / "2_engrossed-amendment-senate.xml").read_bytes()
    assert b">eas<" in (d / "3_engrossed-amendment-senate.xml").read_bytes()


# ---- byte-identity: govinfo BILLS == Congress.gov "Formatted XML" (#10 guard) ---
#
# The #10 premise -- "nothing downstream needs to change" -- rests on govinfo's
# bulk BILLS XML being byte-for-byte identical to the Congress.gov Formatted XML
# the corpus was built from. Two guards:
#   1. A hermetic, always-runs check against a vendored cross-source pair for one
#      small bill (118-hr-2882 introduced-in-house, 17 U.S.C. 105 public domain).
#      The two files were independently sourced -- one from govinfo bulkdata, one
#      from the Congress.gov API -- so equality is a real provenance lock, not a
#      tautology, and it catches a future divergence in CI.
#   2. A broader local check over the freshly-downloaded bulk ZIP vs the curated
#      corpus, which skips on a clean/CI checkout (both dirs are gitignored).

_FIXTURES = REPO / "tests" / "fixtures" / "byte_identity"
_GOVINFO_FIXTURE = _FIXTURES / "govinfo_BILLS-118hr2882ih.xml"
_CONGRESSGOV_FIXTURE = _FIXTURES / "congressgov_118-hr-2882_introduced-in-house.xml"


def test_govinfo_bytes_identical_to_congressgov_fixture():
    assert _GOVINFO_FIXTURE.read_bytes() == _CONGRESSGOV_FIXTURE.read_bytes(), (
        "govinfo BILLS text must be byte-identical to the Congress.gov Formatted XML"
    )


_BULK_ZIP = REPO / "bills_bulk_text" / "BILLS-119-1-hr.zip"
_CURATED = REPO / "bills" / "119-hr-1" / "1_reported-in-house.xml"


@pytest.mark.skipif(
    not (_BULK_ZIP.exists() and _CURATED.exists()),
    reason="local-only: freshly-downloaded bulk ZIP + curated corpus (both gitignored)",
)
def test_govinfo_bytes_identical_to_curated_corpus():
    with zipfile.ZipFile(_BULK_ZIP) as zf:
        member = next(n for n in zf.namelist() if n.endswith("BILLS-119hr1rh.xml"))
        govinfo_bytes = zf.read(member)
    assert govinfo_bytes == _CURATED.read_bytes(), (
        "govinfo BILLS text must be byte-identical to the Congress.gov-sourced corpus"
    )
