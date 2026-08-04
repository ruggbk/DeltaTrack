#!/usr/bin/env python3
"""Derive committee report pairings for all corpus bills from BILLSTATUS metadata.

This script fetches BILLSTATUS for each bill in the corpus manifest and extracts
committee report citations. The pairings are keyed per (bill, version, chamber)
since a bill can have different reports at different stages (e.g., House report
for the reported-in-House version, Senate report for the reported-in-Senate version).

Outputs a TOML structure that can be merged into corpus_manifest.toml.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import httpx

# Run-from-anywhere: put the repo root on the path so `tools` and `shared` import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fetch_govinfo import extract_committee_reports, fetch_billstatus_bill  # noqa: E402


def load_manifest() -> list[dict]:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("bill", [])


def sanitize_version_name(name: str) -> str:
    """Convert a version type like 'Reported in House' to 'reported-in-house'."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown"


def get_report_for_stage(reports: list[dict], stage: str, chamber: str) -> dict | None:
    """Match a committee report to a bill version stage.

    The pairing keys on (version stage, chamber):
    - reported-in-house -> House report
    - reported-in-senate -> Senate report
    - engrossed-amendment-house/senate -> the corresponding chamber's report
    - enrolled-bill -> conference report (if any), else the last chamber's report

    For simplicity, we match the chamber of the report to the chamber implied by
    the version stage name.
    """
    if not reports:
        return None

    # Determine which chamber this version stage belongs to
    stage_lower = stage.lower()
    if "house" in stage_lower:
        target_chamber = "house"
    elif "senate" in stage_lower:
        target_chamber = "senate"
    else:
        # For introduced/enrolled without chamber, no clear pairing
        return None

    # Find the report for this chamber
    for r in reports:
        if r["chamber"] == target_chamber:
            return r

    return None


def main():
    bills = load_manifest()

    # For each bill, fetch BILLSTATUS and extract reports
    pairings = {}
    for bill_entry in bills:
        bill_id = bill_entry["id"]
        congress, btype, number = bill_id.split("-")

        print(f"Fetching BILLSTATUS for {bill_id}...", file=sys.stderr)
        with httpx.Client(timeout=30) as client:
            bill_elem = fetch_billstatus_bill(client, int(congress), btype, int(number))

        if bill_elem is None:
            print(f"  WARNING: No BILLSTATUS found for {bill_id}", file=sys.stderr)
            pairings[bill_id] = {"reports": [], "versions": {}}
            continue

        reports = extract_committee_reports(bill_elem)
        print(f"  Found {len(reports)} report(s): {', '.join(r['citation'] for r in reports)}", file=sys.stderr)

        # For each version in the manifest, determine its report pairing
        version_pairings = {}
        for ver in bill_entry.get("versions", []):
            stage = ver["stage"]
            formats = ver.get("formats", [])
            has_xml = "xml" in formats

            # Only pair reports to versions we have XML for (the diff engine uses XML)
            if has_xml:
                report = get_report_for_stage(reports, stage, btype)
                if report:
                    version_pairings[stage] = {
                        "report_pkg": report["pkg"],
                        "report_citation": report["citation"],
                        "report_chamber": report["chamber"],
                    }
                else:
                    version_pairings[stage] = {
                        "report_pkg": None,
                        "report_citation": None,
                        "report_chamber": None,
                        "reason": "no report for this stage/chamber",
                    }

        pairings[bill_id] = {
            "reports": reports,
            "versions": version_pairings,
        }

    # Output as JSON (handles None)
    import json

    print(json.dumps(pairings, indent=2))


if __name__ == "__main__":
    main()
