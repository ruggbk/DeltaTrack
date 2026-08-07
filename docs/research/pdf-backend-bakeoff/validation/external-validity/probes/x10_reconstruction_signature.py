"""x10 -- reconstruction segmentation as a FIRST-CLASS discordance. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic fixtures only. No holdout document is opened, no architecture
is run.

THE DEFECT THIS PROBE EXISTS TO REPRODUCE AND CLOSE

A21's Model G normalises architecture output onto neutral physical lines by source-glyph
partition. That is correct for IDENTITY -- each neutral line gets back exactly its own
glyphs -- and it is precisely why it can erase the thing A17.4 existed to observe:

    neutral N0 = ABC        H emits one line:  ABCDEF        X emits two:  ABC
    neutral N1 = DEF                                                       DEF

    partition gives   N0: H=ABC X=ABC      N1: H=DEF X=DEF      -> both SAME

H performed a cross-line merge and X did not, and the comparison reported no difference at
all, because `differs()` read only `state["state"]` while `H_CROSS_LINE_MERGE` travelled
as a diagnostic that entered nothing.

Part 1  the defect, reproduced under the superseded rule, in both directions
Part 2  the adversarial case matrix, with expected AND observed for each predicate
Part 3  non-vacuous symmetry: D(H,X) == D(X,H) AND the expected membership
Part 4  M3 is preserved -- text correctness and segmentation stay separate concepts
Part 5  M0's components on a mixed population, raw counts preserved
Part 6  negative controls: every predicate is shown capable of BOTH answers
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

from m3_boundaries import HeadingOutcome, decompose, heading_outcome  # noqa: E402
from neutral_identity import (  # noqa: E402
    EmittedLine,
    SourceGlyph,
    build_owner,
    cluster,
    line_discordance,
    line_state,
    m0,
    reconstruction_signature,
    region_discordance,
    segmentation_discordance,
    text_discordance,
)

OUT = EV / "results" / "x10_reconstruction_signature.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, implication: str = "") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def sg(gid, baseline, x0, x1, h=10.0):
    return SourceGlyph(gid, baseline, x0, baseline, x1, baseline + h)


# Three neutral lines, 12 pt apart, tolerance 0.5 x 10 = 5.0 -> three distinct clusters.
#   N0 = gids 0,1,2 = A B C      N1 = gids 3,4,5 = D E F      N2 = gids 6,7,8 = G H I
TEXTS = "ABCDEFGHI"
GLYPHS = [sg(i, 700 - 12 * (i // 3), 72 + 20 * (i % 3), 90 + 20 * (i % 3)) for i in range(9)]
LINES = cluster(GLYPHS, 1)
OWNER = build_owner(LINES)

N0, N1, N2 = (ln.key for ln in LINES)


def el(*gids, insert_after=None, sub=None) -> EmittedLine:
    """Build one emitted printed line from source gids, in source order.

    `insert_after` puts an ARCHITECTURE-INSERTED space (gid None) after that gid -- a word
    space the arm decided on. `sub` replaces one gid's character, to make a text difference
    that carries no segmentation difference.
    """
    cells: list[tuple[int | None, str]] = []
    for g in gids:
        cells.append((g, sub[1] if sub and g == sub[0] else TEXTS[g]))
        if insert_after is not None and g == insert_after:
            cells.append((None, " "))
    return EmittedLine(cells)


def old_differs(state: dict) -> bool:
    """The SUPERSEDED A21 rule, kept executable so the defect is demonstrated, not asserted."""
    return state["state"] != "SAME"


# --------------------------------------------------------------------------- part 1


def part1_defect() -> list[dict]:
    scenarios = [
        ("H merges N0+N1, X emits them separately", [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]),
        ("the inverse: H separate, X merges", [el(0, 1, 2), el(3, 4, 5)], [el(0, 1, 2, 3, 4, 5)]),
        ("pure within-line split of N0, rejoined in source order", [el(0, 1, 2)], [el(0), el(1, 2)]),
    ]
    out = []
    for title, h, x in scenarios:
        print(f"\n  -- {title}")
        rec = {"scenario": title, "lines": []}
        for ln in (LINES[0], LINES[1]):
            st = line_state(h, x, ln, OWNER)
            d = st["diagnostics"]
            print(f"     line {ln.ordinal} text state:            {st['state']}")
            print(f"     line {ln.ordinal} H_CROSS_LINE_MERGE:    {d['H_CROSS_LINE_MERGE']}")
            print(f"     line {ln.ordinal} X_CROSS_LINE_MERGE:    {d['X_CROSS_LINE_MERGE']}")
            print(f"     line {ln.ordinal} SUPERSEDED D-frame:    {old_differs(st)}")
            print(f"     line {ln.ordinal} NEW D-frame:           {line_discordance(st)}")
            rec["lines"].append(
                {
                    "line": ln.key,
                    "state": st["state"],
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "H_CROSS_LINE_MERGE": d["H_CROSS_LINE_MERGE"],
                    "X_CROSS_LINE_MERGE": d["X_CROSS_LINE_MERGE"],
                    "superseded_d_frame": old_differs(st),
                    "new_d_frame": line_discordance(st),
                }
            )
        out.append(rec)

    merge_h, merge_x = [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]
    st0 = line_state(merge_h, merge_x, LINES[0], OWNER)
    st1 = line_state(merge_h, merge_x, LINES[1], OWNER)
    check(
        "REPRODUCED: a cross-line merge/split leaves both text states SAME",
        ("SAME", "SAME"),
        (st0["state"], st1["state"]),
        "partition hands each neutral line back its own glyphs, so the text cannot differ",
    )
    check(
        "REPRODUCED: the superseded rule therefore drops it from the D-frame",
        (False, False),
        (old_differs(st0), old_differs(st1)),
        "the merge/split disagreement A17.4 exists to observe was erased",
    )
    check(
        "...while the merge WAS visible all along, as a diagnostic that entered nothing",
        (True, False),
        (st0["diagnostics"]["H_CROSS_LINE_MERGE"], st0["diagnostics"]["X_CROSS_LINE_MERGE"]),
    )
    check(
        "CLOSED: the new rule puts both neutral lines in the D-frame",
        (True, True),
        (line_discordance(st0), line_discordance(st1)),
    )

    # The second defect: agreement scored as discordance.
    empty = line_state([], [], LINES[0], OWNER)
    check(
        "REPRODUCED: a line NEITHER arm emits was in the D-frame under the superseded rule",
        (True, "BOTH_ABSENT"),
        (old_differs(empty), empty["state"]),
        "every running head, page number and VerDate stamp both arms correctly drop as "
        "chrome entered a census frame as discordance",
    )
    check(
        "CLOSED: a shared drop is not a comparative discordance",
        False,
        line_discordance(empty),
        "PRE-REGISTRATION 5.8: the D-frame 'cannot see a failure both architectures share. "
        "That is exactly why the C-frame exists'",
    )
    return out


# --------------------------------------------------------------------------- part 2


def m3_reads_same(a: str, b: str) -> bool:
    """Would M3 see these two projections as the same heading? Its own frozen decomposition."""
    return decompose(a) == decompose(b)


CASES = [
    # name, H, X, {line: (expect_text, expect_segmentation)}
    (
        "H merge / X split",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2), el(3, 4, 5)],
        {N0: (False, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "H split / X merge",
        [el(0, 1, 2), el(3, 4, 5)],
        [el(0, 1, 2, 3, 4, 5)],
        {N0: (False, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "same merge on both arms",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2, 3, 4, 5)],
        {N0: (False, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "different merge spans (H: N0+N1, X: N1+N2)",
        [el(0, 1, 2, 3, 4, 5), el(6, 7, 8)],
        [el(0, 1, 2), el(3, 4, 5, 6, 7, 8)],
        {N0: (False, True), N1: (False, True), N2: (False, True)},
    ),
    (
        "same glyphs / different emitted-line cardinality",
        [el(0, 1, 2)],
        [el(0), el(1, 2)],
        {N0: (True, True), N1: (False, False), N2: (False, False)},
    ),
    (
        "different text / same cardinality",
        [el(0, 1, 2)],
        [EmittedLine([(0, "A"), (1, "B"), (2, "Z")])],
        {N0: (True, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "same text / same cardinality",
        [el(0, 1, 2)],
        [el(0, 1, 2)],
        {N0: (False, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "merge WITH a spacing difference",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2, insert_after=0), el(3, 4, 5)],
        {N0: (True, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "split WITHOUT a spacing difference",
        [el(0, 1, 2)],
        [el(0, 1), el(2)],
        {N0: (True, True), N1: (False, False), N2: (False, False)},
    ),
]


def part2_matrix() -> list[dict]:
    rows = []
    bad = []
    for name, h, x, expect in CASES:
        states = [line_state(h, x, ln, OWNER) for ln in LINES]
        in_d = region_discordance(states)
        for ln, st in zip(LINES, states):
            et, es = expect[ln.key]
            ot, os_ = text_discordance(st), segmentation_discordance(st)
            rows.append(
                {
                    "case": name,
                    "line": list(ln.key),
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "expected_text_discordance": et,
                    "observed_text_discordance": ot,
                    "expected_segmentation_discordance": es,
                    "observed_segmentation_discordance": os_,
                    "in_d_frame": line_discordance(st),
                    "m3_reads_same": m3_reads_same(st["h_text"], st["x_text"]),
                }
            )
            if (et, es) != (ot, os_):
                bad.append(f"{name}@{ln.ordinal} expected=({et},{es}) observed=({ot},{os_})")
        rows.append({"case": name, "REGION_IN_D_FRAME": in_d})
    check(
        "every adversarial case matches its expected text/segmentation verdict",
        [],
        bad,
        "the two predicates are independent and each fires only where it should",
    )
    expected_regions = [True, True, False, True, True, True, False, True, True]
    observed_regions = [region_discordance([line_state(h, x, ln, OWNER) for ln in LINES]) for _, h, x, _ in CASES]
    check("region-level D-frame membership matches the frozen expectation", expected_regions, observed_regions)
    return rows


# --------------------------------------------------------------------------- part 3


def part3_symmetry() -> None:
    asym, wrong = [], []
    for name, h, x, expect in CASES:
        for ln in LINES:
            fwd = line_discordance(line_state(h, x, ln, OWNER))
            rev = line_discordance(line_state(x, h, ln, OWNER))
            if fwd != rev:
                asym.append(f"{name}@{ln.ordinal}")
            want = expect[ln.key][0] or expect[ln.key][1]
            if fwd != want:
                wrong.append(f"{name}@{ln.ordinal} expected={want} observed={fwd}")
    check("D(H,X) == D(X,H) on every adversarial case", [], asym)
    check(
        "...and the membership is the EXPECTED one, so symmetry is not vacuous",
        [],
        wrong,
        "the prior test passed on False == False while the disagreement was being erased",
    )
    # the single case the prior suite got wrong, stated in the form the review asked for
    h, x = [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]
    check(
        "merge/split: D(H,X) and D(X,H) are both TRUE, not merely equal",
        (True, True),
        (
            line_discordance(line_state(h, x, LINES[0], OWNER)),
            line_discordance(line_state(x, h, LINES[0], OWNER)),
        ),
    )


# --------------------------------------------------------------------------- part 4

# One neutral line carrying a 13-glyph heading; the space between the words is INSERTED by
# the architecture (gid None), never a source glyph, exactly as a generated space is.
HEAD_TEXT = "FAMILYHOUSING"
HEAD_GLYPHS = [SourceGlyph(i, 500.0, 72.0 + 8 * i, 500.0, 79.0 + 8 * i, 510.0) for i in range(13)]
HEAD_LINES = cluster(HEAD_GLYPHS, 2)
HEAD_OWNER = build_owner(HEAD_LINES)
HEAD = HEAD_LINES[0]
ORACLE = "FAMILY HOUSING"


def head_line(*groups) -> list[EmittedLine]:
    """Emitted lines for the heading; each group is (gids, space_after_gid_or_None)."""
    out = []
    for gids, space_after in groups:
        cells: list[tuple[int | None, str]] = []
        for g in gids:
            cells.append((g, HEAD_TEXT[g]))
            if space_after is not None and g == space_after:
                cells.append((None, " "))
        out.append(EmittedLine(cells))
    return out


def part4_m3_preserved() -> None:
    all_g = list(range(13))
    # (a) same physical glyphs, H welds the two words, X spaces them -> a real M3 defect
    h_weld = head_line((all_g, None))
    x_space = head_line((all_g, 5))
    st = line_state(h_weld, x_space, HEAD, HEAD_OWNER)
    check("weld vs space is TEXT_DIFFERS", "TEXT_DIFFERS", st["state"])
    check("...and carries NO segmentation discordance", False, segmentation_discordance(st))
    outcome, hs, xs = heading_outcome(ORACLE, st["h_text"], st["x_text"])
    check("...and reaches M3 as X_CORRECTS", HeadingOutcome.X_CORRECTS, outcome)
    check("...with H scoring exactly one weld", (1, 0), (hs.weld, hs.split))
    check("...and X clean", True, xs.clean)

    # (b) same projected heading text, different emitted-line grouping -> segmentation only
    h_one = head_line((all_g, 5))
    x_two = head_line((list(range(6)), None), (list(range(6, 13)), None))
    st2 = line_state(h_one, x_two, HEAD, HEAD_OWNER)
    check("a split heading IS a segmentation discordance", True, segmentation_discordance(st2))
    check("...and enters the D-frame", True, line_discordance(st2))
    outcome2, hs2, xs2 = heading_outcome(ORACLE, st2["h_text"], st2["x_text"])
    check(
        "...but fabricates NO M3 word-boundary error",
        (HeadingOutcome.BOTH_CLEAN, 0, 0),
        (outcome2, xs2.weld, xs2.split),
        "the '\\n' join is read as a word boundary by m3_boundaries.decompose, so a split "
        "at a word boundary costs nothing -- joining by '' would have scored a false weld",
    )
    check("...and both arms stay clean against the oracle", (True, True), (hs2.clean, xs2.clean))

    # (c) a split MID-WORD is a real boundary defect and must still be caught
    x_midword = head_line((list(range(3)), None), (list(range(3, 13)), 5))
    st3 = line_state(h_one, x_midword, HEAD, HEAD_OWNER)
    _, _, xs3 = heading_outcome(ORACLE, st3["h_text"], st3["x_text"])
    check(
        "a split MID-WORD still scores a real M3 split",
        1,
        xs3.split,
        "the arm genuinely broke FAMILY across two printed lines",
    )


# --------------------------------------------------------------------------- part 5


def part5_m0() -> dict:
    """M0 on a mixed synthetic population, so every component has a nonzero member."""
    population = [
        line_state([el(0, 1, 2)], [el(0, 1, 2)], LINES[0], OWNER),  # agreement
        line_state([el(0, 1, 2)], [EmittedLine([(0, "A"), (1, "B"), (2, "Z")])], LINES[0], OWNER),  # text only
        line_state([el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)], LINES[0], OWNER),  # segmentation only
        line_state([el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2, insert_after=0), el(3, 4, 5)], LINES[0], OWNER),  # both
        line_state([], [], LINES[2], OWNER),  # shared drop
    ]
    got = m0(population)
    check(
        "M0's components decompose the population exactly",
        {
            "neutral_lines": 5,
            "M0a_text": 2,
            "M0b_segmentation": 2,
            "M0_any": 3,
            "M0b_only": 1,
            "M0a_only": 1,
            "both_absent": 1,
        },
        {
            "neutral_lines": got["neutral_lines"],
            "M0a_text": got["M0a_text"],
            "M0b_segmentation": got["M0b_segmentation"],
            "M0_any": got["M0_any"],
            "M0b_only": got["M0b_only_segmentation"],
            "M0a_only": got["M0a_only_text"],
            "both_absent": got["both_absent"],
        },
        "M0b_only is the count that was structurally unreachable under the superseded rule",
    )
    check("M0_any is the UNION, never a sum", True, got["M0_any"] < got["M0a_text"] + got["M0b_segmentation"])
    return got


# --------------------------------------------------------------------------- part 6


def part6_negative_controls() -> None:
    """Every predicate must be shown capable of BOTH answers on this fixture set.

    A gate that has only ever returned one value cannot distinguish 'no defect' from
    'cannot see defects'. These are the paired opposites.
    """
    seen_text = {text_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    seen_seg = {segmentation_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    seen_line = {line_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    check("TEXT_DISCORDANCE returns both True and False on the matrix", [False, True], sorted(seen_text))
    check("SEGMENTATION_DISCORDANCE returns both True and False", [False, True], sorted(seen_seg))
    check("line D-frame membership returns both True and False", [False, True], sorted(seen_line))
    check(
        "ANCHOR_DISCORDANCE returns both",
        [False, True],
        [
            region_discordance([], h_anchors=("ACCOUNT: X",), x_anchors=("ACCOUNT: X",)),
            region_discordance([], h_anchors=("ACCOUNT: X",), x_anchors=()),
        ],
    )
    # the signature itself must be able to distinguish, not merely to be equal
    sig_merge = reconstruction_signature([el(0, 1, 2, 3, 4, 5)], LINES[0], OWNER)
    sig_plain = reconstruction_signature([el(0, 1, 2)], LINES[0], OWNER)
    sig_split = reconstruction_signature([el(0), el(1, 2)], LINES[0], OWNER)
    check("the signature separates merge, plain and split", 3, len({sig_merge, sig_plain, sig_split}))  # noqa: E501
    check(
        "the signature is INSENSITIVE to an inserted space",
        reconstruction_signature([el(0, 1, 2)], LINES[0], OWNER),
        reconstruction_signature([el(0, 1, 2, insert_after=0)], LINES[0], OWNER),
        "a word-space decision must never register as a segmentation difference, or M3 "
        "would see a boundary error that does not exist",
    )
    check(
        "the signature names the merge SPAN, so different spans are distinguishable",
        True,
        reconstruction_signature([el(3, 4, 5, 0, 1, 2)], LINES[1], OWNER)
        != reconstruction_signature([el(3, 4, 5, 6, 7, 8)], LINES[1], OWNER),
    )


def main() -> int:
    print("== part 1: the defect, reproduced under the superseded rule ==")
    defect = part1_defect()
    print("\n== part 2: adversarial case matrix ==")
    matrix = part2_matrix()
    print("\n== part 3: non-vacuous symmetry ==")
    part3_symmetry()
    print("\n== part 4: M3 is preserved ==")
    part4_m3_preserved()
    print("\n== part 5: M0 components ==")
    m0_out = part5_m0()
    print("\n== part 6: negative controls ==")
    part6_negative_controls()

    doc = {
        "population": "SYNTHETIC only -- no holdout opened, no architecture run",
        "supersedes": "A21's D-frame membership rule (any line not SAME)",
        "defect": defect,
        "matrix": matrix,
        "m0": m0_out,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} tests pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
