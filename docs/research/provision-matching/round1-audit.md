# Round-One Matching Audit

**ADR 0020 · Phase 1 · retained measurements**

The measurements the round-1 separation was decided on, kept after the work closed. **Everything
still here earns its place under one of four tests** — it reproduces a consequential result, is a
frozen input, records a durable decision, or maps a retired artifact to the executable invariant
that inherited its question. The investigation itself (the pre-work source survey, the pipeline
walkthrough, the rule-by-rule stage map, the proposed signatures, the oracle design, the slice
plan and the resolved blockers) was working material and was removed at closure. Two different
pins, because they are two different artifacts: the **full pre-cut text of this document** is at
`542de8c^`, and the **eight retired probe files** are at `7fdbf62`. Git history holds the rest.

Read this for *why a number is what it is*. For the architecture, read
[ADR 0020](../../decisions/0020-matching-stages.md) and
[docs/architecture.md](../../architecture.md); the invariants are enforced by
`tests/test_round1_preservation.py`, not here. Section numbers are the originals, so the
surviving cross-references and any external citation still resolve.

| | |
|---|---|
| develop SHA | `0ff0eb1e016c0515b7e7251a635f7ecb3f1ecb3a` |
| #623 merge SHA | `0ff0eb1e` |
| Audit branch | `worktree-adr0020-round1-audit` |
| Worktree | clean, at `0ff0eb1e` |
| Corpus | 27 adjacent XML pairs (`tests/corpus`) |
| Tests | 186 passed, 1 skipped, rc=0 |

---

## The four conclusions this report turns on

1. **The coherent unit is the round, not the stage.** Round 1 is already two retrieval/assignment
   rounds. Extracting one whole-round-1 retrieval stage ahead of assignment is *not*
   behaviour-preserving: flattening the division and cross-division populations into one candidate
   set changes the selected links on 8 of 959 collision groups (+9 / −9 links). Extracting
   retrieval *per round* is safe.

2. **The unique-path fast path is not policy.** Deleting it and routing all 30,547 `match_path`
   groups through `_match_collision_group` produces a byte-identical pairing stream — same order,
   same objects — on 27 of 27 corpus pairs, including the 730 unique pairings whose two nodes sit
   in *different* divisions. It is an optimisation worth 1.62× on the matching stage, not a
   distinct assignment rule.

3. **The assignment-conditioned dependency is real in code and invisible to every corpus gate.**
   238 groups leave within-division assignment leftovers, 30 groups reach the cross-division
   fallback, and the two sets do not intersect. All 102 cross-division participants arrive from
   one-sided divisions — pure retrieval structure. A synthetic fixture is mandatory; no corpus
   gate can tell a correct implementation from one that never feeds assignment leftovers forward.

4. **No STOP condition fired.** Existing contracts express the behaviour with *one* new evidence
   signal. One vocabulary gap is flagged, not a policy conflict.

---

## 4. Assignment-conditioned retrieval

**Can the present behaviour be represented faithfully as retrieval A → evidence A → assignment A →
retrieval B over A's unmatched → evidence B → assignment B?** Yes. ADR 0020 explicitly permits
multi-round retrieval where a later round consults earlier matching state, and forbids only that
retrieval consume the correspondence evidence for the candidates it is emitting. Round 1b reads
which observations remain unclaimed. It never reads a similarity value. Invariant 4 holds.

No intermediate structure beyond the ordered leftover population is required. What *is* required
is that the leftover population keep its order, because that order defines round 1b's index
space — see §5.

### The dependency is real, and the corpus cannot see it

| Measurement over 27 corpus pairs | Value |
|---|---:|
| Collision groups | 959 |
| Groups where within-division assignment left leftovers | 238 |
| Leftover observations produced by assignment (old / new) | 119 / 119 |
| Groups that reached the cross-division fallback | 30 |
| **Groups in both sets** | **0** |
| Cross-division participants from a one-sided division (structural) | 102 |
| **Cross-division participants left over by assignment** | **0** |

> **False-green hazard, and the reason §9 exists.** On the committed corpus, round 1b's population
> is a pure function of retrieval structure. An implementation that fed *only* structurally
> unmatched observations into round 1b — silently dropping the assignment-leftover path — would be
> byte-identical on all 27 canonical digests, would pass every existing gate, and would be wrong.
> A gate that has never once observed the behaviour it protects cannot distinguish a correct
> implementation from a broken one.

### Proving the path can fire

Constructed against the real `_match_collision_group`: one `match_path`, division A holding
2 old / 1 new, division B holding 1 old / 2 new. Within-division assignment leaves one old over in
A and one new over in B; those two can only meet in the fallback.

```
call 0: old=['oA1','oA2'] new=['nA1'] -> [('oA1','nA1'), ('oA2', None)]
call 1: old=['oB1'] new=['nB1','nB2'] -> [('oB1','nB1'), (None,'nB2')]
call 2: old=['oA2'] new=['nB2']       -> [('oA2','nB2')]      <- cross-division

group result: [('oA1','nA1'), ('oB1','nB1'), ('oA2','nB2')]
```

The fallback consumed an observation that within-division *assignment* left over. The dependency
is not hypothetical; the corpus simply never presents the shape.

Reproduce: `tests/test_round1_preservation.py::test_assignment_leftovers_reach_the_cross_division_fallback`.
B0 promoted this construction from a probe into a standing synthetic fixture, and §9's
`no_assignment_leftovers` mutation is the control that proves it can go red. The probe it came
from (`probes/round1_controls.py`) was removed in B4 and is readable at `7fdbf62`.

### When is correspondence settled enough to condition a later round?

Never, in round 1 — and that is correct. A round-1a selection can still be revoked by
`apply_similarity_assignment_rule`, and `CorrespondenceSet` refuses to revise a settled
observation (already demonstrated by `probe_correspondence_revision.py`). So round 1b conditions
on a *provisional selection*, which the ADR's phrase "Correspondence settled by an earlier round"
does not literally cover. Reviewed 2026-08-12 and accepted as a wording gap rather than a policy
conflict: no ADR amendment is required, round 1b consumes the ordered unclaimed population, and
nothing creates settled `Correspondence` early. The prohibition ADR 0020 actually imposes is on
consuming correspondence *evidence*, and round 1b consumes none.

---

## 5. CandidateSet and ordering

`CandidateSet.candidates()` canonicalises by `(old.ordinal, new.ordinal)`. `_similarity_pair`
sorts by `(similarity, oi, ni)` descending over *local list positions*. These are three distinct
index spaces — parser ordinals, round-1a division-local positions, and round-1b
concatenation-local positions — and the report's task was to find out which differences matter.

| Ordering question | Invocations affected | Verdict |
|---|---:|---|
| Substitute parser ordinals for local `(oi, ni)` | 0 / 329 | **no change** — but the agreement is structural for round 1a and *contingent* for round 1b |
| Use `CandidateSet` iteration order as assignment order | 174 / 329 | **changes selection** — assignment must impose its own order |
| Flip the tiebreak to ascending `(oi, ni)` | 97 / 329 | **changes selection** — descending is policy |
| Greedy invocations containing a similarity tie | 157 / 329 | the tiebreak is exercised, not decorative |

### Why local positions and ordinals agree, and why that is not licence to swap them

Every list handed to `_similarity_pair` is currently in ascending parser-ordinal order — 892 of
892 within-division invocations and 30 of 30 cross-division ones. Where that holds, the two sort
keys are order-isomorphic and induce identical sorts, which is why the substitution changes
nothing. This is the opposite of round 2, where #590 measured that substituting ordinals for
`(ri, ai)` moves the selected set on 3 corpus pairs.

For round 1a the monotonicity is **structural**: division sublists are filtered out of a
parser-ordered list, so they cannot be out of order. For round 1b it is **contingent**. The
cross-division list is a concatenation across divisions in first-appearance order, and divisions
that interleave in parser order break it. Constructed and confirmed:

```
old parser order:  X1(0), Y1(1), X2(2)     divisions X, Y, X
  division X: 2 old / 1 new -> assignment leaves X2 (ordinal 2)
  division Y: 1 old / 0 new -> structurally unmatched, Y1 (ordinal 1)

cross-division OLD list ordinals: [2, 1]
ascending parser-ordinal order?   False
```

Reproduce: `tests/test_round1_preservation.py::test_the_fallback_population_is_not_in_parser_ordinal_order`,
the interleaved fixture B0 built from this construction, and the only thing that can see §9's
`ordinal_tiebreak` mutation — which moves 0 of 27 corpus pairs. `retrieve_cross_division_population`'s
docstring cites it for exactly that reason. The probe (`probes/round1_ordering_hazard.py`) was
removed in B4 and is readable at `7fdbf62`.

> **The trap.** A Phase-1 implementation that replaced local positions with `ObservationRef`
> ordinals "because the address exists" would be green on the whole corpus and wrong on the first
> bill whose divisions interleave inside one `match_path` group. The 0/329 figure is a measurement
> of this corpus, not a licence.

### Answers

- **Can assignment consume a CandidateSet without depending on its iteration order?** Yes, and it
  must — 174/329 says so. It reads the candidate set as a *population* and imposes
  `(evidence, local position)` itself, exactly as `_greedy_move_links` builds `ri_of`/`ai_of` from
  the population and sorts on them.
- **Must a legacy local-position key be reconstructed?** Yes. It is cheap (one enumerate per
  invocation) and it is the only form that is correct for both rounds.
- **Is that key assignment policy, retrieval provenance, or preservation machinery?** The
  *direction* (descending) is assignment policy — flipping it moves 97 invocations. The *index
  space* is preservation-only machinery. It should be built inside the assigner and never cross a
  stage boundary, following the precedent already set for `(ri, ai)`.
- **Does materialising candidates change downstream pairing-stream order?** No, provided emission
  order is reconstructed separately. Emission order is a function of group iteration and the
  four-phase append pattern, not of the candidate set — and it is not recoverable from ordinals,
  which `scripts/probe_ordinal_loss.py` is the standing evidence for.

---

## 9. Negative controls

For each proposed gate: the mutation that must make it red. Controls already decisive under
Slice A or #612 are not duplicated. Every mutation below has been *measured* against the current
source, so none is a guess about what would happen.

**Built and run in B0.** The table below is no longer a proposal: each mutation is implemented as
a variant of the oracle in `tests/test_round1_preservation.py` and was run against the frozen
expectation. The counts are what each one actually reddened.

| Mutation (oracle variant) | Corpus pairs red | Synthetic fixtures red |
|---|---:|---|
| `flatten_divisions` — drop the division partition *(also covers "drop division provenance")* | 18 / 27 | both |
| `ascending_tie` — reverse the tie direction | 11 / 27 | interleaved |
| `candidate_set_order` — use `CandidateSet` iteration order as assignment order | 11 / 27 | — |
| `shortcut_computes_similarity` — 1×1 shortcut computes a ratio | 8 / 27 | assignment-leftover |
| `reorder_winners` — same selected set, different emission order | 7 / 27 | — |
| `unique_path_needs_same_division` — change unique-path direct selection | 5 / 27 | — |
| `extra_cross_candidate` — admit a pair the fallback never considers | 5 / 27 | both |
| `reorder_leftovers` — same counts, different order | 4 / 27 | — |
| **`ordinal_tiebreak`** — parser ordinal instead of local `oi`/`ni` | **0 / 27** | **interleaved only** |
| **`no_assignment_leftovers`** — fallback sees only structurally-unmatched observations | **0 / 27** | **both** |

Two further controls are structural rather than mutational:

| Control | What it proves |
|---|---|
| `test_the_independence_guard_can_fire` | A deliberately delegating oracle is caught by the AST guard, so the guard is not an assertion of absence that passes vacuously. |
| `test_the_injection_harness_alone_changes_nothing` | An **unmutated** injection of the oracle into production reproduces all 27 frozen streams — so a red result below is the mutation biting, not the oracle having drifted from production. |
| `test_the_durable_gate_reddens_on_a_fault_injected_into_PRODUCTION` | The fault put inside the function `match_nodes` actually calls turns the durable production gate red. Every other control mutates the oracle; this one mutates production. |

**Two controls are corpus-invisible, exactly as predicted.** `ordinal_tiebreak` and
`no_assignment_leftovers` move **zero** of 27 committed pairs and are caught only by the synthetic
fixtures. `test_the_corpus_cannot_see_the_two_fixture_bound_mutations` pins that as a standing
claim, so if the corpus ever grows a case that exercises either, the gate goes red and the
finding is revisited rather than silently outdated.

> **A weak fixture was caught by its own control.** The first interleaved fixture made local
> position and parser ordinal disagree but gave its two fallback candidates *different*
> similarities, so the tiebreak never fired and `ordinal_tiebreak` changed nothing. The fixture
> now forces a tie, which is what makes the substitution observable. Recorded because it is the
> exact failure mode the negative controls exist to find, and it was found in the harness rather
> than in production.

---

## 10. Measured facts

All figures from `tests/corpus`, 27 adjacent XML version pairs, at `0ff0eb1e`. Re-measured after
#623 rather than carried forward.

### Population and structure

| Quantity | Value |
|---|---:|
| Observations (old / new), summed across pairs | 15,914 / 31,028 |
| `match_path` groups | 30,547 |
| — unique 1×1 (fast path) | 14,001 |
| — one-sided unique (fast path) | 15,587 |
| — collision groups | 959 |
| Pairings emitted | 31,908 |
| Collision groups making no `_similarity_pair` call at all | 378 / 959 |
| Unique 1×1 paths whose nodes sit in different divisions | 730 / 14,001 |

### `_similarity_pair` invocations

| Branch | Count | Note |
|---|---:|---|
| Total invocations | 922 | 892 within-division, 30 cross-division |
| 1×1 shortcut | 593 | no similarity computed |
| One side empty | 0 | unreachable from `_match_collision_group` |
| Greedy | 329 | 1,108 `text_similarity` calls in total |
| Largest single comparison | 49 | 7 × 7 |
| Cross-division: participants / links selected | 102 / 31 | 29 of 30 span more than one division |

### Candidate materialisation, runtime and memory

> **Corrected 2026-08-12, after B0.** The first version of this section quoted 14,899
> candidates and an 8.8 MB peak as though they described one comparison, and recommended
> per-invocation storage on that basis. Both halves were wrong, and the corrected measurement
> reverses the recommendation. See "What the first measurement got wrong" below.

Measured over the **exact populations production forms**, recovered by wrapping
`_similarity_pair` while `match_nodes` runs, by
`probes/round1_candidate_scope.py`. A = one `CandidateSet` per comparison accumulating both
round-1 retriever invocations; B = one per invocation, released after its assignment.

| Measurement | A: comparison-scoped | B: per-invocation |
|---|---:|---:|
| Corpus-total build runtime | **30 ms** | 42 ms |
| Worst single-comparison runtime | **6.3 ms** | 8.8 ms |
| Worst single-comparison peak memory | 0.23 MB | **0.03 MB** |
| Largest **live** candidate count | 350 | **49** |
| Candidates materialised (corpus total) | 1,701 | 1,701 |
| Pairs proposed by more than one invocation | 0 | 0 (cannot observe) |

| Other measurements | Value |
|---|---:|
| Candidates scored today vs. a per-group flatten | 1,108 vs 2,750 |
| Division subgrouping prunes | 1,852 pairs |
| **`match_nodes` over 27 pairs, pre-parsed trees** | **505 ms** |
| Peak traced memory inside `match_nodes`, worst pair | 1.5 MB |
| Retiring the unique-path fast path | 505 → 816 ms (1.62×) |

#### What the first measurement got wrong

Two independent errors compounded, and they pointed the same way:

- **Scope.** 14,899 and 8.8 MB are corpus totals across 27 comparisons. A production peak is a
  per-comparison quantity, and the largest live candidate count is **350**, not 14,899.
- **Population.** 14,899 counted a candidate for every `match_path` group *including the 29,588
  that take the unique-path fast path and never form a retrieval invocation at all*. It is a
  real number for a different question — what retrieval would cost if the fast path were
  retired — and it is not what round-1 retrieval materialises. That figure is **1,701**
  (593 sole-candidate + 1,108 scored), which is 11× smaller.

The corrected comparison shows **A is cheaper in runtime** (one `CandidateSet` per comparison
instead of 922) and both are negligible in memory at 0.23 MB against a 1.5 MB matching stage.
The original argument — that comparison-scoped storage costs 2.1× the matching stage — does not
survive measurement, and the recommendation it produced is withdrawn. Storage scope was left open
here; see §13, where B2 closed it.

> **Both candidate figures in this section are pre-B3, and the smaller one has since moved.**
> 1,701 (593 sole-candidate + 1,108 scored) is what round-1 retrieval materialised while the
> unique path still paired by tuple construction. B3 brought that path under the same stages, so
> round-1 retrieval now also materialises the 14,001 unique pairings — which is the whole reason
> the set had not been comparison-wide candidate recall. The correction this section makes to
> 14,899 stands unchanged: that figure counted every `match_path` group including one-sided ones,
> which form no candidate under B3 either.

---

## 11. Tooling impact

| Script | Status | Action |
|---|---|---|
| `probe_matching_stages.py` | valid | Reproduces ADR 0020's Context figures. Untouched by this work. |
| `probe_ordinal_loss.py` | valid | Keep; it is the evidence that emission order is not ordinal-derivable. |
| `probe_node_identity.py` | valid | Already re-aimed at `apply_similarity_assignment_rule` by #623. |
| `probe_correspondence_revision.py` | valid | Supplies §4's settlement constraint. Keep. |
| `probe_round2_migration.py` | valid | Round 2. Its pinned figures are unaffected. |
| `probe_canonical_sensitivity.py` | **re-aim** | Proves the canonical gate can redden on a *round-2* correspondence change. Round 1 needs the equivalent, and §9 shows three round-1 mutations it can never catch. Extend rather than trust. |
| `probe_slice2.py`, `probe_splits.py`, `probe_provenance.py` | valid | Scoped to round 2 / population sizing. No change. |
| `audit_source_signals.py` | **re-aim** | Calls `match_nodes` for its `@id`-lift comparison. Will still run, but its baseline becomes ambiguous once round 1 is staged; point it at the assignment output explicitly. |
| `compare_selected.py`, `probe_move_assignment.py` | already deleted | Removed by #623. No action. |
| Audit probes written for this report | **promote** | Seven probes covering invocation tracing, the flatten counterfactual, the fast-path equivalence, tie-direction controls and materialisation cost. They are the preservation oracle in draft form and should be promoted into tests by Slice B0 rather than rewritten. |

**Retired in B4, and where each question went.** §11 above ruled that these drafts should be
*promoted* into tests by B0 rather than maintained, and B0–B3 did exactly that. Seven of them had
also stopped running: six wrapped `db._similarity_pair`, which B2 removed, and `round1_cost.py`
called `_match_collision_group` with its pre-B1 two-argument signature. Porting them would have
produced a second, ungated answer to a question a test already answers — and not the audit's
answer either, since every figure here is scoped to the fused matcher at `0ff0eb1e`. So they were
removed.

An eighth, `round1_candidateset_cost.py`, was retired for the opposite reason: it still ran. It
hard-coded `N = 14899` and reported that as its candidate population, which is precisely the
figure §10 disowns — so B4's execution gate would have certified that the probe *runs* while it
published a quantity nobody should read as the round-1 candidate population. **Running is not the
same as informative**, and an execution badge on a stale number is a false green of its own. Its
question — what candidate storage scope costs — is closed: B2 shipped comparison-scoped, and §13
records that the semantic argument decided it while the cost difference did not. A synthetic
benchmark maintained for a settled implementation choice adds no closure value.

All eight are readable at `7fdbf62`.

| Retired probe | What it measured | The executable invariant that owns it now |
|---|---|---|
| `round1_trace.py` | Full per-invocation trace: populations, candidates, similarity values, sort keys, selections, leftovers, plus ordinal and CandidateSet-order counterfactuals | `tests/data/round1_legacy_trace.json` + `test_the_oracle_reproduces_the_frozen_trace`. B0's oracle records the same rows with ADR 0019 provenance, and the two counterfactuals are its `ordinal_tiebreak` / `candidate_set_order` variants (§9) rather than printed counts |
| `round1_counterfactuals.py` | Flatten counterfactual, cross-division provenance, list-order monotonicity | §9's `flatten_divisions` mutation (18/27 red); `test_assignment_leftovers_reach_the_cross_division_fallback`; `test_the_fallback_population_is_not_in_parser_ordinal_order` |
| `round1_decisive.py` | Fast-path redundancy (27/27) and the assignment-conditioned exercise question | `round1_b3_cost.py` carries the equivalence claim forward and asserts it on every arm before reporting a ratio, and the probe gate runs it. B3 also made the question moot by migrating the path (§13), so nothing selects a pairing outside an assignment — `test_no_round_1_pairing_reaches_the_stream_without_an_assignment_selecting_it`. Corpus blindness is pinned by `test_the_corpus_cannot_see_the_two_fixture_bound_mutations` |
| `round1_controls.py` | Synthetic fallback fixture, tie-direction control, ordering controls | `test_assignment_leftovers_reach_the_cross_division_fallback`; `test_assignment_breaks_ties_on_invocation_local_position`; §9's `ascending_tie` (11/27 red) |
| `round1_ordering_hazard.py` | Constructs the case where local-position/ordinal agreement breaks | `test_the_fallback_population_is_not_in_parser_ordinal_order`, the one gate §9's `ordinal_tiebreak` can redden |
| `round1_cost.py` | Fast-path removal cost. Its candidate count is the FAST-PATH-RETIRED population (14,899), not what round-1 retrieval forms — see §10 | `round1_b3_cost.py`, which measures the same arm (`collision_routing`) with every arm in one process — the methodology this one lacked |
| `round1_candidate_scope.py` | Comparison-scoped vs per-invocation storage, on the exact populations production forms | Settled in B2 and shipped comparison-scoped. The argument that decided it was semantic, not cost (§13): only comparison-scoped storage can hold one candidate carrying two invocations' proposals, and that is owned by `test_two_invocations_proposing_one_pair_keep_both_provenances`, `test_one_pair_yields_one_candidate` and `test_duplicate_proposals_add_no_multiplicity_and_no_weight`. That the shipped set materialises exactly what retrieval considered is `test_the_candidate_set_materialises_exactly_what_retrieval_considered` |
| `round1_candidateset_cost.py` | Isolated `CandidateSet` propose/materialise micro-benchmark, at the candidate count §10 corrects | The same durable owners as the row above. There is no cost question left to ask: the storage decision is settled and executably owned, and this probe's only remaining output was a synthetic timing over a population the audit disowns |

**One runnable round-1 probe remains**, at `docs/research/provision-matching/probes/`, executed by
`tests/test_research_probes.py` on every run so it cannot rot the way the others did:

| Probe | What it measures |
|---|---|
| `round1_b3_cost.py` | The four arms B3 sits between, in one process. §13 carries its ratios |

Adding a ninth is a decision, not a convenience: the manifest in `tests/test_research_probes.py`
is closed against what is on disk, so a new probe is either executed by the gate or the gate
fails. The bar is a **still-live research question** — a probe for a settled decision is what was
just removed.

---

## 13. Deferred decisions

Two need your ruling. Neither blocks B0, so the first slice can start regardless.

### 1. Keep or retire the unique-path fast path

In plain terms: `match_nodes` has a shortcut for the easy case — one old section, one new section,
same path — that pairs them immediately instead of going through the general machinery. The
measurement says the shortcut and the general machinery always agree, so the shortcut is buying
speed, not correctness.

- **Keep it** — 1.62× faster on the matching stage, at the cost of two code paths and a test that
  must pin their equivalence forever.
- **Retire it** — one code path, ~311 ms slower across the whole corpus (about 11 ms per bill
  comparison), and the equivalence test becomes unnecessary because there is nothing to diverge.

**Recommendation: keep it, and pin the equivalence in B0.** The preservation-first reading wins
here — retiring it is a real behaviour-adjacent change bundled into a refactor whose whole premise
is changing nothing, and 1.62× on the stage that ADR 0020 already flags for performance work
(#356, #169) is not free. Revisit in B3 if maintaining both paths complicates the assignment
contract.

**Resolved in B3, and neither way round.** The fast path was neither kept nor retired: the unique
group is now retrieved, proposed, described and assigned like any other, but by its own one-round
orchestration (`_match_unique_path_group`) rather than through `_match_collision_group`. Keeping
it would have left 14,001 of the corpus's pairings outside every ADR 0020 boundary — the reason
the candidate set was not comparison-wide recall. Retiring it into the collision path would have
paid for a division partition and a fallback round that a group of at most one observation per
side can never use.

The cost is real and is not what this section anticipated. Re-measured with every arm in one
process (`probes/round1_b3_cost.py`), against the pre-B3 traversal:

| arm | ratio |
|---|---|
| B3, as shipped | 2.37× |
| routing every unique group through `_match_collision_group` | 2.96× |

So B3 keeps about a fifth of the headroom, not most of it. The 1.62× above is a **pre-B1**
measurement and no longer describes the alternative: B1 and B2 gave the collision path a candidate
set, evidence records and a `GroupAssignment`, so the option this section priced got more
expensive while it was being deferred.

> **The ratios are the durable result; the absolute microsecond figures are not portable.**
> `2.37×` is the reported figure. Per-stage attribution over the 14,001 paired unique groups
> showed the cost spread roughly evenly across retrieval, propose, evidence and assignment rather
> than sitting in one hot spot, and **that shape** is the finding.
>
> B4 re-ran the probe unchanged, twice, and the two kinds of number behave differently. The
> absolute totals moved a long way — about 9.7 µs/group against the ~16 µs/group B3 recorded, on a
> different machine state. The ratio moved a little: `2.37×` then `2.30×`, with the rejected
> alternative at `2.93×` then `2.84×`. So the ratio is stable to a few percent rather than exact,
> and what is genuinely invariant is the ordering and the gap — B3 sits between the pre-B3
> traversal and collision-routing, keeping about a fifth of the headroom, on every run.
>
> Quote `2.37×` with that tolerance in mind. Do not cite an absolute µs figure on its own, and do
> not read a few percent of movement in either as a regression: it takes a re-run of all four arms
> in one process to say anything at all, which is what the probe exists to make easy.

Two candidates for recovering some of it, both out of B3's scope because they change
`matching.py`: an admission predicate that does not materialise a `Candidate` the caller discards,
and skipping canonicalisation for 0- and 1-element inputs. Neither is to be taken unless later
end-to-end profiling shows it matters.

The optimisation property that *was* preserved is the one #623 measured: the unique path still
computes **zero** similarities, and the frozen call count is unchanged.

### 2. Candidate storage scope — deferred into B1, and settled there

The earlier recommendation here (per-invocation sets, on a claimed 2.1× cost) is **withdrawn**:
it rested on a corpus-total figure misread as a per-comparison one, over a population 11× larger
than round-1 retrieval actually forms. §10 carries the corrected measurement.

What the corrected data says, on the real populations:

- Comparison-scoped is **faster** (30 ms vs 42 ms corpus-total; 6.3 ms vs 8.8 ms worst
  comparison), because it builds 27 `CandidateSet` objects instead of 922.
- Memory separates them but neither is material: 0.23 MB vs 0.03 MB worst-comparison peak,
  against a matching stage that already peaks at 1.5 MB.
- Largest live candidate count is 350 vs 49.
- **Semantics differ where cost does not.** The checked-in contract says a candidate exists once
  per observation pair, carrying every invocation's proposal. Only comparison-scoped storage can
  express that: per-invocation sets put two proposals for one pair in different objects, where
  nothing can merge them. On this corpus 0 pairs are proposed twice, so the difference is
  currently latent — which is an argument for keeping the capability, not for discarding it, and
  the same shape as the two corpus-invisible behaviours in §4.

**Recommendation, and it is a lean rather than a ruling: comparison-scoped.** It is cheaper, it
is what the contract describes, and it keeps candidate recall inspectable without a second
code path. The cost that would argue against it does not exist at this scale.

**Left open here on purpose.** The architectural requirement was fixed even though the container
was not: *one observation pair is one candidate carrying all applicable proposal provenance, and
assignment still receives the exact ordered per-invocation populations it needs to rebuild legacy
local positions.* Those are compatible — the ordered populations travel beside the candidate set,
not inside it — but which object owns which was a slice decision, to be made against real code
rather than pre-committed here. It shipped as `RetrievedPopulation` beside a comparison-scoped
`CandidateSet`.

**Settled in B2: comparison-scoped, on the semantic argument rather than the cost one.** One
`CandidateSet` per comparison accumulates all three round-1 retriever invocations, and
`RetrievedPopulation` stays the invocation-local ordering authority beside it. The lean above was
followed, but the reason that survived review is the third bullet, not the first two: only
comparison-scoped storage can express one candidate carrying two invocations' proposals, and
`test_two_invocations_proposing_one_pair_keep_both_provenances` is where that now lives. The cost
difference is not what decided it and should not be cited as though it were. A first attempt made
the set a cross-check beside the selection path instead of the admission authority on it, and was
rejected: that shape lets "retrieval did not admit this pair" and "assignment selected it" hold at
once, which is the state the intermediate value exists to make unreachable.

### Not deferred — settled by measurement

- Unique-path representation: **Option A** (retrieval emits one candidate, evidence records
  `sole_candidate`, assignment selects it deterministically). Option B, a separate structural
  assignment path, is not required — the collision path already reproduces the fast path exactly,
  so there is no second policy to model.
- One assignment implementation for both rounds: **yes**, provided the index space is rebuilt per
  invocation.
- Whether to flatten: **no**, measured non-preserving.

---

## Scope and provenance

Audit measured at `0ff0eb1e` over `tests/corpus` (27 adjacent XML pairs). B0 built and re-measured
on `2416425`, whose `src/` and `tests/` are byte-identical to `0ff0eb1e` — the only commits between
them are PR #622's PDF external-validity docs and probes, so the matching baseline the audit names
is unchanged. Audit branch `worktree-adr0020-round1-audit`. No production source has been modified.

**Carry this caveat into the slices:** every corpus figure is scoped to the 27 committed XML
pairs. The two behaviours in §4 and §5 are invisible there by construction, so the synthetic
fixtures are not belt-and-braces — they are the only evidence available for those paths.

**One correction stands against this report's own first draft** (§10): a corpus-total candidate
count and peak were quoted as per-comparison, over a population 11× larger than round-1 retrieval
forms. The storage recommendation built on it is withdrawn and the scope decision is deferred into
B1. Treat any *other* aggregate in §10 as corpus-total unless it says otherwise.
