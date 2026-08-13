"""Round-1 deep analysis: group-level counterfactuals, cross-division provenance, ordering.

Read-only. Wraps production, never reimplements its selection.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import normalize_bill
from deltatrack.similarity import text_similarity

_ORDINAL = re.compile(r"^(\d+)_")

real_similarity_pair = db._similarity_pair
real_collision_group = db._match_collision_group

STATE = {"ordinals": {}, "calls": [], "both_sided": 0, "n_calls": 0}
GROUPS: list[dict] = []


def ordv(node):
    return STATE["ordinals"].get(id(node))


def wrapped_similarity_pair(old_nodes, new_nodes):
    STATE["n_calls"] += 1
    phase = "within" if STATE["n_calls"] <= STATE["both_sided"] else "cross"
    result = real_similarity_pair(old_nodes, new_nodes)
    STATE["calls"].append(
        {
            "phase": phase,
            "old": [ordv(o) for o in old_nodes],
            "new": [ordv(n) for n in new_nodes],
            "old_divs": [o.division_key for o in old_nodes],
            "new_divs": [n.division_key for n in new_nodes],
            "matched": [(ordv(o), ordv(n)) for o, n in result if o and n],
            "left_old": [ordv(o) for o, n in result if o is not None and n is None],
            "left_new": [ordv(n) for o, n in result if o is None and n is not None],
            "n_old": len(old_nodes),
            "n_new": len(new_nodes),
        }
    )
    return result


def greedy(sorted_c):
    co, cn, sel = set(), set(), []
    for _s, a, b in sorted_c:
        if a in co or b in cn:
            continue
        co.add(a)
        cn.add(b)
        sel.append((a, b))
    return sel


def wrapped_collision_group(old_nodes, new_nodes):
    STATE["calls"] = []
    STATE["n_calls"] = 0
    old_divs = {n.division_key for n in old_nodes}
    new_divs = {n.division_key for n in new_nodes}
    STATE["both_sided"] = len(old_divs & new_divs)

    result = real_collision_group(old_nodes, new_nodes)

    # --- Counterfactual: ONE flat candidate population over the whole group, ignoring
    # the division partition entirely. Greedy on (sim, oi, ni) over group-local positions.
    cands = []
    onorm = [db._normalize_text(o.body_text) for o in old_nodes]
    nnorm = [db._normalize_text(n.body_text) for n in new_nodes]
    for oi in range(len(old_nodes)):
        for ni in range(len(new_nodes)):
            cands.append((text_similarity(onorm[oi], nnorm[ni]), oi, ni))
    flat_sel = {(ordv(old_nodes[a]), ordv(new_nodes[b])) for a, b in greedy(sorted(cands, reverse=True))}
    prod_sel = {(ordv(o), ordv(n)) for o, n in result if o is not None and n is not None}

    # --- Counterfactual: cross-division retrieval run BEFORE within-division assignment,
    # i.e. every cross-division pair available from the start (still division-partitioned
    # scoring is impossible then, so this is the same as flat, recorded separately below).

    GROUPS.append(
        {
            "n_old": len(old_nodes),
            "n_new": len(new_nodes),
            "n_divs_old": len(old_divs),
            "n_divs_new": len(new_divs),
            "both_sided_divs": STATE["both_sided"],
            "calls": list(STATE["calls"]),
            "prod_selected": prod_sel,
            "flat_selected": flat_sel,
            "flat_differs": flat_sel != prod_sel,
            "flat_extra": len(flat_sel - prod_sel),
            "flat_missing": len(prod_sel - flat_sel),
            "flat_cands": len(cands),
            "prod_scored": sum(
                c["n_old"] * c["n_new"]
                for c in STATE["calls"]
                if c["n_old"] > 0 and c["n_new"] > 0 and not (c["n_old"] == 1 and c["n_new"] == 1)
            ),
        }
    )
    return result


def adjacent_pairs(bill_dir: Path):
    numbered = []
    for path in bill_dir.glob("*.xml"):
        m = _ORDINAL.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("tests/corpus")
    db._similarity_pair = wrapped_similarity_pair
    db._match_collision_group = wrapped_collision_group

    npairs = 0
    for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for old_path, new_path in adjacent_pairs(bill_dir):
            try:
                old_tree = normalize_bill(old_path)
                new_tree = normalize_bill(new_path)
            except Exception:
                continue
            npairs += 1
            STATE["ordinals"] = {}
            for i, n in enumerate(old_tree.nodes):
                STATE["ordinals"][id(n)] = i
            for i, n in enumerate(new_tree.nodes):
                STATE["ordinals"][id(n)] = i
            db.match_nodes(old_tree, new_tree)

    print(f"corpus pairs: {npairs}")
    print(f"collision groups: {len(GROUPS)}")
    print()

    print("=== A. FLATTEN COUNTERFACTUAL (one candidate population per match_path group) ===")
    differ = [g for g in GROUPS if g["flat_differs"]]
    print(f"groups where flattening changes the selected set: {len(differ)}/{len(GROUPS)}")
    print(f"  links flattening would ADD    : {sum(g['flat_extra'] for g in differ)}")
    print(f"  links flattening would REMOVE : {sum(g['flat_missing'] for g in differ)}")
    print(
        f"  candidates: production scores {sum(g['prod_scored'] for g in GROUPS)}, "
        f"flat would score {sum(g['flat_cands'] for g in GROUPS)}"
    )
    print()

    print("=== B. CROSS-DIVISION FALLBACK ===")
    cross_calls = [c for g in GROUPS for c in g["calls"] if c["phase"] == "cross"]
    print(f"cross-division invocations: {len(cross_calls)}")
    greedy_cross = [c for c in cross_calls if c["n_old"] > 1 or c["n_new"] > 1]
    short_cross = [c for c in cross_calls if c["n_old"] == 1 and c["n_new"] == 1]
    print(f"  of which 1x1 shortcut (no similarity computed): {len(short_cross)}")
    print(f"  of which multi (greedy)                        : {len(greedy_cross)}")
    # Provenance: did each cross-division participant come from an assignment leftover,
    # or from a division present on only one side (structural, never assigned)?
    from_assignment = 0
    from_structural = 0
    for g in GROUPS:
        within = [c for c in g["calls"] if c["phase"] == "within"]
        assigned_left = set()
        for c in within:
            assigned_left |= set(c["left_old"]) | set(c["left_new"])
        for c in g["calls"]:
            if c["phase"] != "cross":
                continue
            for o in c["old"]:
                if o in assigned_left:
                    from_assignment += 1
                else:
                    from_structural += 1
            for n in c["new"]:
                if n in assigned_left:
                    from_assignment += 1
                else:
                    from_structural += 1
    print(f"  participants left over by WITHIN-DIVISION ASSIGNMENT : {from_assignment}")
    print(f"  participants from a one-sided division (structural)  : {from_structural}")
    # Ordinal monotonicity of the concatenated cross lists
    bad = [c for c in cross_calls if c["old"] != sorted(c["old"]) or c["new"] != sorted(c["new"])]
    print(f"  cross lists NOT in ascending parser-ordinal order     : {len(bad)}/{len(cross_calls)}")
    multi_div = [c for c in cross_calls if len(set(c["old_divs"])) > 1 or len(set(c["new_divs"])) > 1]
    print(f"  cross lists spanning more than one division          : {len(multi_div)}/{len(cross_calls)}")
    print()

    print("=== C. TIE DIRECTION (descending oi/ni is production) ===")
    print("  measured by round1_controls.py, which re-derives each greedy call's candidate")
    print("  list and reruns the selection under the opposite tie direction.")
    print()

    print("=== D. WITHIN-DIVISION LIST SHAPES ===")
    within_calls = [c for g in GROUPS for c in g["calls"] if c["phase"] == "within"]
    print(f"within-division invocations: {len(within_calls)}")
    print(f"  1x1 shortcut : {sum(1 for c in within_calls if c['n_old'] == 1 and c['n_new'] == 1)}")
    print(f"  multi        : {sum(1 for c in within_calls if c['n_old'] > 1 or c['n_new'] > 1)}")
    bad_w = [c for c in within_calls if c["old"] != sorted(c["old"]) or c["new"] != sorted(c["new"])]
    print(f"  NOT ascending parser-ordinal order: {len(bad_w)}/{len(within_calls)}")
    print()

    print("=== E. GROUPS WITH NO SIMILARITY CALL AT ALL ===")
    print(f"  {sum(1 for g in GROUPS if not g['calls'])}/{len(GROUPS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
