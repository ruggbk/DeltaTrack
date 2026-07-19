#!/usr/bin/env -S uv run --quiet python
"""GovInfo bulk-data access for bill text + metadata.

Replaces the Congress.gov API (``fetch_bills.py``) for both discovery and text
retrieval (issue #10). Same legacy GPO DTD bill XML, served from
govinfo.gov/bulkdata -- no API key, no rate limit, 113th Congress forward. The
BILLS text is byte-for-byte identical to the Congress.gov "Formatted XML" we
download today, so ``bill_tree.py`` needs no parser changes.

Two access patterns over the same bytes:
  - per-bill on-demand fetch (:func:`fetch_bill_xml` / :func:`fetch_title`) for
    the diff tool's discovery/fetch path.
  - bulk per-(congress, session, type) ZIPs for building a multi-version test
    corpus (see ``fetch_bill_text_archives.py``, which builds on this module).

Two collections:
  - BILLS:      full bill *text* XML (legacy bill.dtd), one file per version.
  - BILLSTATUS: bill *metadata* (title, subjects, version dates) for discovery
                and authoritative version ordering.

URL shapes:
  text (one version): {BASE}/BILLS/{congress}/{session}/{type}/BILLS-{congress}{type}{number}{ver}.xml
  text (bulk ZIP):    {BASE}/BILLS/{congress}/{session}/{type}/BILLS-{congress}-{session}-{type}.zip
  status (one bill):  {BASE}/BILLSTATUS/{congress}/{type}/BILLSTATUS-{congress}{type}{number}.xml

Incorporates the per-bill fetch prototype (fetch_bill_xml / fetch_title /
sessions_for_congress), originally by @willhea.
"""

from __future__ import annotations

import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from shared.http import request_with_retry

BULK_BASE = "https://www.govinfo.gov/bulkdata"
# govinfo bulk data's earliest Congress: 111/112 and older 404 for every file
# (BILLS and BILLSTATUS alike), 113 forward returns 200. ADR 0004 scopes older
# bills out of the default corpus; the Congress.gov API still serves them, so a
# pre-113 govinfo request fails fast pointing at --source api (issue #10).
MIN_CONGRESS = 113
# Package-content base: per-version XML/PDF addressed by package id, e.g.
# .../content/pkg/BILLS-118hr4366rh/xml/BILLS-118hr4366rh.xml. Byte-identical to
# the bulkdata BILLS path and, unlike bulkdata, needs no session in the URL and no
# API key (verified at corpus scale, issue #10). The per-bill fetch path builds
# these from the package id in each BILLSTATUS textVersions URL.
CONTENT_BASE = "https://www.govinfo.gov/content/pkg"

# Bill version codes -> (display name, tier). Single source of truth; NAME_TO_CODE is
# derived below. The display name is sanitized to the slug the corpus uses ("Reported
# in House" -> reported-in-house), so a name that keys an on-disk corpus file cannot be
# changed without renaming that file (and breaking tests/test_govinfo_corpus_parity.py).
#
# The full authoritative code set is govinfo's (govinfo.gov/help/bills, 53 codes; the
# superset congress.gov's list is a subset of), inherited wholesale (#238) so no real
# code falls through resolve_code() to a tier-0 raw-code label -- the unreadable-
# filename bug (3_rth.xml) that #223 closed for rth/ris and #238 closes for all 53.
# Names: the codes that key on-disk corpus files keep their existing corpus-stable
# wording (which is also congress.gov's); the rest use authoritative wording. Where
# govinfo and congress.gov diverge only in the chamber suffix ("(House)" vs " House"),
# the existing table's no-parens style is used for consistency (parens sanitize away).
#
# Tier ranks how final the *text* is; it only breaks date ties and places the undated
# enrolled/engrossed versions (see fetch_bill_text_archives.convert_archives). Tier is
# our own construct (neither source publishes it), assigned by legislative stage:
# introduce=1, refer/receive/reference/held=2, report/calendar/discharge/print=3,
# engross/pass/agree/amend/dispose=4, enroll/print-as-passed=5. Only the ~10 codes with
# on-disk corpus files (ih, rfs, rds, rh, rs, pcs, eh, eah, eas, enr) have load-bearing
# tiers; the rest never appear in an appropriations bill, so their tiers are best-effort
# stage placements (the admin/procedural codes -- ash, sas, sc, pav, pp, oph/ops, hdh/
# hds, rhuc -- do not map cleanly to the 5 stages; see PR for the full mapping review).
VERSION_CODES: dict[str, tuple[str, int]] = {
    # -- tier 1: introduced (+ sponsorship admin, near introduction) --
    "ih": ("Introduced in House", 1),
    "is": ("Introduced in Senate", 1),
    "ash": ("Additional Sponsors House", 1),
    "sas": ("Additional Sponsors Senate", 1),
    "sc": ("Sponsor Change", 1),
    # -- tier 2: referral / receipt / reference / held at desk --
    "rfh": ("Referred in House", 2),
    "rfs": ("Referred in Senate", 2),
    "rdh": ("Received in House", 2),
    "rds": ("Received in Senate", 2),
    "rch": ("Reference Change House", 2),
    "rcs": ("Reference Change Senate", 2),
    # rth/ris were missing, so resolve_code fell them through to tier 0 with the raw
    # code as the label -- unreadable filenames (3_rth.xml, 3_ris.xml), violating ADR
    # 0013's readable-label contract. #238 generalizes that fix to the whole table.
    "rth": ("Referred to Committee House", 2),
    "rts": ("Referred to Committee Senate", 2),
    "rih": ("Referral Instructions House", 2),
    "ris": ("Referral Instructions Senate", 2),
    "rah": ("Referred with Amendments House", 2),
    "ras": ("Referred with Amendments Senate", 2),
    "hdh": ("Held at Desk House", 2),
    "hds": ("Held at Desk Senate", 2),
    # -- tier 3: reported / calendar / committee discharged / print --
    "rh": ("Reported in House", 3),
    "rs": ("Reported in Senate", 3),
    "pch": ("Placed on Calendar House", 3),
    "pcs": ("Placed on Calendar Senate", 3),
    "cdh": ("Committee Discharged House", 3),
    "cds": ("Committee Discharged Senate", 3),
    "oph": ("Ordered to be Printed House", 3),
    "ops": ("Ordered to be Printed Senate", 3),
    "pp": ("Public Print", 3),
    "pav": ("Previous Action Vitiated", 3),
    # -- tier 4: engrossed / passed / agreed / amended / floor disposition --
    "eh": ("Engrossed in House", 4),
    "es": ("Engrossed in Senate", 4),
    "eah": ("Engrossed Amendment House", 4),
    "eas": ("Engrossed Amendment Senate", 4),
    "reah": ("Re-engrossed Amendment House", 4),
    "res": ("Re-engrossed Amendment Senate", 4),
    "eph": ("Engrossed and Deemed Passed by House", 4),
    "cph": ("Considered and Passed House", 4),
    "cps": ("Considered and Passed Senate", 4),
    "ath": ("Agreed to House", 4),
    "ats": ("Agreed to Senate", 4),
    "as": ("Amendment Ordered to be Printed Senate", 4),
    "fah": ("Failed Amendment House", 4),
    "fph": ("Failed Passage House", 4),
    "fps": ("Failed Passage Senate", 4),
    "iph": ("Indefinitely Postponed House", 4),
    "ips": ("Indefinitely Postponed Senate", 4),
    "lth": ("Laid on Table in House", 4),
    "lts": ("Laid on Table in Senate", 4),
    "pwah": ("Ordered to be Printed with House Amendment", 4),
    # rhuc: govinfo drops "the", congress.gov keeps it. Ruled to congress.gov's wording
    # ("Returned to the House...") -- the one added code taking congress.gov over govinfo.
    # url-bearing, so only affects display/slug if an rhuc version is ever downloaded.
    # Tier 4 (post-passage inter-chamber return); #238 suggested 3 -- flagged for review.
    # Resolves #223.
    "rhuc": ("Returned to the House by Unanimous Consent", 4),
    # -- tier 5: enrolled / printed as passed --
    "enr": ("Enrolled Bill", 5),
    "renr": ("Re-enrolled Bill", 5),
    "pap": ("Printed as Passed", 5),
}


def sanitize(name: str) -> str:
    """'Reported in House' -> 'reported-in-house' (matches fetch_bills.py slugs)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unknown"


# Derived reverse map: corpus slug -> version code (for building per-bill URLs
# from a known version label). Note #10 gotcha #1: to discover which versions
# *exist*, read the directory/ZIP listing rather than trusting a label vocabulary
# (BILLSTATUS says "Reported to Senate" while our slugs say "reported-in-senate").
NAME_TO_CODE: dict[str, str] = {sanitize(name): code for code, (name, _tier) in VERSION_CODES.items()}

# BILLSTATUS's textVersions <type> spells a few codes differently from VERSION_CODES'
# canonical display name, so the derived map above misses those spellings. This only
# bites the *name fallback* in _version_code_from_item -- i.e. url-less versions (the
# govinfo XML-less gap, #226), where there is no URL to read the code from. Across a
# 117-119 hr/s sweep "Reported to Senate" (canonical: "Reported in Senate") was the
# only divergence observed -- but that scope can't exercise every code: any code whose
# canonical name here diverges from its BILLSTATUS <type> spelling carries the same
# latent risk (a url-less version of it would drop uncoded). Public/Private Law are a
# different collection and stay unmapped by design. rhuc is now in VERSION_CODES (#238)
# but is url-bearing, so the name fallback never needs it.
NAME_TO_CODE.update({"reported-to-senate": "rs"})


def resolve_code(code: str) -> tuple[str, int]:
    """(display name, tier) for a version code, tolerant of numeric/suffixed variants.

    govinfo emits suffixed variants (eas2, rfs2, eh1s) for re-engrossments and
    repeat referrals. They are not in the base table, so fall back to the longest
    known prefix (eas2 -> eas -> tier 4) rather than tier 0, which would wrongly
    sort a late amendment before the introduced version.
    """
    if code in VERSION_CODES:
        return VERSION_CODES[code]
    for end in range(len(code) - 1, 1, -1):
        prefix = code[:end]
        if prefix in VERSION_CODES:
            return VERSION_CODES[prefix]
    return (code, 0)


def order_versions(codes_dates: Iterable[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """Order (version-code, BILLSTATUS-date) pairs into corpus sequence.

    BILLSTATUS date is the single ordering authority (issue #10). It is complete
    and available *before* any text is downloaded, so the per-bill fetch path --
    which must assign indices before it has bytes -- and the bulk convert path
    number a bill identically. The bulk path *could* read each version's own
    dc:date from the downloaded XML, but the per-bill path cannot; keying both on
    BILLSTATUS avoids a split-brain where the same bill numbers differently
    depending on how it was fetched. Keyed by the govinfo version code, the one
    identifier both sources share verbatim (BILLSTATUS's display ``<type>``
    diverges: "Reported to Senate" vs our "Reported in Senate").

    Rules:
      - Dates truncate to YYYY-MM-DD (``[:10]``) so a BILLSTATUS full datetime and
        a bare date on the same day compare equal and fall through to the
        tie-break rather than sorting by string length.
      - An undated version (empty date) sorts to the bill's latest date
        (null->max), placing the undated enrolled text last, not first.
      - Ties break by tier (how final the text is), then code (deterministic for
        repeated types like eas/eas2, kept in date then code order).

    Does not deduplicate: one entry out per entry in, so callers pass one pair
    per distinct version (convert_archives keys by code, so codes are unique).

    Returns ``[(code, date, tier)]`` in corpus order.
    """
    resolved = [(code, (date or "")[:10], resolve_code(code)[1]) for code, date in codes_dates]
    max_date = max((d for _c, d, _t in resolved if d), default="")
    return sorted(resolved, key=lambda r: (r[1] or max_date, r[2], r[0]))


# ---- URL builders -----------------------------------------------------------


def bill_xml_url(congress: int, session: int, bill_type: str, number: int, ver_code: str) -> str:
    """govinfo BILLS text-XML URL for one version."""
    fname = f"BILLS-{congress}{bill_type}{number}{ver_code}.xml"
    return f"{BULK_BASE}/BILLS/{congress}/{session}/{bill_type}/{fname}"


def bills_zip_url(congress: int, session: int, bill_type: str) -> str:
    """govinfo BILLS bulk-ZIP URL for one (congress, session, type)."""
    fname = f"BILLS-{congress}-{session}-{bill_type}.zip"
    return f"{BULK_BASE}/BILLS/{congress}/{session}/{bill_type}/{fname}"


def billstatus_url(congress: int, bill_type: str, number: int) -> str:
    """govinfo BILLSTATUS metadata-XML URL for one bill."""
    fname = f"BILLSTATUS-{congress}{bill_type}{number}.xml"
    return f"{BULK_BASE}/BILLSTATUS/{congress}/{bill_type}/{fname}"


def package_content_url(pkg: str, fmt: str) -> str:
    """content/pkg URL for one BILLS package version. ``fmt`` is 'xml' or 'pdf'.

    ``pkg`` is the package id (``BILLS-118hr4366rh``). Session-free and keyless,
    byte-identical to the bulkdata BILLS path (issue #10). Used to build the
    format URLs the per-bill fetch path downloads.
    """
    return f"{CONTENT_BASE}/{pkg}/{fmt}/{pkg}.{fmt}"


# ---- per-bill fetch (incorporated from the @willhea prototype) ---------------


def sessions_for_congress(congress: int) -> tuple[int, int]:
    """The two sessions of a Congress. govinfo splits BILLS by session (1/2)."""
    return (1, 2)


def fetch_bill_xml(
    client: httpx.Client, congress: int, bill_type: str, number: int, ver_code: str
) -> tuple[bytes | None, str | None]:
    """Download a version's text XML, probing both sessions of the Congress.

    Returns (content, url) or (None, None) if not found in either session.
    """
    for session in sessions_for_congress(congress):
        url = bill_xml_url(congress, session, bill_type, number, ver_code)
        resp = client.get(url)
        if resp.status_code == 200:
            return resp.content, url
    return None, None


def fetch_title(client: httpx.Client, congress: int, bill_type: str, number: int) -> str | None:
    """Pull the bill title from BILLSTATUS metadata (the field the committee API drops)."""
    url = billstatus_url(congress, bill_type, number)
    resp = client.get(url)
    if resp.status_code != 200:
        return None
    root = ET.fromstring(resp.content)
    el = root.find(".//bill/title")
    return el.text if el is not None else None


# ---- BILLSTATUS version dates (authoritative ordering for bulk downloads) ----

# The BILLS package id embedded in a textVersions format URL, e.g.
# https://www.govinfo.gov/content/pkg/BILLS-119s337rs/xml/BILLS-119s337rs.xml
# -> "BILLS-119s337rs". Matches only the BILLS collection: a Public-Law item
# carries a PLAW-* url, so it does not match and is treated as url-less.
_URL_PKG_RE = re.compile(r"/(BILLS-\d+[a-z]+\d+[a-z0-9]+)\.(?:xml|htm|pdf)\b", re.IGNORECASE)
# Split the package id back into its trailing version code: BILLS-119s337rs -> rs.
_PKG_CODE_RE = re.compile(r"^BILLS-\d+[a-z]+\d+([a-z0-9]+)$", re.IGNORECASE)


def _version_pkg_from_item(item: ET.Element) -> str | None:
    """The BILLS package id from a textVersions <item>'s format URL, else None.

    URL-only, no name fallback. An item that carries no BILLS format URL is a
    phantom -- a Public Law (a different collection) or an unpublished amendment
    (115-hr-1625's "Engrossed Amendment House") -- and returns None here so the
    enumeration path can drop it. This is deliberately the *non*-fallback half of
    :func:`_version_code_from_item`: reusing that function's name fallback for
    enumeration would invent a code for these phantoms and seat them in the list.
    """
    for url in item.iter("url"):
        m = _URL_PKG_RE.search(url.text or "")
        if m:
            return m.group(1)
    return None


def _code_from_pkg(pkg: str) -> str | None:
    """'BILLS-119s337rs' -> 'rs' (the trailing version code), else None."""
    m = _PKG_CODE_RE.match(pkg)
    return m.group(1).lower() if m else None


def _version_code_from_item(item: ET.Element) -> str | None:
    """Extract the govinfo version code from a BILLSTATUS textVersions <item>.

    Primary: the code embedded in the item's format URL. It is unambiguous and
    survives the <type>-vs-VERSION_CODES name divergence ("Reported to Senate"
    vs "Reported in Senate"), so the URL is preferred whenever present.

    Fallback: some items carry a <type> and <date> but no BILLS format URL (govinfo
    has not published one yet). Map the display name to a code so these still land
    in the index -- notably engrossed-in-house, whose ordering depends entirely on
    this fallback. Only the handful of names BILLSTATUS spells differently from
    VERSION_CODES stay unresolved here, which is no worse than a name-based join.

    This is the *full* resolver used by :func:`build_billstatus_date_index`, where
    the bulk ZIP already says which versions exist so the name fallback is safe.
    The enumeration path must NOT use it (see :func:`_version_pkg_from_item`).
    """
    pkg = _version_pkg_from_item(item)
    if pkg:
        return _code_from_pkg(pkg)
    typ = item.findtext("type")
    return NAME_TO_CODE.get(sanitize(typ)) if typ else None


def build_billstatus_date_index(billstatus_dir: Path) -> dict[str, dict[str, str]]:
    """{bill_id: {version-code: date}} from local BILLSTATUS ZIPs.

    The govinfo BILLS text carries dc:date only ~74% of the time, and it is
    missing on exactly the versions whose order is load-bearing (engrossed-in-
    house). BILLSTATUS metadata (downloaded by fetch_bill_archives.py) supplies
    the complete, authoritative dates -- the same source the curated corpus was
    ordered from -- so bulk-downloaded versions order correctly.

    Keyed by the govinfo *version code* (extracted from each textVersions item's
    format URL, e.g. .../BILLS-119s337rs.xml -> ``rs``), not the display-name.
    BILLSTATUS's ``<type>`` vocabulary diverges from VERSION_CODES's names for
    some versions (it says "Reported to Senate" where our table says "Reported
    in Senate"), so a name-based join would silently miss those and mis-order
    the very versions this index exists to place. The code is the one identifier
    both sides share verbatim, including suffixed variants (eas2, rfs2).
    """
    index: dict[str, dict[str, str]] = {}
    for zp in sorted(billstatus_dir.glob("*.zip")):
        try:
            zf = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        for name in zf.namelist():
            if not Path(name).name.startswith("BILLSTATUS"):
                continue
            try:
                bill = ET.fromstring(zf.read(name)).find("bill")
            except Exception:
                continue
            if bill is None:
                continue
            congress = bill.findtext("congress")
            btype = (bill.findtext("type") or "").lower()
            number = bill.findtext("number")
            tv = bill.find("textVersions")
            if not (congress and btype and number) or tv is None:
                continue
            dates: dict[str, str] = {}
            for it in tv.findall("item"):
                code = _version_code_from_item(it)
                if code:
                    dates[code] = it.findtext("date") or ""
            if dates:
                index[f"{congress}-{btype}-{number}"] = dates
    return index


# ---- title-search index (discovery by title; approps as a facet) ------------
#
# #10's last acceptance item: find any bill by title over an index built from the
# local BILLSTATUS ZIPs (the same source build_billstatus_date_index reads, and
# fetch_bill_archives.py downloads -- keyless, no network). Appropriations is a
# facet, not the discovery gate it is in the committee-API pipeline: it keys on
# committee referral systemCode (hsap00/ssap00), which #10 found more precise than
# the "Appropriations" subject term, and is independent of the title text.

APPROPRIATIONS_SYSTEM_CODES = frozenset({"hsap00", "ssap00"})


def _committee_system_codes(bill: ET.Element) -> set[str]:
    """Committee referral systemCodes for a BILLSTATUS bill (modern or legacy layout)."""
    items = bill.findall("committees/item")
    if not items:
        items = bill.findall("committees/billCommittees/item")
    codes = {(it.findtext("systemCode") or "").strip().lower() for it in items}
    codes.discard("")
    return codes


def build_title_index(billstatus_dir: Path) -> dict[str, dict]:
    """``{bill_id: {"title": str, "committee_codes": set[str]}}`` from local BILLSTATUS ZIPs.

    Mirrors :func:`build_billstatus_date_index`: walks every ``*.zip`` in
    ``billstatus_dir``, reading its ``BILLSTATUS-*`` members. Scope is whatever ZIPs
    are present locally -- no hardcoded congress/type, and no network. ``committee_codes``
    backs the appropriations facet (see :func:`search_titles`).
    """
    index: dict[str, dict] = {}
    for zp in sorted(billstatus_dir.glob("*.zip")):
        try:
            zf = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        for name in zf.namelist():
            if not Path(name).name.startswith("BILLSTATUS"):
                continue
            try:
                bill = ET.fromstring(zf.read(name)).find("bill")
            except Exception:
                continue
            if bill is None:
                continue
            congress = bill.findtext("congress")
            btype = (bill.findtext("type") or bill.findtext("billType") or "").strip().lower()
            # Legacy BILLSTATUS layout pairs <billType> with <billNumber> (not <number>);
            # read both so a legacy-format member isn't silently dropped by the guard below.
            # #10's migration scope reaches back to the 113th, where un-regenerated legacy
            # files exist in the bulk data.
            number = bill.findtext("number") or bill.findtext("billNumber")
            title = (bill.findtext("title") or "").strip()
            if not (congress and btype and number):
                continue
            index[f"{congress}-{btype}-{number}"] = {
                "title": title,
                "committee_codes": _committee_system_codes(bill),
            }
    return index


# ASCII fold for title matching (#244). BILLSTATUS titles are typeset, not ASCII:
# over the live corpus (43,267 titles) 1,292 carry non-ASCII, dominated by the
# curly apostrophe U+2019 (1,024) and the en dash U+2013 (217), with a smaller
# accented-letter tail (~73). A user or agent types ASCII, so an unfolded match
# silently misses those bills -- and the miss reads exactly like "no such bill".
# The fold is applied to BOTH the query and the title, so it corrects either
# side's typography rather than assuming which side is "clean".
_PUNCT_FOLD = {
    # Single quotes / apostrophes -> ASCII '
    0x2018: "'",
    0x2019: "'",
    0x201A: "'",
    0x201B: "'",
    0x2032: "'",
    # Double quotes -> ASCII "
    0x201C: '"',
    0x201D: '"',
    0x201E: '"',
    0x201F: '"',
    0x2033: '"',
    # Dash-likes -> ASCII -
    0x2010: "-",
    0x2011: "-",
    0x2012: "-",
    0x2013: "-",
    0x2014: "-",
    0x2015: "-",
    0x2212: "-",
    # Invisible/whitespace variants: the soft hyphen has no glyph, so a title
    # containing one looks identical to the ASCII query that fails to match it.
    # Drop it outright rather than mapping it to a visible character.
    0x00AD: None,
    0x00A0: " ",
    0x2007: " ",
    0x202F: " ",
    0xFEFF: None,
}


# Latin letters carrying no combining mark, so the NFD pass below cannot reach
# them: a stroked or ligated letter is one indivisible code point. Without these
# the fold silently UNDER-corrects ("lodz" would still miss "Łódź", whose ó and ź
# fold but whose Ł does not). Listed transliterations are the conventional ones.
_LETTER_FOLD = {
    0x0141: "L",
    0x0142: "l",  # Ł ł
    0x00D8: "O",
    0x00F8: "o",  # Ø ø
    0x0110: "D",
    0x0111: "d",  # Đ đ
    0x00C6: "AE",
    0x00E6: "ae",  # Æ æ
    0x0152: "OE",
    0x0153: "oe",  # Œ œ
    0x00DE: "Th",
    0x00FE: "th",  # Þ þ
    0x00D0: "D",
    0x00F0: "d",  # Ð ð
    0x00DF: "ss",  # ß
}

# Deliberately NOT folded: phonetic and modifier letters (ʔ glottal stop, ə schwa,
# ɬ l-with-belt, ʷ modifier w) and symbols (®). These are letters in their own
# right, not accented Latin ones, so there is no ASCII form a user would
# predictably type -- guessing one would invent matches rather than recover them.
# Reaching them would take NFKD (compatibility) rather than the NFD (canonical)
# pass used here, and NFKD also rewrites ligatures, fractions and superscripts,
# which is a broader transformation than title matching wants. Titles containing
# them stay discoverable through their other tokens (the match is AND-of-tokens).


def _fold_for_match(text: str) -> str:
    """Normalize typographic punctuation and accented letters to ASCII, for comparison only.

    Never applied to a stored or displayed title -- callers keep the original
    text and fold only the key they match on.
    """
    folded = text.translate(_PUNCT_FOLD).translate(_LETTER_FOLD)
    # NFD splits a precomposed letter into base + combining mark(s); dropping the
    # marks leaves the base ("é" -> "e"). NFD (canonical) not NFKD (compatibility)
    # -- see the note above _fold_for_match's tables. Characters that are not
    # accented Latin letters have no combining mark and pass through untouched.
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _bill_id_sort_key(bill_id: str) -> tuple[int, str, int]:
    congress, btype, number = bill_id.split("-")
    return (int(congress), btype, int(number))


def search_titles(index: dict[str, dict], query: str, *, appropriations: bool = False) -> list[tuple[str, str]]:
    """Return ``[(bill_id, title), ...]`` for bills whose title matches ``query``.

    Match is case-insensitive AND-of-tokens substring on the title, over a
    typographic-punctuation fold applied to both sides (see :func:`_fold_for_match`),
    so an ASCII apostrophe reaches a curly one and vice versa. ``appropriations``
    is an *additive facet*: when set, it further keeps only bills referred to the
    appropriations committee (systemCode hsap00/ssap00) -- it never gates a plain
    title search. Results are sorted by (congress, type, number) for determinism.
    """
    tokens = _fold_for_match(query).lower().split()
    results: list[tuple[str, str]] = []
    for bill_id, entry in index.items():
        title = entry["title"]
        if not title:
            continue
        low = _fold_for_match(title).lower()
        if not all(tok in low for tok in tokens):
            continue
        if appropriations and not (entry["committee_codes"] & APPROPRIATIONS_SYSTEM_CODES):
            continue
        results.append((bill_id, title))
    return sorted(results, key=lambda r: _bill_id_sort_key(r[0]))


# ---- per-bill version enumeration (the API-source drop-in) -------------------
#
# fetch_bills.py's per-bill path (versions / download / download-all --file)
# discovers a bill's versions from the Congress.gov API's textVersions payload:
# a list of {type, date, formats:[{type, url}]} dicts that download_version /
# format_version_list consume. enumerate_versions produces that *same* shape from
# BILLSTATUS so those consumers, and their tests, are untouched when --source
# flips to govinfo (issue #10). The seam is the dict shape, not a refactor.


def versions_from_billstatus(bill: ET.Element) -> list[dict]:
    """API-shaped, corpus-ordered version list from a BILLSTATUS ``<bill>`` element.

    Enumerates ONLY textVersions items that carry a BILLS format URL. An item
    without one is a phantom -- a Public Law (a different collection) or an
    unpublished amendment (115-hr-1625's "Engrossed Amendment House") -- and is
    excluded. The exclusion is the point: :func:`_version_code_from_item`'s name
    fallback would invent a code for such an item and seat it in the list, so the
    URL-only :func:`_version_pkg_from_item` is used here instead. The failure mode
    of a name-based enumeration is fail-open (a phantom silently enters), which is
    exactly what url-only closes.

    Ordering is :func:`order_versions` -- BILLSTATUS date as the single authority,
    identical to the bulk convert path -- so the same bill numbers the same way
    however it was fetched.

    Each returned dict is ``{"type": display-name, "date": billstatus-date,
    "formats": [{"type": "Formatted XML", "url": ...}, {"type": "PDF", "url": ...}]}``.
    Both format URLs are the session-free content/pkg address built from the
    package id; the fetch step validates each on download.
    """
    tv = bill.find("textVersions")
    if tv is None:
        return []
    # code -> (original BILLSTATUS date, package id). Codes are unique within a
    # bill (eas vs eas2 are distinct codes), so keying by code is lossless.
    by_code: dict[str, tuple[str, str]] = {}
    for item in tv.findall("item"):
        pkg = _version_pkg_from_item(item)
        if pkg is None:
            continue  # phantom / url-less: excluded, do not name-fallback
        code = _code_from_pkg(pkg)
        if code is None:
            continue
        by_code[code] = (item.findtext("date") or "", pkg)

    versions: list[dict] = []
    for code, _date_trunc, _tier in order_versions((c, d) for c, (d, _p) in by_code.items()):
        orig_date, pkg = by_code[code]
        name, _tier = resolve_code(code)
        versions.append(
            {
                "type": name,
                "date": orig_date,
                "formats": [
                    {"type": "Formatted XML", "url": package_content_url(pkg, "xml")},
                    {"type": "PDF", "url": package_content_url(pkg, "pdf")},
                ],
            }
        )
    return versions


def urlless_declared_versions(bill: ET.Element) -> list[tuple[str, str]]:
    """``[(code, display-name)]`` for versions govinfo can't serve as XML.

    These are BILLSTATUS textVersions items with **no BILLS format URL** whose
    ``<type>`` still resolves to a real version code -- the govinfo XML-less "gap"
    versions (#226): GPO published the PDF/HTML rendition but never composed the
    XML the diff engine reads, so the version is *declared* yet unfetchable as
    XML. :func:`versions_from_billstatus` correctly excludes them from the
    downloadable list (there is no XML to fetch), but they must be *surfaced*, not
    silently dropped (#226 AC#1) -- else a bill diffs as "N versions" with a real
    N+1th version invisibly missing.

    A url-less item whose ``<type>`` does **not** resolve is the Public/Private
    Law collection (a different collection, ``PLAW-*``), an expected skip -- it is
    omitted here so only genuine bill-version gaps are surfaced. (The resolve step
    reuses :func:`_version_code_from_item`'s name fallback, so a new BILLSTATUS
    spelling divergence would misclassify a gap version as a law and re-hide it;
    a standing gate against that is tracked in #231.)
    """
    tv = bill.find("textVersions")
    if tv is None:
        return []
    gaps: list[tuple[str, str]] = []
    for item in tv.findall("item"):
        if _version_pkg_from_item(item) is not None:
            continue  # url-bearing: a real, fetchable version
        code = _version_code_from_item(item)  # url-less: name fallback only
        if code is None:
            continue  # Public/Private Law (or unmappable): expected skip
        gaps.append((code, resolve_code(code)[0]))
    return gaps


class CongressNotAvailable(Exception):
    """A requested Congress predates govinfo's bulk-data floor (:data:`MIN_CONGRESS`).

    Raised so the caller can fail fast with an actionable message rather than
    letting every per-file fetch 404 into a silent empty download (issue #10).
    """


def require_supported_congress(congress: int) -> None:
    """Fail fast if ``congress`` predates govinfo's bulk floor.

    govinfo serves the 113th Congress forward; 111/112 and earlier 404 for every
    BILLS/BILLSTATUS file, which would otherwise surface as a bill that silently
    "has no versions". Point the user at ``--source api``, which still serves
    older Congresses (ADR 0004 scopes them out of the default corpus).
    """
    if congress < MIN_CONGRESS:
        raise CongressNotAvailable(
            f"govinfo bulk data starts at the {MIN_CONGRESS}th Congress; "
            f"Congress {congress} is not available there. "
            f"Re-run with --source api for pre-{MIN_CONGRESS} bills."
        )


def enumerate_versions(client: httpx.Client, congress: int, bill_type: str, number: int) -> list[dict]:
    """Fetch one bill's BILLSTATUS and return its ordered, API-shaped versions.

    Drop-in for ``fetch_bills.fetch_text_versions`` on the govinfo source. Raises
    on a non-200 BILLSTATUS response rather than mapping it to an empty list: an
    enumeration failure must be loud, not a silent "bill has no versions" that
    numbers a partial download as if it were complete (issue #10). A bill that
    genuinely exists but has no published text yields an empty list from a 200.

    Any BILLSTATUS-declared version govinfo can't serve as XML (the XML-less gap,
    #226 AC#1) is surfaced as a stderr warning here rather than silently dropped;
    it is still absent from the returned (downloadable) list.
    """
    resp = request_with_retry(client, billstatus_url(congress, bill_type, number))
    # request_with_retry already raises on persistent 429/5xx (and on 4xx), so this
    # is belt-and-suspenders: it keeps a BILLSTATUS enumeration failure loud even if
    # that helper's contract ever changes to a non-raising return (its fetch_bills
    # callers guard with `if resp else`), never a silent "bill has no versions" (#10).
    resp.raise_for_status()
    bill = ET.fromstring(resp.content).find("bill")
    if bill is None:
        return []
    gaps = urlless_declared_versions(bill)
    if gaps:
        listed = ", ".join(f"{code} ({name})" for code, name in gaps)
        print(
            f"WARNING: {len(gaps)} version(s) declared in BILLSTATUS but not available "
            f"as govinfo XML (XML-less gap, #226/#228): {listed}",
            file=sys.stderr,
        )
    return versions_from_billstatus(bill)
