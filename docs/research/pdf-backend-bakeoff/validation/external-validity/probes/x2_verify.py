"""x2_verify -- EXECUTE the X-2 contract assertions. RESULT-BEARING.

    frozen rule    PRE-REGISTRATION X-2, as amended by A24.1 and A25:
                     X2-a  no glyph with codepoint 32 exists in X's contract, on any page
                     X2-b  on all X2-b-TESTABLE PDFium-generated boundaries, supplying
                           PDFium's generated boundary DECISIONS in addition to X's ordinary
                           geometric decisions must change no reconstructed printed line
    executable     X2-a counts codepoint-32 glyphs in the emitted contract. X2-b builds the
                   counterfactual X-prime and compares printed lines byte-for-byte.
    test           `--self-test` proves X2-a can FAIL, X2-b can PASS, X2-b can FAIL, and
                   that a zero denominator is caught separately
    evidence       `results/x2_contract_assertions.json`

WHY A BOUNDARY COUNTERFACTUAL AND NOT GLYPH RE-ADMISSION (A25). The first implementation
re-admitted PDFium-generated U+0020 as GLYPHS. Those characters report `font_size` exactly
1.0 -- PDFium hands generated characters the identity matrix -- and X's `cluster_lines`
keeps `size > _SIZE_FLOOR` with `_SIZE_FLOOR = 1.0`, so every one was dropped before a
single boundary was considered. Both sides reconstructed an identical glyph set and the
gate compared a page against itself: vacuous, and unable to fail.

The repair is to re-admit what a generated space actually CARRIES. It is not an ink glyph;
it is the single fact "there is a word boundary between source character i and source
character j". X-prime therefore uses X's own contract, its surviving ink glyphs, the same
clustering, ordering, chrome and margin handling and the same downstream reconstruction --
and differs ONLY in the word-boundary decision. No generated character ever enters X's
contract, is never clustered, never contributes geometry or a font size, and never receives
a neutral gid. X's scoring behaviour is untouched.

WHAT X2-b FALSIFIES, stated exactly:

    If PDFium's generated boundary decisions are supplied on top of X's own, X's
    reconstructed printed lines must not change -- i.e. X already recovered them.

    PASS -> PDFium's generated boundary decisions are NOT NECESSARY to those lines.
    FAIL -> X is still dependent on a PDFium-generated boundary decision.

A PASS is deliberately narrow. It does NOT mean X is generally correct, does NOT mean X
reproduces all source spacing, and does NOT mean X matches H. Those are comparative and
oracle questions this file cannot answer.

SCOPE, per A24.1. "the engine's spaces" means PDFium-GENERATED U+0020
(`FPDFText_IsGenerated == true`). The all-source-spaces comparison is retained as a
DEVELOPMENT DIAGNOSTIC under `all_source_space_diagnostic` -- explicitly NON-AUTHORITATIVE.
It can differ without closing G2 and without voiding X, because a content-stream space was
supplied by the PDF rather than invented by PDFium.

THE DENOMINATOR IS PART OF THE GATE. A PASS on zero testable boundaries is vacuous, so the
testable count is reported, required to be > 0, and checked by `x04` independently of the
boolean. Non-vacuity is established by evidence, never inferred from a PASS.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
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
sys.path.insert(0, str(BAKE / "validation" / "phase2"))

import pdfium_extended_corrected  # noqa: E402
import reconstruct_extended_corrected  # noqa: E402

OUT = EV / "results" / "x2_contract_assertions.json"

# DEVELOPMENT fixtures. Never a holdout member -- x04's G2 re-checks that against the
# frozen membership manifest rather than believing this list.
FIXTURES = [
    REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
    REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf",
]
PAGE_LIMIT = 8


def blob_sha(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)], capture_output=True, text=True, cwd=str(REPO)
    ).stdout.strip()


def x2a(pages) -> tuple[bool, int]:
    """No glyph with codepoint 32 exists in the contract, on any page."""
    n = sum(1 for pg in pages for g in pg.glyphs if g[pdfium_extended_corrected.CP] == 32)
    return n == 0, n


def generated_boundary_map(path: Path, limit: int) -> tuple[dict, dict]:
    """PDFium's GENERATED word-boundary decisions, keyed by stable source provenance.

    A PDFium-generated U+0020 is NOT an ink glyph. What it carries is exactly one fact:

        there is a word boundary between source character i and source character j

    So the boundary is identified as `(page_number, sci_before, sci_after)`, read from
    PDFium's own text-page character stream -- never from geometry, string matching,
    reconstructed line ordinals, or any X output.

    NEIGHBOUR RULE, derived rather than assumed. PDFium's stream carries generated
    newlines, runs of generated characters, control entries and content-stream spaces, so
    "index +/- 1" is not the intended boundary. The rule is: the nearest preceding and
    nearest following characters that are NOT generated and NOT CR/LF. If either side is a
    content-stream U+0020, the pair is recorded but classified untestable -- X-2 drops every
    U+0020, so those two characters can never be adjacent in X.
    """
    import run_hybrid
    from contract_hybrid import CP, GEN

    bmap: dict[tuple[int, int, int], bool] = {}
    census = {
        "generated_u0020_total": 0,
        "no_real_neighbour_before": 0,
        "no_real_neighbour_after": 0,
        "neighbour_is_content_stream_space": 0,
        "candidate_pairs": 0,
    }
    for pno, chars in run_hybrid.extract_with_gids(path, limit=limit):
        for i, (_gid, c) in enumerate(chars):
            if not (c[GEN] and c[CP] == 32):
                continue
            census["generated_u0020_total"] += 1
            j = i - 1
            while j >= 0 and (chars[j][1][GEN] or chars[j][1][CP] in (10, 13)):
                j -= 1
            k = i + 1
            while k < len(chars) and (chars[k][1][GEN] or chars[k][1][CP] in (10, 13)):
                k += 1
            if j < 0:
                census["no_real_neighbour_before"] += 1
                continue
            if k >= len(chars):
                census["no_real_neighbour_after"] += 1
                continue
            if chars[j][1][CP] == 32 or chars[k][1][CP] == 32:
                census["neighbour_is_content_stream_space"] += 1
                continue
            census["candidate_pairs"] += 1
            bmap[(pno, chars[j][0], chars[k][0])] = True
    return bmap, census


def classify_boundaries(path: Path, limit: int, bmap: dict) -> tuple[list, dict]:
    """Which generated boundaries can X's geometric decision actually be compared against?

    A boundary is X2-b-TESTABLE only when X could have made the same decision: both source
    characters must survive X's contract, land on the SAME X reconstructed line, and be
    ADJACENT in the pen-origin order on which `wants_space` is evaluated.

    CROSS-LINE PAIRS ARE NOT TESTABLE, and that is a considered reading rather than a
    convenience. X2-b asks whether X independently recovers a WORD boundary. When X assigns
    the two characters to different reconstructed lines, there is no within-line word
    boundary for X to have made: the disagreement is line-reconstruction behaviour, which
    A22/A23 already route to M0b and the D-frame. Inventing a word space across an X line
    break would make X2-b answer a segmentation question it was never scoped to.
    """
    pages, _ = pdfium_extended_corrected.extract(path, limit=limit)
    testable, stats = [], {
        "both_survive_x_contract": 0,
        "not_in_x_contract": 0,
        "same_x_line": 0,
        "different_x_lines": 0,
        "not_adjacent_in_pen_order": 0,
        "testable": 0,
    }
    for pg in pages:
        present = {g[pdfium_extended_corrected.SCI]: g for g in pg.glyphs}
        pairs = {(b, a) for (p, b, a) in bmap if p == pg.page_number}
        survived = {(b, a) for (b, a) in pairs if b in present and a in present}
        stats["both_survive_x_contract"] += len(survived)
        stats["not_in_x_contract"] += len(pairs) - len(survived)

        adjacency, same_line = set(), set()
        for row in reconstruct_extended_corrected.cluster_lines(pg):
            ordered = sorted(row, key=lambda g: g[pdfium_extended_corrected.ORIGIN_X])
            ids = [g[pdfium_extended_corrected.SCI] for g in ordered]
            same_line |= {(x, y) for x in ids for y in ids if x != y}
            adjacency |= set(zip(ids, ids[1:]))
        for pair in survived:
            if pair not in same_line:
                stats["different_x_lines"] += 1
                continue
            stats["same_x_line"] += 1
            if pair not in adjacency:
                stats["not_adjacent_in_pen_order"] += 1
                continue
            stats["testable"] += 1
            testable.append((pg.page_number, pair[0], pair[1]))
    return testable, stats


def reconstruct_with(path: Path, limit: int, decider_for_page):
    """Reconstruct every page with a per-page boundary decider. Ordinary X when None."""
    pages, _ = pdfium_extended_corrected.extract(path, limit=limit)
    out = []
    for pg in pages:
        page_obj, _em, _diag = reconstruct_extended_corrected.reconstruct_page(
            pg, decider=decider_for_page(pg.page_number)
        )
        out.append((pg.page_number, [ln.text for ln in page_obj.print_lines]))
    return out


def counterfactual_decider(page_number: int, bmap: dict, base):
    """X-prime's boundary decision: X's own rule OR a PDFium generated-boundary decision.

    X-prime is NOT a third architecture and never sees a generated glyph. It uses the same
    contract, the same surviving ink glyphs, the same clustering, ordering, chrome and
    margin handling, and the same downstream reconstruction. Only the boundary decision
    differs, which is precisely the quantity X2-b is about.
    """
    SCI_ = pdfium_extended_corrected.SCI

    def decide(prev, cur):
        if (page_number, prev[SCI_], cur[SCI_]) in bmap:
            return True
        return base(prev, cur)

    return decide


def x2b_generated_boundary_counterfactual(path: Path, limit: int, base=None, bmap=None):
    """AUTHORITATIVE X2-b. Supplying PDFium's generated boundary decisions in addition to
    X's ordinary geometric decisions must change no reconstructed printed line.

        X       ordinary X
        X'      ordinary X + the PDFium generated-boundary map
        PASS    X.print_lines == X'.print_lines, byte-for-byte, page-for-page, line-for-line
    """
    base = base or reconstruct_extended_corrected.wants_space
    if bmap is None:
        bmap, _ = generated_boundary_map(path, limit)
    x = reconstruct_with(path, limit, lambda _p: base)
    xp = reconstruct_with(path, limit, lambda p: counterfactual_decider(p, bmap, base))
    diffs = []
    for (pno, a), (_pno2, b) in zip(x, xp):
        if len(a) != len(b):
            diffs.append(f"p{pno}: {len(a)} lines vs {len(b)}")
            continue
        for i, (u, v) in enumerate(zip(a, b)):
            if u != v:
                diffs.append(f"p{pno} line {i}: X={u!r} X'={v!r}")
    total = sum(len(a) for _p, a in x)
    return not diffs, total, diffs


def all_source_space_diagnostic(path: Path, limit: int) -> tuple[bool, int, list[str]]:
    """A24.1's DEVELOPMENT diagnostic, explicitly NON-AUTHORITATIVE.

    Re-admits every U+0020 as a glyph and compares reconstructions. It differs from the gate
    in both scope (all source spaces, not just generated ones) and mechanism (glyph
    re-admission, not a boundary decision). Retained because it records that X can genuinely
    disagree with content-stream spacing; it never closes G2 and never voids X.
    """
    without, _ = pdfium_extended_corrected.extract(path, limit=limit)
    with_, _ = pdfium_extended_corrected.extract(path, limit=limit, readmit="all")
    diffs: list[str] = []
    total = 0
    for a, b in zip(without, with_):
        pa, _ea, _da = reconstruct_extended_corrected.reconstruct_page(a)
        pb, _eb, _db = reconstruct_extended_corrected.reconstruct_page(b)
        ta = [ln.text for ln in pa.print_lines]
        tb = [ln.text for ln in pb.print_lines]
        total += len(ta)
        if len(ta) != len(tb):
            diffs.append(f"p{a.page_number}: {len(ta)} lines vs {len(tb)}")
            continue
        for i, (x, y) in enumerate(zip(ta, tb)):
            if x != y:
                diffs.append(f"p{a.page_number} line {i}: {x!r} != {y!r}")
    return not diffs, total, diffs[:10]


def self_test() -> int:
    """Prove each assertion can take BOTH values, through its real semantic path."""
    ok = True
    path, limit = FIXTURES[0], 4
    real = reconstruct_extended_corrected.wants_space

    # --- X2-a can FAIL: the UNCORRECTED adapter emits U+0020 by the thousand.
    import pdfium_extended
    from contract_extended import CP as OLD_CP

    pages, _ = pdfium_extended.extract(path, limit=limit)
    n32 = sum(1 for pg in pages for g in pg.glyphs if g[OLD_CP] == 32)
    ok &= n32 > 0
    print(f"[{'PASS' if n32 > 0 else 'FAIL'}] X2-a FAIL control: uncorrected adapter emits {n32} U+0020")

    bmap, census = generated_boundary_map(path, limit)
    testable, stats = classify_boundaries(path, limit, bmap)

    # --- the denominator must be non-zero, or the gate means nothing.
    ok &= len(testable) > 0
    print(
        f"[{'PASS' if testable else 'FAIL'}] X2-b denominator control: "
        f"{census['generated_u0020_total']} generated U+0020 -> {census['candidate_pairs']} candidate pairs "
        f"-> {stats['testable']} X2-b-testable"
    )

    # --- X2-b can PASS, on the real arm.
    passed, total, diffs = x2b_generated_boundary_counterfactual(path, limit, real, bmap)
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] X2-b PASS control: X == X' on {total} printed lines")

    # --- X2-b can FAIL. Suppress ONE ordinary geometric decision that the PDFium map also
    #     supplies. X' keeps the boundary because the MAP supplies it, so the sabotage is
    #     isolated to ordinary X: separate callables, no global monkeypatch.
    SCI_ = pdfium_extended_corrected.SCI
    target = None
    for pno, sb, sa in testable:
        pages_x, _ = pdfium_extended_corrected.extract(path, limit=limit)
        for pg in pages_x:
            if pg.page_number != pno:
                continue
            by = {g[SCI_]: g for g in pg.glyphs}
            if sb in by and sa in by and real(by[sb], by[sa]):
                target = (pno, sb, sa)
                break
        if target:
            break

    if target is None:
        print("[FAIL] X2-b FAIL control: no testable boundary where ordinary wants_space is True")
        ok = False
    else:
        tp, tb_, ta_ = target

        def sabotaged(prev, cur):
            if prev[SCI_] == tb_ and cur[SCI_] == ta_:
                return False  # DEVELOPMENT-only fault, ordinary X only
            return real(prev, cur)

        sab_passed, _t, sab_diffs = x2b_generated_boundary_counterfactual(path, limit, sabotaged, bmap)
        ok &= not sab_passed
        print(
            f"[{'PASS' if not sab_passed else 'FAIL'}] X2-b FAIL control: suppressing the boundary "
            f"between source chars {tb_} and {ta_} on p{tp} makes X != X'\n"
            f"        {(sab_diffs[0] if sab_diffs else 'no differing line')}"
        )

    # --- zero-testable-boundary control: an empty map must not silently look like a PASS.
    empty_pass, _t, _d = x2b_generated_boundary_counterfactual(path, limit, real, {})
    empty_testable, _st = classify_boundaries(path, limit, {})
    zero_ok = empty_pass and not empty_testable
    ok &= zero_ok
    print(
        f"[{'PASS' if zero_ok else 'FAIL'}] zero-denominator control: an empty boundary map yields "
        f"{len(empty_testable)} testable boundaries and a vacuous PASS -- which is why G2 requires "
        f"the denominator separately"
    )
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    results = []
    all_a = all_gate = True
    total_testable = 0
    for path in FIXTURES:
        if not path.exists():
            print(f"  SKIP {path.name} (absent)")
            continue
        pages, summary = pdfium_extended_corrected.extract(path, limit=PAGE_LIMIT)
        ok_a, n32 = x2a(pages)
        bmap, census = generated_boundary_map(path, PAGE_LIMIT)
        testable, stats = classify_boundaries(path, PAGE_LIMIT, bmap)
        ok_gate, n_lines, diffs = x2b_generated_boundary_counterfactual(path, PAGE_LIMIT, None, bmap)
        ok_diag, _dt, diag_diffs = all_source_space_diagnostic(path, PAGE_LIMIT)

        # boundary-level diagnostic: does X's own rule recover each testable boundary?
        SCI_ = pdfium_extended_corrected.SCI
        recovered = missed = 0
        examples = []
        for pno, sb, sa in testable:
            for pg in pages:
                if pg.page_number != pno:
                    continue
                by = {g[SCI_]: g for g in pg.glyphs}
                if sb in by and sa in by:
                    got = reconstruct_extended_corrected.wants_space(by[sb], by[sa])
                    recovered += got
                    missed += not got
                    if len(examples) < 3:
                        examples.append(
                            {
                                "page": pno,
                                "sci_before": sb,
                                "char_before": chr(by[sb][pdfium_extended_corrected.CP]),
                                "sci_after": sa,
                                "char_after": chr(by[sa][pdfium_extended_corrected.CP]),
                                "ordinary_wants_space": bool(got),
                                "pdfium_generated_boundary": True,
                            }
                        )
        all_a &= ok_a
        all_gate &= ok_gate
        total_testable += stats["testable"]
        results.append(
            {
                "path": str(path.relative_to(REPO)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pages": len(pages),
                "glyphs": summary["glyphs"],
                "u0020_dropped": summary["u0020_dropped"],
                "X2a_codepoint_32_glyphs": n32,
                "X2a_pass": ok_a,
                "boundary_census": census,
                "boundary_classification": stats,
                "X2b_testable_boundaries": stats["testable"],
                "X2b_boundary_level_recovered_by_X": recovered,
                "X2b_boundary_level_missed_by_X": missed,
                "X2b_examples": examples,
                "X2b_printed_lines_compared": n_lines,
                "X2b_gate_pass": ok_gate,
                "X2b_differing_lines": diffs[:10],
                "X2b_diagnostic_all_source_spaces_pass": ok_diag,
                "X2b_diagnostic_all_source_differing_lines": diag_diffs,
            }
        )
        print(
            f"  {path.name:34} X2a={'PASS' if ok_a else 'FAIL'}  "
            f"testable={stats['testable']:4} (recovered={recovered} missed={missed})  "
            f"X2b={'PASS' if ok_gate else 'FAIL'} over {n_lines} lines  "
            f"[all-source diagnostic {'agrees' if ok_diag else 'differs'}]"
        )

    vacuous = total_testable == 0
    doc = {
        "population": "DEVELOPMENT",
        "assertions": {
            "X2a": "no glyph with codepoint 32 exists in the contract, on any page",
            "X2b": "on all X2-b-testable PDFium-generated boundaries, supplying PDFium's generated "
            "boundary decisions in addition to X's ordinary geometric decisions must change no "
            "reconstructed printed line",
        },
        "method": (
            "A25: the counterfactual re-admits the BOUNDARY DECISION, not the generated glyph. "
            "X' uses X's own contract, surviving ink glyphs, clustering, ordering, chrome and margin "
            "handling and downstream reconstruction; only the word-boundary decision differs. No "
            "generated character ever enters X's contract."
        ),
        "X2a_no_u0020": all_a,
        "X2b_gate_generated_only": all_gate,
        "X2b_testable_boundaries_total": total_testable,
        "X2b_gate_is_vacuous_SEE_A25": vacuous,
        "X2b_diagnostic_all_source_spaces": all(r["X2b_diagnostic_all_source_spaces_pass"] for r in results),
        "diagnostic_is_authoritative": False,
        "fixtures": results,
        "adapter_blob": blob_sha(EV / "probes" / "pdfium_extended_corrected.py"),
        "reconstructor_blob": blob_sha(EV / "probes" / "reconstruct_extended_corrected.py"),
        "verifier_blob": blob_sha(HERE),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(
        f"\nX2-a {'PASS' if all_a else 'FAIL'}   "
        f"X2-b gate {'PASS' if all_gate else 'FAIL'} on {total_testable} testable boundaries"
    )
    if vacuous:
        print("\n  BLOCKING: zero testable boundaries -- the gate would be vacuous. Failing closed.")
    print(f"wrote {OUT}")
    return 0 if (all_a and all_gate and not vacuous) else 1


if __name__ == "__main__":
    sys.exit(main())
