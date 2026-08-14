"""What B3's unique-path migration costs, measured against the two paths it sits between.

B3 routes the non-colliding ``match_path`` group through retrieval, evidence and assignment
instead of pairing its two observations directly. The audit's §13 ruling was *keep the fast
path*, on a measurement that the alternative -- routing every unique group through
``_match_collision_group`` -- costs 1.62x. B3 keeps that ruling by migrating the fast path to
the staged contracts **without** sending it through the collision machinery: no division
partition, no cross-division round, no similarity measurement.

So the number that matters is not "is it slower than a tuple append" (it is, by construction)
but **where it lands between the two paths the audit already priced**. Three timings, same
corpus, same process:

``production``
    ``match_nodes`` as it stands in the checkout this is run from.
``collision_routing``
    Every group, unique ones included, through ``_match_collision_group``. The audit's
    "retire the fast path" arm, re-measured here so the comparison is same-process and
    same-machine rather than quoted across sessions.
``grouping_floor``
    The ``match_path`` grouping alone, emitting the legacy tuple for a unique group and
    skipping collision groups entirely. Not a candidate implementation -- it produces a wrong
    stream -- but it is the cost of the traversal every arm pays, so it separates "the stage
    migration is expensive" from "parsing 27 bill pairs into groups is expensive".

Run it on the checkout BEFORE the change and again AFTER; ``production`` moves and the other
two are the fixed reference points either side of it.

    uv run python docs/research/provision-matching/probes/round1_b3_cost.py

Timing is best-of-N rather than a mean: the minimum is the run least disturbed by whatever
else the machine was doing, and this is a comparison between arms rather than a service-level
figure. Trees are parsed once, outside every timed region, because parsing dwarfs matching and
would bury the difference this exists to show.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from deltatrack import diff_bill as db  # noqa: E402
from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.matching import CandidateSet  # noqa: E402
from tests.conftest import manifest_version_pairs  # noqa: E402

REPEATS = 5


def group_by_path(tree) -> dict[tuple[str, ...], list]:
    groups: dict[tuple[str, ...], list] = defaultdict(list)
    for node in tree.nodes:
        groups[node.match_path].append(node)
    return groups


def collision_routing(old, new) -> list:
    """Every group through the collision path -- the audit's "retire the fast path" arm."""
    old_groups, new_groups = group_by_path(old), group_by_path(new)
    registry = db.observation_registry(old, new)
    candidates = CandidateSet()
    pairs: list = []
    for path in dict.fromkeys(list(old_groups) + list(new_groups)):
        group_pairs, _assignments = db._match_collision_group(
            old_groups.get(path, []), new_groups.get(path, []), registry, candidates
        )
        pairs.extend(group_pairs)
    return pairs


def grouping_floor(old, new) -> list:
    """The traversal every arm pays for, and nothing else. Deliberately not a correct matcher."""
    old_groups, new_groups = group_by_path(old), group_by_path(new)
    pairs: list = []
    for path in dict.fromkeys(list(old_groups) + list(new_groups)):
        old_nodes, new_nodes = old_groups.get(path, []), new_groups.get(path, [])
        if len(old_nodes) <= 1 and len(new_nodes) <= 1:
            pairs.append((old_nodes[0] if old_nodes else None, new_nodes[0] if new_nodes else None))
    return pairs


def best_of(fn, trees) -> float:
    best = float("inf")
    for _ in range(REPEATS):
        start = time.perf_counter()
        for old, new in trees:
            fn(old, new)
        best = min(best, time.perf_counter() - start)
    return best


def group_census(trees) -> dict[str, int]:
    """How many groups of each shape the corpus presents, so the timings are interpretable."""
    census = {"unique_1x1": 0, "unique_one_sided": 0, "collision": 0}
    for old, new in trees:
        old_groups, new_groups = group_by_path(old), group_by_path(new)
        for path in dict.fromkeys(list(old_groups) + list(new_groups)):
            old_nodes, new_nodes = old_groups.get(path, []), new_groups.get(path, [])
            if len(old_nodes) <= 1 and len(new_nodes) <= 1:
                census["unique_1x1" if old_nodes and new_nodes else "unique_one_sided"] += 1
            else:
                census["collision"] += 1
    return census


def main() -> None:
    pairs = manifest_version_pairs()
    assert pairs, "no committed version pairs; there is nothing to measure"
    trees = [(normalize_bill(old), normalize_bill(new)) for old, new in pairs]

    census = group_census(trees)
    print(f"corpus pairs        : {len(trees)}")
    print(f"unique 1x1 groups   : {census['unique_1x1']}")
    print(f"unique one-sided    : {census['unique_one_sided']}")
    print(f"collision groups    : {census['collision']}")

    # The stream each arm produces, so a timing is never reported for an arm that stopped
    # doing the work. `collision_routing` must agree with production exactly -- the audit
    # measured that equivalence on 27/27 pairs and it is the premise of the comparison.
    for old, new in trees:
        produced = db.match_nodes(old, new)
        routed = collision_routing(old, new)
        assert len(produced) == len(routed), (
            f"collision routing emitted {len(routed)} pairings against production's {len(produced)}; "
            "the arms are no longer doing the same job and the ratio below would be meaningless"
        )

    production = best_of(db.match_nodes, trees)
    routed = best_of(collision_routing, trees)
    floor = best_of(grouping_floor, trees)

    print()
    print("=== round-1 matching, best of %d over the committed corpus ===" % REPEATS)
    print(f"  grouping_floor     : {floor * 1000:8.1f} ms   (traversal only, not a matcher)")
    print(f"  production         : {production * 1000:8.1f} ms   {production / floor:5.2f}x floor")
    print(f"  collision_routing  : {routed * 1000:8.1f} ms   {routed / floor:5.2f}x floor")
    print()
    print(f"  production vs collision_routing : {routed / production:.2f}x")
    print(f"  per comparison, production      : {production / len(trees) * 1000:.1f} ms")


if __name__ == "__main__":
    main()
