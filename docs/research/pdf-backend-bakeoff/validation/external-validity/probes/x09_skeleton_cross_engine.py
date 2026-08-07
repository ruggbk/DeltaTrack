"""x09 -- cross-engine control on the NEUTRAL SKELETON, not on line counts.

NOT CONFIRMATORY. DEVELOPMENT documents only.

A19 re-pointed the protocol's 10 % PyMuPDF cross-check at "per-page neutral line counts".
That is insufficient and the review is right: two engines can both report 30 lines while
disagreeing about which baselines and which glyphs belong to each line. Counting is not
correspondence.

THE PROPERTY. The skeleton is PDFium-derived. Both architectures inherit it together, so a
PDFium geometry error cannot bias H against X -- but it CAN move the adjudication unit, and
a reader is entitled to know whether an independent engine sees substantially the same
physical lines. So the control is a GEOMETRIC CORRESPONDENCE between two independently
built skeletons.

THE MATCHING RULE, frozen here, derived from the intended property rather than from the old
0.95 (which belonged to a different estimand -- agreement on a page SET).

    A PDFium line P matches a PyMuPDF line M iff
        |baseline(P) - baseline(M)| <= 0.5 * median ink height of the PDFium page   and
        x-span overlap / min(span(P), span(M)) >= 0.5
    Matching is greedy by ascending baseline distance, each line used at most once, so it
    is one-to-one and deterministic. Ties break on the lower PDFium ordinal.

Reported: line counts both sides, one-to-one matched count and fraction, and the baseline
delta and x-overlap distributions. NO TEXT is used anywhere.
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

from neutral_identity import SourceGlyph, cluster, eligible  # noqa: E402

OUT = EV / "results" / "x09_skeleton_cross_engine.json"
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]
OVERLAP_MIN = 0.5


def pdfium_lines(path: Path, limit: int):
    import pdfium_hybrid
    from contract_hybrid import GEN, UPRIGHT, VBOX, X0, X1

    pages, _ = pdfium_hybrid.extract(path, limit=limit)
    out = {}
    for p in pages:
        glyphs = []
        for i, c in enumerate(p.chars):
            box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
            gid = None if c[GEN] else i
            if eligible(gid, box, bool(c[UPRIGHT])):
                out.setdefault(p.page_number, []).append(SourceGlyph(gid, c[2], box[0], box[1], box[2], box[3]))
        del glyphs
    return {pg: cluster(gs, pg) for pg, gs in out.items()}


def pymupdf_lines(path: Path, limit: int):
    import pymupdf

    doc = pymupdf.open(str(path))
    out = {}
    try:
        for pno in range(min(limit, doc.page_count)):
            page = doc[pno]
            height = page.rect.height
            glyphs = []
            gid = 0
            for span in page.get_texttrace():
                d = span.get("dir", (1.0, 0.0))
                if not (abs(d[1]) < 1e-6 and d[0] > 0):
                    continue  # non-upright spans, the rule every adapter here applies
                for ch in span.get("chars", ()):
                    # (cp, gid, origin, bbox) -- and MuPDF is y-DOWN from the page top,
                    # so every y is flipped against the page height to reach PDF page
                    # space. Getting this wrong silently produces a skeleton that matches
                    # nothing, which reads like engine disagreement rather than a bug.
                    origin, bx = ch[2], ch[3]
                    if bx is None or origin is None:
                        continue
                    x0, y0, x1, y1 = bx
                    if (x1 - x0) <= 0 or (y1 - y0) <= 0:
                        continue
                    glyphs.append(SourceGlyph(gid, height - origin[1], x0, height - y1, x1, height - y0))
                    gid += 1
            out[pno + 1] = cluster(glyphs, pno + 1)
    finally:
        doc.close()
    return out


def match_page(p_lines, m_lines) -> dict:
    if not p_lines or not m_lines:
        return {"pdfium": len(p_lines), "pymupdf": len(m_lines), "matched": 0, "deltas": [], "overlaps": []}
    tol = 0.5 * (statistics.median([ln.y1 - ln.y0 for ln in p_lines]) or 1.0)
    cands = []
    for p in p_lines:
        for m in m_lines:
            d = abs(p.baseline - m.baseline)
            if d > tol:
                continue
            lo, hi = max(p.x0, m.x0), min(p.x1, m.x1)
            span = min(p.x1 - p.x0, m.x1 - m.x0)
            ov = (hi - lo) / span if span > 0 and hi > lo else 0.0
            if ov >= OVERLAP_MIN:
                cands.append((d, p.ordinal, m.ordinal, ov))
    cands.sort()
    used_p, used_m, deltas, overlaps = set(), set(), [], []
    for d, po, mo, ov in cands:
        if po in used_p or mo in used_m:
            continue
        used_p.add(po)
        used_m.add(mo)
        deltas.append(round(d, 4))
        overlaps.append(round(ov, 4))
    return {
        "pdfium": len(p_lines),
        "pymupdf": len(m_lines),
        "matched": len(used_p),
        "deltas": deltas,
        "overlaps": overlaps,
    }


def main(limit: int = 10) -> int:
    out = []
    for name, path in DOCS:
        if not path.exists():
            continue
        pl, ml = pdfium_lines(path, limit), pymupdf_lines(path, limit)
        tot_p = tot_m = tot_k = 0
        all_d, all_o = [], []
        for pg in sorted(set(pl) | set(ml)):
            r = match_page(pl.get(pg, []), ml.get(pg, []))
            tot_p += r["pdfium"]
            tot_m += r["pymupdf"]
            tot_k += r["matched"]
            all_d += r["deltas"]
            all_o += r["overlaps"]
        rec = {
            "document": name,
            "pages": limit,
            "pdfium_neutral_lines": tot_p,
            "pymupdf_neutral_lines": tot_m,
            "one_to_one_matched": tot_k,
            "matched_fraction_of_pdfium": round(tot_k / tot_p, 4) if tot_p else None,
            "baseline_delta_median": round(statistics.median(all_d), 4) if all_d else None,
            "baseline_delta_max": max(all_d) if all_d else None,
            "x_overlap_median": round(statistics.median(all_o), 4) if all_o else None,
            "x_overlap_min": min(all_o) if all_o else None,
        }
        out.append(rec)
        print(
            f"  {name:16} pdfium={tot_p:5} pymupdf={tot_m:5} matched={tot_k:5} "
            f"frac={rec['matched_fraction_of_pdfium']} "
            f"d_med={rec['baseline_delta_median']} ov_med={rec['x_overlap_median']}"
        )

    fracs = [r["matched_fraction_of_pdfium"] for r in out if r["matched_fraction_of_pdfium"] is not None]
    doc = {
        "population": "DEVELOPMENT -- not a holdout",
        "property": "do two independent engines see substantially the same physical line skeleton?",
        "rule": {
            "baseline_tolerance": "0.5 * median PDFium ink height on the page",
            "x_overlap_min": OVERLAP_MIN,
            "matching": "greedy by ascending baseline distance, one-to-one, ties on lower PDFium ordinal",
            "text_used": False,
        },
        "threshold_note": (
            "No threshold is adopted here. The protocol's old 0.95 belonged to a different "
            "estimand (agreement on a page SET) and must not be transplanted. A threshold "
            "should be set from the distribution below, before execution, and stated."
        ),
        "observed_matched_fraction": fracs,
        "documents": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
