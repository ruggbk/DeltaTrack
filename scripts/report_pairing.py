#!/usr/bin/env python3
"""Shared committee report pairing logic.

This module contains the single authoritative implementation of report-to-version
pairing, used by both derivation scripts and manifest update scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReportSource:
    """One physical committee report package (e.g., one book of a multi-book report)."""

    pkg: str  # govinfo package ID, e.g. "CRPT-119hrpt106"
    citation: str  # Full citation, e.g. "H. Rept. 119-106,Book 1"
    chamber: str  # "house" or "senate"
    book: Optional[str] = None  # "Book 1", "Book 2", etc. if applicable


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
    import re

    # Match "H. Rept. 118-553" or "H. Rept. 119-106,Book 1" or "S. Rept. 114-57"
    m = re.match(r"^(H\.|S\.)\s*Rept\.\s*(\d+)-(\d+)(?:,Book\s*(\d+))?", citation)
    if not m:
        return None
    prefix, congress_str, number_str, book_num = m.groups()
    chamber = "house" if prefix == "H." else "senate"
    book = f"Book {book_num}" if book_num else None
    return chamber, int(congress_str), int(number_str), book


def extract_report_sources(bill_elem) -> list[ReportSource]:
    """Extract all committee report sources from a BILLSTATUS bill element."""

    sources = []
    for child in bill_elem:
        if child.tag == "committeeReports":
            for subchild in child:
                citation = None
                for subsub in subchild:
                    if subsub.tag == "citation":
                        citation = subsub.text
                if citation:
                    parsed = parse_citation(citation)
                    if parsed:
                        chamber, congress, number, book = parsed
                        pkg = f"CRPT-{congress}{chamber[0]}rpt{number}"
                        sources.append(
                            ReportSource(
                                pkg=pkg,
                                citation=citation,
                                chamber=chamber,
                                book=book,
                            )
                        )
    return sources


def get_report_pairing(
    report_sources: list[ReportSource],
    stage: str,
    bill_type: str,  # "hr" or "s"
    is_enrolled: bool = False,
) -> ReportPairing:
    """Match committee report sources to a bill version stage.

    Pairing rules:
    - For non-enrolled stages: match by chamber (House versions -> House reports, Senate -> Senate)
    - For enrolled bills: if there's a conference report (multiple sources from same chamber
      with different book numbers, or both chambers represented), include all sources.
      The conference report is typically the final agreed text explained by both chambers' reports.
    - If no matching report exists, return empty sources with a reason.
    """
    if not report_sources:
        return ReportPairing(
            sources=(), reason="bill has no committee reports (introduced only or floor-amended omnibus)"
        )

    target_chamber = "house" if bill_type == "hr" else "senate"

    # For enrolled bills, we want ALL report sources (both chambers if available)
    # because the enrolled text reflects the conference agreement
    if is_enrolled:
        # Include all sources - the enrolled version is explained by the full set of reports
        return ReportPairing(sources=tuple(report_sources))

    # For non-enrolled stages, match by chamber
    chamber_sources = [s for s in report_sources if s.chamber == target_chamber]

    if not chamber_sources:
        return ReportPairing(sources=(), reason=f"no {target_chamber} report for this stage")

    return ReportPairing(sources=tuple(chamber_sources))
