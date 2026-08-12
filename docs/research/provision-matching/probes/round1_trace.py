"""Instrument round-1 matching on the committed corpus. Read-only measurement.

Wraps (does not reimplement) ``_match_collision_group`` and ``_similarity_pair`` so every
invocation population, its candidate list, its similarity values, its sort key, its selected
links and its leftovers are recorded as production computes them.
"""

from __future__ import annotations

import json
import re
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import normalize_bill

_ORDINAL = re.compile(r"^(\d+)_")

real_similarity_pair = db._similarity_pair
real_collision_group = db._match_collision_group

TRACE: list[dict] = []
STATE = {"group": -1, "calls_in_group": 0, "both_sided_divs": 0, "ordinals": {}}


def ordinal_of(node):
    return STATE["ordinals"].get(id(node))


def wrapped_similarity_pair(old_nodes, new_nodes):
    seq = len(TRACE)
    STATE["calls_in_group"] += 1
    phase = "within_division" if STATE["calls_in_group"] <= STATE["both_sided_divs"] else "cross_division"

    rec = {
        "seq": seq,
        "group": STATE["group"],
        "phase": phase,
        "n_old": len(old_nodes),
        "n_new": len(new_nodes),
        "old_ordinals": [ordinal_of(o) for o in old_nodes],
        "new_ordinals": [ordinal_of(n) for n in new_nodes],
        "old_divs": [o.division_key for o in old_nodes],
        "new_divs": [n.division_key for n in new_nodes],
    }

    # Which early-return branch production takes.
    if not old_nodes and not new_nodes:
        rec["branch"] = "both_empty"
    elif not old_nodes:
        rec["branch"] = "old_empty"
    elif not new_nodes:
        rec["branch"] = "new_empty"
    elif len(old_nodes) == 1 and len(new_nodes) == 1:
        rec["branch"] = "shortcut_1x1"
    else:
        rec["branch"] = "greedy"

    result = real_similarity_pair(old_nodes, new_nodes)

    # Recompute the candidate list exactly as production does, for ordering analysis only.
    # This is measurement, never a substitute for the production call above.
    if rec["branch"] == "greedy":
        from deltatrack.similarity import text_similarity

        cands = []
        for oi, o in enumerate(old_nodes):
            o_norm = db._normalize_text(o.body_text)
            for ni, n in enumerate(new_nodes):
                n_norm = db._normalize_text(n.body_text)
                cands.append((text_similarity(o_norm, n_norm), oi, ni))
        rec["n_candidates"] = len(cands)
        sims = [c[0] for c in cands]
        rec["n_distinct_sims"] = len(set(sims))
        rec["has_sim_ties"] = len(set(sims)) != len(sims)

        def greedy(sorted_c):
            co, cn, sel = set(), set(), []
            for _s, oi, ni in sorted_c:
                if oi in co or ni in cn:
                    continue
                co.add(oi)
                cn.add(ni)
                sel.append((oi, ni))
            return sel

        legacy_sel = greedy(sorted(cands, reverse=True))
        rec["selected_local"] = legacy_sel

        # Counterfactual A: parser ordinal in place of local position.
        oord = rec["old_ordinals"]
        nord = rec["new_ordinals"]
        by_ord = sorted(cands, key=lambda c: (c[0], oord[c[1]], nord[c[2]]), reverse=True)
        rec["selected_by_ordinal"] = greedy(by_ord)
        rec["ordinal_changes_selection"] = set(map(tuple, rec["selected_by_ordinal"])) != set(
            map(tuple, legacy_sel)
        )

        # Counterfactual B: CandidateSet iteration order (ascending ordinal pair), no score.
        by_candset = sorted(cands, key=lambda c: (oord[c[1]], nord[c[2]]))
        rec["selected_by_candset_order"] = greedy(by_candset)
        rec["candset_order_changes_selection"] = set(map(tuple, rec["selected_by_candset_order"])) != set(
            map(tuple, legacy_sel)
        )

        # Is the local list already in ascending parser-ordinal order?
        rec["old_local_is_ordinal_sorted"] = oord == sorted(oord)
        rec["new_local_is_ordinal_sorted"] = nord == sorted(nord)
    else:
        rec["n_candidates"] = 0

    rec["out_matched"] = [
        (ordinal_of(o), ordinal_of(n)) for o, n in result if o is not None and n is not None
    ]
    rec["out_left_old"] = [ordinal_of(o) for o, n in result if o is not None and n is None]
    rec["out_left_new"] = [ordinal_of(n) for o, n in result if o is None and n is not None]

    TRACE.append(rec)
    return result


def wrapped_collision_group(old_nodes, new_nodes):
    STATE["group"] += 1
    STATE["calls_in_group"] = 0
    old_divs = {n.division_key for n in old_nodes}
    new_divs = {n.division_key for n in new_nodes}
    STATE["both_sided_divs"] = len(old_divs & new_divs)
    return real_collision_group(old_nodes, new_nodes)


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
    out = Path(argv[2]) if len(argv) > 2 else Path("round1_trace.json")

    db._similarity_pair = wrapped_similarity_pair
    db._match_collision_group = wrapped_collision_group

    all_pairs = []
    totals = defaultdict(int)
    per_pair = []

    for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for old_path, new_path in adjacent_pairs(bill_dir):
            try:
                old_tree = normalize_bill(old_path)
                new_tree = normalize_bill(new_path)
            except Exception as exc:
                print(f"SKIP {bill_dir.name} {old_path.stem}->{new_path.stem}: {exc}", file=sys.stderr)
                continue

            label = f"{bill_dir.name} {old_path.stem}->{new_path.stem}"
            STATE["ordinals"] = {}
            for i, n in enumerate(old_tree.nodes):
                STATE["ordinals"][id(n)] = i
            for i, n in enumerate(new_tree.nodes):
                STATE["ordinals"][id(n)] = i

            TRACE.clear()
            STATE["group"] = -1

            t0 = time.perf_counter()
            tracemalloc.start()
            pairs = db.match_nodes(old_tree, new_tree)
            _cur, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            elapsed = time.perf_counter() - t0

            # Full-flatten counterfactual: one CandidateSet over every match_path group.
            old_groups = defaultdict(list)
            new_groups = defaultdict(list)
            for n in old_tree.nodes:
                old_groups[n.match_path].append(n)
            for n in new_tree.nodes:
                new_groups[n.match_path].append(n)
            all_paths = dict.fromkeys(list(old_groups) + list(new_groups))
            flat_naive = 0  # every old x new inside each match_path group
            unique_1x1 = 0
            one_sided = 0
            collision_groups = 0
            for p in all_paths:
                o, n = old_groups.get(p, []), new_groups.get(p, [])
                if len(o) <= 1 and len(n) <= 1:
                    if o and n:
                        unique_1x1 += 1
                    else:
                        one_sided += 1
                    flat_naive += len(o) * len(n)
                else:
                    collision_groups += 1
                    flat_naive += len(o) * len(n)

            trace = [dict(r) for r in TRACE]
            scored = sum(r["n_candidates"] for r in trace)
            rec = {
                "label": label,
                "old_nodes": len(old_tree.nodes),
                "new_nodes": len(new_tree.nodes),
                "match_paths": len(all_paths),
                "unique_1x1": unique_1x1,
                "one_sided_unique": one_sided,
                "collision_groups": collision_groups,
                "pairs_emitted": len(pairs),
                "sp_calls": len(trace),
                "sp_within": sum(1 for r in trace if r["phase"] == "within_division"),
                "sp_cross": sum(1 for r in trace if r["phase"] == "cross_division"),
                "sp_shortcut_1x1": sum(1 for r in trace if r["branch"] == "shortcut_1x1"),
                "sp_one_side_empty": sum(1 for r in trace if r["branch"] in ("old_empty", "new_empty")),
                "sp_greedy": sum(1 for r in trace if r["branch"] == "greedy"),
                "scored_candidates": scored,
                "flat_naive_candidates": flat_naive,
                "largest_comparison": max([r["n_old"] * r["n_new"] for r in trace], default=0),
                "greedy_with_sim_ties": sum(1 for r in trace if r.get("has_sim_ties")),
                "greedy_ordinal_changes_selection": sum(
                    1 for r in trace if r.get("ordinal_changes_selection")
                ),
                "greedy_candset_order_changes_selection": sum(
                    1 for r in trace if r.get("candset_order_changes_selection")
                ),
                "cross_pop_old": sum(r["n_old"] for r in trace if r["phase"] == "cross_division"),
                "cross_pop_new": sum(r["n_new"] for r in trace if r["phase"] == "cross_division"),
                "cross_selected": sum(len(r["out_matched"]) for r in trace if r["phase"] == "cross_division"),
                "local_not_ordinal_sorted": sum(
                    1
                    for r in trace
                    if r["branch"] == "greedy"
                    and not (r["old_local_is_ordinal_sorted"] and r["new_local_is_ordinal_sorted"])
                ),
                "runtime_s": round(elapsed, 4),
                "peak_kb": round(peak / 1024, 1),
            }
            per_pair.append(rec)
            all_pairs.append({"label": label, "trace": trace})
            for k, v in rec.items():
                if isinstance(v, (int, float)) and k not in ("runtime_s", "peak_kb"):
                    totals[k] += v

    out.write_text(json.dumps({"per_pair": per_pair, "traces": all_pairs}, default=str))

    print(f"corpus pairs examined: {len(per_pair)}")
    print(f"trace written to {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print()
    keys = [
        "old_nodes", "new_nodes", "match_paths", "unique_1x1", "one_sided_unique",
        "collision_groups", "pairs_emitted", "sp_calls", "sp_within", "sp_cross",
        "sp_shortcut_1x1", "sp_one_side_empty", "sp_greedy", "scored_candidates",
        "flat_naive_candidates", "greedy_with_sim_ties",
        "greedy_ordinal_changes_selection", "greedy_candset_order_changes_selection",
        "cross_pop_old", "cross_pop_new", "cross_selected", "local_not_ordinal_sorted",
    ]
    for k in keys:
        print(f"{k:42s} {totals[k]}")
    print(f"{'largest_comparison (max)':42s} {max(r['largest_comparison'] for r in per_pair)}")
    print(f"{'total match_nodes runtime (s)':42s} {sum(r['runtime_s'] for r in per_pair):.3f}")
    print(f"{'peak traced mem, max over pairs (KB)':42s} {max(r['peak_kb'] for r in per_pair)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
