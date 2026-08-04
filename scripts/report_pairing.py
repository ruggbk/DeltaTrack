#!/usr/bin/env python3
"""Shared committee report pairing logic.

The single authoritative implementation of report-to-version pairing. Both the
manifest update script and the tests read their rules from here, so there is one
place where "which report explains this text" is defined.

Two distinctions drive every rule below, and both were conflated in the first
version of this module (see #295 review):

1. **Authoring chamber, not bill type.** A version's report is the one that
   explains *that text*. Keying off the bill type ("hr" -> House) pairs the same
   House report with every stage of the bill, including the Senate's substitute
   text in ``engrossed-amendment-senate``. The authoring chamber is a property of
   the stage.
2. **Conference reports are terminal.** A conference report explains the agreed
   final text. It postdates every pre-conference stage, so it pairs with the
   enrolled bill only -- never with the as-reported House text it precedes by
   months. Chamber alone cannot separate them: a House conference report and a
   House committee report are both ``house``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

# Stages whose text is authored by the Senate: the Senate wrote this version.
_SENATE_AUTHORED = ("reported-in-senate", "engrossed-amendment-senate")

# Stages whose text is authored by the House.
_HOUSE_AUTHORED = (
    "introduced-in-house",
    "reported-in-house",
    "engrossed-in-house",
    "engrossed-amendment-house",
)

# Transit stages: the receiving chamber has not amended anything yet, so the text
# is still the originating chamber's. ``placed-on-calendar-senate`` on an H.R. is
# the House-passed bill sitting on the Senate calendar, explained by the House
# report.
_TRANSIT = (
    "received-in-senate",
    "referred-in-senate",
    "placed-on-calendar-senate",
    "received-in-house",
    "referred-in-house",
    "placed-on-calendar-house",
)


@dataclass(frozen=True)
class ReportSource:
    """One physical committee report package (e.g., one book of a multi-book report)."""

    citation: str  # Full citation, e.g. "H. Rept. 119-106,Book 1"
    chamber: str  # "house" or "senate"
    number: int  # Report number within the congress, e.g. 929
    # govinfo package ID, e.g. "CRPT-118hrpt553". None when govinfo publishes no
    # text rendition for this report -- see ``text_available``. Never guess one:
    # a fabricated package ID reads as a vendorable fixture and silently is not.
    pkg: Optional[str] = None
    book: Optional[str] = None  # "Book 1", "Book 2", etc. if applicable
    conference: bool = False  # True if this is the conference report
    # False when govinfo serves no text rendition for this report. Recorded as data
    # so the vendoring script and the fixture floor agree on it, rather than each
    # carrying its own hardcoded list of exceptions.
    text_available: bool = True
    unavailable_reason: Optional[str] = None


@dataclass(frozen=True)
class ReportPairing:
    """The committee report pairing for one bill version."""

    sources: tuple[ReportSource, ...]  # Physical report packages (empty = no report)
    reason: Optional[str] = None  # Why no report, if sources is empty


def parse_citation(citation: str) -> tuple[str, int, int, Optional[str]] | None:
    """Parse a BILLSTATUS citation into (chamber, congress, number, book).

    Returns (chamber, congress, number, book) where book is "Book 1"/"Book 2"/etc.
    or None if no book suffix.
    """
    # Match "H. Rept. 118-553" or "H. Rept. 119-106,Book 1" or "S. Rept. 114-57"
    m = re.match(r"^(H\.|S\.)\s*Rept\.\s*(\d+)-(\d+)(?:,\s*Book\s*(\d+))?", citation)
    if not m:
        return None
    prefix, congress_str, number_str, book_num = m.groups()
    chamber = "house" if prefix == "H." else "senate"
    book = f"Book {book_num}" if book_num else None
    return chamber, int(congress_str), int(number_str), book


def predicted_pkg(chamber: str, congress: int, number: int) -> str:
    """The govinfo package ID a single-book report of this citation would carry.

    Only ever a *prediction*: callers must confirm the package actually resolves
    before recording it, because govinfo answers an unknown package with a 302 to
    an HTML error page served as HTTP 200 (#295 review). Multi-book reports have
    no known per-book ID at all, which is why ``ReportSource.pkg`` is optional.
    """
    return f"CRPT-{congress}{chamber[0]}rpt{number}"


def authoring_chamber(stage: str, bill_type: str) -> str:
    """The chamber that wrote the text of this version.

    ``bill_type`` ("hr"/"s") supplies the originating chamber, which is the answer
    for transit stages and the fallback for stages naming no chamber.
    """
    origin = "house" if bill_type == "hr" else "senate"
    key = stage.lower()

    for marker in _TRANSIT:
        if marker in key:
            return origin
    for marker in _SENATE_AUTHORED:
        if marker in key:
            return "senate"
    for marker in _HOUSE_AUTHORED:
        if marker in key:
            return "house"
    return origin


def is_enrolled_stage(stage: str) -> bool:
    """Whether this stage is the enrolled (final, agreed) text."""
    return "enrolled" in stage.lower()


def mark_conference_reports(sources: list[ReportSource]) -> list[ReportSource]:
    """Flag the conference report among a bill's report sources.

    Heuristic: when a chamber filed more than one *distinct* report number for the
    bill, the higher-numbered one is the conference report -- it is filed after
    conference concludes. Books of one report share a number and so never trip it.

    The heuristic is allowed to be approximate because it is not the last word:
    ``test_conference_flag_matches_fixture_text`` checks every flag against the
    vendored report text, which states "CONFERENCE REPORT" outright. A wrong flag
    goes red there rather than silently mispairing a version.
    """
    by_chamber: dict[str, set[int]] = {}
    for s in sources:
        by_chamber.setdefault(s.chamber, set()).add(s.number)

    return [
        replace(s, conference=len(by_chamber[s.chamber]) > 1 and s.number == max(by_chamber[s.chamber]))
        for s in sources
    ]


def extract_report_sources(bill_elem) -> list[ReportSource]:
    """Extract all committee report sources from a BILLSTATUS bill element.

    ``pkg`` is left unset here: this function reads BILLSTATUS, which says nothing
    about whether govinfo published a text rendition. Resolving and confirming the
    package is the vendoring step's job.
    """
    sources = []
    for child in bill_elem:
        if child.tag != "committeeReports":
            continue
        for subchild in child:
            citation = None
            for subsub in subchild:
                if subsub.tag == "citation":
                    citation = subsub.text
            if not citation:
                continue
            parsed = parse_citation(citation)
            if not parsed:
                continue
            chamber, _congress, number, book = parsed
            sources.append(
                ReportSource(
                    citation=citation,
                    chamber=chamber,
                    number=number,
                    book=book,
                )
            )
    return mark_conference_reports(sources)


def get_report_pairing(
    report_sources: list[ReportSource],
    stage: str,
    bill_type: str,  # "hr" or "s"
) -> ReportPairing:
    """Match committee report sources to a bill version stage.

    - Enrolled: every report source, both chambers. The enrolled text is the
      agreed product of all of them, and the conference report explains it.
    - Every other stage: the reports authored by the chamber that wrote this text,
      excluding conference reports (which postdate the stage).
    """
    if not report_sources:
        return ReportPairing(
            sources=(),
            reason="bill has no committee reports (introduced only or floor-amended omnibus)",
        )

    if is_enrolled_stage(stage):
        return ReportPairing(sources=tuple(report_sources))

    chamber = authoring_chamber(stage, bill_type)
    candidates = [s for s in report_sources if s.chamber == chamber and not s.conference]

    if not candidates:
        return ReportPairing(sources=(), reason=f"no {chamber} committee report explains this stage")

    return ReportPairing(sources=tuple(candidates))
