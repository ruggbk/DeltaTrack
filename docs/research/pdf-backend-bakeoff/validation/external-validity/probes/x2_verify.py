"""x2_verify -- EXECUTE the X-2 contract assertions. RESULT-BEARING.

    frozen rule        PRE-REGISTRATION X-2:
                         X2-a  no glyph with codepoint 32 exists in the contract, on any page
                         X2-b  re-admitting the engine's spaces changes NO reconstructed
                               line -- the geometric rule independently recovers every
                               boundary they were supplying
    executable here    X2-a counts codepoint-32 glyphs directly in the emitted contract.
                       X2-b RE-RUNS the whole arm with the spaces re-admitted and compares
                       every reconstructed printed line, in order, byte for byte.
    test               this file is the test; `--self-test` proves X2-a can FAIL
    evidence           `results/x2_contract_assertions.json`

WHAT X2-b FALSIFIES, stated exactly:

    If PDFium-generated spaces are removed, X's geometric reconstruction must still recover
    the same printed-line text those generated spaces would have supplied.

    PASS -> the generated PDFium spaces are NOT NECESSARY to reproduce those boundaries.
    FAIL -> X is still dependent on a PDFium-generated boundary decision.

A PASS is deliberately narrow. It does NOT mean X is generally correct, does NOT mean X
reproduces all source spacing, and does NOT mean X matches H. Those are comparative and
oracle questions and this file cannot answer any of them.

SCOPE, per A24.1. "the engine's spaces" means PDFium-GENERATED U+0020
(`FPDFText_IsGenerated == true`). The frozen prose admitted two readings; generated-only is
now operative and the all-source-spaces comparison is retained as a DEVELOPMENT DIAGNOSTIC
only -- it can differ without closing G2 and without voiding X, because a content-stream
space was supplied by the PDF rather than invented by PDFium, and requiring X to reproduce
it would make this a partial H/X equivalence gate.

BLOCKING DEFECT IN THIS GATE, found by its own negative control and NOT repaired here.
Re-admitting generated spaces currently changes NOTHING that reaches the reconstruction:
they report `font_size` exactly 1.0 (PDFium gives generated characters the identity matrix)
and `cluster_lines` keeps `size > _SIZE_FLOOR` with `_SIZE_FLOOR = 1.0`, so all 565 of them
are dropped first. Both sides then reconstruct an identical glyph set -- 3914 glyphs either
way -- so X2-b as executed compares a page against itself and CANNOT FAIL. `--self-test`
asserts this and fails until it is resolved. See amendment A25; making the gate non-vacuous
changes what it measures, which is a ruling rather than an edit.

WHY THIS RUNS THE ARM TWICE RATHER THAN ASSERTING. §5's own words: a failure here means the
rule is not doing the work and the run is void for X. That is a claim about BEHAVIOUR, so
the only honest check re-runs the behaviour. The previous state of this gate was a JSON file
asserting its own success -- G2 was green on a hand-written record naming "fake-doc-123".

WHAT X2-b IS REALLY TESTING. Phase 3's D2 found `pdfium_extended.py` taking eight of every
nine word boundaries from PDFium's invented spaces while claiming to decide them
geometrically. If the ported rule genuinely recovers those boundaries, adding the engine's
spaces back is a no-op on the reconstructed text. If it does not, the lines differ and X's
independence is disproved -- on development material, before any holdout document is opened.

NEGATIVE CONTROL. `--self-test` runs both assertions against
`validation/phase2/pdfium_extended.py`, the UNCORRECTED adapter, which is known to emit
U+0020. Both must FAIL there. A gate that has only ever returned PASS cannot distinguish
"the contract holds" from "this check cannot see a violation".
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


def x2b(path: Path, limit: int, readmit: str) -> tuple[bool, int, list[str]]:
    """Re-admitting spaces under `readmit` must change no reconstructed printed line.

    BOTH readings of "the engine's spaces" are run, because the frozen wording does not
    determine which is meant and they disagree on development material:

      "generated"  only spaces PDFium INVENTED. Supported by X-2's own sentence that not
                   carrying U+0020 "excludes engine-invented spaces without the Experimental
                   predicate", and by X2-b's "the boundaries THEY were supplying".
      "all"        every U+0020 the contract drops, which under X-2 includes real
                   content-stream spaces. Supported by X-2's rationale that "a space carries
                   no ink" -- true of a content-stream space too -- and by X2-a, which is
                   stated over ALL codepoint-32 glyphs.
    """
    without, _ = pdfium_extended_corrected.extract(path, limit=limit)
    with_, _ = pdfium_extended_corrected.extract(path, limit=limit, readmit=readmit)
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


def generated_space_boundaries(path: Path, limit: int) -> list[tuple[int, int]]:
    """(sci_before, sci_after) for every PDFium-GENERATED space between two real glyphs.

    These are exactly the boundaries X2-b is about: places where PDFium INVENTED a word
    space, so X's geometric rule must recover the boundary on its own.
    """
    import run_hybrid
    from contract_hybrid import CP, GEN

    out = []
    for _pno, chars in run_hybrid.extract_with_gids(path, limit=limit):
        for i in range(1, len(chars) - 1):
            _gid, c = chars[i]
            if not (c[GEN] and c[CP] == 32):
                continue
            pg, pc = chars[i - 1]
            ng, nc = chars[i + 1]
            if pc[GEN] or nc[GEN] or pc[CP] in (32, 13, 10) or nc[CP] in (32, 13, 10):
                continue
            out.append((pg, ng))
    return out


def readmission_reaches_reconstruction(path: Path, limit: int) -> tuple[bool, dict]:
    """Does re-admitting generated spaces change what the reconstruction actually sees?

    THE PRECONDITION FOR X2-b MEANING ANYTHING. X2-b compares the reconstruction with and
    without PDFium-generated U+0020. If those spaces never reach the reconstruction, the two
    sides are the same input and the assertion compares a page against itself -- it passes
    for a reason that has nothing to do with whether X's rule recovers boundaries.

    MEASURED, and it currently FAILS: every generated space reports `font_size` exactly
    1.0, because PDFium hands generated characters the identity matrix, while
    `reconstruct_extended_corrected.cluster_lines` keeps `size > _SIZE_FLOOR` with
    `_SIZE_FLOOR = 1.0`. `1.0 > 1.0` is false, so all of them are dropped before a single
    boundary is considered.
    """
    stats = {}
    for mode in ("none", "generated"):
        pages, _ = pdfium_extended_corrected.extract(path, limit=limit, readmit=mode)
        kept = spaces_kept = 0
        for pg in pages:
            for row in reconstruct_extended_corrected.cluster_lines(pg):
                kept += len(row)
                spaces_kept += sum(1 for g in row if g[pdfium_extended_corrected.CP] == 32)
        stats[mode] = {
            "glyphs_in_contract": sum(len(pg.glyphs) for pg in pages),
            "u0020_in_contract": sum(1 for pg in pages for g in pg.glyphs if g[pdfium_extended_corrected.CP] == 32),
            "glyphs_reaching_reconstruction": kept,
            "u0020_reaching_reconstruction": spaces_kept,
        }
    reaches = stats["generated"]["glyphs_reaching_reconstruction"] != stats["none"]["glyphs_reaching_reconstruction"]
    return reaches, stats


def x2b_can_fail(path: Path, limit: int) -> tuple[bool, str]:
    """NEGATIVE CONTROL for the authoritative X2-b predicate itself.

    The distinction this exists to close: "G2 notices x2_verify exited 1" is NOT the same
    claim as "X2-b detects dependence on a PDFium-generated space". Only the second is the
    property X2-b gates, and until this control existed nothing established it.

    THE SABOTAGE TRAVELS THE REAL PATH. It does not mock `x2b`, does not force an exit code
    and does not touch confirmatory inputs. It wraps the actual geometric spacing decision
    -- `reconstruct_extended_corrected.wants_space` -- so that ONE boundary which a
    PDFium-generated space also supplies is suppressed. Everything downstream is the
    production path: extraction, the rule, reconstruction, re-admission, and the
    line-by-line comparison.

        without generated spaces   the boundary is gone -> reconstructed text differs
        with them re-admitted      the generated glyph supplies it -> boundary restored
        X2b_generated_only         FAIL

    That asymmetry is precisely "X still depends on a PDFium-generated boundary decision",
    which is the condition X2-b exists to reject.

    The wrapper is installed by this function, used, and removed. There is NO configuration
    surface on the production module: default scoring behaviour is unreachable from here and
    the sabotage cannot be switched on by anything but this test.
    """
    real = reconstruct_extended_corrected.wants_space
    candidates = generated_space_boundaries(path, limit)
    try:
        for pg, ng in candidates[:40]:

            def sabotaged(prev, cur, _pg=pg, _ng=ng):
                if prev[pdfium_extended_corrected.SCI] == _pg and cur[pdfium_extended_corrected.SCI] == _ng:
                    return False  # DEVELOPMENT-only fault: pretend the rule missed this one
                return real(prev, cur)

            reconstruct_extended_corrected.wants_space = sabotaged
            ok, _total, diffs = x2b(path, limit, "generated")
            if not ok:
                return False, f"suppressed the boundary between source chars {pg} and {ng}: {diffs[0]}"
    finally:
        reconstruct_extended_corrected.wants_space = real
    return True, "no single suppressed generated-space boundary changed a reconstructed line"


def self_test() -> int:
    """Prove BOTH assertions can fail, through their real semantic paths."""
    ok = True
    path = FIXTURES[0]

    # --- X2-a can fail: the UNCORRECTED adapter emits U+0020 by the thousand.
    import pdfium_extended
    from contract_extended import CP as OLD_CP

    pages, _ = pdfium_extended.extract(path, limit=4)
    n32 = sum(1 for pg in pages for g in pg.glyphs if g[OLD_CP] == 32)
    a_fails = n32 > 0
    ok &= a_fails
    print(f"[{'PASS' if a_fails else 'FAIL'}] X2-a FAILS on the uncorrected adapter: {n32} U+0020 glyphs")

    # --- X2-b holds on the real corrected arm.
    held, total, diffs = x2b(path, 4, "generated")
    ok &= held
    print(f"[{'PASS' if held else 'FAIL'}] X2-b gate HOLDS unsabotaged: {total} lines, {len(diffs)} differing")

    # --- PRECONDITION: the re-admitted spaces must actually reach the reconstruction.
    reaches, stats = readmission_reaches_reconstruction(path, 4)
    ok &= reaches
    print(
        f"[{'PASS' if reaches else 'FAIL'}] re-admitted generated spaces REACH the reconstruction\n"
        f"        none:      {stats['none']['u0020_in_contract']:4} U+0020 in contract, "
        f"{stats['none']['glyphs_reaching_reconstruction']} glyphs reach reconstruction\n"
        f"        generated: {stats['generated']['u0020_in_contract']:4} U+0020 in contract, "
        f"{stats['generated']['glyphs_reaching_reconstruction']} glyphs reach reconstruction, "
        f"{stats['generated']['u0020_reaching_reconstruction']} of them spaces"
    )
    if not reaches:
        print(
            "        => X2-b IS VACUOUS: both sides reconstruct the identical glyph set, so the\n"
            "           assertion compares a page against itself. Generated spaces report\n"
            "           font_size exactly 1.0 (PDFium hands them the identity matrix) and\n"
            "           cluster_lines keeps `size > _SIZE_FLOOR` with _SIZE_FLOOR = 1.0.\n"
            "           BLOCKING -- see amendment A25. Not repaired here: making the gate\n"
            "           non-vacuous changes what it measures, which is a ruling, not an edit."
        )

    # --- X2-b can fail, through the rule itself. Only meaningful once the precondition holds.
    n_bounds = len(generated_space_boundaries(path, 4))
    failed, detail = x2b_can_fail(path, 4)
    can_fail = not failed
    ok &= can_fail
    print(
        f"[{'PASS' if can_fail else 'FAIL'}] X2-b gate FAILS when the rule stops recovering a "
        f"generated-space boundary\n        {n_bounds} such boundaries on 4 pages; {detail}"
    )
    if not can_fail:
        print(
            "        => the sabotage fires in BOTH arms, because both arms reconstruct the\n"
            "           same glyph set. That is the vacuity above, seen from the rule side."
        )
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    results = []
    all_a = all_gen = all_all = True
    for path in FIXTURES:
        if not path.exists():
            print(f"  SKIP {path.name} (absent)")
            continue
        pages, summary = pdfium_extended_corrected.extract(path, limit=PAGE_LIMIT)
        ok_a, n32 = x2a(pages)
        ok_gen, n_lines, diffs_gen = x2b(path, PAGE_LIMIT, "generated")
        ok_all, _n, diffs_all = x2b(path, PAGE_LIMIT, "all")
        all_a &= ok_a
        all_gen &= ok_gen
        all_all &= ok_all
        results.append(
            {
                "path": str(path.relative_to(REPO)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pages": len(pages),
                "glyphs": summary["glyphs"],
                "u0020_dropped": summary["u0020_dropped"],
                "X2a_codepoint_32_glyphs": n32,
                "X2a_pass": ok_a,
                "X2b_reconstructed_lines_compared": n_lines,
                "X2b_generated_only_pass": ok_gen,
                "X2b_generated_only_differing_lines": diffs_gen,
                "X2b_all_u0020_pass": ok_all,
                "X2b_all_u0020_differing_lines": diffs_all,
            }
        )
        print(
            f"  {path.name:34} glyphs={summary['glyphs']:6} dropped={summary['u0020_dropped']:5} "
            f"X2a={'PASS' if ok_a else 'FAIL'}  X2b[generated]={'PASS' if ok_gen else 'FAIL'}  "
            f"X2b[all U+0020]={'PASS' if ok_all else 'FAIL'}  ({n_lines} lines)"
        )

    doc = {
        "population": "DEVELOPMENT",
        "assertions": {
            "X2a": "no glyph with codepoint 32 exists in the contract, on any page",
            "X2b": "re-admitting the engine's spaces changes no reconstructed printed line",
        },
        "method": "X2-b RE-RUNS the arm and compares every reconstructed printed line in order; "
        "it is not an assertion about the code",
        "RULING": (
            "A24.1 froze 'the engine's spaces' as PDFium-GENERATED U+0020 "
            "(FPDFText_IsGenerated == true). X2-b exists to prove the extended rule is not "
            "secretly consuming PDFium's own inserted boundary decisions -- the phase-3 D2 "
            "finding -- while X2-a separately guarantees no U+0020 crosses the seam. Requiring "
            "every CONTENT-STREAM space to be reproduced would turn X2-b into a partial H/X "
            "equivalence gate, making a genuine architecture disagreement void X before the "
            "independent oracle could say which arm is right."
        ),
        "X2a_no_u0020": all_a,
        "X2b_gate_generated_only": all_gen,
        "X2b_diagnostic_all_source_spaces": all_all,
        "X2b_gate_is_vacuous_SEE_A25": not readmission_reaches_reconstruction(FIXTURES[0], PAGE_LIMIT)[0],
        "fixtures": results,
        "adapter_blob": blob_sha(EV / "probes" / "pdfium_extended_corrected.py"),
        "reconstructor_blob": blob_sha(EV / "probes" / "reconstruct_extended_corrected.py"),
        "verifier_blob": blob_sha(HERE),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(
        f"\nX2-a {'PASS' if all_a else 'FAIL'}"
        f"   X2-b[generated only] {'PASS' if all_gen else 'FAIL'}"
        f"   X2-b[all U+0020] {'PASS' if all_all else 'FAIL'}"
    )
    if not all_all:
        print(
            "\n  NOTE: the all-source-spaces DIAGNOSTIC differs. Per A24.1 that is not a gate --\n"
            "  it records that X can genuinely disagree with content-stream spacing, which is a\n"
            "  comparative finding for the oracle to adjudicate, not a contract violation."
        )
    vacuous = not readmission_reaches_reconstruction(FIXTURES[0], PAGE_LIMIT)[0]
    if vacuous:
        print(
            "\n  BLOCKING (A25): the X2-b gate is VACUOUS -- re-admitting generated spaces changes\n"
            "  nothing that reaches the reconstruction, so the assertion compares a page against\n"
            "  itself and cannot fail. Exiting non-zero so G2 cannot open on an unsupported claim.\n"
            "  Run --self-test for the measurement."
        )
    print(f"wrote {OUT}")
    return 0 if (all_a and all_gen and not vacuous) else 1


if __name__ == "__main__":
    sys.exit(main())
