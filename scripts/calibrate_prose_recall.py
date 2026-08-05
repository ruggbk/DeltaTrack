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
    _KNOWN_DEGRADED,
    _SHELL_VERSIONS,
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

    # Report each version against the floor the TEST would actually hold it to. Judging
    # a version with an approved degraded floor against the healthy target prints a
    # BELOW FLOOR on a case the suite passes, which trains the reader to discount the
    # warning that matters. The two are shown as different things instead.
    worst_healthy = 1.0
    rows = []
    breaches = []
    for bill, xml_path, pdf_path in versions:
        fragments, missing = prose_recall(xml_path, pdf_path)
        label = f"{bill}/{xml_path.stem}"

        if label in _SHELL_VERSIONS:
            expected = _SHELL_VERSIONS[label]
            if len(fragments) != expected:
                breaches.append(label)
                print(
                    f"{label}: SHELL DRIFT -- {len(fragments)} fragments, expected {expected} "
                    f"({len(missing)} missing)"
                )
                continue
            if missing:
                breaches.append(label)
                print(
                    f"{label}: SHELL MISSING -- {len(fragments)} fragments, "
                    f"{len(missing)} missing (shell versions must have full recall)"
                )
                continue
            print(f"{label}: SHELL OK ({len(fragments)} fragments, 0 missing)")
            continue

        if len(fragments) < MIN_FRAGMENTS:
            breaches.append(label)
            print(
                f"{label}: REGRESSION -- only {len(fragments)} fragments (minimum {MIN_FRAGMENTS}), "
                f"{len(missing)} missing. Not a known shell; fragment extraction has regressed."
            )
            continue

        recall = (len(fragments) - len(missing)) / len(fragments)
        floor = _KNOWN_DEGRADED.get(label)
        if floor is None:
            worst_healthy = min(worst_healthy, recall)
            rows.append((recall, label))
            flag = "  <-- BELOW FLOOR" if recall < RECALL_FLOOR else ""
        elif recall < floor:
            flag = f"  <-- BELOW ITS DEGRADED FLOOR ({floor:.0%})"
        elif recall >= RECALL_FLOOR:
            flag = "  <-- DEGRADED ENTRY NO LONGER NEEDED, remove it"
        else:
            flag = f"  (degraded floor {floor:.0%}, known defect)"
        if "<--" in flag:
            breaches.append(label)
        print(f"{label}: {recall:.1%} ({len(missing)}/{len(fragments)} missing){flag}")
        for miss in missing[: args.misses]:
            print(f"    MISS: {miss[:200]}")

    print(
        f"\nhealthy versions: worst {worst_healthy:.1%} against the {RECALL_FLOOR:.0%} "
        f"floor, headroom {worst_healthy - RECALL_FLOOR:+.1%}"
    )
    for recall, label in sorted(rows)[:5]:
        print(f"  lowest: {label} {recall:.1%}")
    if _KNOWN_DEGRADED:
        print(f"excluded from that figure, on a degraded floor: {', '.join(_KNOWN_DEGRADED)}")
    print(f"needs attention: {', '.join(breaches) if breaches else 'nothing'}")
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(main())
