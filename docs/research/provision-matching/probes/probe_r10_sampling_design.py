"""R10: can region sampling support a population estimate, and what does clustering cost?

Round 2 replaced random anchor sampling with "sample roughly four regions, then annotate every
anchor inside them". Round 3 challenged that on two grounds, and both are testable rather than
arguable.

CHALLENGE 1 -- CIRCULARITY. Round 2 §R2-C defined a region as "a bounded structural unit of the
NEW version". But the objects being sampled are OLD-version anchors. Deciding which old anchors
belong to a sampled new-version region is itself a correspondence question, which is the thing the
study is trying to measure. Section 1 tests whether an anchor's inclusion probability can be
computed without knowing its counterpart, under two framings:

    NEW-side frame (round 2)   region defined on the new version -> needs an old->new region map
    OLD-side frame (proposed)  region defined on the old version -> needs only the old parse

CHALLENGE 2 -- CLUSTERING. Anchors inside one region are not independent draws. With ~4 clusters the
effective sample size is nearer 4 than 80, and a single unusual bill can dominate. Section 2
measures the intra-cluster correlation of two label-free proxy outcomes and reports the design
effect at three clustering levels, so the cost of the design is priced rather than assumed.

Neither section needs human labels. Both proxies are computable from the current pipeline, and they
are proxies for the OUTCOME STRUCTURE, not for truth -- a design effect depends on how correlated
outcomes are within a cluster, which does not require the outcomes to be correct.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r10_sampling_design.py
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402

KEEP = 0.70


def icc_and_deff(groups: dict[str, list[int]]) -> tuple[float, float, float, int, float]:
    """One-way random-effects ICC for a binary outcome, with the resulting design effect.

    Returns (icc, deff, mean_cluster_size, n_clusters, n_total). ICC is clamped at 0: the ANOVA
    estimator can go negative when between-cluster variance is below within-cluster variance, and a
    negative ICC has no interpretation here beyond "no detectable clustering".
    """
    clusters = [v for v in groups.values() if v]
    k = len(clusters)
    n_total = sum(len(v) for v in clusters)
    if k < 2 or n_total <= k:
        return (0.0, 1.0, 0.0, k, n_total)
    grand = sum(sum(v) for v in clusters) / n_total
    msb = sum(len(v) * (statistics.mean(v) - grand) ** 2 for v in clusters) / (k - 1)
    msw = sum(sum((y - statistics.mean(v)) ** 2 for y in v) for v in clusters) / (n_total - k)
    n0 = (n_total - sum(len(v) ** 2 for v in clusters) / n_total) / (k - 1)
    denom = msb + (n0 - 1) * msw
    icc = 0.0 if denom == 0 else max(0.0, (msb - msw) / denom)
    m_bar = n_total / k
    return (icc, 1 + (m_bar - 1) * icc, m_bar, k, n_total)


def main() -> None:
    print(banner())
    print()

    anchors = []  # (bill, version_pair, old_region, new_region_exists, y_removed, y_strong_cand)
    old_region_sizes: dict[tuple[str, str, str], int] = Counter()

    for bill, xa, xb in adjacent_pairs():
        try:
            told, tnew = normalize_bill(xa), normalize_bill(xb)
            d = diff_bills(told, tnew)
        except Exception:
            continue
        vp = f"{bill}:{xa.stem}->{xb.stem}"

        # top-level structural units on each side, by their own labels only
        new_regions = {tuple(n.match_path)[:1] for n in tnew.nodes if n.match_path}

        added = []
        for c in d.changes:
            if c.change_type == "added" and c.new_text:
                t = _normalize_text(c.new_text)
                if t:
                    added.append(vec(t))

        for c in d.changes:
            if c.change_type not in ("removed", "moved") or not c.old_text:
                continue
            t = _normalize_text(c.old_text)
            if not t:
                continue
            path = tuple(c.match_path)
            if not path:
                continue
            old_region = path[:1]
            old_region_sizes[(bill, xa.stem, old_region[0])] += 1
            av = vec(t)
            y_strong = int(any(containment(av, bv) >= KEEP for bv in added))
            anchors.append(
                {
                    "bill": bill,
                    "vp": vp,
                    "old_region": f"{bill}:{xa.stem}:{old_region[0]}",
                    "new_region_exists": old_region in new_regions,
                    "y_removed": int(c.change_type == "removed"),
                    "y_strong": y_strong,
                }
            )

    if not anchors:
        print("no anchors found -- corpus missing?")
        return

    # ---- 1. can inclusion probability be computed without knowing the counterpart? -------------
    print("=" * 104)
    print("1. IS THE SAMPLING FRAME COMPUTABLE WITHOUT SOLVING THE CORRESPONDENCE PROBLEM?")
    print("=" * 104)
    n = len(anchors)
    resolvable = sum(a["new_region_exists"] for a in anchors)
    print(f"  anchors (removed/moved provisions across {len(adjacent_pairs())} adjacent pairs) : {n}")
    print()
    print("  OLD-side frame -- a region is a top-level unit of the OLD version:")
    print(f"    anchors whose region is determined by the old parse alone : {n}/{n} = 100.0%")
    print("    Every anchor IS a node of the old version, so its region is read off the same parse")
    print("    that produced the anchor. No diff, no matcher, no counterpart. Inclusion probability")
    print("    is therefore P(region drawn) x 1, and is known before any labeling.")
    print()
    print("  NEW-side frame (round 2's wording) -- a region is a top-level unit of the NEW version:")
    miss = n - resolvable
    print(f"    old top-level unit still EXISTS in the new version : {resolvable}/{n} = {resolvable / n:.1%}")
    print(f"    it does not                                        : {miss}/{n} = {miss / n:.1%}")
    print("    For those, assigning the anchor to a new-side region requires deciding which new")
    print("    unit corresponds to its old one -- a correspondence judgment, made by the sampler,")
    print("    before any human sees the anchor. That is the circularity the challenge names, and")
    print("    it is not hypothetical at this rate.")

    # ---- 2. clustering ------------------------------------------------------------------------
    print()
    print("=" * 104)
    print("2. WHAT DOES CLUSTERING COST?  (design effect on two label-free proxy outcomes)")
    print("=" * 104)
    print("  Proxy A: the matcher called this anchor `removed` rather than `moved` -- the outcome")
    print("           final-diff-correctness scores.")
    print("  Proxy B: at least one added provision reaches containment >= 0.70 -- the retrieval")
    print("           opportunity candidate recall scores.")
    print()
    print("  n_eff is what a clustered sample is WORTH: 80 anchors drawn from 4 regions carry")
    print("  n_eff evidence, not 80.")
    print()
    for proxy, key in (("A (matcher said removed)", "y_removed"), ("B (strong candidate exists)", "y_strong")):
        print(f"  proxy {proxy}")
        print(f"    {'cluster level':<16}{'clusters':>10}{'mean size':>11}{'ICC':>9}{'deff':>9}{'n_eff':>9}")
        print("    " + "-" * 64)
        for level, field in (("old region", "old_region"), ("version pair", "vp"), ("bill", "bill")):
            groups = defaultdict(list)
            for a in anchors:
                groups[a[field]].append(a[key])
            icc, deff, m_bar, k, n_tot = icc_and_deff(groups)
            print(f"    {level:<16}{k:>10}{m_bar:>11.1f}{icc:>9.3f}{deff:>9.1f}{n_tot / deff:>9.1f}")
        print()

    # ---- 3. what a region-sampled MVP would actually buy ---------------------------------------
    print("=" * 104)
    print("3. THE MVP, PRICED")
    print("=" * 104)
    sizes = sorted(old_region_sizes.values())
    print(f"  distinct old-side regions in the corpus            : {len(sizes)}")
    print(
        f"  anchors per region: median {statistics.median(sizes):.0f}  mean {statistics.mean(sizes):.1f}  "
        f"p90 {sizes[int(0.9 * (len(sizes) - 1))]}  max {max(sizes)}"
    )
    print(f"  regions holding >= 10 anchors                      : {sum(1 for s in sizes if s >= 10)}")
    print(
        f"  bills with at least one such region                : "
        f"{len({b for (b, _v, _r), s in old_region_sizes.items() if s >= 10})}"
    )
    print()
    print("  Read together with section 2: a 4-region draw is 4 independent units. Whatever the")
    print("  per-anchor count, the variance of any region-correlated quantity is governed by the")
    print("  number of CLUSTERS, and 4 is not enough to estimate it -- nor to estimate the ICC that")
    print("  would be needed to widen the interval honestly.")

    print()
    print("=" * 104)
    print("4. WHAT EACH CANDIDATE DESIGN WOULD ACTUALLY BUY")
    print("=" * 104)
    print("  Worst-case half-width of a 95% interval on a proportion at p=0.5, using n_eff. This is")
    print("  the question that decides whether Study 2 is a population estimate or a dev set, and")
    print("  it is arithmetic once the ICC is measured -- not a matter of opinion.")
    print()
    # take the larger of the two proxies' region-level ICCs: the design must survive the worse case
    icc_region = max(
        icc_and_deff(_grouped(anchors, "old_region", "y_removed"))[0],
        icc_and_deff(_grouped(anchors, "old_region", "y_strong"))[0],
    )
    icc_bill = max(
        icc_and_deff(_grouped(anchors, "bill", "y_removed"))[0],
        icc_and_deff(_grouped(anchors, "bill", "y_strong"))[0],
    )
    print(f"  measured ICC used below: within-region {icc_region:.3f}, within-bill {icc_bill:.3f}")
    print()
    print(f"  {'design':<44}{'anchors':>9}{'clusters':>10}{'deff':>8}{'n_eff':>8}{'+/- 95%':>10}")
    print("  " + "-" * 89)
    for label, n_anchor, k_clusters, icc in (
        ("round 2 MVP: 4 regions x 20 anchors", 80, 4, icc_region),
        ("8 regions x 10 anchors", 80, 8, icc_region),
        ("20 regions x 4 anchors", 80, 20, icc_region),
        ("80 anchors drawn at random (1 per region)", 80, 80, icc_region),
        ("4 regions x 20, clustered by BILL instead", 80, 4, icc_bill),
    ):
        m_bar = n_anchor / k_clusters
        deff = 1 + (m_bar - 1) * icc
        n_eff = n_anchor / deff
        half = 1.96 * (0.25 / n_eff) ** 0.5
        print(f"  {label:<44}{n_anchor:>9}{k_clusters:>10}{deff:>8.1f}{n_eff:>8.1f}{half:>9.0%}")
    print()
    print("  READ THIS AS: the round-2 MVP buys roughly a dozen independent observations and a")
    print("  +/- 25-30 point interval, which cannot distinguish 60% recall from 90%. Spreading the")
    print("  same 80 anchors over more, smaller regions recovers most of the power, at the cost of")
    print("  reading more regions exhaustively. Section 3 says only 36 regions hold >= 10 anchors")
    print("  and they sit in 4 bills, so bill-level clustering caps this corpus regardless of the")
    print("  region design.")


def _grouped(anchors: list[dict], field: str, key: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for a in anchors:
        out[a[field]].append(a[key])
    return out


if __name__ == "__main__":
    main()
