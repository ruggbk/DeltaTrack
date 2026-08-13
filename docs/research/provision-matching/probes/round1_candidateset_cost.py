"""Isolate CandidateSet cost from the grouping overhead it was measured alongside."""

from __future__ import annotations

import time
import tracemalloc

from deltatrack.matching import NEW, OLD, CandidateSet, ObservationRef, RetrieverInvocation

N = 14899
inv = RetrieverInvocation.of("path_division_group", round=1)

# Pre-build refs so we time propose() alone, then time ref construction separately.
t0 = time.perf_counter()
refs = [(ObservationRef(OLD, i), ObservationRef(NEW, i)) for i in range(N)]
ref_time = time.perf_counter() - t0

tracemalloc.start()
t0 = time.perf_counter()
cs = CandidateSet()
for o, n in refs:
    cs.propose(o, n, inv)
propose_time = time.perf_counter() - t0
_c, peak_propose = tracemalloc.get_traced_memory()

t0 = time.perf_counter()
cands = cs.candidates()
materialize_time = time.perf_counter() - t0
_c, peak_total = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"candidates: {N}")
print(f"  ObservationRef construction (2N)     : {ref_time * 1000:.1f} ms")
print(f"  CandidateSet.propose x N             : {propose_time * 1000:.1f} ms")
print(f"  CandidateSet.candidates() (sort+build): {materialize_time * 1000:.1f} ms")
print(f"  total                                 : {(ref_time + propose_time + materialize_time) * 1000:.1f} ms")
print(f"  peak traced memory after propose      : {peak_propose / 1024 / 1024:.1f} MB")
print(f"  peak traced memory after materialize  : {peak_total / 1024 / 1024:.1f} MB")
print(f"  bytes per candidate (materialized)    : ~{peak_total / N:.0f}")
print()
print(f"  produced {len(cands)} Candidate objects")
