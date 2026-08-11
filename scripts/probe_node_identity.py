"""Where an ADR 0019 ordinal can still be recovered, and which recovery mechanisms are wrong.

Investigation B for the #581 prerequisite. ``ObservationRef.ordinal`` must index the
parser's **complete emitted sequence**. This measures four things and tries to break three
of them:

1. **Does ``match_nodes`` pass node objects through by identity?** If every node it
   returns *is* (``id()``) a node of its source ``BillTree.nodes``, the ordinal is
   recoverable there without any new field. If it reconstructs or copies, it is not.
2. **Is the recovery a bijection?** Every node claimed at most once, and no node omitted.
3. **Does identity survive the whole pre-classification sequence?** Since #591 that
   sequence is two stages, not one: ``apply_similarity_revocation(match_nodes(...))``.
   The second stage replaces a revoked pairing with the two unmatched observations it
   becomes, so it rebuilds the tuple list -- and a stage that rebuilds tuples is exactly
   where a copy would be introduced without anyone noticing. Measuring only ``match_nodes``
   would leave a future ObservationRef wired at a seam one stage short of classification.
4. **Where does that mechanism stop working?** ``NodeDiff`` carries no node reference, so
   identity is available up to the end of that sequence and gone the moment classification
   emits records.

NEGATIVE CONTROLS, because a green identity check proves nothing on its own -- a lookup
that always hits is indistinguishable from one that cannot miss. Three faults are injected
and each must turn the check red:

control A (copy)
    Substitute a ``dataclasses.replace(node)`` -- a distinct object with identical field
    values -- into the output. Identity lookup must raise; value-equality lookup must
    silently succeed with an address it did not earn. This is the whole argument for
    identity over value equality, run rather than asserted.

control B (value collision)
    Count nodes within one tree that are value-equal to another. ``BillNode`` is a frozen
    dataclass, so it hashes by field values: wherever two nodes collide, a ``{node:
    ordinal}`` dict silently holds one address for two observations. Reported as a
    measured population, and control A covers the case where that population is zero --
    zero collisions today is not a guarantee, and the mechanism is wrong either way.

control C (output position as ordinal)
    Derive the ordinal from the node's position in the stage output instead of from the
    identity index, and count how many nodes then carry a WRONG address. This is ADR
    0019's named hazard -- indexing a re-sorted view -- measured rather than described.

    Run against both stages, and the two figures MUST come out equal. That is not a
    coincidence to report as if it were a second measurement: the revocation stage
    replaces a pairing with its two halves *in place*, so each side's observation
    sequence is untouched and the per-side positions cannot move. Asserting the equality
    turns the second run into a tripwire for the one mutation #591's own docstring flags
    as dangerous -- reversing the two replacements, or appending them elsewhere, which
    moves canonical output while leaving every change count untouched. A difference here
    means the revocation stage reordered observations.

Read-only, writes nothing. Run from the project root:

    uv run python scripts/probe_node_identity.py

``id()`` is safe as a key here only because each tree is held alive for the whole of its
own measurement: CPython may reuse the id of a collected object, and a map outliving its
nodes would be reading addresses that no longer mean anything.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import apply_similarity_revocation, match_nodes  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402


def identity_index(nodes: list) -> dict[int, int]:
    """``{id(node): ordinal}`` over the complete emitted sequence."""
    return {id(node): ordinal for ordinal, node in enumerate(nodes)}


def survey(tuples: list, old_at: dict[int, int], new_at: dict[int, int], old_total: int, new_total: int) -> tuple:
    """``(foreign, claimed_twice, omitted)`` for one stage's tuple list."""
    foreign = 0
    old_seen: Counter[int] = Counter()
    new_seen: Counter[int] = Counter()
    for old_node, new_node in tuples:
        for node, index, seen in ((old_node, old_at, old_seen), (new_node, new_at, new_seen)):
            if node is None:
                continue
            if id(node) not in index:
                foreign += 1
                continue
            seen[index[id(node)]] += 1
    claimed_twice = sum(n - 1 for n in old_seen.values() if n > 1)
    claimed_twice += sum(n - 1 for n in new_seen.values() if n > 1)
    omitted = (old_total - len(old_seen)) + (new_total - len(new_seen))
    return foreign, claimed_twice, omitted


def position_errors(tuples: list, old_at: dict[int, int], new_at: dict[int, int]) -> tuple[int, int]:
    """``(total, wrong)`` addresses if a node's position in this list were its ordinal."""
    total = wrong = 0
    for side, index in ((0, old_at), (1, new_at)):
        for position, node in enumerate(t[side] for t in tuples if t[side] is not None):
            total += 1
            if index[id(node)] != position:
                wrong += 1
    return total, wrong


def main() -> None:
    pairs_checked = 0
    stage_totals = {
        "match_nodes": [0, 0, 0],
        "after revocation": [0, 0, 0],
    }
    position_totals = {
        "match_nodes": [0, 0],
        "after revocation": [0, 0],
    }
    revocation_added = 0
    value_collision_sides = 0
    value_collision_nodes = 0
    control_a_red = 0
    control_a_value_silent = 0

    for _key, old_path, new_path in baseline_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        old_at = identity_index(old_tree.nodes)
        new_at = identity_index(new_tree.nodes)

        # Value-keyed maps, for control B. A shorter dict means two nodes collapsed.
        old_by_value = {node: ordinal for ordinal, node in enumerate(old_tree.nodes)}
        new_by_value = {node: ordinal for ordinal, node in enumerate(new_tree.nodes)}
        for by_value, tree in ((old_by_value, old_tree), (new_by_value, new_tree)):
            lost = len(tree.nodes) - len(by_value)
            if lost:
                value_collision_sides += 1
                value_collision_nodes += lost

        pairs = match_nodes(old_tree, new_tree)
        decided = apply_similarity_revocation(pairs)
        revocation_added += len(decided) - len(pairs)

        for label, tuples in (("match_nodes", pairs), ("after revocation", decided)):
            found = survey(tuples, old_at, new_at, len(old_tree.nodes), len(new_tree.nodes))
            for slot, value in enumerate(found):
                stage_totals[label][slot] += value
            total, wrong = position_errors(tuples, old_at, new_at)
            position_totals[label][0] += total
            position_totals[label][1] += wrong

        # Control A: a copy carrying identical field values, in place of the real node.
        original = old_tree.nodes[0]
        impostor = replace(original)
        if id(impostor) not in old_at:
            control_a_red += 1
        if old_by_value.get(impostor) is not None:
            control_a_value_silent += 1

        pairs_checked += 1

    print("===== IDENTITY SURVIVAL THROUGH THE PRE-CLASSIFICATION SEQUENCE =====")
    print(f"corpus pairs checked: {pairs_checked}")
    print(f"tuples added by the revocation stage (one per revoked pairing): {revocation_added}")
    for label in ("match_nodes", "after revocation"):
        foreign, claimed_twice, omitted = stage_totals[label]
        print(f"  {label}:")
        print(f"    returned nodes NOT an object of their source tree (copies/reconstructions): {foreign}")
        print(f"    observations claimed by more than one tuple: {claimed_twice}")
        print(f"    observations reaching no tuple at all: {omitted}")

    print("\n===== CONTROL A: A COPY IS SUBSTITUTED FOR THE REAL NODE =====")
    print(f"pairs where the IDENTITY lookup went red (correct): {control_a_red}/{pairs_checked}")
    print(f"pairs where the VALUE-EQUALITY lookup answered anyway (wrong address, no error): {control_a_value_silent}")

    print("\n===== CONTROL B: VALUE-EQUAL NODES WITHIN ONE TREE =====")
    print(f"tree sides holding at least one value-collision: {value_collision_sides}")
    print(f"observations a value-keyed map would silently lose: {value_collision_nodes}")

    print("\n===== CONTROL C: OUTPUT POSITION USED AS THE ORDINAL =====")
    for label in ("match_nodes", "after revocation"):
        total, wrong = position_totals[label]
        share = f"{100.0 * wrong / total:.1f}%" if total else "n/a"
        print(f"  {label}: {wrong} WRONG of {total} addresses derived from position ({share})")
    if position_totals["match_nodes"] != position_totals["after revocation"]:
        raise SystemExit(
            "the revocation stage moved a per-side observation position. Its replacements are "
            "supposed to be adjacent and in place, and canonical output depends on that "
            f"(match_nodes={position_totals['match_nodes']}, "
            f"after revocation={position_totals['after revocation']})"
        )
    print("  equal by construction: the revocation stage replaces a pairing in place, so")
    print("  per-side observation order is untouched. A difference would mean it reordered.")


if __name__ == "__main__":
    main()
