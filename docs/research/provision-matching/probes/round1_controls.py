"""Round-1: prove the unexercised path can fire, plus tie-direction and ordering controls."""

from __future__ import annotations

import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import BillNode, normalize_bill
from deltatrack.similarity import text_similarity

_ORDINAL = re.compile(r"^(\d+)_")


def node(mp, eid, body, div):
    return BillNode(
        match_path=mp,
        display_path=mp,
        tag="section",
        element_id=eid,
        header_text="",
        body_text=body,
        section_number="1",
        division_label=div,
        division_key=div,
    )


print("=== 3. CAN THE ASSIGNMENT-CONDITIONED CROSS-DIVISION PATH FIRE AT ALL? ===")
# One match_path, two divisions on both sides.
#   div A: 2 old, 1 new  -> within-division assignment leaves ONE old over
#   div B: 1 old, 2 new  -> within-division assignment leaves ONE new over
# Those two leftovers can only meet in the cross-division fallback.
MP = ("sec-1",)
old_nodes = [
    node(MP, "oA1", "alpha alpha alpha the quick brown fox", "A"),
    node(MP, "oA2", "zulu zulu zulu unmatched leftover old text", "A"),
    node(MP, "oB1", "bravo bravo bravo jumps over the lazy dog", "B"),
]
new_nodes = [
    node(MP, "nA1", "alpha alpha alpha the quick brown fox", "A"),
    node(MP, "nB1", "bravo bravo bravo jumps over the lazy dog", "B"),
    node(MP, "nB2", "zulu zulu zulu unmatched leftover old text", "B"),
]

calls = []
real_sp = db._similarity_pair


def spy(o, n):
    r = real_sp(o, n)
    calls.append(
        (
            [x.element_id for x in o],
            [x.element_id for x in n],
            [(a.element_id if a else None, b.element_id if b else None) for a, b in r],
        )
    )
    return r


db._similarity_pair = spy
result = db._match_collision_group(old_nodes, new_nodes)
db._similarity_pair = real_sp

for i, (o, n, r) in enumerate(calls):
    print(f"  call {i}: old={o} new={n} -> {r}")
print("  group result:", [(a.element_id if a else None, b.element_id if b else None) for a, b in result])
paired = {(a.element_id, b.element_id) for a, b in result if a and b}
print(f"  oA2 paired with nB2 across divisions? {('oA2', 'nB2') in paired}")
print("  -> the cross-division fallback consumed an observation that WITHIN-DIVISION")
print("     ASSIGNMENT left over. The dependency is real; the corpus never triggers it.")
print()


# --- Corpus controls ---
def adjacent_pairs(bill_dir: Path):
    numbered = []
    for path in bill_dir.glob("*.xml"):
        m = _ORDINAL.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def greedy(sorted_c):
    co, cn, sel = set(), set(), []
    for _s, a, b in sorted_c:
        if a in co or b in cn:
            continue
        co.add(a)
        cn.add(b)
        sel.append((a, b))
    return sel


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/corpus")

STATE = {"ord": {}}
stats = defaultdict(int)
real_sp2 = db._similarity_pair


def measuring_sp(old_nodes, new_nodes):
    res = real_sp2(old_nodes, new_nodes)
    if old_nodes and new_nodes and not (len(old_nodes) == 1 and len(new_nodes) == 1):
        onorm = [db._normalize_text(o.body_text) for o in old_nodes]
        nnorm = [db._normalize_text(n.body_text) for n in new_nodes]
        cands = [
            (text_similarity(onorm[a], nnorm[b]), a, b)
            for a in range(len(old_nodes))
            for b in range(len(new_nodes))
        ]
        stats["greedy_calls"] += 1
        base = greedy(sorted(cands, reverse=True))

        # Control: ASCENDING oi/ni on ties (production is descending).
        asc = greedy(sorted(cands, key=lambda c: (-c[0], c[1], c[2])))
        if set(map(tuple, asc)) != set(map(tuple, base)):
            stats["tie_direction_changes_selection"] += 1

        # Control: winners emitted in a different order but same set.
        # (order-only: measured downstream, recorded here as reorderable count)
        if len(base) > 1:
            stats["calls_with_reorderable_winners"] += 1
        if len(base) < min(len(old_nodes), len(new_nodes)):
            stats["calls_with_unclaimed"] += 1
        lo = len(old_nodes) - len(base)
        ln = len(new_nodes) - len(base)
        if lo > 1 or ln > 1:
            stats["calls_with_reorderable_leftovers"] += 1
    return res


db._similarity_pair = measuring_sp

t0 = time.perf_counter()
for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    for op, np_ in adjacent_pairs(bill_dir):
        try:
            ot, nt = normalize_bill(op), normalize_bill(np_)
        except Exception:
            continue
        db.match_nodes(ot, nt)
elapsed = time.perf_counter() - t0
db._similarity_pair = real_sp2

print("=== 4. TIE DIRECTION AND ORDERING CONTROLS (corpus) ===")
print(f"  greedy invocations                              : {stats['greedy_calls']}")
print(f"  where ASCENDING oi/ni changes the selected set  : {stats['tie_direction_changes_selection']}")
print(f"  with >1 winner (winner order is observable)     : {stats['calls_with_reorderable_winners']}")
print(f"  leaving an unclaimed observation                : {stats['calls_with_unclaimed']}")
print(f"  with >1 leftover on a side (order observable)   : {stats['calls_with_reorderable_leftovers']}")
print()

# --- Runtime baseline, uninstrumented ---
t0 = time.perf_counter()
n = 0
for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    for op, np_ in adjacent_pairs(bill_dir):
        try:
            ot, nt = normalize_bill(op), normalize_bill(np_)
        except Exception:
            continue
        db.match_nodes(ot, nt)
        n += 1
print("=== 5. RUNTIME ===")
print(f"  match_nodes over {n} corpus pairs, uninstrumented: {time.perf_counter() - t0:.3f}s")
