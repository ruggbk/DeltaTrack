"""Slice 6 phases B/C: read the move census and adjudicate the boundary.

Consumes ``results/move-semantics-census.json`` (written by
``pdf_move_semantics_census.py``) and reports the things the design question turns on:

* the round-2 population's anchor behaviour -- does every round-2 move actually change
  location, and does any keep the same anchor?
* the overlap distribution of every partition, so the 0.6 cutoff can be judged against
  where the population actually sits rather than against one fixture;
* every row within reach of the cutoff, with enough anchor and body context for a human
  to say whether "moved" is a truthful description;
* the exact output impact of H1 (provenance only) and H2 (location change), computed as
  row-level type flips against the current output.

Read-only over the census artifact: it decides nothing and changes nothing.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_move_boundary_report.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parent.parent / "results" / "move-semantics-census.json"

_MOVE_CUTOFF = 0.6
_NEAR = 0.15


def _label(row: dict) -> str:
    return f"{row['bill']} {row['pair']} old#{row['old_ordinal']} new#{row['new_ordinal']}"


def _show(row: dict, *, body: bool = True) -> None:
    overlap = row["word_overlap"]
    shown = f"{overlap:.4f}" if isinstance(overlap, float) else "-"
    print(f"  [{row['partition']}] {row['change_type']:8s} overlap={shown}  {_label(row)}")
    print(f"      anchor  {row['old_anchor']!r} -> {row['new_anchor']!r}")
    print(f"      range   {row['old_range']} -> {row['new_range']}   words {row['old_words']} -> {row['new_words']}")
    if body:
        print(f"      old: {row['old_preview']}")
        print(f"      new: {row['new_preview']}")


def _distribution(rows: list[dict], name: str) -> None:
    values = sorted(r["word_overlap"] for r in rows if isinstance(r["word_overlap"], float))
    if not values:
        print(f"  {name:44s} (none)")
        return
    buckets = Counter()
    for value in values:
        buckets[min(int(value * 10) / 10, 1.0)] += 1
    span = " ".join(f"{edge:.1f}:{count}" for edge, count in sorted(buckets.items()))
    print(f"  {name:44s} n={len(values):3d}  min={values[0]:.4f} max={values[-1]:.4f}")
    print(f"  {'':44s} {span}")


def main() -> None:
    if not RESULTS.exists():
        sys.exit(f"missing {RESULTS}; run pdf_move_semantics_census.py first")
    data = json.loads(RESULTS.read_text())
    rows = data["rows"]
    described = [r for r in rows if r["change_type"] in {"moved", "modified"}]
    by = lambda p: [r for r in described if r["partition"] == p]  # noqa: E731

    print("=== 1. the described population ===")
    print(f"  settled rows emitted as a hunk            {len(described)}")
    for part in "ABCDEF":
        print(f"  partition {part}                               {len(by(part))}")

    print("\n=== 2. round-2 moves (A): does assignment provenance imply a location change? ===")
    a = by("A")
    same_anchor = [r for r in a if r["old_anchor"] == r["new_anchor"]]
    absent = [r for r in a if r["old_anchor"] is None or r["new_anchor"] is None]
    identical = [r for r in a if r["text_identical"]]
    same_page = [r for r in a if r["old_range"] and r["new_range"] and r["old_range"][0] == r["new_range"][0]]
    print(f"  round-2 moves                              {len(a)}")
    print(f"    with the SAME anchor text on both sides  {len(same_anchor)}")
    print(f"    with an anchor absent on a side          {len(absent)}")
    print(f"    whose two texts are identical            {len(identical)}")
    print(f"    starting on the same page number         {len(same_page)}")
    for row in same_anchor[:20]:
        _show(row)

    print("\n=== 3. overlap distributions ===")
    _distribution(a, "A round-2 moves")
    _distribution(by("B"), "B round-1 identical-text moves")
    _distribution(by("C"), "C round-1 changed-anchor moves")
    _distribution(by("D"), "D round-1 changed-anchor modified")
    _distribution(by("E"), "E round-1 same-anchor rows")

    print("\n=== 4. the round-1 changed-anchor population, sorted by overlap ===")
    changed = sorted(by("B") + by("C") + by("D"), key=lambda r: r["word_overlap"])
    for row in changed:
        _show(row, body=False)

    print(f"\n=== 5. every changed-anchor row within {_NEAR} of the {_MOVE_CUTOFF} cutoff, in full ===")
    near = [r for r in changed if abs(r["word_overlap"] - _MOVE_CUTOFF) <= _NEAR]
    print(f"  {len(near)} rows\n")
    for row in near:
        _show(row)
        print()

    print("=== 6. exact output impact of each candidate definition ===")
    h1_flips = [r for r in described if r["change_type"] == "moved" and r["round"] == 1]
    print(f"  H1 provenance-only: moved -> modified        {len(h1_flips)}")
    print(
        f"     (B {len([r for r in h1_flips if r['partition'] == 'B'])}, "
        f"C {len([r for r in h1_flips if r['partition'] == 'C'])})"
    )
    h2_gain = by("D")
    h2_loss = [r for r in a if r["old_anchor"] == r["new_anchor"]]
    print(f"  H2 location-change: modified -> moved        {len(h2_gain)}")
    print(f"  H2 location-change: moved -> modified        {len(h2_loss)}  (round-2, same anchor)")
    print("  H3 legacy assignment-reason: no flips        0")

    print("\n=== 7. round-2 moves whose anchors differ only cosmetically ===")

    def norm(text: str | None) -> str:
        return "".join(ch for ch in (text or "").upper() if ch.isalnum())

    cosmetic = [r for r in a if r["old_anchor"] != r["new_anchor"] and norm(r["old_anchor"]) == norm(r["new_anchor"])]
    print(f"  {len(cosmetic)} rows whose anchors differ only in punctuation/case/space")
    for row in cosmetic[:10]:
        _show(row, body=False)


if __name__ == "__main__":
    main()
