"""x12 -- what the geometric eligibility rule actually admits. DESIGN MATERIAL.

NOT CONFIRMATORY. DEVELOPMENT documents only. No holdout document is opened.

    frozen rule   A19/A21 -- "a source glyph is neutral-eligible iff it has a VALID INK BOX
                  -- present, finite, and positive area -- and is upright. NO codepoint is
                  consulted."
    this probe    asks what that rule admits, rather than only what it excludes

WHY THIS EXISTS. A21 measured eligibility in ONE direction: "the number excluded ONLY by a
codepoint rule is 0". That is true and it is not the whole question. It says nothing about
what the geometric rule INCLUDES that a codepoint rule would have excluded -- and the answer
turns out to be every real word space on the page.

MEASURED. PDFium reports a positive-area box for a content-stream U+0020. The box is a
sliver: about 3.6 pt wide and 0.014 pt tall, against 8.44 pt tall for a capital letter. It
clears `(y1 - y0) > 0` by a hair, so `eligible()` admits it.

WHY THIS MATTERS, and it is not cosmetic:

  * those gids become NEUTRAL SKELETON MEMBERS, so the skeleton contains units that carry
    no ink -- contradicting the rule's own justification, "a real ink mark";
  * X's contract drops every U+0020 (X-2), so X can NEVER emit them. They are therefore
    permanently outside `common` and permanently inside `X_SOURCE_GLYPH_LOSS`, on a large
    share of lines, which a reader would reasonably misread as X dropping content;
  * they widen each neutral line's x-extent, which feeds region geometry and the oracle's
    rendered bbox.

WHAT IS NOT DONE HERE. No threshold is chosen. A minimum ink height would separate a space
from a letter by a factor of ~600 and would stay purely geometric -- it needs no codepoint
-- but PICKING one is a new outcome-affecting decision and belongs in an amendment, not in a
probe. The frozen rule is implemented faithfully and its consequence is measured. See A24.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import run_hybrid  # noqa: E402
from contract_hybrid import CP, GEN, UPRIGHT, VBOX, X0, X1  # noqa: E402
from neutral_identity import eligible  # noqa: E402

OUT = EV / "results" / "x12_skeleton_eligibility.json"
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]


def main(limit: int = 8) -> int:
    out = []
    for name, path in DOCS:
        if not path.exists():
            continue
        space_h, space_w, letter_h = [], [], []
        n_space_eligible = n_space_total = 0
        lines_touched = 0
        total_lines = 0
        for pno, chars in run_hybrid.extract_with_gids(path, limit=limit):
            space_gids = set()
            for gid, c in chars:
                box = (
                    None
                    if c[X0] is None or c[X1] is None or c[VBOX] is None
                    else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
                )
                g = None if c[GEN] else gid
                ok = eligible(g, box, bool(c[UPRIGHT]))
                if c[CP] == 32:
                    n_space_total += 1
                    if ok:
                        n_space_eligible += 1
                        space_gids.add(gid)
                        space_w.append(box[2] - box[0])
                        space_h.append(box[3] - box[1])
                elif ok and 65 <= c[CP] <= 90:
                    letter_h.append(box[3] - box[1])
            lines = run_hybrid.neutral_skeleton(pno, chars)
            total_lines += len(lines)
            lines_touched += sum(1 for ln in lines if ln.gids & space_gids)
        rec = {
            "document": name,
            "pages": limit,
            "u0020_chars": n_space_total,
            "u0020_admitted_to_skeleton": n_space_eligible,
            "space_box_median_width": round(statistics.median(space_w), 4) if space_w else None,
            "space_box_median_height": round(statistics.median(space_h), 4) if space_h else None,
            "space_box_max_height": round(max(space_h), 4) if space_h else None,
            "capital_box_median_height": round(statistics.median(letter_h), 4) if letter_h else None,
            "height_ratio_capital_over_space": (
                round(statistics.median(letter_h) / statistics.median(space_h), 1) if space_h and letter_h else None
            ),
            "neutral_lines": total_lines,
            "neutral_lines_containing_a_space_gid": lines_touched,
            "share_of_lines_affected": round(lines_touched / total_lines, 4) if total_lines else None,
        }
        out.append(rec)
        print(
            f"  {name:16} U+0020 admitted={rec['u0020_admitted_to_skeleton']:5}/{rec['u0020_chars']:5}  "
            f"space_h={rec['space_box_median_height']}  capital_h={rec['capital_box_median_height']}  "
            f"ratio={rec['height_ratio_capital_over_space']}x  "
            f"lines_affected={rec['neutral_lines_containing_a_space_gid']}/{rec['neutral_lines']} "
            f"({rec['share_of_lines_affected']})"
        )

    doc = {
        "population": "DEVELOPMENT -- no holdout opened",
        "frozen_rule": "eligible iff valid finite positive-area ink box AND upright; no codepoint consulted",
        "finding": (
            "the rule admits every content-stream U+0020, because PDFium reports a positive-area "
            "box for it. A21 measured eligibility only in the exclusion direction, so this was not "
            "visible: nothing is excluded ONLY by a codepoint rule, but spaces are INCLUDED that a "
            "codepoint rule would have removed."
        ),
        "consequence": (
            "those gids are skeleton members X can never emit (X-2 drops all U+0020), so they sit "
            "permanently outside `common` and inside X_SOURCE_GLYPH_LOSS, and they widen each "
            "neutral line's x-extent, which feeds region geometry and the oracle bbox"
        ),
        "not_done_here": (
            "no threshold is chosen. A minimum ink height would stay purely geometric and separates "
            "space from capital by ~600x, but picking one is outcome-affecting and belongs in an "
            "amendment"
        ),
        "documents": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
