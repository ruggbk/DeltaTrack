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


# ---- conversion: ordering + min_versions filter -----------------------------


def _member(congress, btype, num, code, date=None):
    """One fake BILLS-*.xml member (name, bytes). dc:date embedded when given."""
    date_el = f"<dublinCore><dc:date>{date}</dc:date></dublinCore>" if date else ""
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
    # 999hr1: ih, rh, eas2 dated; enr undated (must sort last via max_date + tier).
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 1, "rh", "2025-02-01"),
            _member(999, "hr", 1, "ih", "2025-01-01"),
            _member(999, "hr", 1, "enr"),  # no date
            _member(999, "hr", 1, "eas2", "2025-03-01"),
        ],
    )
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats["bills_written"] == 1
    names = sorted(p.name for p in (out / "999-hr-1").glob("*.xml"))
    assert names == [
        "1_introduced-in-house.xml",
        "2_reported-in-house.xml",
        "3_engrossed-amendment-senate.xml",  # eas2 resolved to base slug
        "4_enrolled-bill.xml",  # undated, sorted last
    ]


def test_convert_min_versions_filter(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 2, "ih", "2025-01-01"),  # single version
            _member(999, "hr", 3, "ih", "2025-01-01"),
            _member(999, "hr", 3, "eh", "2025-02-01"),  # two versions
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
        [_member(999, "hr", 4, "ih", "2025-01-01"), _member(999, "hr", 4, "eh", "2025-02-01")],
    )
    out = tmp_path / "bills"
    (out / "999-hr-4").mkdir(parents=True)  # pre-existing (curated) dir
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats.get("existing_dir_skipped") == 1
    assert stats.get("bills_written", 0) == 0


def test_convert_uses_billstatus_date_when_govinfo_date_missing(tmp_path):
    # The real 119-hr-1 bug: engrossed-in-house carries no govinfo dc:date, so
    # without the BILLSTATUS fallback it sorts AFTER placed-on-calendar-senate.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 5, "ih", "2025-05-20"),
            _member(999, "hr", 5, "eh"),  # govinfo omits the date
            _member(999, "hr", 5, "pcs", "2025-06-28"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(bs_dir / "999-hr.zip", 999, "hr", 5, [("Engrossed in House", "2025-05-22", "eh")])

    # Without the join, eh has no date -> sorts to max_date, after pcs (wrong order).
    out_none = tmp_path / "none"
    fbt.convert_archives(zip_dir, out_none, min_versions=2, billstatus_dir=None)
    names_none = sorted(p.name for p in (out_none / "999-hr-5").glob("*.xml"))
    assert names_none.index("3_engrossed-in-house.xml") > names_none.index("2_placed-on-calendar-senate.xml")

    # With the BILLSTATUS date (2025-05-22), eh sorts between ih and pcs.
    out = tmp_path / "with"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-hr-5").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_engrossed-in-house.xml",
        "3_placed-on-calendar-senate.xml",
    ]


def test_billstatus_join_survives_type_name_divergence(tmp_path):
    # Real bug: BILLSTATUS spells rs "Reported to Senate" while VERSION_CODES says
    # "Reported in Senate". A name-based join misses it, so a dateless rs sorts to
    # max_date (last) instead of its true mid-sequence position. Keying by the
    # version code (shared verbatim by both sources) fixes it.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 8, "is", "2025-01-10"),
            _member(999, "s", 8, "rs"),  # govinfo omits the date
            _member(999, "s", 8, "es", "2025-03-15"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # Divergent display name; the code in the URL is still "rs".
    _billstatus_zip(bs_dir / "999-s.zip", 999, "s", 8, [("Reported to Senate", "2025-02-05", "rs")])

    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    # rs (2025-02-05) sorts between is and es, not last.
    assert sorted(p.name for p in (out / "999-s-8").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_reported-in-senate.xml",
        "3_engrossed-in-senate.xml",
    ]


def test_same_day_cross_source_dates_break_tie_by_tier(tmp_path):
    # es (engrossed) and pap (printed-as-passed) fall on the same calendar day, but
    # es's date comes from BILLSTATUS (full datetime) while pap's is the bare
    # govinfo date. Both must normalize to the date so the tie breaks by tier
    # (es=4 before pap=5), not by the datetime string being longer than the date.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 9, "is", "2025-01-05"),
            _member(999, "s", 9, "es"),  # govinfo omits date -> BILLSTATUS datetime
            _member(999, "s", 9, "pap", "2025-03-20"),  # bare govinfo date, same day as es
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(bs_dir / "999-s.zip", 999, "s", 9, [("Engrossed in Senate", "2025-03-20T04:00:00Z", "es")])

    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-s-9").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_engrossed-in-senate.xml",  # tier 4, before printed-as-passed on the same day
        "3_printed-as-passed.xml",  # tier 5
    ]


def test_convert_skips_corrupt_zip_without_aborting(tmp_path):
    # A truncated/garbage ZIP alongside good ones (e.g. an interrupted prior run)
    # must be skipped, not abort the whole conversion.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [_member(999, "hr", 7, "ih", "2025-01-01"), _member(999, "hr", 7, "eh", "2025-02-01")],
    )
    (zip_dir / "BILLS-999-2-hr.zip").write_bytes(b"not a real zip file")
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats["corrupt_zip_skipped"] == 1
    assert stats["bills_written"] == 1
    assert (out / "999-hr-7").exists()


def test_convert_repeated_type_ordered_by_own_date(tmp_path):
    # eas and eas2 both resolve to "Engrossed Amendment Senate"; they must stay
    # ordered by their own govinfo dates, not collapse to an arbitrary order.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 6, "ih", "2025-01-01"),
            _member(999, "hr", 6, "eas2", "2025-07-02"),
            _member(999, "hr", 6, "eas", "2025-07-01"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    d = out / "999-hr-6"
    # Both eas versions share the slug; the earlier-dated eas must get the lower index.
    assert b">eas<" in (d / "2_engrossed-amendment-senate.xml").read_bytes()
    assert b">eas2<" in (d / "3_engrossed-amendment-senate.xml").read_bytes()


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
