"""Round-1 decisive experiments.

1. Do within-division assignments ever leave leftovers, and do those leftovers ever
   reach the cross-division fallback? (the assignment-conditioned retrieval question)
2. Is match_nodes' unique-path fast path behaviourally redundant with routing the same
   group through _match_collision_group? (measured, not argued)
3. Tie direction: does ascending (oi, ni) change selection?
4. Emission order under a CandidateSet-ordinal-driven assignment.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import normalize_bill

_ORDINAL = re.compile(r"^(\d+)_")
real_sp = db._similarity_pair
real_cg = db._match_collision_group

STATE = {"ordinals": {}, "calls": [], "both_sided": 0, "n": 0}
GROUPS: list[dict] = []


def ordv(n):
    return STATE["ordinals"].get(id(n))


def wrapped_sp(old_nodes, new_nodes):
    STATE["n"] += 1
    phase = "within" if STATE["n"] <= STATE["both_sided"] else "cross"
    res = real_sp(old_nodes, new_nodes)
    STATE["calls"].append(
        {
            "phase": phase,
            "n_old": len(old_nodes),
            "n_new": len(new_nodes),
            "left_old": [ordv(o) for o, n in res if o is not None and n is None],
            "left_new": [ordv(n) for o, n in res if o is None and n is not None],
        }
    )
    return res


def wrapped_cg(old_nodes, new_nodes):
    STATE["calls"] = []
    STATE["n"] = 0
    od = {n.division_key for n in old_nodes}
    nd = {n.division_key for n in new_nodes}
    STATE["both_sided"] = len(od & nd)
    res = real_cg(old_nodes, new_nodes)
    within = [c for c in STATE["calls"] if c["phase"] == "within"]
    cross = [c for c in STATE["calls"] if c["phase"] == "cross"]
    GROUPS.append(
        {
            "within_calls": len(within),
            "within_with_leftovers": sum(1 for c in within if c["left_old"] or c["left_new"]),
            "within_leftover_old": sum(len(c["left_old"]) for c in within),
            "within_leftover_new": sum(len(c["left_new"]) for c in within),
            "reached_cross": bool(cross),
            "n_old": len(old_nodes),
            "n_new": len(new_nodes),
        }
    )
    return res


def adjacent_pairs(bill_dir: Path):
    numbered = []
    for path in bill_dir.glob("*.xml"):
        m = _ORDINAL.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def match_nodes_no_fastpath(old, new):
    """match_nodes with the unique-path shortcut removed: every group goes to the collision path."""
    old_groups = defaultdict(list)
    new_groups = defaultdict(list)
    for node in old.nodes:
        old_groups[node.match_path].append(node)
    for node in new.nodes:
        new_groups[node.match_path].append(node)
    all_paths = dict.fromkeys(list(old_groups.keys()) + list(new_groups.keys()))
    pairs = []
    for path in all_paths:
        pairs.extend(real_cg(old_groups.get(path, []), new_groups.get(path, [])))
    return pairs


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("tests/corpus")

    # --- Experiment 2 first, with production UNPATCHED ---
    print("=== 2. IS THE UNIQUE-PATH FAST PATH REDUNDANT? ===")
    same = diff = 0
    fastpath_cross_div = 0
    fastpath_total = 0
    for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for op, np_ in adjacent_pairs(bill_dir):
            try:
                ot, nt = normalize_bill(op), normalize_bill(np_)
            except Exception:
                continue
            prod = db.match_nodes(ot, nt)
            alt = match_nodes_no_fastpath(ot, nt)
            prod_k = [(id(o) if o else None, id(n) if n else None) for o, n in prod]
            alt_k = [(id(o) if o else None, id(n) if n else None) for o, n in alt]
            if prod_k == alt_k:
                same += 1
            else:
                diff += 1
                print(f"  DIFFERS: {bill_dir.name} {op.stem}->{np_.stem}")
            # how many unique 1x1 paths pair across different divisions
            og, ng = defaultdict(list), defaultdict(list)
            for x in ot.nodes:
                og[x.match_path].append(x)
            for x in nt.nodes:
                ng[x.match_path].append(x)
            for p in dict.fromkeys(list(og) + list(ng)):
                o, n = og.get(p, []), ng.get(p, [])
                if len(o) == 1 and len(n) == 1:
                    fastpath_total += 1
                    if o[0].division_key != n[0].division_key:
                        fastpath_cross_div += 1
    print(f"  corpus pairs with IDENTICAL stream (order + identity): {same}")
    print(f"  corpus pairs that differ                             : {diff}")
    print(f"  unique 1x1 paths whose two nodes are in DIFFERENT divisions: {fastpath_cross_div}/{fastpath_total}")
    print()

    # --- Experiment 1: within-division leftovers ---
    db._similarity_pair = wrapped_sp
    db._match_collision_group = wrapped_cg
    for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for op, np_ in adjacent_pairs(bill_dir):
            try:
                ot, nt = normalize_bill(op), normalize_bill(np_)
            except Exception:
                continue
            STATE["ordinals"] = {}
            for i, x in enumerate(ot.nodes):
                STATE["ordinals"][id(x)] = i
            for i, x in enumerate(nt.nodes):
                STATE["ordinals"][id(x)] = i
            db.match_nodes(ot, nt)

    print("=== 1. ASSIGNMENT-CONDITIONED RETRIEVAL: IS IT EXERCISED? ===")
    print(f"collision groups: {len(GROUPS)}")
    wl = [g for g in GROUPS if g["within_with_leftovers"]]
    print(f"  groups where WITHIN-division assignment left leftovers: {len(wl)}")
    print(f"    total leftover old observations: {sum(g['within_leftover_old'] for g in GROUPS)}")
    print(f"    total leftover new observations: {sum(g['within_leftover_new'] for g in GROUPS)}")
    both = [g for g in wl if g["reached_cross"]]
    print(f"  of those groups, ones that ALSO reached the cross fallback: {len(both)}")
    print(f"  groups that reached cross at all: {sum(1 for g in GROUPS if g['reached_cross'])}")
    print()
    print("  -> If 'left leftovers' > 0 but 'also reached cross' == 0, the dependency is")
    print("     REAL IN CODE but UNEXERCISED on this corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
