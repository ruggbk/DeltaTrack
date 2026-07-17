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
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable
from pathlib import Path

import httpx

BULK_BASE = "https://www.govinfo.gov/bulkdata"

# Bill version codes (govinfo "About Congressional Bills") -> (display name, tier).
# Single source of truth; NAME_TO_CODE is derived below. The display name is
# sanitized to the slug the corpus uses ("Reported in House" -> reported-in-house).
# Tier ranks how final the *text* is; it only breaks date ties and places the
# undated enrolled/engrossed versions (see fetch_bill_text_archives.convert_archives).
VERSION_CODES: dict[str, tuple[str, int]] = {
    "ih": ("Introduced in House", 1),
    "is": ("Introduced in Senate", 1),
    "rfh": ("Referred in House", 2),
    "rfs": ("Referred in Senate", 2),
    "rdh": ("Received in House", 2),
    "rds": ("Received in Senate", 2),
    "rch": ("Reference Change House", 2),
    "rcs": ("Reference Change Senate", 2),
    "rh": ("Reported in House", 3),
    "rs": ("Reported in Senate", 3),
    "pcs": ("Placed on Calendar Senate", 3),
    "pch": ("Placed on Calendar House", 3),
    "eh": ("Engrossed in House", 4),
    "es": ("Engrossed in Senate", 4),
    "eah": ("Engrossed Amendment House", 4),
    "eas": ("Engrossed Amendment Senate", 4),
    "reah": ("Re-engrossed Amendment House", 4),
    "cph": ("Considered and Passed House", 4),
    "cps": ("Considered and Passed Senate", 4),
    "ath": ("Agreed to House", 4),
    "ats": ("Agreed to Senate", 4),
    "enr": ("Enrolled Bill", 5),
    "renr": ("Reprint of Enrolled Bill", 5),
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

# The govinfo version code embedded in a BILLS package URL, e.g.
# https://www.govinfo.gov/content/pkg/BILLS-119s337rs/xml/BILLS-119s337rs.xml -> "rs".
_URL_CODE_RE = re.compile(r"/BILLS-\d+[a-z]+\d+([a-z0-9]+)\.(?:xml|htm|pdf)\b", re.IGNORECASE)


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
    """
    for url in item.iter("url"):
        m = _URL_CODE_RE.search(url.text or "")
        if m:
            return m.group(1).lower()
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
