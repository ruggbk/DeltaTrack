#!/usr/bin/env python3
"""Update corpus_manifest.toml with committee report pairings.

Comment-preserving: the manifest carries 40+ lines of documentation (why the file
exists, how the gates read it, how to add a fixture) that a load-and-dump through
a plain TOML writer silently deletes. tomlkit edits the document in place instead.

Two modes:

default (offline)
    Re-derive pairings from the report sources already recorded in the manifest.
    BILLSTATUS said which reports a bill has; that answer does not change, so
    re-applying the *pairing rules* needs no network. This is the mode to run
    after editing scripts/report_pairing.py.

``--refresh``
    Re-fetch BILLSTATUS for every bill and rebuild the source list from scratch.
    Needed only when a bill gains a report.

Package IDs are confirmed against govinfo before being recorded (``--refresh``
only): a predicted ID that does not resolve is stored as ``text_available =
false`` rather than as a fixture that will never exist.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

# Run-from-anywhere. Both roots, mirroring pytest's `pythonpath = [".", "tools"]`:
# tools/fetch_govinfo.py resolves its sibling as a bare `shared.http`, so the repo
# root alone is not enough to import it.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(1, str(_ROOT / "tools"))

import httpx  # noqa: E402
import tomlkit  # noqa: E402

from scripts.report_pairing import (  # noqa: E402
    ReportSource,
    extract_report_sources,
    get_report_pairing,
    mark_conference_reports,
    parse_citation,
    predicted_pkg,
)
from tools.fetch_govinfo import fetch_billstatus_bill  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"


def load_manifest_doc() -> tomlkit.TOMLDocument:
    """Load the corpus manifest as a tomlkit document (preserves comments)."""
    return tomlkit.parse(MANIFEST_PATH.read_text(encoding="utf-8"))


def write_manifest_doc(doc: tomlkit.TOMLDocument) -> None:
    """Write the manifest document."""
    MANIFEST_PATH.write_text(tomlkit.dumps(doc), encoding="utf-8")


def pkg_resolves(pkg: str) -> bool:
    """Whether govinfo serves a text rendition for this package.

    Checking the status code is not enough: an unknown package 302s to an error
    page that answers 200. Follow the redirect and require the final URL to still
    be under ``/content/pkg/``, which the error page is not.
    """
    url = f"https://www.govinfo.gov/content/pkg/{pkg}/html/{pkg}.htm"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (govinfo, https)
            return f"/content/pkg/{pkg}/" in resp.geturl()
    except urllib.error.URLError:
        return False


def resolve_pkgs(sources: list[ReportSource], congress: int) -> list[ReportSource]:
    """Attach a confirmed ``pkg`` to each source, or mark it text-unavailable."""
    out = []
    for s in sources:
        if s.book:
            # Multi-book reports have no known per-book package ID, and the
            # single-book prediction would point both books at one file.
            out.append(
                replace(
                    s,
                    text_available=False,
                    unavailable_reason="multi-book report: no per-book govinfo package ID is known",
                )
            )
            continue
        pkg = predicted_pkg(s.chamber, congress, s.number)
        if pkg_resolves(pkg):
            out.append(replace(s, pkg=pkg))
        else:
            out.append(
                replace(
                    s,
                    text_available=False,
                    unavailable_reason=f"govinfo serves no text rendition for {pkg}",
                )
            )
    return out


def sources_from_manifest(bill_entry) -> list[ReportSource]:
    """Every distinct report source already recorded across a bill's versions."""
    seen: dict[str, ReportSource] = {}
    for ver in bill_entry.get("versions", []):
        for raw in ver.get("committee_report", []) or []:
            citation = raw.get("citation")
            if not citation or citation == "none":
                continue
            parsed = parse_citation(citation)
            if not parsed:
                continue
            chamber, _congress, number, book = parsed
            seen.setdefault(
                citation,
                ReportSource(
                    citation=citation,
                    chamber=chamber,
                    number=number,
                    book=book,
                    pkg=raw.get("pkg"),
                    text_available=raw.get("text_available", True),
                    unavailable_reason=raw.get("unavailable_reason"),
                ),
            )
    return mark_conference_reports(list(seen.values()))


def format_report_source(source: ReportSource) -> tomlkit.items.InlineTable:
    """Format a report source as an inline table, omitting defaulted keys."""
    table = tomlkit.inline_table()
    if source.pkg:
        table["pkg"] = source.pkg
    table["citation"] = source.citation
    table["chamber"] = source.chamber
    if source.book:
        table["book"] = source.book
    if source.conference:
        table["conference"] = True
    if not source.text_available:
        table["text_available"] = False
        table["unavailable_reason"] = source.unavailable_reason or "no govinfo text rendition"
    return table


def format_report_pairing(pairing) -> tomlkit.items.Array:
    """Format a ReportPairing as an array of inline tables.

    "No report" is a single entry carrying only a reason -- deliberately with no
    ``pkg`` key, so nothing downstream can mistake a sentinel string for a
    vendorable package.
    """
    arr = tomlkit.array()
    if not pairing.sources:
        table = tomlkit.inline_table()
        table["citation"] = "none"
        table["chamber"] = "none"
        table["reason"] = pairing.reason or "no report available"
        arr.append(table)
    else:
        for s in pairing.sources:
            arr.append(format_report_source(s))
    return arr


def main():
    ap = argparse.ArgumentParser(description="Update corpus_manifest.toml committee report pairings.")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch BILLSTATUS and re-confirm package IDs (network); default is offline re-pairing",
    )
    args = ap.parse_args()

    doc = load_manifest_doc()

    for bill_entry in doc.get("bill", []):
        bill_id = bill_entry["id"]
        congress, bill_type, number = bill_id.split("-")

        if args.refresh:
            print(f"Fetching BILLSTATUS for {bill_id}...", file=sys.stderr)
            with httpx.Client(timeout=30) as client:
                bill_elem = fetch_billstatus_bill(client, int(congress), bill_type, int(number))
            if bill_elem is None:
                print(f"  WARNING: No BILLSTATUS found for {bill_id}", file=sys.stderr)
                continue
            report_sources = resolve_pkgs(extract_report_sources(bill_elem), int(congress))
        else:
            report_sources = sources_from_manifest(bill_entry)

        print(
            f"{bill_id}: {len(report_sources)} report source(s): "
            f"{', '.join(s.citation for s in report_sources) or 'none'}",
            file=sys.stderr,
        )

        for ver in bill_entry.get("versions", []):
            if "xml" not in ver.get("formats", []):
                continue
            stage = ver["stage"]
            pairing = get_report_pairing(report_sources, stage, bill_type)
            ver["committee_report"] = format_report_pairing(pairing)
            desc = ", ".join(s.citation for s in pairing.sources) if pairing.sources else "none"
            print(f"    {stage}: {desc} ({pairing.reason or 'ok'})", file=sys.stderr)

    write_manifest_doc(doc)
    print("Manifest updated (comments preserved).", file=sys.stderr)


if __name__ == "__main__":
    main()
