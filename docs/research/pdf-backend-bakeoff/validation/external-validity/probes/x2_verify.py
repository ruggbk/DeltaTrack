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

UNRESOLVED, AND NOT RESOLVED HERE. "the engine's spaces" is ambiguous between spaces PDFium
INVENTED and every U+0020 the contract drops, and MEASURED the two readings disagree:
generated-only PASSES on both development documents, all-U+0020 FAILS on `114-hr-2029/4`.
Both are run and reported; the headline field carries the stricter reading so G2 cannot open
on an interpretation chosen by this file. See amendment A24.

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


def self_test() -> int:
    """Both assertions must FAIL on the uncorrected adapter. Prove the gate can fire."""
    import pdfium_extended
    from contract_extended import CP as OLD_CP

    path = FIXTURES[0]
    pages, _ = pdfium_extended.extract(path, limit=4)
    n32 = sum(1 for pg in pages for g in pg.glyphs if g[OLD_CP] == 32)
    a_fails = n32 > 0
    print(f"[{'PASS' if a_fails else 'FAIL'}] X2-a FAILS on the uncorrected adapter: {n32} U+0020 glyphs")

    # X2-b on the corrected adapter, but with the spaces re-admitted on BOTH sides, is a
    # tautology; the meaningful negative control is that the uncorrected contract carries
    # engine spaces at all, which is what makes its boundaries not independently derived.
    ok, total, diffs = x2b(path, 4, "generated")
    print(f"[{'PASS' if ok else 'FAIL'}] X2-b holds on the corrected adapter: {total} lines, {len(diffs)} differing")
    return 0 if (a_fails and ok) else 1


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
        "AMBIGUITY": (
            "'the engine's spaces' is not determined by the frozen text and the two readings "
            "DISAGREE on development material. generated-only PASSES; all-U+0020 FAILS. This "
            "file therefore reports both and does NOT choose. The headline field below carries "
            "the STRICTER reading so that G2 cannot go green on an interpretation chosen here. "
            "See amendment A24; a ruling is required before execution readiness can open."
        ),
        "X2a_no_u0020": all_a,
        "X2b_rule_recovers_engine_spaces": all_all,
        "X2b_reading_generated_only": all_gen,
        "X2b_reading_all_u0020": all_all,
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
    if all_gen != all_all:
        print("\n  AMBIGUITY: the two readings of X2-b disagree. Not resolved here -- see A24.")
    print(f"wrote {OUT}")
    return 0 if (all_a and all_gen and all_all) else 1


if __name__ == "__main__":
    sys.exit(main())
