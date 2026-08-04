#!/usr/bin/env python3
"""Update corpus_manifest.toml with committee report pairings."""

from __future__ import annotations

import sys
import tempfile
import tomllib
from pathlib import Path

# Run-from-anywhere: put the repo root on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fetch_govinfo import extract_committee_reports, fetch_billstatus_bill  # noqa: E402


def load_manifest() -> dict:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        return tomllib.load(f)


def sanitize_version_name(name: str) -> str:
    """Convert a version type like 'Reported in House' to 'reported-in-house'."""
    import re
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown"


def get_report_for_stage(reports: list[dict], stage: str, chamber: str, is_enrolled: bool = False) -> dict | None:
    """Match a committee report to a bill version stage.

    For enrolled bills, try to find a conference report (highest-numbered report
    from either chamber when there are multiple reports from the same chamber).
    For other stages, match by chamber.
    """
    if not reports:
        return None

    stage_lower = stage.lower()
    
    # For enrolled bills, check for conference reports
    if is_enrolled:
        # Group reports by chamber
        by_chamber: dict[str, list[dict]] = {"house": [], "senate": []}
        for r in reports:
            by_chamber[r["chamber"]].append(r)
        
        # If a chamber has multiple reports, the highest-numbered is likely the conference report
        for ch in ("house", "senate"):
            chamber_reports = by_chamber[ch]
            if len(chamber_reports) > 1:
                # Sort by report number, highest first
                chamber_reports.sort(key=lambda r: r["number"], reverse=True)
                # The highest-numbered report from either chamber is the conference report
                # (conference reports are typically from the chamber that originated the bill)
                return chamber_reports[0]
        
        # If no chamber has multiple reports, fall through to chamber matching
    
    # Standard chamber matching for non-enrolled stages
    if "house" in stage_lower:
        target_chamber = "house"
    elif "senate" in stage_lower:
        target_chamber = "senate"
    else:
        return None

    for r in reports:
        if r["chamber"] == target_chamber:
            return r

    return None


def main():
    import httpx
    import tomli_w

    manifest = load_manifest()
    bills = manifest.get("bill", [])

    # For each bill, fetch BILLSTATUS and extract reports
    for bill_entry in bills:
        bill_id = bill_entry["id"]
        congress, btype, number = bill_id.split("-")

        print(f"Fetching BILLSTATUS for {bill_id}...", file=sys.stderr)
        with httpx.Client(timeout=30) as client:
            bill_elem = fetch_billstatus_bill(client, int(congress), btype, int(number))

        if bill_elem is None:
            print(f"  WARNING: No BILLSTATUS found for {bill_id}", file=sys.stderr)
            continue

        reports = extract_committee_reports(bill_elem)
        print(f"  Found {len(reports)} report(s): {', '.join(r['citation'] for r in reports)}", file=sys.stderr)

        # For each version in the manifest, determine its report pairing
        for ver in bill_entry.get("versions", []):
            stage = ver["stage"]
            formats = ver.get("formats", [])
            has_xml = "xml" in formats
            is_enrolled = "enrolled" in stage.lower()

            if has_xml:
                report = get_report_for_stage(reports, stage, btype, is_enrolled)
                if report:
                    ver["committee_report"] = {
                        "pkg": report["pkg"],
                        "citation": report["citation"],
                        "chamber": report["chamber"],
                    }
                else:
                    # Determine the reason for no report
                    if not reports:
                        reason = "bill has no committee reports (introduced only or floor-amended omnibus)"
                    elif is_enrolled:
                        reason = "enrolled bill; no conference report identified"
                    else:
                        reason = f"no {btype} report for this stage"
                    ver["committee_report"] = {
                        "pkg": "none",
                        "citation": "none",
                        "chamber": "none",
                        "reason": reason,
                    }

    # Write to temp file first, then move
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with tempfile.NamedTemporaryFile(mode="wb", dir=manifest_path.parent, delete=False) as tf:
        tomli_w.dump(manifest, tf)
        temp_path = Path(tf.name)
    
    # Atomic move
    temp_path.replace(manifest_path)
    
    print("Manifest updated successfully!", file=sys.stderr)


if __name__ == "__main__":
    main()