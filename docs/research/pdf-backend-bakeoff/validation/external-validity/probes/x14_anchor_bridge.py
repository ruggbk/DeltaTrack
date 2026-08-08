"""x14 -- can a production Anchor be placed on a neutral region WITHOUT text matching?

NOT CONFIRMATORY. Synthetic + DEVELOPMENT documents only. No holdout document is opened,
nothing is scored.

    frozen rule   A22/A23 -- ANCHOR_DISCORDANCE is region-level, and an anchor is placed in
                  a region BY IDENTITY: the neutral line owning the first gid of the emitted
                  line the anchor was read from decides its region.
    the question  is that executable today, exactly, with no heading-text fallback?
    evidence      `results/x14_anchor_bridge.json`

THE CHAIN UNDER TEST

    Anchor(page_number, line_number)          production, from Page.lines / Page.print_lines
      -> index i in Page.print_lines with that margin line_number
      -> run_hybrid.emitted_lines(...)[i]     SAME index, already gated by x11
      -> EmittedLine.cells -> ngid            neutral ink identity (A24.2)
      -> owning NeutralLine -> region

`Anchor.line_number` is the GPO PRINTED margin number, not an index, so the join is a source
fact rather than a position in an architecture's list. The index step is safe because `x11`
already asserts, element for element, that `emitted_lines` reproduces `Page.print_lines` in
order; this probe re-asserts it locally so the bridge cannot silently rest on a stale gate.

WHY NO TEXT IS CONSULTED ANYWHERE. Matching an anchor to a line by its heading text would
make anchor discordance circular -- the arms disagree about text, which is the thing being
measured. Every step here is either a source margin number, a list index proven equal, or a
neutral gid.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid  # noqa: E402
import run_hybrid  # noqa: E402
from neutral_identity import build_owner  # noqa: E402

from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402

OUT = EV / "results" / "x14_anchor_bridge.json"
ROWS: list[dict] = []
FAILED: list[str] = []
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]
REGION_SIZE = 8


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def place_anchor(anchor, print_lines, emitted, neutral, owner):
    """(region_ordinal, neutral_line_key) for one anchor, or a reason it is UNPLACEABLE.

    Deterministic and text-free. Returns `(None, reason)` rather than guessing.
    """
    hits = [i for i, ln in enumerate(print_lines) if ln.line_number == anchor.line_number]
    if not hits:
        return None, "NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER"
    if len(hits) > 1:
        return None, "AMBIGUOUS_MARGIN_NUMBER_ON_PAGE"
    i = hits[0]
    if i >= len(emitted):
        return None, "EMITTED_INDEX_OUT_OF_RANGE"
    gids = sorted(emitted[i].gids)
    if not gids:
        return None, "EMITTED_LINE_CARRIES_NO_NEUTRAL_INK"
    key = owner.get(gids[0])
    if key is None:
        return None, "FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE"
    ordinals = {ln.key: ln.ordinal for ln in neutral}
    return (ordinals[key] // REGION_SIZE, key), None


def main(limit: int = 8) -> int:
    report = []
    for name, path in DOCS:
        if not path.exists():
            continue
        print(f"\n== {name} ==")
        frozen_pages, _ = pdfium_hybrid.extract(path, limit=limit)
        gid_pages = run_hybrid.extract_with_gids(path, limit=limit)
        pages, per_page = [], {}
        for fp, (pno, chars) in zip(frozen_pages, gid_pages):
            page_obj, _diag = reconstruct_hybrid.reconstruct_page(fp)
            emitted = run_hybrid.emitted_lines(pno, chars)
            neutral = run_hybrid.neutral_skeleton(pno, chars)
            pages.append(page_obj)
            per_page[pno] = (page_obj, emitted, neutral, build_owner(neutral))

        # the index step must be exact, re-asserted locally rather than inherited
        drift = [
            pno
            for pno, (pg, em, _n, _o) in per_page.items()
            if [ln.text for ln in pg.print_lines] != [e.text() for e in em]
        ]
        check(
            f"{name}: emitted_lines matches Page.print_lines index-for-index",
            [],
            drift,
            "the bridge's index step is only sound while this holds",
        )

        anchors = extract_anchors(pages)
        placed, reasons = 0, Counter()
        examples = []
        for a in anchors:
            entry = per_page.get(a.page_number)
            if entry is None:
                reasons["PAGE_NOT_IN_SAMPLE"] += 1
                continue
            pg, em, neutral, owner = entry
            result, reason = place_anchor(a, pg.print_lines, em, neutral, owner)
            if reason:
                reasons[reason] += 1
                continue
            placed += 1
            if len(examples) < 3:
                examples.append(
                    {
                        "kind": a.kind,
                        "page": a.page_number,
                        "margin_line": a.line_number,
                        "region": result[0],
                        "neutral_line": list(result[1]),
                    }
                )
        rec = {
            "document": name,
            "pages": limit,
            "anchors_total": len(anchors),
            "placed_uniquely": placed,
            "unplaceable": dict(reasons),
            "examples": examples,
        }
        report.append(rec)
        print(f"  anchors={len(anchors)} placed={placed} unplaceable={dict(reasons)}")
        check(
            f"{name}: every anchor on a sampled page places uniquely",
            0,
            sum(v for k, v in reasons.items() if k != "PAGE_NOT_IN_SAMPLE"),
            "any residue here makes anchor discordance non-executable as frozen",
        )

    # ---- negative controls: the bridge must be able to REFUSE, not guess.
    class FakeLine:
        def __init__(self, n, t):
            self.line_number, self.text = n, t

    class FakeEmitted:
        def __init__(self, g):
            self._g = set(g)

        @property
        def gids(self):
            return self._g

    from neutral_identity import NeutralLine

    nl = NeutralLine(page=1, ordinal=0, baseline=0.0, x0=0, y0=0, x1=1, y1=1, gids=frozenset({5}))
    owner = build_owner([nl])
    check(
        "negative: a margin number present twice on a page is AMBIGUOUS, not guessed",
        "AMBIGUOUS_MARGIN_NUMBER_ON_PAGE",
        place_anchor(
            FakeLine(7, "X"), [FakeLine(7, "a"), FakeLine(7, "b")], [FakeEmitted({5}), FakeEmitted({5})], [nl], owner
        )[1],
    )
    check(
        "negative: a margin number that exists on no print line is refused",
        "NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER",
        place_anchor(FakeLine(99, "X"), [FakeLine(7, "a")], [FakeEmitted({5})], [nl], owner)[1],
    )
    check(
        "negative: an emitted line with no neutral ink is refused",
        "EMITTED_LINE_CARRIES_NO_NEUTRAL_INK",
        place_anchor(FakeLine(7, "X"), [FakeLine(7, "a")], [FakeEmitted(set())], [nl], owner)[1],
    )
    check(
        "positive: a clean anchor places on its region",
        (0, (1, 0)),
        place_anchor(FakeLine(7, "X"), [FakeLine(7, "a")], [FakeEmitted({5})], [nl], owner)[0],
    )

    doc = {
        "population": "DEVELOPMENT + synthetic -- no holdout opened, nothing scored",
        "chain": "Anchor(page, margin line_number) -> Page.print_lines index -> emitted_lines[i]"
        " -> ngid -> NeutralLine -> region",
        "text_matching_used": False,
        "region_size_neutral_lines": REGION_SIZE,
        "documents": report,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
