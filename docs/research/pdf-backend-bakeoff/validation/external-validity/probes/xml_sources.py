"""xml_sources -- A40/F1/F2: independent account-heading source truth, from the committed XML.

    frozen rule   A40.3 -- no H or X output may participate in eligibility, ranking or
                  targeting of an N-A/N-B control source
    executable    `account_records()` (XML), `locate_occurrences()` (PDF), `bridge()` (both)
    test          `x24_xml_source_bridge.py`

NOTHING HERE IMPORTS OR CALLS AN ARCHITECTURE. There is no `run_hybrid`, no `run_extended`, and
no `pdf_anchors.extract_anchors` on any path in this module. `x24` proves that by making all
three raise on import and requiring the source population, eligibility, ranking and selected
identities to come out byte-identical.

WHAT ESTABLISHES "ACCOUNT", AND ON WHOSE AUTHORITY. Both committed DEVELOPMENT sources declare

    <!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN" "bill.dtd">
    <bill bill-type="appropriations" ...>

the LEGACY US Congress bill DTD (not USLM). That schema has no `<account>` element -- there are
zero in this corpus -- and expresses the appropriations hierarchy as three flat, non-nesting
sibling levels under `<title>`:

    appropriations-major         the major grouping
    appropriations-intermediate  the agency
    appropriations-small         THE ACCOUNT

The authority for that mapping is GPO's own renderer, not this study's parser: `bills.css` and
`billres-details.xsl` style the three levels distinctly, and `docs/gpo-render-conventions.md`
records the correspondence (`appropriations-intermediate` (agency), `appropriations-small`
(account)) with `docs/bill-structure.md` documenting the flat-sibling nesting. The direction
matters: the XML CARRIES the hierarchy explicitly and the PDF-side segmentation is what has to
RECOVER it -- so reading the account level off the XML uses the authority, while reading it off
an H anchor's `kind` would be reading the reconstruction under test.

TWO STRUCTURAL FACTS THAT MUST NOT BE ASSUMED AWAY, both measured on the committed files:

  * `header` is a CHILD ELEMENT here, never the attribute the prose examples abbreviate it to
    (105/105 and 41/41 child, 0 attribute). A header-LESS `appropriations-small` is the money
    half of a split account (2 and 3 of them) and carries no printed heading, so it is excluded.

  * THE XML HEADER IS NOT THE PRINTED STRING. `billres-details.xsl` applies
    `translate($upper,$lower)` to this level, so 114-hr-2029 stores `Compensation and pensions`
    while the page prints it in capitals. The XML therefore establishes WHICH heading and that
    it is an account; the exact printed characters are read back from the PDF and are what the
    adjudicator will transcribe.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ACCOUNT_ELEMENT = "appropriations-small"
AGENCY_ELEMENT = "appropriations-intermediate"
MAJOR_ELEMENT = "appropriations-major"
EXPECTED_DOCTYPE_PUBLIC_ID = "-//US Congress//DTDs/bill.dtd//EN"

# physical-bridge refusal classes -- every one fails closed
NO_PHYSICAL_OCCURRENCE = "NO_PHYSICAL_OCCURRENCE"
GROUP_COUNT_MISMATCH = "GROUP_COUNT_MISMATCH"
AMBIGUOUS_PHYSICAL_ORDER = "AMBIGUOUS_PHYSICAL_ORDER"
ORDER_INVERSION = "ORDER_INVERSION"
CROSSES_INDEPENDENT_ANCHOR = "CROSSES_INDEPENDENT_ANCHOR"
UNEXPECTED_SCHEMA = "UNEXPECTED_SCHEMA"


class XmlSourceError(Exception):
    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def normalize(s: str) -> str:
    """NFKC + whitespace-run collapse + strip. CASE IS PRESERVED (section 6.2's rule)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def schema_identity(xml_path) -> dict:
    """The committed file's own schema declaration, read from the bytes."""
    head = Path(xml_path).read_text(errors="replace")[:2048]
    doctype = re.search(r"<!DOCTYPE\s+(\S+)\s+PUBLIC\s+\"([^\"]+)\"\s+\"([^\"]+)\"", head)
    stylesheet = re.search(r'<\?xml-stylesheet[^>]*href="([^"]+)"', head)
    if not doctype:
        raise XmlSourceError(UNEXPECTED_SCHEMA, {"path": str(xml_path), "why": "no DOCTYPE"})
    return {
        "doctype_root": doctype.group(1),
        "public_id": doctype.group(2),
        "system_id": doctype.group(3),
        "stylesheet": stylesheet.group(1) if stylesheet else None,
    }


def account_records(xml_path) -> list[dict]:
    """Every structurally identified ACCOUNT heading in one committed XML file.

    The predicate is structural and nothing else: element name `appropriations-small`, carrying
    a `<header>` child. No text heuristic, no casing test, and no architecture output.
    """
    xml_path = Path(xml_path)
    schema = schema_identity(xml_path)
    if schema["public_id"] != EXPECTED_DOCTYPE_PUBLIC_ID:
        raise XmlSourceError(UNEXPECTED_SCHEMA, {"path": str(xml_path), "schema": schema})

    root = ET.parse(xml_path).getroot()
    parent = {child: p for p in root.iter() for child in p}

    def ancestor_path(el) -> str:
        out, cur = [], el
        while cur is not None:
            out.append(cur.tag)
            cur = parent.get(cur)
        return "/".join(reversed(out))

    records, ordinal = [], 0
    for el in root.iter():
        if el.tag != ACCOUNT_ELEMENT:
            continue
        header = el.find("header")
        if header is None:
            continue  # the money half of a split account: no printed heading of its own
        source_text = normalize("".join(header.itertext()))
        if not source_text:
            continue
        records.append(
            {
                "element": el.tag,
                "element_id": el.get("id"),
                "ancestor_path": ancestor_path(el),
                "xml_source_text": source_text,
                "xml_document_ordinal": ordinal,
                "schema_public_id": schema["public_id"],
                "schema_system_id": schema["system_id"],
                "doctype_root": schema["doctype_root"],
                "stylesheet": schema["stylesheet"],
            }
        )
        ordinal += 1
    return records


# ------------------------------------------------------------- independent PDF locator


#: GPO's documented margin-number convention -- the same `^(\d{1,2}) (.*)$` shape section 6
#: records for production's `_coverage`. Stripped before comparison because the margin number
#: is page furniture, not part of the heading.
MARGIN_NUMBER = re.compile(r"^\s*\d{1,2}\s+")


def physical_lines(pdf_path) -> list[dict]:
    """Every printed line on every page, with geometry. Independent renderer, no architecture."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        out = []
        for pno in range(doc.page_count):
            page = doc[pno]
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = normalize("".join(span["text"] for span in line["spans"]))
                    if text:
                        out.append(
                            {
                                "page_number": pno + 1,
                                "bbox_topleft": list(line["bbox"]),
                                "printed_text": text,
                                "page_height": page.rect.height,
                            }
                        )
        out.sort(key=lambda h: (h["page_number"], round(h["bbox_topleft"][1], 3), round(h["bbox_topleft"][0], 3)))
        return out
    finally:
        doc.close()


def locate_occurrences(lines: list[dict], needle: str) -> list[dict]:
    """Physical occurrences where the printed LINE IS the heading, in physical print order.

    WHOLE-LINE OCCUPANCY, and it is a structural constraint rather than a typographic one. A
    match counts only when the heading is the entire printed line once its margin number is
    stripped. That excludes the same words occurring inside body prose -- which is what made a
    plain substring search refuse almost every real account name for count mismatch -- WITHOUT
    consulting size, case, centering or any other heading cue. Classifying by those would be
    re-implementing the PDF-side heading recognition that is under test.

    Case-insensitive comparison is licensed by GPO's own stylesheet, which applies
    `translate($upper,$lower)` at this level, so the XML string and the printed string
    legitimately differ in case. The exact PRINTED characters are what is returned and what
    every downstream expectation uses; the XML casing is never the expected text.

    Ordering is physical -- page, then vertical, then horizontal -- so it is a property of the
    page rather than of any extraction order.
    """
    target = normalize(needle).upper()
    return [line for line in lines if MARGIN_NUMBER.sub("", line["printed_text"]).upper() == target]


def _physically_ordered(hits: list[dict]) -> bool:
    """Is the physical order strict? Two hits at the same page/y/x are indistinguishable."""
    keys = [(h["page_number"], round(h["bbox_topleft"][1], 3), round(h["bbox_topleft"][0], 3)) for h in hits]
    return len(set(keys)) == len(keys)


def bridge(pdf_path, records: list[dict]) -> dict:
    """A40 -- pair XML account records with physical PDF occurrences, or REFUSE the group.

    The rule, and it is deliberately narrow: within ONE structurally identical source-text
    group, sort the XML occurrences in XML document order, sort the independently located PDF
    occurrences in physical print order, require EQUAL POSITIVE COUNTS, and pair index to
    index. Anything else refuses the WHOLE group.

    This is not a claim that arbitrary XML and PDF order always agree. It is licensed only by
    the validation `x24` performs first: every group whose occurrences are independently and
    uniquely identifiable is checked for order agreement, and the pairing rule is used only
    where that evidence holds and the counts match exactly.
    """
    lines = physical_lines(pdf_path)
    by_text: dict[str, list[dict]] = {}
    for r in records:
        by_text.setdefault(r["xml_source_text"], []).append(r)

    paired, refusals = [], []
    for text, group in sorted(by_text.items()):
        hits = locate_occurrences(lines, text)
        if not hits:
            refusals.append({"reason": NO_PHYSICAL_OCCURRENCE, "text": text, "xml_count": len(group)})
            continue
        if len(hits) != len(group):
            refusals.append(
                {"reason": GROUP_COUNT_MISMATCH, "text": text, "xml_count": len(group), "pdf_count": len(hits)}
            )
            continue
        if not _physically_ordered(hits):
            refusals.append({"reason": AMBIGUOUS_PHYSICAL_ORDER, "text": text, "pdf_count": len(hits)})
            continue
        for rec, hit in zip(sorted(group, key=lambda r: r["xml_document_ordinal"]), hits):
            paired.append({**rec, **hit, "group_size": len(group)})
    paired.sort(key=lambda p: p["xml_document_ordinal"])
    return {"paired": paired, "refusals": refusals, "n_xml": len(records), "n_paired": len(paired)}


def order_agreement(paired: list[dict]) -> dict:
    """Does XML document order agree with physical print order on the paired set?

    Reported per document, and computed on the UNIQUE-occurrence subset first: those are the
    records whose physical identity needs no pairing rule at all, so they are the independent
    evidence for whether the ordering assumption holds before it is relied on.
    """
    unique = [p for p in paired if p["group_size"] == 1]
    inversions = []
    for name, subset in (("unique_only", unique), ("all_paired", paired)):
        ordered = sorted(subset, key=lambda p: p["xml_document_ordinal"])
        physical = [(p["page_number"], round(p["bbox_topleft"][1], 3)) for p in ordered]
        bad = [i for i in range(1, len(physical)) if physical[i] < physical[i - 1]]
        inversions.append({"scope": name, "n": len(subset), "n_inversions": len(bad), "at": bad[:8]})
    return {"checks": inversions, "n_unique": len(unique), "n_paired": len(paired)}
