# 20. Separate candidate generation, identity evidence, correspondence assignment and change classification

- Status: Proposed
- Date: 2026-08-07

## Context

Comparing two versions of a bill means answering four different questions:

```text
Which nodes are plausible counterparts?          (retrieval)
How much evidence supports each pairing?         (scoring)
Which pairings should actually be selected?      (assignment)
Given those, what changed?                       (classification)
```

`diff_bill.diff_bills` answers all four in one pass, and answers several of them with the
same number. This record separates them. It does **not** decide which measure, which
cutoffs, or which retrievers ship; those are research questions, and the separation exists
precisely so they can be answered independently.

### One measure, five decision sites

`deltatrack.similarity` defines two cutoffs over one word-overlap ratio. Tracing every
consumer under `src/deltatrack`:

| site | question it answers | cutoff |
|---|---|---|
| `diff_bill._similarity_pair` | which node in a collision group pairs with which | argmax, no cutoff |
| `diff_bill.diff_bills` | is this path-matched pair the same provision, or a removal plus an addition | `SIMILARITY_THRESHOLD` |
| `diff_bill.reconcile_moves` | which unmatched removal corresponds to which addition | `MOVE_THRESHOLD` |
| `diff_pdf._hunk_for_paired_blocks` | is this differing-anchor pair *moved* or merely *modified* | `MOVE_THRESHOLD` |
| `formatters/_text.word_diff` | should the reader see an inline word-diff or two stacked paragraphs | `SIMILARITY_THRESHOLD` |

Those are retrieval, assignment, classification and presentation, decided by one function.
The last row is the sharpest illustration: the rendering layer recomputes an identity score
against the differ's own cutoff. The two agree today because they read the same text, so
this is a coupling rather than a live defect — but it means changing what "the same
provision" means also changes what a reader sees, in the same edit, with no way to test the
two apart.

### Retrieval is implicit, and there are two of it

`match_nodes` groups nodes by `match_path` and pairs within each group. That grouping
silently decides what can ever be compared: a node whose counterpart sits at a different
path is never scored at all, because no pair is ever formed.

`reconcile_moves` then runs over the surviving removals × additions under a *different*
cutoff. It is a second retrieval pass, unnamed as such, running after classification. It is
not marginal: measured with `scripts/probe_matching_stages.py`, it converts **496 changes**
to `moved` across 27 adjacent version pairs of the committed corpus (**668** across 51 pairs
of a wider local set). That is the volume of correspondence the first retriever structurally
cannot find.

Neither pass produces an inspectable candidate set, so there is no value against which
candidate recall could be computed.

### Evidence is computed and thrown away

`_similarity_pair` computes every pairwise similarity in a collision group, sorts them,
claims greedily, and discards every score. `NodeDiff` carries no score, no rank, and no
per-signal breakdown. The data needed to ask "was the true counterpart ranked first?"
exists for microseconds and is never retained.

### The fused split decision has a measured money cost

At `diff_bill.diff_bills`, a path-matched pair whose similarity falls below
`SIMILARITY_THRESHOLD` is split into a `removed` carrying only the old text and an `added`
carrying only the new. Money extraction then runs one-sided on each, so a value edit inside
a heavily rewritten section renders as the whole old amount removed and the whole new amount
added. [#368](https://github.com/AgoraDMV/DeltaTrack/issues/368) traced that mechanism and
said plainly that the frequency was not measured, and asked for it to be sized first.

Measured now:

| | committed corpus (27 pairs) | wider local set (51 pairs) |
|---|---:|---:|
| changes emitted | 31,739 | 41,200 |
| path-matched pairs split by the cutoff | 327 | 218 |
| ...of those, carrying amounts on **both** sides | **27** | **13** |

Named instances on the committed corpus include `114-hr-2029` v5→v6 at `department of
defense/administrative provisions/sec. 129` (3 old amounts against 1 new) and `115-hr-5895`
v2→v4 at `corps of engineers—civil/…/sec. 101/(a)` (2 old against 16 new). The money layer is behaving
correctly on the input it is given; the defect is a correspondence failure surfacing as a
financial one, one stage downstream. That is the concrete cost of fusing identity with
classification.

### The result type cannot express a real legislative shape

`match_nodes` returns `list[tuple[BillNode | None, BillNode | None]]`. Exactly two sides,
one node each. A provision absorbed into a larger one, or split across several, has no
representation: it necessarily degrades to independent removals and additions.

Consolidation is a documented case, not a hypothetical. The provision-matching study
characterises the 119-hr-1 Senate rewrite as deliberate consolidation, and the Study 2
protocol carries a consolidation mining stratum and an anchor unit that records "including
NONE and including MANY" because one-to-one is not general enough.

The same probe finds **7** match paths on the committed corpus (**21** on the wider set)
where the output already carries a multi-node removal-plus-addition group at one path, for
example `117-hr-2471` v1→v6 at `sec. 2` with one removal against three additions, and
`113-hr-83` v5→v7 at `sec. 1` with one against five on the wider set. **These are
candidate shapes, not confirmed consolidations** — nobody has ruled them, and some will be
collisions rather than relations. They establish that the shape occurs, not how often it is
genuine.

## Decision

We will make the four questions four named stages with explicit intermediate values, and
give each stage one responsibility.

```text
observations (ADR 0019 identity)
      ↓
  RETRIEVAL      → CandidateSet    which pairings are worth evaluating
      ↓
  SCORING        → Evidence        what supports each pairing, with no decision taken
      ↓
  ASSIGNMENT     → Correspondence  which pairings are selected. Owns every threshold.
      ↓
  CLASSIFICATION → Changes         what changed, given the selected correspondence
      ↓
  canonical diff JSON (ADR 0006, unchanged)
```

Money is deliberately **not** a stage in that chain. See "Where financial interpretation
sits" below.

Four requirements, one per boundary.

**1. Retrieval is a named stage whose output is a value.** A `CandidateSet` enumerates the
pairings that will be evaluated, and records for each which retriever proposed it.
Retrieval may consult structure, text, or anything else, and may be a union of several
retrievers. It may not read a score produced by the scoring stage, and it may not be
performed a second time after classification.

**2. Scoring produces evidence and takes no decision.** For a candidate pairing, the scoring
stage yields an `Evidence` value carrying named signals. It applies no threshold, selects
nothing, and has no knowledge of policy. Evidence is retained for the candidates that reach
assignment, so ranking can be measured after the fact.

**3. Assignment owns all policy.** Converting candidates plus evidence into a
`Correspondence` is one stage, and **every threshold in the matching path lives there**. Its
output is a first-class type, not a tuple.

**4. Classification consumes correspondence and does not relitigate it.** Given the selected
correspondence, classification decides what changed. It may compare the corresponding texts
directly — exact equality, a word-level diff, whether a path or a label moved. It may **not**
apply a threshold to an identity score. Once a correspondence is assigned, it is not
revisited.

### The correspondence type

`Correspondence` must be able to represent at least 1:1, 1:0, 0:1, 1:N and N:1, with each
link carrying the evidence that selected it.

**Representable by the architecture is not the same as produced by the algorithm.** The
current assigner emits only 1:1, 1:0 and 0:1, and this record does not change that. What
changes is that the *type* stops being the reason a real legislative shape cannot be
expressed, so the consolidation stratum in Study 2 has a production shape to be measured
against, and a later algorithm change is not also a type migration through every consumer.

### Per-anchor assignment and global collision resolution are distinct

Selecting a counterpart for one old provision, and resolving a group of provisions competing
for the same targets, are different questions with different correctness criteria. The
provision-matching review separates them as different estimands and has **deferred global
collision resolution out of Study 2 entirely**. Today the code has neither seam:
`_similarity_pair` resolves inside a collision group and `reconcile_moves` resolves across
the whole bill, and neither knows the other exists.

This record requires the two to be separable within the assignment stage. It does **not**
require global collision resolution to be implemented, and does not choose an algorithm for
it.

### Where financial interpretation sits

Money extraction is a function of the **corresponding text pair**, not of the change type,
and this is already true in the code: `bill_diff_to_dict` calls `compute_financial_change`
for every change whatever its `change_type`, and the PDF path runs `match_amounts` against an
empty side for whole-item additions and removals.

So financial interpretation consumes the *correspondence*, in parallel with classification
rather than downstream of it, and it may not participate in deciding identity. #368 is what
this rule prevents: money reported exactly what correspondence handed it, and the error was
made a stage earlier. Placing money after classification in the chain would suggest the
change type is an input to it, which would be a regression in the model as well as in fact.

### What this record does not decide

Deliberately, and this list is the point of the record rather than a caveat on it. If
Study 2 later shows that rare-token containment is a poor measure, **nothing in this decision
becomes wrong** — only the contents of one stage change.

- whether containment, word overlap, or anything else becomes the production score;
- any cutoff value, or whether the current two survive;
- whether structural signals are primary, secondary or worthless. The architecture provides
  a place to put a structural evidence term and to measure it; it assigns it no weight.
  ([#170](https://github.com/AgoraDMV/DeltaTrack/issues/170)'s "structure primary, text
  demoted to tiebreaker" framing is stronger than the research supports and is not adopted
  here);
- whether header equality is privileged;
- which retrievers ultimately ship;
- whether global collision resolution ships at all;
- the algorithm for many-to-one assignment;
- whether GumTree-style descendant propagation or any other tree differ is adopted;
- whether confidence or evidence is ever published in canonical JSON;
- **whether XML and PDF share one assignment implementation.** They may eventually share
  these internal contracts, but the full matcher has never been validated on a PDF-only
  correspondence fixture and the PDF seam study's external-validity holdout is frozen and
  unscored. That is a separate decision and this record does not make it.

### Alternatives rejected

- **Keep the stages fused and tune the thresholds.** Rejected on measurement. One number
  decides identity and render form, so a tuning change is untestable in isolation; and the
  27 measured split-with-money instances show the fusion producing a wrong-looking financial
  result that no threshold value fixes, because the two populations it separates (genuine
  false matches, and heavily rewritten real sections) are not separated by that measure.

- **Add tracing to the existing code instead of materialising a `CandidateSet`.** Rejected,
  and this is the alternative that came closest. Instrumentation would in fact let ranking be
  measured over the pairs that are scored. What it cannot supply is the *denominator*: pairs
  the path-grouping never forms produce no event to trace, and those are exactly the
  population candidate recall is about. It also leaves retrieval unreplaceable — adding a
  retriever today means adding another whole-pipeline pass, which is what `reconcile_moves`
  already is.

- **Let the score object carry its own policy** (an `Evidence` that decides). Rejected: one
  score is already consumed by three different policies (split at one cutoff, move at
  another, collision assignment by rank with no cutoff) plus the renderer. A policy-bearing
  score object either picks one of them, which is wrong, or grows one per consumer, which is
  the same coupling with more indirection. It would also put the differ's policy inside the
  rendering layer, which `similarity.py` was extracted specifically to avoid.

- **Let classification re-consult similarity.** Rejected as stated, with a carve-out.
  Classification legitimately asks *how much* the corresponding texts differ — that is what
  `move.body_unchanged` records, and it needs no score. What it may not do is apply a
  threshold to an identity score, which is what `diff_bill.diff_bills` and
  `diff_pdf._hunk_for_paired_blocks` both do today.

- **Keep `Correspondence` pair-shaped and revisit if consolidation proves common.**
  Rejected on cost asymmetry. Capability costs a type that permits N sides. Not having it
  costs Study 2 a production shape for its consolidation stratum, and turns any later change
  into a migration through every consumer of the matcher's output.

- **A full tree-diff rewrite** (GumTree-style, matching containers by matched descendants).
  Rejected as premature: the study defers descendant propagation explicitly, and it is a
  large behaviour change where this record is a behaviour-preserving separation.

## Consequences

- **Four research targets become measurable against the production engine**, which is
  currently impossible for three of them: candidate recall (needs the candidate set),
  ranking quality (needs retained evidence), per-anchor assignment correctness, and final
  diff correctness. Global collision correctness becomes measurable *if* it is ever
  implemented.

- **A behaviour change to one stage stops being a behaviour change to the others.** The
  concrete case: swapping the identity measure no longer edits what the renderer shows,
  because the renderer's legibility cutoff stops being the differ's identity cutoff.

- **#368 becomes fixable at its cause.** Whether a heavily edited section is one provision or
  two is an assignment question; how its money is paired is a consequence. Today they are one
  expression.

- **Retrieval becomes additive.** A new retriever joins a union instead of becoming another
  pass over the whole bill after classification.

- **Evidence retention has a memory cost, and the requirement is scoped to bound it.**
  Evidence is retained for candidates that reach assignment, not for every pair ever scored:
  `move_candidates` already evaluates on the order of 78,000 pairs on one large bill, and
  retaining all of them would work against
  [#356](https://github.com/AgoraDMV/DeltaTrack/issues/356) and
  [#169](https://github.com/AgoraDMV/DeltaTrack/issues/169). Nothing requires evidence in the
  shipped output.

- **More named types and one more indirection.** The honest cost. Each boundary is justified
  below by at least one testable invariant, one measurable target, one real case the current
  types cannot express, or one coupling that has produced a defect; a boundary buying none of
  those is not in this record.

- **The canonical contract is unchanged, and one shape cannot be projected onto it.** See
  below.

- **This is a two-phase change, and the phases must not merge.** See "Implementation".

## Where the canonical contract cannot follow

A canonical `Change` is a **binary row**: one `text.old` and one `text.new`, one `path.v1`
and one `path.v2`, one `amount_entries` list, `additionalProperties: false`, and no field
linking one change to another. So:

| correspondence | canonical representation |
|---|---|
| 1:1 | one `Change` with both sides |
| 1:0 | one `Change`, `change_type: removed`, null new side |
| 0:1 | mirror |
| **1:N, N:1** | **no faithful representation** |

The two available projections both lose something. Emitting N rows that share one side
duplicates that side's `amount_entries` N times, which corrupts the money — unacceptable
under [ADR 0001](0001-structured-money-diff.md). Degrading to N removals plus one addition
loses the relation but keeps every amount counted once, and it is exactly what the engine
emits today.

**Decision for now: degrade, explicitly.** The canonical projection of a non-binary
correspondence is the degraded form, named and tested as a projection rather than arising by
accident. Whether the contract should grow a grouping field is a separate question for
[ADR 0006](0006-canonical-diff-contract.md), needs a consumer, and is **not decided here**.

This is what makes the behaviour-preserving phase possible: a richer internal type whose
projection reproduces today's output byte for byte.

## Implementation

Separated as the review asked, because conflating these is how a staged refactor becomes a
rewrite.

**Required by this record** — the data contracts, and only these:

- `CandidateSet`, carrying per-candidate retriever provenance;
- `Evidence`, carrying named signals and no decision, retained for candidates reaching
  assignment;
- `Correspondence`, first-class, capable of 1:1 / 1:0 / 0:1 / 1:N / N:1, each link carrying
  its evidence;
- assignment as the sole owner of thresholds;
- classification as a consumer of correspondence that applies no identity threshold;
- an explicit, tested canonical projection, including the degradation above.

Observations are identified per [ADR 0019](0019-observation-identity.md)
(`source_sha256`, `parser_revision`, `node_ordinal`). This record introduces **no second
notion of node identity**; candidates, evidence and correspondence all reference
observations by that key.

**Accepted implementation shape** — one public entry point over the four stages, so callers
do not orchestrate them and the stages can be reordered internally.

**Illustrative only, and not decided here** — a layout such as:

```text
matching/
    candidates
    evidence
    assignment
```

Module layout is a preference. A reviewer should push back on any part of this record that
argues from layout rather than from a contract.

**Deferred until Study 2 supports it** — every item in "What this record does not decide",
plus removing whichever matching paths are superseded.

### Two phases, and why they must stay apart

**Phase 1, behaviour-preserving.** Introduce the types and seams while reproducing current
matching behaviour exactly. Acceptance is canonical JSON byte-identical across the corpus on
both pipelines. This is what gives Study 2 something production-shaped to measure, and it is
the last point at which a revert is cheap.

**Phase 2, behaviour-changing.** Only once ground truth supports it: change retrievers,
introduce evidence signals, calibrate assignment policy, remove superseded paths. Every
change here needs precision and recall evidence in the same pull request.

The separation is not advisory. Phase 1's acceptance criterion is *byte-identical output*,
which a phase-2 change necessarily breaks, so the two cannot be combined without the
combined change failing phase 1's gate. That is the mechanism, rather than a convention
someone has to remember.

## Relationship to other records

- **[ADR 0019](0019-observation-identity.md)** (proposed) — supplies the identity every type
  here references. This record depends on it and adds no competing identity.
- **[ADR 0006](0006-canonical-diff-contract.md)** — a hard constraint. The contract's shape
  does not change; the non-binary projection question above is where a future amendment
  would be argued.
- **[ADR 0008](0008-deterministic-engine.md)** — preserved and tightened. Each stage is a
  deterministic function of its input, which makes determinism testable per stage rather
  than only end to end.
- **[ADR 0009](0009-validation-ground-truth.md)** — unchanged. Committee reports remain the
  external oracle for amounts. This record adds internal targets that are not a substitute
  for external ground truth, and says so because "we can now measure ranking accuracy" is
  the kind of claim that quietly displaces an external check.
- **[ADR 0014](0014-leveled-heading-tree-scope.md)** — the enabler. `structure_tree.py`'s
  own docstring names the conservation-checked tree plus its gate as "that future refactor's
  de-risking spec". This is that refactor, and the tree is what a structural evidence term
  would read.
- **[ADR 0001](0001-structured-money-diff.md)** — why the duplicate-side projection is
  rejected: it would double-count amounts.
- **[ADR 0018](0018-text-triggers-are-financial-only.md)** — the pattern the classification
  gate below copies, and a constraint on any evidence term: a structural signal may not be
  appropriations vocabulary.

## Invariants and tests this decision implies

Each names the direction that can regress, and how the check is proven capable of firing.

| # | invariant | proven able to fail by |
|---|---|---|
| 1 | Retrieval reads no score, and runs once. No retrieval happens after classification | a retriever that consults evidence fails an import-graph gate; assert no second retrieval pass exists after the classification stage |
| 2 | The candidate set is inspectable, and every candidate records which retriever proposed it | a candidate with no retriever provenance is rejected |
| 3 | Scoring applies no threshold and selects nothing | the scoring module may not import a threshold constant; plant one and assert the gate fires, on the fail-closed pattern ADR 0018 uses |
| 4 | **Every threshold in the matching path lives in assignment** | plant a threshold comparison in retrieval, scoring or classification and assert the gate flags it |
| 5 | Classification applies no identity threshold, and does not change which observations correspond | feed classification a fixed correspondence, perturb the evidence, and assert the emitted change set is unchanged |
| 6 | Evidence is retained for every candidate that reaches assignment | drop an evidence value and assert ranking measurement refuses rather than silently scoring over a subset |
| 7 | `Correspondence` round-trips 1:1 / 1:0 / 0:1 / 1:N / N:1 without loss | construct each shape by hand and assert it survives; an N:1 that silently becomes two 1:1s must fail |
| 8 | The canonical projection of a non-binary correspondence degrades **explicitly**, and never duplicates a side's amounts | project a hand-built N:1 and assert each amount appears exactly once across the emitted rows |
| 9 | Phase 1 changes no output | canonical JSON byte-identical across the corpus, both pipelines. This gate must itself be shown able to fail: perturb a cutoff and confirm it goes red before trusting a green |
| 10 | Each stage is deterministic in isolation (ADR 0008) | same inputs, repeated calls, identical outputs, per stage |

Invariant 9 is the one that carries the others. A byte-identical-output claim from a gate
nobody has seen fail is indistinguishable from a gate that is not reading the output, and
the corpus gates are exactly where that has bitten before
([#299](https://github.com/AgoraDMV/DeltaTrack/issues/299),
[#542](https://github.com/AgoraDMV/DeltaTrack/issues/542)).

The evidence in Context is reproducible with:

```
uv run python scripts/probe_matching_stages.py tests/corpus
```
