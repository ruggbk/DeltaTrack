"""Comparison-scoped vs per-invocation CandidateSet, on the real round-1 retrieval populations.

Read-only. Corrects a scope error in the round-1 audit, which quoted a CORPUS-TOTAL candidate
count (14,899) and a corpus-total peak (8.8 MB) as if they described one comparison. They do
not: the largest single comparison holds far fewer, and a production peak is a per-comparison
quantity.

Both modes are fed the EXACT populations production forms, recovered by wrapping
``_similarity_pair`` while ``match_nodes`` runs -- so this compares two storage layouts over
one candidate population rather than two different populations.

    A. one CandidateSet per comparison, accumulating both round-1 retriever invocations
    B. one CandidateSet per invocation, released when that invocation's assignment is done

Usage:

    uv run python docs/research/provision-matching/probes/round1_candidate_scope.py tests/corpus
"""

from __future__ import annotations

import re
import sys
import time
import tracemalloc
from pathlib import Path

from deltatrack import diff_bill as db
from deltatrack.bill_tree import normalize_bill
from deltatrack.matching import NEW, OLD, CandidateSet, ObservationRef, RetrieverInvocation

_ORDINAL = re.compile(r"^(\d+)_")

#: Round 1 runs two retriever invocations. A per-division run is the SAME retriever over a
#: partition, not a new configuration, so the division key is deliberately not in the config --
#: putting it there would make every division its own invocation and inflate provenance.
WITHIN = RetrieverInvocation.of("path_division_group", round=1)
CROSS = RetrieverInvocation.of("path_group_cross_division", round=1)


def adjacent_pairs(bill_dir: Path):
    numbered = []
    for path in bill_dir.glob("*.xml"):
        m = _ORDINAL.match(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def real_populations(old_tree, new_tree) -> list[tuple[str, list, list]]:
    """Every ``_similarity_pair`` population production forms, in order, with its phase."""
    seen: list[tuple[str, list, list]] = []
    real_pair = db._similarity_pair
    real_group = db._match_collision_group
    state = {"both_sided": 0, "n": 0}

    def spy_pair(old_nodes, new_nodes):
        state["n"] += 1
        phase = "within" if state["n"] <= state["both_sided"] else "cross"
        seen.append((phase, list(old_nodes), list(new_nodes)))
        return real_pair(old_nodes, new_nodes)

    def spy_group(old_nodes, new_nodes):
        state["n"] = 0
        state["both_sided"] = len({n.division_key for n in old_nodes} & {n.division_key for n in new_nodes})
        return real_group(old_nodes, new_nodes)

    db._similarity_pair = spy_pair
    db._match_collision_group = spy_group
    try:
        db.match_nodes(old_tree, new_tree)
    finally:
        db._similarity_pair = real_pair
        db._match_collision_group = real_group
    return seen


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("tests/corpus")

    comparisons = []
    for bill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for old_path, new_path in adjacent_pairs(bill_dir):
            try:
                ot, nt = normalize_bill(old_path), normalize_bill(new_path)
            except Exception:
                continue
            label = f"{bill_dir.name} {old_path.stem}->{new_path.stem}"
            ordinals = {id(n): i for i, n in enumerate(ot.nodes)}
            ordinals.update({id(n): i for i, n in enumerate(nt.nodes)})
            comparisons.append((label, ordinals, real_populations(ot, nt)))

    print(f"comparisons: {len(comparisons)}")

    # --- A: comparison-scoped -------------------------------------------------------------
    a_total_time = 0.0
    a_worst_time = ("", 0.0)
    a_worst_mem = ("", 0)
    a_largest_live = ("", 0)
    a_total_candidates = 0
    duplicate_pairs_total = 0

    for label, ordinals, pops in comparisons:
        tracemalloc.start()
        t0 = time.perf_counter()
        cs = CandidateSet()
        for phase, old_nodes, new_nodes in pops:
            inv = WITHIN if phase == "within" else CROSS
            for o in old_nodes:
                for n in new_nodes:
                    cs.propose(ObservationRef(OLD, ordinals[id(o)]), ObservationRef(NEW, ordinals[id(n)]), inv)
        candidates = cs.candidates()
        elapsed = time.perf_counter() - t0
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        proposed = sum(len(o) * len(n) for _p, o, n in pops)
        duplicate_pairs_total += proposed - len(cs)
        a_total_candidates += len(candidates)
        a_total_time += elapsed
        if elapsed > a_worst_time[1]:
            a_worst_time = (label, elapsed)
        if peak > a_worst_mem[1]:
            a_worst_mem = (label, peak)
        if len(candidates) > a_largest_live[1]:
            a_largest_live = (label, len(candidates))

    # --- B: per-invocation ----------------------------------------------------------------
    b_total_time = 0.0
    b_worst_time = ("", 0.0)
    b_worst_mem = ("", 0)
    b_largest_live = ("", 0)
    b_total_candidates = 0

    for label, ordinals, pops in comparisons:
        tracemalloc.start()
        t0 = time.perf_counter()
        largest_here = 0
        made = 0
        for phase, old_nodes, new_nodes in pops:
            inv = WITHIN if phase == "within" else CROSS
            cs = CandidateSet()
            for o in old_nodes:
                for n in new_nodes:
                    cs.propose(ObservationRef(OLD, ordinals[id(o)]), ObservationRef(NEW, ordinals[id(n)]), inv)
            candidates = cs.candidates()
            made += len(candidates)
            largest_here = max(largest_here, len(candidates))
            del cs, candidates  # released before the next invocation, which is the whole point
        elapsed = time.perf_counter() - t0
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        b_total_candidates += made
        b_total_time += elapsed
        if elapsed > b_worst_time[1]:
            b_worst_time = (label, elapsed)
        if peak > b_worst_mem[1]:
            b_worst_mem = (label, peak)
        if largest_here > b_largest_live[1]:
            b_largest_live = (label, largest_here)

    def row(name, a, b):
        print(f"  {name:38s} {a:>26s}  {b:>26s}")

    print()
    print(f"  {'':38s} {'A: comparison-scoped':>26s}  {'B: per-invocation':>26s}")
    print("  " + "-" * 92)
    row("corpus-total build runtime", f"{a_total_time * 1000:.0f} ms", f"{b_total_time * 1000:.0f} ms")
    row(
        "worst single-comparison runtime",
        f"{a_worst_time[1] * 1000:.1f} ms",
        f"{b_worst_time[1] * 1000:.1f} ms",
    )
    row(
        "worst single-comparison peak mem",
        f"{a_worst_mem[1] / 1024 / 1024:.2f} MB",
        f"{b_worst_mem[1] / 1024 / 1024:.2f} MB",
    )
    row("largest LIVE candidate count", f"{a_largest_live[1]}", f"{b_largest_live[1]}")
    row("candidates materialised (corpus)", f"{a_total_candidates}", f"{b_total_candidates}")
    print()
    print(f"  worst-runtime comparison   A: {a_worst_time[0]}")
    print(f"  worst-memory comparison    A: {a_worst_mem[0]}")
    print(f"  largest live set           A: {a_largest_live[0]}")
    print()
    print("  duplicate pair/proposal semantics")
    print(f"    pairs proposed more than once across the two invocations: {duplicate_pairs_total}")
    print(
        "    A collapses each into ONE candidate carrying both proposals; B cannot see the "
        "duplication at all,\n    because the two proposals live in different sets."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
