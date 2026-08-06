"""The canonical Study 2 sampling frame. ONE executable definition, consumed by everything.

WHY THIS FILE EXISTS. Round 3 claimed the sampling frame was matcher-independent, on the reasoning
that "every anchor is a node of the old parse, so its region is read off the same parse that
produced the anchor". Round 4 read the code. `probe_r10_sampling_design.py` built its anchors like
this:

    d = diff_bills(told, tnew)
    ...
    if c.change_type not in ("removed", "moved"):
        continue

So the **matcher chose which old provisions became anchors**, and the probe then measured that the
*region* of those matcher-selected anchors was computable without the matcher. That is a true
statement about the wrong thing. Every downstream number -- 2,137 anchors, 147 regions, 36 regions
over the size floor, ICC 0.27-0.29, n_eff 12.2, +/-28 points -- was computed on a
matcher-conditioned population while being described as the independent frame.

The deeper lesson, which is the whole reason this module is a module and not a paragraph: the
research document, the sampling probe and the eventual labeling UI were each free to hold their own
idea of what an "anchor" is. Three rounds of review did not catch the divergence because prose and
code were never forced to agree. They are now: this file is the only definition, it does not import
`diff_bill`, and a test asserts that it never will.

THE FRAME, stated plainly:

    An ANCHOR is any node of the OLD version of an adjacent version pair that carries non-empty
    body text and sits at a non-empty structural path. Nothing else. No diff, no matcher, no
    similarity measure, no retrieval.

    A REGION is the top-level structural unit of the OLD version that an anchor sits under --
    read off the same parse that produced the anchor.

That population deliberately includes provisions the matcher handles perfectly. Those are not
wasted labels: a correspondence dataset that contains only the cases the matcher already flagged
cannot measure whether the matcher is right about the ordinary ones, and "the matcher says this is
unchanged" is a claim that can be wrong.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/study2_frame.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner, manifest_digest  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402

# NOTE: `deltatrack.diff_bill` is deliberately NOT imported. `tests/test_research_probes.py`
# asserts it stays that way -- the frame must not be able to consult the matcher even by accident.

#: A region must hold at least this many anchors to be drawable. Purely a cost floor: a region with
#: three anchors costs a full exhaustive sweep to yield three labels. It is measure-independent.
MIN_REGION_ANCHORS = 10


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enumerate_study2_anchors(bill: str, old_xml: Path) -> list[dict]:
    """Every eligible anchor in one old version. Matcher-independent by construction.

    Eligibility is two structural predicates and nothing else:
      * non-empty body text  -- a node with no text cannot be adjudicated;
      * non-empty match_path -- a node with no structural path has no region, so it cannot enter a
        region-based design at all. This is a real exclusion and it is reported, not hidden.
    """
    tree = normalize_bill(old_xml)
    src = _sha(old_xml)
    out = []
    for ordinal, node in enumerate(tree.nodes):
        if not node.body_text.strip() or not node.match_path:
            continue
        out.append(
            {
                "bill": bill,
                "version": old_xml.stem,
                "source_sha256": src,
                "node_ordinal": ordinal,
                "element_id": node.element_id,
                "match_path": list(node.match_path),
                "region": node.match_path[0],
                "body_len": len(node.body_text),
            }
        )
    return out


def enumerate_study2_regions(min_anchors: int = MIN_REGION_ANCHORS) -> dict[str, dict]:
    """{region_key: {...}} over the whole corpus. The drawable frame.

    A region key is `bill:old_version:top_level_unit`, which is unique and human-readable, and is
    what gets frozen in a draw so a later run can prove it read the same units.
    """
    regions: dict[str, dict] = {}
    for bill, xa, _xb in adjacent_pairs():
        try:
            anchors = enumerate_study2_anchors(bill, xa)
        except Exception:
            continue
        for a in anchors:
            key = f"{a['bill']}:{a['version']}:{a['region']}"
            r = regions.setdefault(
                key,
                {"key": key, "bill": bill, "version": xa.stem, "region": a["region"], "anchors": []},
            )
            r["anchors"].append(a)
    for r in regions.values():
        r["n_anchors"] = len(r["anchors"])
        r["drawable"] = r["n_anchors"] >= min_anchors
    return regions


def _allocate_quota(supply: dict[str, int], n_regions: int, rng: random.Random) -> dict[str, int]:
    """How many regions each bill contributes. Equal base share, remainder by seeded shuffle.

    Returns {bill: k_b} with `sum(k_b) == min(n_regions, sum(supply))` and `k_b <= supply[b]`.

    The shuffle is what stops `n_regions < len(bills)` from excluding whole strata: under the
    round-4 deterministic bill order, a 4-region request over 12 bills could only ever touch the
    four alphabetically first. Capping and redistributing is what stops a small bill from silently
    shrinking the sample below what was asked for.
    """
    bills = sorted(supply)
    total_supply = sum(supply.values())
    target = min(n_regions, total_supply)
    quota = dict.fromkeys(bills, 0)
    if not bills or target == 0:
        return quota

    base = target // len(bills)
    for b in bills:
        quota[b] = min(base, supply[b])

    order = bills[:]
    rng.shuffle(order)
    # Hand out what is still owed, one at a time, to bills that still have supply. Looping rather
    # than a single pass so that capping one bill genuinely redistributes to the others.
    while sum(quota.values()) < target:
        progressed = False
        for b in order:
            if sum(quota.values()) >= target:
                break
            if quota[b] < supply[b]:
                quota[b] += 1
                progressed = True
        if not progressed:  # pragma: no cover - unreachable while target <= total_supply
            break
    return quota


def draw_study2_sample(
    n_regions: int,
    seed: int,
    anchors_per_region: int | None = None,
    min_anchors: int = MIN_REGION_ANCHORS,
) -> dict:
    """Draw regions, then anchors within them. All randomization explicit and reproducible.

    Resolves an ambiguity round 3 left in prose: §R3-C said "take every anchor in a drawn region"
    while the cost table priced "8 regions x 10 anchors". Those are different designs with different
    inclusion probabilities. Here `anchors_per_region=None` means take them all; an integer means
    draw uniformly without replacement within the region.

    TWO DEFECTS ROUND 5 FOUND IN THE ROUND-4 DRAW, both fixed here.

    1. THE RECORDED PROBABILITY WAS WRONG. The round-4 code recorded
       `p_region = len(selected) / len(drawable)` for every region, a single corpus-wide figure.
       Under round-robin allocation the real probability is stratum-specific. Simulated on a frame
       with bill A holding 10 drawable regions and bill B holding 80, requesting 3 regions:

           region in A : true P = 0.202   recorded 0.033   (6x understated)
           region in B : true P = 0.013   recorded 0.033   (2.6x overstated)

       The errors run in OPPOSITE directions, so no scale factor repairs them.

    2. SOME BILLS HAD ZERO SELECTION PROBABILITY. Round-robin iterated `sorted(by_bill)`, a
       deterministic order, so when `n_regions < len(bills)` only the alphabetically-first bills
       could ever be drawn. With 12 drawable bills and a 4-region request, eight bills were
       unsamplable -- a stratification scheme that silently excluded most strata.

    THE FIX is an explicit quota: allocate k_b regions to each bill, then sample k_b uniformly
    without replacement from that bill's n_b drawable regions, so

        P(region r in bill b selected) = k_b / n_b        exactly, and recorded per region.

    Base quota is `n_regions // n_bills` for every bill; the remainder goes to a SEEDED SHUFFLE of
    the bills, so no bill is structurally excluded. A bill whose quota exceeds its supply is capped
    and the surplus redistributed, so a small bill cannot silently shrink the sample.
    """
    regions = enumerate_study2_regions(min_anchors)
    drawable = sorted([r for r in regions.values() if r["drawable"]], key=lambda r: r["key"])
    rng = random.Random(seed)

    by_bill: dict[str, list[dict]] = {}
    for r in drawable:
        by_bill.setdefault(r["bill"], []).append(r)
    bills = sorted(by_bill)

    quota = _allocate_quota({b: len(by_bill[b]) for b in bills}, n_regions, rng)

    selected: list[dict] = []
    p_region_by_bill: dict[str, float] = {}
    for b in bills:
        k = quota.get(b, 0)
        n_b = len(by_bill[b])
        p_region_by_bill[b] = (k / n_b) if n_b else 0.0
        if k:
            selected.extend(rng.sample(by_bill[b], k))

    picked = []
    for r in selected:
        pool = sorted(r["anchors"], key=lambda a: a["node_ordinal"])
        if anchors_per_region is None or anchors_per_region >= len(pool):
            chosen, p_within = pool, 1.0
        else:
            chosen = rng.sample(pool, anchors_per_region)
            p_within = anchors_per_region / len(pool)
        p_r = p_region_by_bill[r["bill"]]
        for a in chosen:
            picked.append(
                {
                    **a,
                    "region_key": r["key"],
                    "p_region": p_r,
                    "p_within_region": p_within,
                    "p_inclusion": p_r * p_within,
                }
            )

    return {
        "corpus_digest": manifest_digest(),
        "seed": seed,
        "n_regions_requested": n_regions,
        "anchors_per_region": anchors_per_region,
        "min_region_anchors": min_anchors,
        "frame": {
            "regions_total": len(regions),
            "regions_drawable": len(drawable),
            "bills_drawable": len({r["bill"] for r in drawable}),
            "anchors_total": sum(r["n_anchors"] for r in regions.values()),
            "anchors_in_drawable_regions": sum(r["n_anchors"] for r in drawable),
        },
        # Per-bill quota and supply, so the recorded probabilities can be re-derived by hand rather
        # than trusted: P(region) = quota[b] / supply[b].
        "quota_by_bill": quota,
        "drawable_by_bill": {b: len(by_bill[b]) for b in bills},
        "p_region_by_bill": p_region_by_bill,
        "selected_regions": [r["key"] for r in selected],
        "selected_anchors": [
            {
                "bill": a["bill"],
                "version": a["version"],
                "source_sha256": a["source_sha256"],
                "node_ordinal": a["node_ordinal"],
                "element_id": a["element_id"],
                "region_key": a["region_key"],
                "p_region": a["p_region"],
                "p_within_region": a["p_within_region"],
                "p_inclusion": a["p_inclusion"],
            }
            for a in picked
        ],
    }


def main() -> None:
    print(banner())
    print()
    regions = enumerate_study2_regions()
    drawable = [r for r in regions.values() if r["drawable"]]
    sizes = sorted(r["n_anchors"] for r in regions.values())
    print("=" * 104)
    print("THE CANONICAL FRAME  (no diff_bills; eligibility is structural only)")
    print("=" * 104)
    print(f"  eligible anchors in the corpus                    : {sum(sizes)}")
    print(f"  old-side regions                                  : {len(regions)}")
    print(f"  regions with >= {MIN_REGION_ANCHORS} anchors (drawable)          : {len(drawable)}")
    print(f"  bills contributing a drawable region              : {len({r['bill'] for r in drawable})}")
    print(f"  anchors inside drawable regions                   : {sum(r['n_anchors'] for r in drawable)}")
    if sizes:
        med, p90 = sizes[len(sizes) // 2], sizes[int(0.9 * (len(sizes) - 1))]
        print(f"  region size: median {med}  p90 {p90}  max {max(sizes)}")
    print()
    demo = draw_study2_sample(n_regions=8, seed=20260806, anchors_per_region=10)
    print("  DEMONSTRATION DRAW (synthetic, for testing the algorithm -- NOT the study's sample):")
    print(f"    seed {demo['seed']}  corpus {demo['corpus_digest']}")
    print(
        f"    regions selected : {len(demo['selected_regions'])} across "
        f"{len({k.split(':')[0] for k in demo['selected_regions']})} bills"
    )
    print(f"    anchors selected : {len(demo['selected_anchors'])}")
    if demo["selected_anchors"]:
        p = demo["selected_anchors"][0]["p_inclusion"]
        print(f"    example inclusion probability : {p:.4f}")
    print()
    print("  The ALGORITHM is frozen in this PR. The study's actual draw is not performed here.")
    if "--json" in sys.argv:
        print(json.dumps(demo, indent=2))


if __name__ == "__main__":
    main()
