"""What B3's unique-path migration costs, measured against the two paths it sits between.

B3 routes the non-colliding ``match_path`` group through retrieval, evidence and assignment
instead of pairing its two observations directly. The audit's §13 ruling was *keep the fast
path*, on a measurement that the alternative -- routing every unique group through
``_match_collision_group`` -- costs 1.62x. B3 keeps that ruling by migrating the fast path to
the staged contracts **without** sending it through the collision machinery: no division
partition, no cross-division round, no similarity measurement.

So the number that matters is not "is it slower than a tuple append" (it is, by construction)
but **where it lands between the two paths the audit already priced**. Four arms, same corpus,
same process, one run:

``legacy_fast_path``
    The pre-B3 traversal, transcribed: a unique group emits its tuple directly, a collision
    group goes to ``_match_collision_group``. The "before" measurement.
``production``
    ``match_nodes`` as it stands in the checkout this is run from. The "after" measurement.
``collision_routing``
    Every group, unique ones included, through ``_match_collision_group``. The audit's
    "retire the fast path" arm, whose 1.62x is the cost §13 ruled against paying.
``grouping_floor``
    The ``match_path`` grouping alone, emitting the legacy tuple for a unique group and
    skipping collision groups entirely. Not a candidate implementation -- it produces a wrong
    stream -- but it is the cost of the traversal every arm pays, so it separates "the stage
    migration is expensive" from "parsing 27 bill pairs into groups is expensive".

    uv run python docs/research/provision-matching/probes/round1_b3_cost.py

**All four arms run in one process, and that is the methodology rather than a convenience.**
An earlier version measured ``production`` before and after the change in two separate runs.
A concurrent pytest in another worktree started between them and inflated every matching-heavy
arm by ~1.8x, including one whose code had not changed -- which is indistinguishable from a
real regression if only the changed arm is looked at. Interleaving the arms makes contention a
common-mode effect: the ratios survive it, and the unchanged arms are the evidence that they
did. Report the ratios, not the milliseconds.

Timing is best-of-N rather than a mean: the minimum is the repeat least disturbed by whatever
else the machine was doing. Trees are parsed once, outside every timed region, because parsing
dwarfs matching and would bury the difference this exists to show.
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


def legacy_fast_path(old, new) -> list:
    """The pre-B3 traversal, transcribed. The unique group is paired by a tuple construction.

    Transcribed rather than imported from git history, for the same reason the preservation
    harness transcribes the legacy composition: an arm that called production could not measure
    a difference from production. It reproduces the ONE thing B3 changed and nothing else --
    collision groups still go through the real stage, so the difference between this arm and
    ``production`` is the unique-path migration alone.
    """
    old_groups, new_groups = group_by_path(old), group_by_path(new)
    registry = db.observation_registry(old, new)
    candidates = CandidateSet()
    pairs: list = []
    for path in dict.fromkeys(list(old_groups) + list(new_groups)):
        old_nodes, new_nodes = old_groups.get(path, []), new_groups.get(path, [])
        if len(old_nodes) <= 1 and len(new_nodes) <= 1:
            pairs.append((old_nodes[0] if old_nodes else None, new_nodes[0] if new_nodes else None))
        else:
            group_pairs, _assignments = db._match_collision_group(old_nodes, new_nodes, registry, candidates)
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


def paired_unique_groups(trees) -> list[tuple[list, list, object]]:
    """Every 1x1 non-colliding group of the corpus, with its comparison's registry.

    The population B3 moved. One-sided groups are excluded: they are not retrieved, so they cost
    the dispatch and nothing else, and including them would dilute the per-group figure below
    with rows that have no stages to attribute.
    """
    groups = []
    for old, new in trees:
        registry = db.observation_registry(old, new)
        old_groups, new_groups = group_by_path(old), group_by_path(new)
        for path in dict.fromkeys(list(old_groups) + list(new_groups)):
            old_nodes, new_nodes = old_groups.get(path, []), new_groups.get(path, [])
            if len(old_nodes) == 1 and len(new_nodes) == 1:
                groups.append((old_nodes, new_nodes, registry))
    return groups


def stage_attribution(groups) -> None:
    """What each of the four stages costs per group, by cumulative difference.

    Cumulative rather than isolated, because the stages are not independent: evidence needs the
    proposals, assignment needs the evidence. Each row runs everything up to and including its
    stage, so the difference between two adjacent rows is that stage's marginal cost on real
    corpus input.

    This is the attribution a bare ratio cannot give. It answers whether the migration's cost
    sits in one avoidable place or is spread across four stages each doing genuine contract work
    -- which is the difference between "optimise this" and "this is what the contracts cost".
    """

    def legacy():
        for old_nodes, new_nodes, _registry in groups:
            (old_nodes[0], new_nodes[0])

    def retrieval():
        for old_nodes, new_nodes, registry in groups:
            db.retrieve_unique_path_population(old_nodes, new_nodes, registry)

    def propose():
        candidates = CandidateSet()
        for old_nodes, new_nodes, registry in groups:
            db.retrieve_unique_path_population(old_nodes, new_nodes, registry).propose_into(candidates)

    def evidence():
        candidates = CandidateSet()
        for old_nodes, new_nodes, registry in groups:
            population = db.retrieve_unique_path_population(old_nodes, new_nodes, registry)
            population.propose_into(candidates)
            db.group_correspondence_evidence(population, candidates)

    def assignment():
        candidates = CandidateSet()
        for old_nodes, new_nodes, registry in groups:
            population = db.retrieve_unique_path_population(old_nodes, new_nodes, registry)
            population.propose_into(candidates)
            db.assign_group(population, db.group_correspondence_evidence(population, candidates))

    stages = [
        ("legacy tuple", legacy),
        ("retrieval", retrieval),
        ("propose", propose),
        ("evidence", evidence),
        ("assignment", assignment),
    ]
    timings = [(label, best_of_call(fn)) for label, fn in stages]

    print()
    print(f"=== per-stage marginal cost, over the corpus's {len(groups)} paired unique groups ===")
    previous = timings[0][1]
    for label, elapsed in timings[1:]:
        print(f"  {label:14s} {(elapsed - previous) / len(groups) * 1e6:6.2f} us/group")
        previous = elapsed
    print(f"  {'TOTAL':14s} {(timings[-1][1] - timings[0][1]) / len(groups) * 1e6:6.2f} us/group")


def best_of_call(fn) -> float:
    best = float("inf")
    for _ in range(REPEATS):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


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

    # Every real arm must emit the same stream, so a timing is never reported for an arm that
    # stopped doing the work. The audit measured production/collision-routing equivalence on
    # 27/27 pairs and it is the premise of the comparison; B3 preserves it, and `legacy_fast_path`
    # is the pre-B3 stream, which is the claim the preservation harness proves independently.
    for old, new in trees:
        produced = db.match_nodes(old, new)
        for name, arm in (("legacy_fast_path", legacy_fast_path), ("collision_routing", collision_routing)):
            emitted = arm(old, new)
            assert emitted == produced, (
                f"{name} emitted a different pairing stream from production ({len(emitted)} vs "
                f"{len(produced)} pairings); the arms are not doing the same job and the ratios "
                "below would be meaningless"
            )

    # Interleaved rather than run arm-by-arm, so a load spike lands on all four rather than on
    # whichever one happened to be running when it arrived.
    legacy = best_of(legacy_fast_path, trees)
    production = best_of(db.match_nodes, trees)
    routed = best_of(collision_routing, trees)
    floor = best_of(grouping_floor, trees)

    print()
    print("=== round-1 matching, best of %d over the committed corpus ===" % REPEATS)
    print(f"  grouping_floor     : {floor * 1000:8.1f} ms   (traversal only, not a matcher)")
    print(f"  legacy_fast_path   : {legacy * 1000:8.1f} ms   {legacy / floor:5.2f}x floor   [pre-B3]")
    print(f"  production         : {production * 1000:8.1f} ms   {production / floor:5.2f}x floor   [post-B3]")
    print(f"  collision_routing  : {routed * 1000:8.1f} ms   {routed / floor:5.2f}x floor   [fast path retired]")
    print()
    print("=== the ratios, which are what survive machine contention ===")
    print(f"  B3 cost, production / legacy_fast_path      : {production / legacy:.2f}x")
    print(f"  the rejected alternative, routed / legacy   : {routed / legacy:.2f}x")
    print(f"  headroom kept, collision_routing / production: {routed / production:.2f}x")
    print(f"  per comparison, production                  : {production / len(trees) * 1000:.1f} ms")

    stage_attribution(paired_unique_groups(trees))


if __name__ == "__main__":
    main()
