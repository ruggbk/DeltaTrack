"""
Detailed unknown-node inspection per bill.
Run from DeltaTrack/:  uv run python financial_classifier/stress_test_detail.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bill_tree import normalize_bill
from financial_classifier.classify_bill import DOLLAR, classify_text

BILLS_DIR = Path(__file__).parent.parent / "bills"

TARGETS = {
    "approp": [
        ("118", "hr", "4366", "MILCON/VA"),
        ("118", "hr", "4368", "CJS FY2024"),
    ],
    "reconciliation": [
        ("117", "hr", "5376", "IRA"),
        ("119", "hr", "1", "BBB"),
    ],
    "authorization": [
        ("118", "s", "2226", "NDAA FY2024"),
        ("115", "hr", "2", "Farm Bill 2018"),
        ("117", "hr", "3684", "IIJA"),
    ],
}


def get_unknowns(congress, btype, number):
    pattern = BILLS_DIR / f"{congress}-{btype}-{number}"
    xmls = sorted(pattern.glob("*.xml"))
    if not xmls:
        return []
    tree = normalize_bill(xmls[0])
    results = []
    for node in tree.nodes:
        text = node.body_text or ""
        if not DOLLAR.search(text):
            continue
        label = classify_text(text)
        if label == "unknown":
            results.append(text)
    return results


def show_unknowns(label, congress, btype, number, name, max_show=25):
    unknowns = get_unknowns(congress, btype, number)
    print(f"\n{'=' * 72}")
    print(f"[{label}] {congress}-{btype}-{number} — {name} — {len(unknowns)} unknowns")
    print("=" * 72)
    for i, text in enumerate(unknowns[:max_show]):
        print(f"\n--- node {i + 1} ---")
        print(text[:400])
    if len(unknowns) > max_show:
        print(f"\n... ({len(unknowns) - max_show} more not shown)")


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("approp", "all"):
        for args in TARGETS["approp"]:
            show_unknowns("APPROP", *args)

    if mode in ("reconciliation", "all"):
        for args in TARGETS["reconciliation"]:
            show_unknowns("RECON", *args, max_show=15)

    if mode in ("authorization", "all"):
        for args in TARGETS["authorization"]:
            show_unknowns("AUTH", *args, max_show=10)
