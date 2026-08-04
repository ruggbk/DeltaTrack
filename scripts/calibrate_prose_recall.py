#!/usr/bin/env python
"""Measure XML-prose-to-PDF recall across the corpus, to calibrate the floor in
tests/test_pdf_xml_prose_recall.py.

The floor in that test is a budget, and a budget calibrated on a sample is a budget
that goes red on the first unmeasured member. Run this over the whole fixture tree
(and `CORPUS_SWEEP=1` for the wider downloaded corpus) before changing it, and read
the misses: the point of the exercise is to know what the residue IS, not to pick a
number under it.

    uv run python scripts/calibrate_prose_recall.py [--misses N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

from pdf_corpus import dual_format_versions  # noqa: E402
from test_pdf_xml_prose_recall import (  # noqa: E402
    MIN_FRAGMENTS,
    RECALL_FLOOR,
    prose_recall,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--misses", type=int, default=3, help="misses to print per version")
    args = parser.parse_args()

    versions = dual_format_versions()
    print(f"{len(versions)} dual-format versions\n")

    worst = 1.0
    rows = []
    for bill, xml_path, pdf_path in versions:
        fragments, missing = prose_recall(xml_path, pdf_path)
        label = f"{bill}/{xml_path.stem}"
        if len(fragments) < MIN_FRAGMENTS:
            print(f"{label}: SKIP ({len(fragments)} fragments)")
            continue
        recall = (len(fragments) - len(missing)) / len(fragments)
        worst = min(worst, recall)
        rows.append((recall, label))
        flag = "  <-- BELOW FLOOR" if recall < RECALL_FLOOR else ""
        print(f"{label}: {recall:.1%} ({len(missing)}/{len(fragments)} missing){flag}")
        for miss in missing[: args.misses]:
            print(f"    MISS: {miss[:200]}")

    print(f"\nworst: {worst:.1%}   floor: {RECALL_FLOOR:.0%}   headroom: {worst - RECALL_FLOOR:+.1%}")
    for recall, label in sorted(rows)[:5]:
        print(f"  lowest: {label} {recall:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
