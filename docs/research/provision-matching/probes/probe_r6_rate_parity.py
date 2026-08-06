"""R6: is the high-containment false-keep shape really MORE available inside a bill than across?

The first review answered "yes" by putting two numbers side by side:

    cross-bill random, cited shorts   0 / 976   = 0.0%     (probe_review_gameability.py)
    production neighbourhood         27 / 77    = 35.1%    (probe_r4_production_neighborhood.py)

The second review challenged that as a comparison of two different statistics, and it is right.
Three things differ between those numbers, not one:

  1. THE STATISTIC. 0/976 is per-COMPARISON (one short x one long). 27/77 is per-ANCHOR (a short
     with at least ONE partner anywhere in its neighbourhood). A short compared against 57 longs
     has ~57 chances to hit; a short compared against one has one. The per-anchor number is
     larger for arithmetic reasons before any effect of same-bill vocabulary.
  2. THE CANDIDATE-SET SIZE. Nothing held it constant.
  3. THE RARITY MODEL -- which neither review noticed. `probe_review_gameability.py` builds its
     own document frequencies inline over the 34-bill union (65,502 bodies). `probe_r4` imports
     `mine_common.vec`, which loads `idf_cache.json`, built over `bills/` + `bills_corpus/`:
     232,924 bodies over 2,983 bills. The two published numbers were computed under DIFFERENT
     IDF weights, so they were never comparable even in principle.

This probe removes all three differences. One rarity model, one measure, one anchor set, one
statistic reported both ways, and a control whose candidate-set size is matched anchor-by-anchor:

    PRODUCTION   anchor i (short, cited, removed)  x  its k_i long added provisions, SAME bill
    CONTROL      anchor i (the same short)         x  k_i long added provisions from OTHER bills

Same anchors, same k, same measure, same weights. The ONLY thing that varies is whether the long
side comes from the anchor's own bill. That is the single-variable version of the claim.

WHAT THIS IS NOT. Nothing here is a labeled false positive. A same-bill hit may be a genuine
consolidation ("absorbed into"), and 119-hr-1 -- which dominates the production hits -- is the
known consolidation bill. So the production arm is an OPPORTUNITY rate: how often a spurious keep
is even available. Reading it as a false-positive rate is the error this probe exists to prevent,
so it also reports the by-bill split and a leave-119-hr-1-out arm.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r6_rate_parity.py
"""

from __future__ import annotations

import math
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402

_cite = re.compile(r"u\.s\.c\.|\bsection\s+\d|\bact of \d{4}|\bpublic law", re.I)
SHORT_MAX = 200
LONG_MIN = 800
KEEP = 0.70
REPLICATES = 20  # control draws per anchor; variance reduction only, no threshold is fitted
SEED = 42


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Normal-approximation CIs are useless at k=0, which is the
    exact regime the cross-bill arm sits in -- '0/976' is not 0%, it is 'at most about 0.4%'."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    rate = (k / n) if n else 0.0
    return f"{k:>6}/{n:<7} = {rate:>7.3%}  [95% CI {lo:.3%}, {hi:.3%}]"


def collect():
    """Anchors (short, cited, removed) with their own-bill long-added neighbourhood, plus the
    corpus-wide pool of long added provisions used to build the matched control."""
    anchors = []  # (bill, short_vec, short_text, [own-bill long vecs])
    pool_by_bill: dict[str, list[dict]] = {}
    for bill, xa, xb in adjacent_pairs():
        try:
            d = diff_bills(normalize_bill(xa), normalize_bill(xb))
        except Exception:
            continue
        shorts, longs = [], []
        for c in d.changes:
            if c.change_type == "removed" and c.old_text:
                t = _normalize_text(c.old_text)
                if len(t) <= SHORT_MAX and _cite.search(t):
                    shorts.append(t)
            elif c.change_type == "added" and c.new_text:
                t = _normalize_text(c.new_text)
                if len(t) >= LONG_MIN:
                    longs.append(t)
        long_vecs = [vec(t) for t in longs]
        pool_by_bill.setdefault(bill, []).extend(long_vecs)
        if not shorts or not longs:
            continue
        for st in shorts:
            anchors.append((bill, vec(st), st, long_vecs))
    return anchors, pool_by_bill


def own_bill_draw(_bill, _k, own):
    """The production arm: an anchor's candidates ARE its own bill's added provisions."""
    return own


def arm(anchors, draw) -> tuple[int, int, int, int, dict[str, int]]:
    """(hits, comparisons, anchors_with_hit, n_anchors, hits_by_bill) for one candidate source.

    `draw(bill, k, own)` returns the k candidate vectors this arm offers that anchor. Both arms
    go through this one loop so the two rates cannot drift apart in the counting."""
    hits = comparisons = anchors_with_hit = 0
    by_bill: dict[str, int] = {}
    for bill, sv, _st, own in anchors:
        cands = draw(bill, len(own), own)
        hit_here = 0
        for lv in cands:
            comparisons += 1
            if containment(sv, lv) >= KEEP:
                hits += 1
                hit_here += 1
        if hit_here:
            anchors_with_hit += 1
            by_bill[bill] = by_bill.get(bill, 0) + 1
    return hits, comparisons, anchors_with_hit, len(anchors), by_bill


def report(name: str, hits, comps, anch_hit, n_anch, by_bill, replicates: int = 1) -> None:
    print(f"  {name}")
    print(f"    per-COMPARISON  {pct(hits, comps)}")
    print(f"    per-ANCHOR      {pct(anch_hit, n_anch * replicates)}")
    if by_bill:
        order = sorted(by_bill, key=lambda k: -by_bill[k])
        print(f"    anchors with >=1 hit, by bill: {', '.join(f'{b}={by_bill[b]}' for b in order)}")
    print()


def main() -> None:
    random.seed(SEED)
    print(banner())
    print()
    anchors, pool_by_bill = collect()
    if not anchors:
        print("no anchors found -- corpus missing?")
        return

    ks = [len(own) for _b, _v, _t, own in anchors]
    bills = sorted({b for b, _v, _t, _o in anchors})
    print("=" * 104)
    print("SETUP  (one rarity model, one measure, one anchor set; only the candidate SOURCE varies)")
    print("=" * 104)
    print(f"  anchors: short(<= {SHORT_MAX} chars), carries a statute citation, `removed` in an adjacent pair")
    print(f"  candidates: long(>= {LONG_MIN} chars) `added` provisions;  keep bar: containment >= {KEEP}")
    print(f"  anchors                     : {len(anchors)} across {len(bills)} bills ({', '.join(bills)})")
    print(f"  own-bill neighbourhood size : mean {sum(ks) / len(ks):.1f}  min {min(ks)}  max {max(ks)}")
    print(
        f"  control pool                : {sum(len(v) for v in pool_by_bill.values())} long added "
        f"provisions across {len(pool_by_bill)} bills"
    )
    print(f"  control draws per anchor    : {REPLICATES} (matched k, sampled from OTHER bills only)")
    print()

    # --- production arm ------------------------------------------------------------------------
    print("=" * 104)
    print("1. THE COMPARISON, WITH THE DENOMINATORS MADE IDENTICAL")
    print("=" * 104)
    p_hits, p_comps, p_anch, _n, p_by_bill = arm(anchors, own_bill_draw)
    report("PRODUCTION  (own-bill added provisions)", p_hits, p_comps, p_anch, len(anchors), p_by_bill)

    # --- matched control arm -------------------------------------------------------------------
    flat_by_other: dict[str, list[dict]] = {
        b: [v for ob, vs in pool_by_bill.items() if ob != b for v in vs] for b in bills
    }

    def other_bill_draw(bill, k, _own):
        pool = flat_by_other[bill]
        return random.sample(pool, min(k, len(pool)))

    c_hits = c_comps = c_anch = 0
    c_by_bill: dict[str, int] = {}
    for _r in range(REPLICATES):
        h, cm, a, _n, bb = arm(anchors, other_bill_draw)
        c_hits += h
        c_comps += cm
        c_anch += a
        for k, v in bb.items():
            c_by_bill[k] = c_by_bill.get(k, 0) + v
    report(
        f"CONTROL     (other-bill added provisions, k matched, {REPLICATES} draws)",
        c_hits,
        c_comps,
        c_anch,
        len(anchors),
        c_by_bill,
        replicates=REPLICATES,
    )

    plo, phi = wilson(p_hits, p_comps)
    clo, chi = wilson(c_hits, c_comps)
    separated = plo > chi
    print(
        f"  per-comparison CIs {'DO NOT overlap' if separated else 'OVERLAP'}: "
        f"production [{plo:.3%}, {phi:.3%}] vs control [{clo:.3%}, {chi:.3%}]"
    )
    print(
        f"  => the same-bill effect is {'supported' if separated else 'NOT established'} "
        "at this sample size, on this statistic."
    )
    print()

    # --- leave-119-hr-1-out --------------------------------------------------------------------
    print("=" * 104)
    print("2. WITHOUT 119-hr-1  (it dominates the hits AND is the known consolidation bill, so its")
    print("   hits are the ones most likely to be genuine 'absorbed into' relations, not errors)")
    print("=" * 104)
    sub = [a for a in anchors if a[0] != "119-hr-1"]
    if not sub:
        print("  no anchors outside 119-hr-1")
    else:
        s_hits, s_comps, s_anch, _n, s_by_bill = arm(sub, own_bill_draw)
        report("PRODUCTION minus 119-hr-1", s_hits, s_comps, s_anch, len(sub), s_by_bill)

        t_hits = t_comps = t_anch = 0
        for _r in range(REPLICATES):
            h, cm, a, _n, _bb = arm(sub, other_bill_draw)
            t_hits += h
            t_comps += cm
            t_anch += a
        report(
            f"CONTROL minus 119-hr-1 (k matched, {REPLICATES} draws)",
            t_hits,
            t_comps,
            t_anch,
            len(sub),
            {},
            replicates=REPLICATES,
        )

    # --- reconciling the two published numbers --------------------------------------------------
    print("=" * 104)
    print("3. RECONCILING THE TWO NUMBERS THE FIRST REVIEW PUT SIDE BY SIDE")
    print("=" * 104)
    print("  Under THIS probe's single rarity model, on the per-COMPARISON statistic:")
    print(f"    production (own bill)      {pct(p_hits, p_comps)}")
    print(f"    control    (other bills)   {pct(c_hits, c_comps)}")
    print()
    print("  The published '0/976' came from a probe with its own inline 34-bill IDF table, and")
    print("  '27/77' from a probe using the 2,983-bill idf_cache.json. Neither number is wrong for")
    print("  what it measured; they were never a comparison. Cite the two lines above instead.")
    print()
    c_rate = c_hits / c_comps if c_comps else 0.0
    expected = 976 * c_rate
    p_zero = math.exp(-expected)
    print("  And '0/976' was never evidence of a near-zero cross-bill rate. At the control rate")
    print(f"  measured here ({c_rate:.3%}), 976 draws expect {expected:.2f} hits, so observing ZERO has")
    print(f"  probability about {p_zero:.0%}. It is the likeliest single outcome of a sample that small.")
    print("  Reporting it as 0.0% next to a 35.1% read as a 350x gap; the honest reading is that the")
    print("  cross-bill probe had no power to measure a rate this low, and its Wilson upper bound")
    print(f"  alone ({wilson(0, 976)[1]:.3%}) already overlapped the production per-comparison rate.")


if __name__ == "__main__":
    main()
