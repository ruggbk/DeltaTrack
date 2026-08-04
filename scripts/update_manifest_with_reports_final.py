#!/usr/bin/env python3
"""Update corpus_manifest.toml with committee report pairings (comment-preserving using tomlkit)."""

from __future__ import annotations

import sys
from pathlib import Path

# Run-from-anywhere: put the repo root on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from tools.fetch_govinfo import fetch_billstatus_bill  # noqa: E402
from scripts.report_pairing import extract_report_sources, get_report_pairing, ReportSource  # noqa: E402
import tomlkit


def load_manifest_doc() -> tomlkit.TOMLDocument:
    """Load the corpus manifest as a tomlkit document (preserves comments)."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    return tomlkit.parse(manifest_path.read_text(encoding="utf-8"))


def write_manifest_doc(doc: tomlkit.TOMLDocument) -> None:
    """Write the manifest document."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    manifest_path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def format_report_source(source: ReportSource) -> tomlkit.items.InlineTable:
    """Format a report source as an inline table."""
    table = tomlkit.inline_table()
    table["pkg"] = source.pkg
    table["citation"] = source.citation
    table["chamber"] = source.chamber
    if source.book:
        table["book"] = source.book
    return table


def format_report_pairing(pairing) -> tomlkit.items.Array:
    """Format a ReportPairing as an array of inline tables."""
    arr = tomlkit.array()
    if not pairing.sources:
        table = tomlkit.inline_table()
        table["pkg"] = "none"
        table["citation"] = "none"
        table["chamber"] = "none"
        table["reason"] = pairing.reason or "no report available"
        arr.append(table)
    else:
        for s in pairing.sources:
            arr.append(format_report_source(s))
    return arr


def main():
    doc = load_manifest_doc()
    bills = doc.get("bill", [])

    for bill_entry in bills:
        bill_id = bill_entry["id"]
        congress, btype, number = bill_id.split("-")
        bill_type = btype

        print(f"Fetching BILLSTATUS for {bill_id}...", file=sys.stderr)
        with httpx.Client(timeout=30) as client:
            bill_elem = fetch_billstatus_bill(client, int(congress), btype, int(number))

        if bill_elem is None:
            print(f"  WARNING: No BILLSTATUS found for {bill_id}", file=sys.stderr)
            continue

        report_sources = extract_report_sources(bill_elem)
        print(f"  Found {len(report_sources)} report source(s): {', '.join(s.citation for s in report_sources)}", file=sys.stderr)

        versions = bill_entry.get("versions", [])
        for ver in versions:
            stage = ver["stage"]
            formats = ver.get("formats", [])
            has_xml = "xml" in formats
            is_enrolled = "enrolled" in stage.lower()

            if has_xml:
                pairing = get_report_pairing(report_sources, stage, bill_type, is_enrolled)
                ver["committee_report"] = format_report_pairing(pairing)
                sources_desc = ", ".join(s.citation for s in pairing.sources) if pairing.sources else "none"
                print(f"    {stage}: {sources_desc} ({pairing.reason or 'ok'})", file=sys.stderr)

    write_manifest_doc(doc)
    print("Manifest updated successfully (comments preserved with tomlkit)!", file=sys.stderr)


if __name__ == "__main__":
    main()