"""H6 — two things H4 asserted more strongly than it measured.

H4 reported max |Δ advance| = 0.0 pt over 390,582 endpoints and concluded the engines
"return the same advances". Both halves need narrowing.

  **A. The comparison ran on ROUNDED values.** Every adapter rounds `advance` to four
     decimal places on the way into `contract_extended`, so H4 established equality at the
     contract's 1e-4 pt precision. Whether the engines' raw returns are bit-identical was
     never tested, and it is a different claim. `raw_facts.py` re-reads the same glyphs at
     full precision and this probe compares those. **The expected answer is not assumed:**
     PDFium's glyph width arrives through a `c_float` (24-bit mantissa) and MuPDF's
     advance is computed in single precision too, so a small non-zero difference is a live
     possibility and would still leave the architectural result intact.

  **B. 4,579 of PDFium's 200,684 pairs (2.3 %) never joined**, and H4 reported the coverage
     without saying what was in the gap. If the unjoined population were concentrated on
     headings or on the display type that carries account names, the portability claim
     would not reach the places DeltaTrack most depends on. This probe classifies it.

NEGATIVE CONTROLS.

  N13  `raw_facts.check()` asserts the raw sidecar reproduces each adapter glyph for
       glyph. Without it this probe could compare a different population and report
       agreement.
  N14  the joined population is asserted to match H4's committed totals exactly. If the
       key set here differed, the "same population" claim in A would be false.
  N15  the raw comparison reports the EXACTLY-EQUAL count separately from the
       below-contract-precision count. Collapsing them is what produced the overstatement
       being corrected.
  N16  the unjoined diagnosis attempts a tolerance-based nearest-neighbour rematch. That is
       a diagnostic, not a repair: it exists to say whether the gap is a quantisation
       artefact of the join or a real difference between engines, and the rematched pairs
       are reported separately and never folded into H4's headline count.

Read-only. Writes JSON only under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
P2 = HERE.parents[0] / "phase2"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P2))

import raw_facts  # noqa: E402
from contract_extended import ADVANCE, BASELINE, CP, ORIGIN_X, UPRIGHT  # noqa: E402
from h04_page_scale_agreement import BACKENDS, DOCUMENTS, PAGES, _adjacent_pairs, _extract, _key  # noqa: E402

# TWO DIFFERENT QUANTITIES, and the first version of this probe conflated them.
#
#   QUANT_STEP        the contract's four-decimal quantisation step. Two values that differ
#                     by less than this can still round to different 4 dp results.
#   ROUND_MAX_ERROR   the largest error `round(x, 4)` can introduce, which is half a step.
#                     A difference below this is invisible to round-to-nearest.
#
# The bug: bins were computed against ROUND_MAX_ERROR and then labelled
# "at_or_above_contract_precision", so counts at or above 5e-5 were reported as counts at
# or above 1e-4. Every bin below now names its literal threshold instead.
QUANT_STEP = 1e-4
ROUND_MAX_ERROR = QUANT_STEP / 2

ORIGIN_TOL = 0.05
BASELINE_TOL = 0.6


def _is_float32(v: float) -> bool:
    """Does this value survive a round trip through single precision unchanged?

    If every one of an engine's advances is exactly representable in float32, the value
    reached Python through a single-precision path. That turns "the deltas are about
    1.5e-5" from an observation into a mechanism, and it is checkable rather than asserted.
    """
    return struct.unpack("f", struct.pack("f", v))[0] == v


def _detectable_epsilon_bracket(pairs: list[tuple], rule) -> dict:
    """How large must a RELATIVE advance perturbation be before the rule notices at all?

    The number that decides whether a cross-engine difference matters is not its absolute
    size, it is its size against the smallest perturbation the rule can feel. Reporting the
    delta alone invites the reader to guess at that comparison.

    Returned as a BRACKET, not a point: the ladder is decade-spaced, so the true threshold
    lies between the largest step that changed nothing and the smallest that changed
    something. Headroom is then quoted from the LARGEST-CHANGED-NOTHING end, which is the
    conservative direction.
    """
    ladder = (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1)
    changed_nothing: float | None = None
    for eps in ladder:
        for a, b in pairs:
            sa = tuple(v * (1 + eps) if i == ADVANCE and v is not None else v for i, v in enumerate(a))
            sb = tuple(v * (1 + eps) if i == ADVANCE and v is not None else v for i, v in enumerate(b))
            if rule(sa, sb) != rule(a, b):
                return {"largest_that_changed_nothing": changed_nothing, "smallest_that_changed_something": eps}
        changed_nothing = eps
    return {"largest_that_changed_nothing": changed_nothing, "smallest_that_changed_something": None}


def _type_size_profile(joined: list[float], unjoined: list[float]) -> dict:
    """Where does the unjoined population sit in the TYPE-SIZE distribution?

    The concern this addresses is that the join gap might be concentrated in display
    typography, which is what carries account names, and therefore the heading tree and
    the financial data contract.

    WHAT THIS DOES NOT DO. It does not classify pairs as headings or as body prose. Font
    size is a proxy for semantic role and nothing here validates it as one; this project
    still lacks a trustworthy heading-level oracle, which is item 1 on the list blocking
    an ADR. A low share of above-modal type reduces the concern. It does not license a
    sentence about what the text *is*.

    The modal size is computed ONCE. The first version of this evaluated
    `Counter(joined).most_common(1)` inside a generator condition, which rebuilt a
    195,291-element counter per element and turned a millisecond of arithmetic into an
    O(n^2) walk that ran for twenty minutes before it was profiled.
    """
    if not joined:
        return {"joined": {}, "unjoined": {}, "joined_modal_size": None}
    modal = Counter(joined).most_common(1)[0][0]
    return {
        "joined": dict(Counter(joined).most_common(8)),
        "unjoined": dict(Counter(unjoined).most_common(8)),
        "joined_modal_size": modal,
        "joined_share_above_modal": round(sum(1 for s in joined if s > modal) / len(joined), 4),
        "unjoined_share_above_modal": (
            round(sum(1 for s in unjoined if s > modal) / len(unjoined), 4) if unjoined else None
        ),
    }


def _pct(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)

    def q(p: float) -> float:
        return s[min(len(s) - 1, int(len(s) * p))]

    return {
        "n": len(s),
        "max": s[-1],
        "median": statistics.median(s),
        "p90": q(0.90),
        "p99": q(0.99),
        "p999": q(0.999),
        # Bins named for their literal thresholds. The previous version computed against
        # 5e-5 and labelled the result "at_or_above_contract_precision", which a reader
        # would take as 1e-4. Both are now reported, separately, and neither name implies
        # a rounding interpretation the number does not carry.
        "exactly_zero": sum(1 for v in s if v == 0.0),
        "gt_zero_and_lt_5e_5": sum(1 for v in s if 0.0 < v < ROUND_MAX_ERROR),
        "ge_5e_5": sum(1 for v in s if v >= ROUND_MAX_ERROR),
        "ge_1e_4": sum(1 for v in s if v >= QUANT_STEP),
    }


def _pair_index(records: list[dict]) -> dict[tuple, tuple[dict, dict]]:
    """H4's `_adjacent_pairs` + `_key`, carrying the raw sidecar alongside the packed tuple.

    Keyed on the PACKED tuple exactly as H4 does, so the population is H4's population and
    not a near-neighbour of it. N14 asserts that.
    """
    rows: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        g = r["packed"]
        if not g[UPRIGHT] or g[CP] in (32, 10, 13):
            continue
        rows[round(g[BASELINE] / BASELINE_TOL)].append(r)
    out: dict[tuple, tuple[dict, dict]] = {}
    for row in rows.values():
        row.sort(key=lambda r: r["packed"][ORIGIN_X])
        for a, b in zip(row, row[1:]):
            out[_key(a["packed"])] = (a, b)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=PAGES)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h06_raw_precision.json")
    args = ap.parse_args()

    pages = list(range(1, args.pages + 1))
    result: dict = {
        "question": "are the engines' RAW advances equal, or only equal after the contract rounds them?",
        "thresholds_pt": {
            "quantisation_step_1e_4": QUANT_STEP,
            "round_to_nearest_max_error_5e_5": ROUND_MAX_ERROR,
            "note": (
                "a difference below 5e-5 cannot survive round(x, 4); a difference below 1e-4 still can, "
                "because two values under one step apart can straddle a rounding boundary"
            ),
        },
        "documents": [],
    }
    d_adv: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
    d_org: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
    d_rel: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
    grand = Counter()
    unjoined_cp = Counter()
    unjoined_reason = Counter()
    unjoined_by_doc: dict[str, int] = {}
    rematch_decisions = Counter()
    unjoined_examples: list[dict] = []
    unjoined_sizes: list[float] = []
    joined_sizes: list[float] = []

    import reconstruct_extended as RE

    for rel in DOCUMENTS:
        path = REPO / rel
        if not path.exists():
            print(f"  MISSING {rel}")
            continue
        print(f"\n=== {rel}")
        # h04's `_extract` returns (pages, summary); only the pages are needed here.
        adapters = {b: _extract(b, path, pages)[0] for b in BACKENDS}
        raws = {}
        for b in BACKENDS:
            raws[b] = raw_facts.raw_pages(b, path, pages)
            raw_facts.check(b, raws[b], adapters[b])  # N13
        print("    N13 raw sidecar matches every adapter glyph")

        doc_adv: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
        doc_org: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
        doc_rel: dict[str, list[float]] = {"pdfminer": [], "pymupdf": []}
        doc_f32 = {b: Counter() for b in BACKENDS}
        eps_pairs: list[tuple] = []
        doc_unjoined = 0

        for pno in pages:
            idx = {b: _pair_index(raws[b][pno]) for b in BACKENDS}
            # N14: the key set must be H4's key set, built from the adapter output.
            for b in BACKENDS:
                h4_keys = {_key(a) for a, _c in _adjacent_pairs(next(p for p in adapters[b] if p.page_number == pno))}
                assert set(idx[b]) == h4_keys, f"{b} p{pno}: raw pair index diverged from H4's"

            shared = set.intersection(*(set(m) for m in idx.values()))
            grand["pairs_pdfium"] += len(idx["pdfium"])
            grand["shared"] += len(shared)

            for k in shared:
                if len({idx[b][k][1]["cp"] for b in BACKENDS}) != 1:
                    grand["different_next_glyph"] += 1
                    continue
                grand["compared"] += 1
                eps_pairs.append((idx["pdfium"][k][0]["packed"], idx["pdfium"][k][1]["packed"]))
                joined_sizes.append(round(idx["pdfium"][k][0]["size"], 1))
                for b in BACKENDS:
                    for side in (0, 1):
                        av = idx[b][k][side]["advance"]
                        if av is not None:
                            doc_f32[b]["advances"] += 1
                            doc_f32[b]["exactly_representable_in_float32"] += _is_float32(av)
                for b in ("pdfminer", "pymupdf"):
                    for side in (0, 1):
                        rb, rf = idx[b][k][side], idx["pdfium"][k][side]
                        doc_org[b].append(abs(rb["origin_x"] - rf["origin_x"]))
                        if rb["advance"] is not None and rf["advance"] is not None:
                            d = abs(rb["advance"] - rf["advance"])
                            doc_adv[b].append(d)
                            if rf["advance"]:
                                doc_rel[b].append(d / abs(rf["advance"]))
                        else:
                            grand[f"advance_missing_{b}"] += 1

            # ---- B: what did not join, and why -----------------------------------------
            # Indexed by the pair's two codepoints so N16's rematch is a short list scan
            # rather than a walk of the whole page for every unjoined pair.
            by_cps: dict[str, dict[tuple, list]] = {}
            for bk in ("pdfminer", "pymupdf"):
                m: dict[tuple, list] = defaultdict(list)
                for v in idx[bk].values():
                    m[(v[0]["cp"], v[1]["cp"])].append(v)
                by_cps[bk] = m

            for k, (a, b_) in idx["pdfium"].items():
                if k in shared:
                    continue
                doc_unjoined += 1
                unjoined_cp[f"U+{a['packed'][CP]:04X}"] += 1
                absent = [bk for bk in ("pdfminer", "pymupdf") if k not in idx[bk]]
                unjoined_reason["absent_in_" + "_and_".join(absent)] += 1
                # N16: is the key merely in a neighbouring bucket? Diagnostic only.
                #
                # STRENGTHENED. The first version matched on the two codepoints plus the
                # FIRST glyph's origin and baseline, and then the prose claimed the
                # recovered pairs were "the same pairs separated only by a bucket edge".
                # It had not established that: nothing tied the candidate's SECOND glyph
                # to the second glyph of the PDFium pair, so a candidate whose first
                # glyph coincided but whose successor was a different instance of the
                # same character would have been accepted. Both endpoints are now
                # constrained, and the tolerances are unchanged.
                rematched = {}
                ambiguous = False
                for bk in ("pdfminer", "pymupdf"):
                    if k in idx[bk]:
                        rematched[bk] = idx[bk][k]
                        continue
                    hit = [
                        v
                        for v in by_cps[bk].get((a["cp"], b_["cp"]), ())
                        if abs(v[0]["origin_x"] - a["origin_x"]) <= ORIGIN_TOL
                        and abs(v[0]["baseline"] - a["baseline"]) <= BASELINE_TOL
                        and abs(v[1]["origin_x"] - b_["origin_x"]) <= ORIGIN_TOL
                        and abs(v[1]["baseline"] - b_["baseline"]) <= BASELINE_TOL
                    ]
                    if len(hit) == 1:
                        rematched[bk] = hit[0]
                    elif len(hit) > 1:
                        ambiguous = True
                if len(rematched) == 2:
                    unjoined_reason["RECOVERABLE_by_two_endpoint_rematch"] += 1
                    dec = {"pdfium": RE.wants_space(a["packed"], b_["packed"])}
                    for bk, (ra, rb) in rematched.items():
                        dec[bk] = RE.wants_space(ra["packed"], rb["packed"])
                    rematch_decisions["compared"] += 1
                    rematch_decisions["disagree"] += len(set(dec.values())) != 1
                else:
                    unjoined_reason["AMBIGUOUS_candidate" if ambiguous else "NOT_recoverable"] += 1
                    # 21 in total, so all of them are kept rather than a sample.
                    unjoined_examples.append(
                        {
                            "pdf": rel,
                            "page": pno,
                            "chars": f"{chr(a['packed'][CP])}|{chr(b_['packed'][CP])}",
                            "codepoints": [f"U+{a['packed'][CP]:04X}", f"U+{b_['packed'][CP]:04X}"],
                            "involves_undecodable_carrier": 0xFFFD in (a["packed"][CP], b_["packed"][CP]),
                            "absent_in": absent,
                            "origin_x": a["origin_x"],
                            "baseline": a["baseline"],
                            "size": a["size"],
                        }
                    )
                # The question the unjoined population has to answer is whether it hides
                # the display type that carries account names. Type size is the proxy:
                # body prose sits at the modal size, headings above it.
                unjoined_sizes.append(round(a["size"], 1))

        unjoined_by_doc[rel] = doc_unjoined
        for b in ("pdfminer", "pymupdf"):
            d_adv[b].extend(doc_adv[b])
            d_org[b].extend(doc_org[b])
            d_rel[b].extend(doc_rel[b])
        eps = _detectable_epsilon_bracket(eps_pairs, RE.wants_space)
        floor = eps["largest_that_changed_nothing"]
        max_rel = {b: (max(doc_rel[b]) if doc_rel[b] else 0.0) for b in ("pdfminer", "pymupdf")}
        entry = {
            "pdf": rel,
            "raw_advance_delta_vs_pdfium": {b: _pct(doc_adv[b]) for b in ("pdfminer", "pymupdf")},
            "raw_origin_x_delta_vs_pdfium": {b: _pct(doc_org[b]) for b in ("pdfminer", "pymupdf")},
            # Does the difference matter? Compare it with the smallest perturbation the
            # rule can feel at all, on this same page set.
            "headroom": {
                "max_relative_advance_delta": max_rel,
                "decision_changing_perturbation_bracket": eps,
                # Quoted from the conservative end of the bracket.
                "orders_of_magnitude_of_headroom_CONSERVATIVE": {
                    b: (round(math.log10(floor / max_rel[b]), 1) if floor and max_rel[b] else None)
                    for b in ("pdfminer", "pymupdf")
                },
            },
            # Where does PyMuPDF's ~1.5e-5 floor come from? If every one of its advances is
            # exactly representable in float32 and PDFium's are not, the answer is that
            # MuPDF carries the advance box in single precision.
            "float32_representable": {
                b: {
                    "advances": doc_f32[b]["advances"],
                    "exactly_representable": doc_f32[b]["exactly_representable_in_float32"],
                    "share": (
                        round(doc_f32[b]["exactly_representable_in_float32"] / doc_f32[b]["advances"], 4)
                        if doc_f32[b]["advances"]
                        else None
                    ),
                }
                for b in BACKENDS
            },
            "unjoined_pdfium_pairs": doc_unjoined,
        }
        result["documents"].append(entry)
        for b in ("pdfminer", "pymupdf"):
            a_, o_ = entry["raw_advance_delta_vs_pdfium"][b], entry["raw_origin_x_delta_vs_pdfium"][b]
            print(
                f"    raw vs {b:<9} advance max={a_['max']:.3e} zero={a_['exactly_zero']}/{a_['n']}"
                f"   origin max={o_['max']:.3e} zero={o_['exactly_zero']}/{o_['n']}"
            )
        print(f"    unjoined pdfium pairs: {doc_unjoined}")

    result["totals"] = {
        "pairs_seen_by_pdfium": grand["pairs_pdfium"],
        "pairs_shared_by_all_three": grand["shared"],
        "different_next_glyph_excluded": grand["different_next_glyph"],
        "pairs_compared": grand["compared"],
        "raw_advance_delta_vs_pdfium": {b: _pct(d_adv[b]) for b in ("pdfminer", "pymupdf")},
        "raw_origin_x_delta_vs_pdfium": {b: _pct(d_org[b]) for b in ("pdfminer", "pymupdf")},
        "max_relative_advance_delta": {b: (max(d_rel[b]) if d_rel[b] else None) for b in ("pdfminer", "pymupdf")},
        "advance_unavailable_on_one_side": {b: grand[f"advance_missing_{b}"] for b in ("pdfminer", "pymupdf")},
    }
    # N15: the verdict is written FROM the measurement rather than chosen. "Identical" and
    # "equal once rounded" are different claims and the first one has to earn itself.
    _adv_totals = result["totals"]["raw_advance_delta_vs_pdfium"]
    worst = max((t["max"] for t in _adv_totals.values() if t.get("n")), default=0.0)
    all_zero = all(t.get("n") and t["exactly_zero"] == t["n"] for t in _adv_totals.values())
    result["totals"]["verdict"] = (
        "IDENTICAL: every raw advance matches bit for bit"
        if all_zero
        else (
            f"NOT IDENTICAL, but EQUIVALENT UNDER ROUND-TO-NEAREST at 4 dp: raw advances differ by up to "
            f"{worst:.3e} pt, which is below the {ROUND_MAX_ERROR} pt maximum error that round(x, 4) "
            f"can itself introduce"
            if worst < ROUND_MAX_ERROR
            else (
                f"NOT IDENTICAL: raw advances differ by up to {worst:.3e} pt, which is at or above the "
                f"{ROUND_MAX_ERROR} pt round-to-nearest error bound -- state the threshold explicitly"
            )
        )
    )
    result["unjoined_population"] = {
        "count": sum(unjoined_by_doc.values()),
        "share_of_pdfium_pairs": (
            round(sum(unjoined_by_doc.values()) / grand["pairs_pdfium"], 5) if grand["pairs_pdfium"] else None
        ),
        "by_document": unjoined_by_doc,
        "by_first_codepoint": dict(unjoined_cp.most_common(15)),
        # TYPOGRAPHY ONLY. This measures where the unjoined pairs sit in the type-size
        # distribution. It does NOT classify them as headings or as body prose: font size
        # is a proxy for semantic role, and this project does not yet have a trustworthy
        # heading-level oracle to check such a classification against.
        "type_size_profile": _type_size_profile(joined_sizes, unjoined_sizes),
        "by_reason": dict(unjoined_reason),
        "N16_two_endpoint_rematch": {
            "note": "diagnostic only; these are NOT folded into H4's compared count",
            "rule": (
                "both codepoints equal, and BOTH glyphs' origin_x within 0.05 pt and baseline within "
                "0.6 pt of the PDFium pair, with exactly one candidate"
            ),
            "unjoined_total": sum(unjoined_by_doc.values()),
            "uniquely_rematched_in_both_engines": unjoined_reason.get("RECOVERABLE_by_two_endpoint_rematch", 0),
            "ambiguous_candidate": unjoined_reason.get("AMBIGUOUS_candidate", 0),
            "unmatched": unjoined_reason.get("NOT_recoverable", 0),
            "boundary_decisions_compared": rematch_decisions.get("compared", 0),
            "boundary_disagreements": rematch_decisions.get("disagree", 0),
        },
        "unrecovered_examples": unjoined_examples,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))
    print("\n" + "=" * 72)
    print(json.dumps({k: v for k, v in result["totals"].items() if k != "raw_origin_x_delta_vs_pdfium"}, indent=1))
    print(json.dumps(result["unjoined_population"], indent=1)[:1800])
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
