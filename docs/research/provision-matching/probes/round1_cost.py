"""Cost of retiring the unique-path fast path, and CandidateSet materialization cost."""

from __future__ import annotations

import re
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import normalize_bill
from deltatrack.matching import NEW, OLD, CandidateSet, ObservationRef, RetrieverInvocation

_ORDINAL = re.compile(r"^(\d+)_")


def adjacent_pairs(bill_dir: Path):
    numbered = []
    for path in bill_dir.glob("*.xml"):
        m = _ORDINAL.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def match_nodes_no_fastpath(old, new):
    og, ng = defaultdict(list), defaultdict(list)
    for n in old.nodes:
        og[n.match_path].append(n)
    for n in new.nodes:
        ng[n.match_path].append(n)
    pairs = []
    for p in dict.fromkeys(list(og) + list(ng)):
        pairs.extend(db._match_collision_group(og.get(p, []), ng.get(p, [])))
    return pairs


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/corpus")
trees = []
for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    for op, np_ in adjacent_pairs(bill_dir):
        try:
            trees.append((normalize_bill(op), normalize_bill(np_)))
        except Exception:
            pass

print(f"corpus pairs: {len(trees)}")

t0 = time.perf_counter()
for ot, nt in trees:
    db.match_nodes(ot, nt)
prod = time.perf_counter() - t0

t0 = time.perf_counter()
for ot, nt in trees:
    match_nodes_no_fastpath(ot, nt)
nofast = time.perf_counter() - t0

print()
print("=== 6. COST OF RETIRING THE UNIQUE-PATH FAST PATH ===")
print(f"  production match_nodes             : {prod:.3f}s")
print(f"  every group via collision path     : {nofast:.3f}s")
print(f"  ratio                              : {nofast / prod:.2f}x")

# --- CandidateSet materialization cost for round-1 retrieval ---
print()
print("=== 7. CANDIDATE MATERIALIZATION COST ===")
inv_a = RetrieverInvocation.of("path_division_group", round=1)
inv_b = RetrieverInvocation.of("path_group_cross_division", round=1)

tracemalloc.start()
t0 = time.perf_counter()
total_cands = 0
biggest = 0
for ot, nt in trees:
    og, ng = defaultdict(list), defaultdict(list)
    for i, n in enumerate(ot.nodes):
        og[n.match_path].append((i, n))
    for i, n in enumerate(nt.nodes):
        ng[n.match_path].append((i, n))
    cs = CandidateSet()
    for p in dict.fromkeys(list(og) + list(ng)):
        o, n = og.get(p, []), ng.get(p, [])
        # round A: division-partitioned candidate formation
        obyd, nbyd = defaultdict(list), defaultdict(list)
        for i, x in o:
            obyd[x.division_key].append((i, x))
        for i, x in n:
            nbyd[x.division_key].append((i, x))
        for k in dict.fromkeys(list(obyd) + list(nbyd)):
            for i, _ in obyd.get(k, []):
                for j, _ in nbyd.get(k, []):
                    cs.propose(ObservationRef(OLD, i), ObservationRef(NEW, j), inv_a)
                    total_cands += 1
    biggest = max(biggest, len(cs))
elapsed = time.perf_counter() - t0
_cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"  round-A candidates materialized over corpus : {total_cands}")
print(f"  largest single-comparison CandidateSet      : {biggest}")
print(f"  build time over 27 pairs                    : {elapsed:.3f}s")
print(f"  peak traced memory                          : {peak / 1024 / 1024:.1f} MB")
print(f"  bytes per candidate (peak/largest set)      : ~{peak / max(biggest, 1):.0f}")
