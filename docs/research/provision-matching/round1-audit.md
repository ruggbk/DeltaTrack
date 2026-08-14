# Round-One Matching Audit

**ADR 0020 · Phase 1 · Investigation report**

What is left fused in `match_nodes` after PR #623, which ADR 0020 stage each rule belongs to,
and the smallest sequence of changes that separates them without moving a single canonical byte.

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

## 1. Verified source state

PR #623 was still in the merge queue when this investigation began; it merged at 19:36:40Z on
2026-08-12. Every measurement below was re-run against the post-merge commit and reproduced
identically, so the numbers belong to `0ff0eb1e` and not to the branch point.

| Item | Value |
|---|---|
| `origin/develop` head | `0ff0eb1e016c0515b7e7251a635f7ecb3f1ecb3a` — 2026-08-12 19:31:07 +0000 |
| #623 final merge commit | `0ff0eb1e` (the merge itself). Carries `6e2964f`, `c317abb`, `8ace371`. |
| Worktree | `.claude/worktrees/adr0020-round1-audit`, branch `worktree-adr0020-round1-audit`, hard-reset to `0ff0eb1e`, clean |
| Test state at this SHA | 186 passed, 1 skipped (`UPDATE_BASELINE` mode), rc=0 — canonical baseline, assignment/classification boundary, matching contracts, diff_bill |
| Canonical gate | 27 SHA-256 digests in `tests/data/canonical_baseline.json` |

### What #623 changed, and what it did not

#623 touched 9 files. In `src/deltatrack/diff_bill.py` the diff is confined to the
similarity-revocation region, which it replaced with a named evidence stage and an assignment
owner. **It did not touch `match_nodes`, `_match_collision_group` or `_similarity_pair`.** Those
three are byte-identical to their pre-#623 form, which is why the pre-merge measurements
reproduced exactly.

| Function | Line | Role after #623 |
|---|---:|---|
| `_similarity_pair` | 202 | **fused** — greedy claim, untouched by #623 |
| `_match_collision_group` | 249 | **fused** — division subgrouping + cross fallback, untouched |
| `match_nodes` | 340 | **fused** — path grouping + unique-path selection, untouched |
| `_similarity_signals` | 617 | new in #623 — the two signals, computed conditionally |
| `similarity_correspondence_evidence` | 646 | new — EVIDENCE for every 1:1 pairing |
| `_evidence_by_link` | 682 | new — addresses evidence by `ObservationRef` pair, never by position |
| `_similarity_rule_keeps` | 706 | new — ASSIGNMENT, owns the threshold |
| `apply_similarity_assignment_rule` | 745 | new — replaces `apply_similarity_revocation` |
| `_greedy_move_links` | 891 | round 2 — the pattern round 1 should copy |
| `settle_correspondences` | 951 | now takes keyword-only `round1_evidence` |

### Three precedents #623 sets that this work should reuse rather than re-litigate

- **A round-1 similarity ratio is natively evidence**, not a promoted retrieval score — "the ratio
  is computed for the express purpose of deciding the pairing". `WORD_OVERLAP` is now shared by
  both rounds because it is one quantity by one measure.
- **An uncomputed signal is absent, not `None`.** `Scalar` admits `None`, so omitting the name is
  what keeps "not computed" distinguishable from "computed as null" through `.names`. The
  conditional shape is preserved deliberately: computing unconditionally would skip nothing on
  13,866 of 15,034 path-matched pairings and cost a measured +21% on `diff_bills`.
- **The stage triple has a shape**: `X_correspondence_evidence(pairs, registry)` →
  `_X_rule_keeps(evidence, threshold)` → `apply_X_assignment_rule(pairs, evidence, registry, *, threshold)`,
  with the legacy ordering key held privately inside the assigner. Round 1 should be written
  against this shape, not a new one.

---

## 2. Current pipeline

Round 1 is not one retrieval followed by one assignment. It is a structural grouping, then *two*
retrieval/assignment rounds nested inside each collision group, then a single revocation rule
applied across the whole stream. The nesting is what the separation has to reproduce.

```
ROUND 1a — inside each match_path collision group
  RETRIEVAL    division_key subgroups; old x new within each
       |
  EVIDENCE     text_similarity per pair, skipped entirely on 1x1
       |
  ASSIGNMENT   greedy on (sim, oi, ni) descending, exclusive both sides

ROUND 1b — cross-division fallback, same group
  RETRIEVAL    leftovers from 1a  U  one-sided divisions
               gated on both sides non-empty
       |       ^-- population depends on round 1a's SELECTIONS
       |           (the dependency this report is about)
  EVIDENCE     text_similarity, recomputed
       |
  ASSIGNMENT   same greedy, NEW local index space

ACROSS THE WHOLE STREAM — migrated by #623
  EVIDENCE     similarity_correspondence_evidence: body_unchanged + word_overlap
       |
  ASSIGNMENT   apply_similarity_assignment_rule — may revoke a 1a or 1b selection
       |
  PRESERVATION emission order: group order, then
               matched-within / matched-cross / left-old / left-new
```

> **Ordering consequence.** The revocation in the third band applies to selections made in the
> first two. So a round-1a selection is *provisional* at the moment round 1b consults it — it is
> not settled `Correspondence`, and `CorrespondenceSet` has no operation that could later revise
> it. Nothing settles until `settle_correspondences`, after round 2. §14 treats this as a
> vocabulary gap rather than a policy conflict.

---

## 3. Rule-by-rule classification

Every branch and rule inside the three functions, classified by what it *does* rather than where
it sits. The test applied throughout: does this rule exclude a pairing from consideration
(retrieval), describe a pairing without deciding (evidence), or declare that two observations
correspond (assignment)?

| # | Rule | Stage | Why this stage, not where it lives |
|---:|---|---|---|
| 1 | `match_path` grouping | RETRIEVAL | It decides what can *ever* be compared: a node whose counterpart sits at another path is never scored because no pair is formed. It never declares correspondence — a 1-old/1-new group still needs something to select it. This is the ADR's own example of implicit retrieval. |
| 2 | Unique-path 1×1 direct pairing | ASSIGNMENT + preservation | Selecting the pair *is* a correspondence declaration, unthresholded and unconditional (invariant 6). But the *fast path* carrying it is measured redundant: routing these groups through `_match_collision_group` gives an identical stream on 27/27 pairs, including all 730 whose nodes are in different divisions. So the decision is assignment; the shortcut is preservation-only machinery worth 1.62×. |
| 3 | One-sided unique-path output | PRESERVATION | Not a settled 1:0 or 0:1 and must not become one — round 2 may still pair the observation elsewhere. Current code is already correct here: nothing settles before `settle_correspondences`. Its only roles are stream position and membership in the next round's retrieval population. |
| 4 | `division_key` subgrouping | RETRIEVAL | Pure structural bounding of consideration. It removes 1,852 pairs from the population that path grouping admitted and says nothing about whether the survivors correspond. Textbook retrieval policy under the ADR's "may bound" clause. |
| 5 | Within-division candidate formation | RETRIEVAL | The full cross product of `div_old × div_new`. This is the candidate population of round 1a, and it is exactly what a `CandidateSet` would hold. |
| 6 | 1×1 shortcut inside `_similarity_pair` | ASSIGNMENT + preservation | Selecting the sole candidate is assignment, and it is behaviourally identical to running the greedy over a one-candidate list — the greedy always claims it. The shortcut's real effect is that *no similarity is computed* on 593 invocations. That is a performance fact, and it forces the evidence design in §6. |
| 7 | Pairwise `text_similarity` | EVIDENCE | A described quantity, not a verdict. #623 already ruled that a round-1 ratio is natively evidence rather than a promoted retrieval score, and named it `WORD_OVERLAP`. Reuse the name; it is one quantity by one measure. |
| 8 | Descending `(similarity, oi, ni)` ordering | ASSIGNMENT + preservation | Competition policy, and live rather than incidental: 157 of 329 greedy invocations contain a similarity tie, and flipping the tiebreak to ascending changes the selected set on 97 of them. The `(oi, ni)` half is preservation-only machinery — it must be reconstructed explicitly and must not leave the assigner, exactly as `_greedy_move_links` keeps `(ri, ai)` private. |
| 9 | Greedy old/new exclusivity | ASSIGNMENT | The competition rule itself. Note a structural property worth relying on: because every old × new pair inside an invocation is a candidate, the greedy always saturates — 0 of 329 invocations leave an observation unclaimed on the smaller side. Leftovers are pure size imbalance and always on one side per invocation. |
| 10 | Within-division leftovers | PRESERVATION | Not correspondence of any kind. Their sole function is to be the retrieval population of round 1b, in a specific order. Their order is what makes the round-1b index space, so it is load-bearing. |
| 11 | Cross-division fallback eligibility | RETRIEVAL *(assignment-conditioned)* | `if unmatched_old and unmatched_new` gates whether round 1b runs. It reads round 1a's *selections*, never round 1a's evidence, so it satisfies invariant 4 and the multi-round clause. §4 is entirely about this row. |
| 12 | Cross-division candidate formation | RETRIEVAL | Round 1b's population: the concatenated leftovers, cross-producted. A second retriever invocation under a different configuration, in the ADR's sense. |
| 13 | Cross-division greedy competition | ASSIGNMENT | Identical rule to row 8 over a different population and a *different local index space*. One implementation can serve both rounds; the index space must be rebuilt per invocation, not carried. |
| 14 | Final leftovers | PRESERVATION | Unmatched observations, unsettled, feeding round 2. Their emission order (all old, then all new) is canonical output. |
| 15 | Output / emission ordering | PRESERVATION | Composed of three orderings: `match_path` group first-appearance order; then within a group, matched-within-division (in division first-appearance order) ++ matched-cross ++ leftover-old ++ leftover-new. **Not derivable from ordinals** — `probe_ordinal_loss` shows the stream is out of parser order on 10 of 27 pairs for old nodes and 22 of 27 for new. It must be reconstructed, never inferred. |

**Nothing classified as mixed or unresolved.** Every rule resolved to a stage. Three carry a
second *preservation* tag because a real decision and a real piece of order-machinery are
currently expressed by the same code — rows 2, 6 and 8. Those three are where the separation has
to be careful; the rest are mechanical.

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
does not literally cover. Treated in §14.

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
  four-phase append pattern, not of the candidate set — and it is not recoverable from ordinals
  (§3 row 15).

---

## 6. Evidence vocabulary

The instruction was to identify what evidence actually selected each assignment act, and not to
invent evidence merely because a value is available. Applying that strictly leaves **one** new
signal.

| Signal | Status | Describes or decides? | Already computed? | Needed by assignment? |
|---|---|---|---|---|
| `word_overlap` (float) | exists | Describes. One quantity, one measure, shared with round 2. | Yes, on 1,108 of the pairs formed | Yes — the greedy sorts on it |
| `body_unchanged` (bool) | exists | Describes what `diff_text` produced. | Yes, by #623 | By the revocation rule only, not by the greedy |
| `sole_candidate` (bool) | **new — the only addition** | Describes a structural fact about the candidate's group: it is the only member. It does not say the pair corresponds; assignment reads it as grounds to select without a ratio. | No — it is what licenses *not* computing the ratio | Yes — it is the whole content of the 1×1 shortcut, currently implicit in control flow |

### Signals deliberately not added

- **`same_match_path`** — constant `True` for every round-1 candidate, because path grouping is
  what formed the candidate. Zero discriminating power; it is a retrieval fact, and recording it
  as evidence would be exactly the "invented because a value is available" case the ADR warns
  about.
- **`same_division_key`** — constant `True` across round 1a and constant `False` across round 1b.
  It restates which retriever invocation proposed the candidate, which `Proposal.invocation`
  already records as provenance. Adding it would duplicate provenance as evidence and invite
  assignment to read retriever identity as support, which "proposals are provenance, not votes"
  forbids.

**Contract sufficiency.** `CorrespondenceEvidence` represents all three signals with no change:
they are named scalars, booleans are explicitly welcome, and the absent-not-`None` convention for
`word_overlap` is already established. **No new shared contract is required.** Growing the
vocabulary means adding a signal, never a field — and this adds one.

### Why conditional computation must survive

593 of 922 invocations take the 1×1 shortcut and compute no ratio. Emitting evidence for those
links with `sole_candidate=True` and `word_overlap` absent preserves the exact set of
`text_similarity` calls the engine makes today. Computing the ratio unconditionally would be a
behaviour change dressed as a refactor — the same argument #623 made when it measured +21% for the
equivalent tidying, and rejected it.

---

## 7. Proposed stage signatures

Written against #623's shape so round 1 and round 2 read the same way. Names follow ADR 0021: each
names the job it performs, and none claims coverage it does not have.

```python
# ---- RETRIEVAL, round 1a -------------------------------------------------
def retrieve_division_candidates(
    group: PathGroup, registry: ObservationRegistry
) -> tuple[GroupRetrieval, ...]:
    """One GroupRetrieval per division present on both sides.

    GroupRetrieval carries the ORDERED old/new Observation tuples (the index
    space assignment will rebuild) and a CandidateSet holding their cross
    product under RetrieverInvocation.of("path_division", round=PATH_ROUND).
    """

# ---- RETRIEVAL, round 1b -------------------------------------------------
def retrieve_cross_division_candidates(
    leftovers: GroupLeftovers, registry: ObservationRegistry
) -> GroupRetrieval | None:
    """None when either side is empty -- the eligibility gate, made explicit.

    `leftovers` is ORDERED: within-division leftovers in division
    first-appearance order, then one-sided divisions. That order IS round 1b's
    index space; it is not recoverable from ObservationRef ordinals.
    """

# ---- CORRESPONDENCE EVIDENCE (shared by 1a and 1b) -----------------------
def group_correspondence_evidence(
    retrieval: GroupRetrieval,
) -> tuple[CorrespondenceEvidence, ...]:
    """sole_candidate=True with word_overlap ABSENT for a 1x1 population;
    otherwise sole_candidate=False and word_overlap for every candidate.
    Preserves today's exact set of text_similarity calls."""

# ---- ASSIGNMENT (shared by 1a and 1b) ------------------------------------
def assign_group(
    retrieval: GroupRetrieval,
    evidence: tuple[CorrespondenceEvidence, ...],
) -> GroupAssignment:
    """Greedy, exclusive on both sides, unthresholded.

    Sorts on (word_overlap, oi, ni) DESCENDING, where (oi, ni) are positions in
    `retrieval`'s ordered tuples, rebuilt here and NEVER leaving this function
    -- the rule _greedy_move_links already follows for (ri, ai).

    A sole_candidate population selects without reading word_overlap, which is
    why the signal is absent rather than None.

    Returns selected links in greedy order plus leftovers in ascending local
    position -- both are canonical output.
    """
```

**Why `GroupRetrieval` rather than a bare `CandidateSet`:** the assigner needs the ordered
observation tuples to rebuild its index space, and `CandidateSet` deliberately does not carry
order (§5: using its order changes 174/329). Bundling the population with its candidates is what
keeps the ordering contract explicit instead of reconstructed by convention. This mirrors
`UnmatchedPopulation`, which exists for precisely this reason in round 2.

**Does `Proposal` need rank or score?** No. Round-1 retrieval is structural — it emits membership
and provenance. A proposal with null rank and score is fully valid and is the honest
representation; inventing a score here would be the ADR's named anti-pattern. The similarity ratio
is evidence, not a retrieval score, per #623.

---

## 8. Preservation oracle design

The existing canonical gate (27 digests) is necessary and badly insufficient here: it observes
only the final bytes, and §4 shows one whole behaviour it structurally cannot see. The oracle must
be independent of the new production stages — it transcribes the *old* rule rather than calling
the new helper.

| # | Pinned quantity | Identity bridge | Source |
|---:|---|---|---|
| 1 | `match_nodes` pairing stream by observation identity | `ObservationRef` | corpus |
| 2 | Stream *order*, as an ordered sequence | position + `ObservationRef` | corpus |
| 3 | Unique-path direct selections | `ObservationRef` | corpus |
| 4 | Every `_similarity_pair` invocation population, in order | ordered `ObservationRef` tuples | corpus |
| 5a | Candidate identities per invocation | `ObservationRef` pairs | corpus |
| 5b | Exact similarity values where computed | float, exact equality | corpus |
| 5c | The `(similarity, oi, ni)` sort key | **local positions, kept separately** | corpus |
| 5d | Selected links, in greedy order | ordered `ObservationRef` pairs | corpus |
| 5e | Leftovers, in order | ordered `ObservationRef` | corpus |
| 6 | Division-round selections | `ObservationRef` | corpus |
| 7 | Exact observations entering the cross-division fallback | ordered `ObservationRef` | **corpus + synthetic** |
| 8 | Cross-division candidates and selections | `ObservationRef` | **corpus + synthetic** |
| 9 | Provisional stream before the similarity rule | ordered `ObservationRef` | corpus |
| 10 | Post-rule stream | ordered `ObservationRef` | corpus |
| 11 | Ordered round-2 unmatched population | `UnmatchedPopulation` | corpus, already gated |
| 12 | Selected round-2 moves and order | `Correspondence` | corpus, already gated |
| 13 | All 27 canonical digests | SHA-256 | corpus, already gated |

### Two rules the oracle must follow

- **Local positions are pinned as local positions.** Rows 5c and 7 must record the legacy index
  space directly, not re-derive it from ordinals. §5 shows the two agree on this corpus and
  diverge on constructible input; an oracle that pinned ordinals would be pinning the wrong thing
  while looking rigorous.
- **The oracle must not call the new production stages.** It wraps the pre-change
  `_similarity_pair` / `_match_collision_group` by monkeypatch and records what production
  computes. The probes written for this audit already do exactly that and can be promoted (§11).

> **Rows 7 and 8 cannot be pinned from the corpus alone.** Both need a synthetic fixture
> exercising the assignment-leftover path, because the corpus supplies 0 such participants. The
> two constructions in §4 and §5 are minimal and already verified against the real functions —
> they should ship as fixtures in the first slice, before any production change.

> **Correction, after B0 review.** The "identity bridge" column above says `ObservationRef` for
> every result-bearing row, and that was the right design. The first B0 implementation did not
> follow it: it serialized the pairing stream and invocation populations by `element_id`, and
> the frozen digests derived from that. ADR 0019 keeps `element_id` as traceability metadata and
> refuses it as identity, because `bill_tree` reads it as `attrib.get("id", "")` and its
> uniqueness is a sampled property of externally authored markup rather than a contract. The
> consequence is a real false green: two observations sharing an id make the stream unable to
> distinguish a matcher that exchanges their partners. The trace is now addressed by
> complete-emitted-sequence ordinal, the artifact carries each side's `source_sha256` and the
> derived `parser_revision` that scope those ordinals, and a duplicate-id fixture demonstrates
> both halves — the element-id projection blind to a swap, the ordinal projection catching it.
> Local `(oi, ni)` positions stay local positions, per the first bullet above.

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
| `probe_ordinal_loss.py` | valid | Directly corroborates §3 row 15. Keep; it is the evidence that emission order is not ordinal-derivable. |
| `probe_node_identity.py` | valid | Already re-aimed at `apply_similarity_assignment_rule` by #623. |
| `probe_correspondence_revision.py` | valid | Supplies §4's settlement constraint. Keep. |
| `probe_round2_migration.py` | valid | Round 2. Its pinned figures are unaffected. |
| `probe_canonical_sensitivity.py` | **re-aim** | Proves the canonical gate can redden on a *round-2* correspondence change. Round 1 needs the equivalent, and §9 shows three round-1 mutations it can never catch. Extend rather than trust. |
| `probe_slice2.py`, `probe_splits.py`, `probe_provenance.py` | valid | Scoped to round 2 / population sizing. No change. |
| `audit_source_signals.py` | **re-aim** | Calls `match_nodes` for its `@id`-lift comparison. Will still run, but its baseline becomes ambiguous once round 1 is staged; point it at the assignment output explicitly. |
| `compare_selected.py`, `probe_move_assignment.py` | already deleted | Removed by #623. No action. |
| Audit probes written for this report | **promote** | Seven probes covering invocation tracing, the flatten counterfactual, the fast-path equivalence, tie-direction controls and materialisation cost. They are the oracle of §8 in draft form and should be promoted into `scripts/` + tests by Slice B0 rather than rewritten. |

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

## 12. Recommended slices

Derived from the dependency structure, not from the example sequence in the brief. The key
departure: **a preservation-harness slice must come first**, because three consequential mutations
are invisible to every gate that exists today, and **the unique-path slice collapses**, because
the measurement shows there is no separate policy to migrate.

| Slice | Content | Why here | Gate |
|---|---|---|---|
| **B0** ✅ *shipped* | `tests/test_round1_preservation.py` + `tests/data/round1_legacy_trace.json`: independent legacy transcription, frozen trace, structural independence guard, both synthetic fixtures, 10 negative controls, production fault injection. No production change. | Every later slice's gate depends on it. Shipping B1 first would mean changing round 1 while three mutations are unobservable. | 75 passed, 1 skipped. Each control's red gate recorded in §9. |
| **B1** | Name the two retrieval rounds inside `_match_collision_group`. Extract `retrieve_division_candidates` and `retrieve_cross_division_candidates` returning ordered populations. `_similarity_pair` stays the assigner. | Retrieval is extractable *per round* without touching selection. The ordered population is what B2 needs to address. | Oracle rows 4, 6, 7, 8; canonical digests. |
| **B2** | Route the greedy through evidence + contracts: `group_correspondence_evidence`, `assign_group`, with the local index space rebuilt privately. One implementation serves both rounds. | Needs B1's named populations. Adds `sole_candidate`. | Oracle rows 5a–5e; tie-direction and CandidateSet-order controls. |
| **B3** | Unique-path handling. Pin the fast path's equivalence with a test, and decide whether to keep it as a retrieval-side optimisation or retire it. | Last, because the measurement removes it from the critical path — it is not a policy that must be migrated before B2 can proceed. | Oracle rows 1, 2, 3; the 27/27 equivalence test. |
| **B4** | Closure: probe re-aiming, remove the residual `diff_text` double-call #623 flagged. Candidate storage scope is settled in B1, not deferred to here (§13). | Cleanup with its own evidence, deliberately not bundled. | Canonical digests + runtime regression check. |

**B4 as shipped, and one deliberate divergence from the row above.** B4 retired the eight probes
whose questions B0–B3 had taken over (§11), gave the one survivor an executable gate in
`tests/test_research_probes.py`, and closed the transitional statements B1–B3 left behind — this
section's own storage-scope entry among them.

It did **not** touch the `diff_text` double-call, and on review that row was framed wrongly. The
duplication is **performance debt, not an unfinished ADR 0020 architecture requirement**: the two
calls answer separate stage-owned questions, #591 quantified and accepted the cost deliberately,
and no round-1 invariant depends on it. Optimization is deferred unless later end-to-end profiling
justifies a separate change, and the call-count gate belongs with that change rather than ahead of
it. §14 carries the reasoning. Round 1 is closed with this outstanding, not despite it.

**On "can retrieval be extracted alone?"** Yes — *per round*. A single whole-round-1 retrieval
stage producing one candidate population before any assignment is **not** behaviour-preserving:
measured at 8 of 959 groups, ±9 links. The smallest coherent unit is therefore the round, and B1
is exactly that unit.

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
local positions.* Those are compatible — the ordered populations travel beside the candidate set
(§7's `GroupRetrieval`), not inside it — but which object owns which was a slice decision, to be
made against real code rather than pre-committed here.

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

## 14. Conflicts and blockers

**No STOP condition fired.** Existing ADR 0020 contracts express the current behaviour without
changing policy. `CandidateSet` semantics do not force a result-changing order, provided
assignment imposes its own (§5). Faithful preservation does not require violating the
retrieval/assignment boundary — the cross-division fallback reads selections, never evidence,
which is exactly what invariant 4 permits. Every current policy is independently observable,
*given* the two synthetic fixtures.

### One vocabulary gap, flagged not blocking

ADR 0020 says a later retrieval round "may use `Correspondence` settled by an earlier round".
Round 1b uses something weaker: round 1a's *provisional selections*, which the similarity rule may
still revoke and which `CorrespondenceSet` cannot represent without settling them prematurely. The
behaviour is compliant — the prohibition is on consuming evidence, and round 1b consumes none —
but the record's wording does not describe it.

**Recommended handling:** name the provisional carrier explicitly in B1 (the ordered leftover
population is already that object) rather than promoting round-1a output to `Correspondence`.
Promoting it early would collide with `CorrespondenceSet`'s no-revision rule, which
`probe_correspondence_revision.py` already demonstrates. Whether ADR 0020's sentence should be
amended to say "settled or provisionally selected" is a documentation question for after the
slices land, not a precondition.

**Reviewed and accepted (2026-08-12).** No ADR amendment is required now: do not create settled
`Correspondence` prematurely, let round 1b consume the ordered unclaimed population, and keep the
wording issue open as a non-blocking vocabulary gap.

### One residue #623 left, noted for B4

`_similarity_signals` calls `diff_text` and `_paired_record` calls it again on the same pairing.
#623 named this deliberately as visible residue of the fusion it did not remove, and said deleting
it owes its own evidence. It is not this work's scope; B4 is the natural home.

**Reclassified at B4 closure, and it is not an ADR 0020 gap.** The duplicate `diff_text`
computation is known **performance debt, not an unfinished ADR 0020 architecture requirement**.
Optimization is deferred unless later end-to-end profiling justifies a separate change.

The two calls answer separate stage-owned questions, which is why the duplication is not a
redundancy to delete:

1. **correspondence evidence** computes `BODY_UNCHANGED` — it reads only whether the word-level
   diff is empty (`_similarity_signals`);
2. **classification** computes the actual textual diff carried in the output record
   (`_paired_record`'s `text_diff`, and the `unchanged`/`modified` verdict).

#591 already quantified and deliberately accepted this as preservation cost, rather than routing
classification output back across the stage boundary. Nothing about round-1 stage ownership is
waiting on it: no invariant in §9 or the closure inventory depends on the call count, and the
correspondence the engine produces is identical either way.

**No `diff_text` call-count gate is added here.** A call-count gate belongs with the PR that
actually changes this behaviour — added beforehand it would pin a number no decision rests on,
and would make an unrelated optimisation look like a regression the day someone takes it.

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
