# PDF matching convergence — CLOSED

**Status: the PDF side of [ADR 0020](../../decisions/0020-matching-stages.md) is complete.**
No matching stage remains fused, and canonical PDF output is unchanged by any of it.

This is the closed record. It keeps what explains the current design and what reproduces the
one question still open; it does not keep the investigation.

## Final architecture

```
PDF pages
  -> observations              parsers/pdf_blocks._group_into_blocks + PdfObservationRegistry
  -> retrieval / CandidateSet  which pairs are worth evaluating, with provenance
  -> correspondence evidence   what is measurably true about a pair; decides nothing
  -> assignment                which pairs correspond, and on what basis
  -> settled correspondence    PdfSettledCorrespondence: correspondence + round + slot + move_basis
  -> classification            what changed, given settled correspondence
  -> canonical diff            formatters/canonical.pdf_diff_to_canonical
```

**Two rounds, and the shape is PDF-specific.** Round 1 aligns block keys with
`difflib.SequenceMatcher` and pairs positionally inside a `replace` opcode; round 2 recovers
moves from whatever round 1 left unmatched. Both rounds run **before** classification — round 2
used to read the classified hunk stream, which made classification an input to matching.

Production files:

| file | holds |
|---|---|
| `src/deltatrack/diff_pdf.py` | every stage, the stage vocabulary, and `diff_pdfs` |
| `src/deltatrack/pdf_observations.py` | `PdfObservation`, the registry, `pdf_parser_revision()` |
| `src/deltatrack/parsers/pdf_blocks.py` | observation production (no matcher import) |
| `src/deltatrack/amounts.py` | the source-neutral amount primitive |
| `src/deltatrack/similarity.py` | both cutoffs, shared with the XML path |

## Behaviour preservation

**The architecture changed; canonical PDF output did not.** Every slice was gated on
byte-identical output, and the canonical baseline was never regenerated.

Two independent authorities:

- `tests/test_pdf_canonical_baseline.py` — a digest over canonical output for every committed
  adjacent PDF pair, *including* the six pairs production declines to diff, so a regression in
  the decline rule cannot silently shrink coverage.
- `tests/test_pdf_round2_stages.py` — a whole-output comparison against an independently
  transcribed pre-extraction pipeline, agreeing on all 23 adjacent pairs, which covers the six
  the baseline cannot.

The baseline exists because the suite was provably blind before it: mutating either cutoff by
±0.05 changed real corpus output and all 3227 tests still passed, on all four mutations. All
four now go red.

## Permanent invariants, and which module owns each

| test module | invariant it owns |
|---|---|
| `test_pdf_canonical_baseline.py` | canonical output over the committed corpus, and the decline decision, are pinned byte for byte |
| `test_pdf_matching_boundary.py` | the split rule and the round-2 competition, transcribed independently and never importing the production helpers, plus four named tiebreak mutations |
| `test_pdf_observation_emission.py` | what an observation *is*: the post-filter block sequence, its completeness, order, non-overlap and stability |
| `test_pdf_observation_identity.py` | ADR 0019 addressing and `pdf_parser_revision()`: the revision moves on any parser module and on the engine, and not on the matcher |
| `test_pdf_round1_retrieval.py` | round-1 retrieval is a named retriever emitting a `CandidateSet`; membership equals the transcribed considered population; the set's canonical order stays out of the emitted order |
| `test_pdf_round1_revocation.py` | the similarity rule reads named evidence, owns its threshold, and evidence never censors at the next stage's cutoff |
| `test_pdf_round2_stages.py` | the four round-2 stages reproduce the legacy reconciliation, in its order, and `_reconcile_moves` is off the production path |
| `test_pdf_move_basis.py` | classification reads `move_basis` and applies no correspondence threshold; the basis vocabulary is closed and fails closed |

## Findings that explain the current design

- **A PDF observation is the post-filter block sequence.** `_group_into_blocks` drops 190 blocks
  (a coordinate collision), correctly, and the ordinals are assigned after that filter. Assigning
  before it produces addresses that look valid and point at the wrong block.
- **Observation identity follows ADR 0019**: side plus ordinal into the complete emitted sequence,
  never into a filtered or re-sorted view. `pdf_parser_revision()` digests the transitive import
  closure of the block former, so an edit to any module that can change what a block *is* moves
  the revision, and a matcher edit does not.
- **`SequenceMatcher` plus the positional `replace` zip are retrieval policy, and source-specific.**
  They decide what may be compared, not what corresponds. Widening them is a matching-policy
  experiment owing precision and recall evidence, not an extraction.
- **Round-2 ordering and tiebreak behaviour are preserved exactly.** The legacy sort is
  `(similarity, ri, ai)` descending, so a similarity tie breaks on descending positions; sorting
  on similarity alone and leaning on a stable secondary order is a different rule.
- **Evidence must not censor at the next stage's cutoff.** The first extraction measured round-1
  overlap with a gated helper that returns `0.0` below its bound, so a pair whose real overlap was
  0.30 was recorded as `0.0` and a threshold of 0.20 revoked it. Evidence now records the exact
  ratio; the cost was measured at +0.9% on a full-corpus sweep, inside run-to-run noise.
- **`CandidateSet` admission is result-bearing.** Evidence fails closed unless retrieval proposed
  the pair *under the invocation now describing it*. A candidate set that is built and then
  ignored is indistinguishable from a correct one by every gate that compares output, so
  admission, membership and ordering each carry their own control.
- **The moved-vs-modified decision arrives as `move_basis`.** Assignment decides and records
  `round1_anchor_similarity` or `round2_unmatched_recovery`; the anchor relationship reaches that
  rule as named evidence (`equal` / `different` / `missing`) rather than the rule reading raw
  block state. Three states because the legacy boolean collapsed "no anchor" into "different
  anchor".
- **Classification contains no correspondence threshold.** It reads the settled basis and
  consults neither the overlap nor the round. It still compares corresponding text and labels to
  *describe* a change, which ADR 0020 permits.
- **Canonical `moved` semantics remain unresolved**, because a stable location identity does not
  exist to express them. See below.

## Known follow-up

**Stable PDF heading and location identity.** An anchor is captured from one printed line, and a
GPO heading wraps across as many lines as it needs, so the anchor is a *fragment* whose content
depends on where the typesetter broke the line. A re-typeset bill therefore yields two different
anchor strings for one unchanged heading, and the report tells the reader a section was renamed
when nothing was. This blocks any location-based definition of `moved` from being expressible at
all.

Measurements, consequences, falsifiers and the reproduction commands are in
[`moved-semantics.md`](moved-semantics.md). No issue is filed; that is Will's call.

## Reproducing the open finding

From the repository root, with the committed PDF corpus present:

```sh
# 1. The current moved population, partitioned by why each row is a move.
#    Asserts an independently transcribed classifier reproduces `diff_pdfs` before
#    reporting any count. Writes results/move-semantics-census.json (gitignored).
uv run python docs/research/pdf-matching-convergence/probes/pdf_move_semantics_census.py

# 2. The line-wrap finding: for every round-1 changed-anchor row, the lines actually
#    printed on the page on both sides. Reads the census output from step 1.
uv run python docs/research/pdf-matching-convergence/probes/pdf_move_anchor_adjudication.py

# 3. What a reader is actually told: the canonical `move` payload and the rendered
#    sentence for every moved card, through the real canonical and view-model code.
uv run python docs/research/pdf-matching-convergence/probes/pdf_move_user_facing.py
```

Step 2 requires step 1 to have run in the same checkout. `results/` is gitignored, so the
artifacts are local and regenerated on demand — see [`.gitignore`](.gitignore) for the one
exception.

`probes/corpus.py` is shared discovery and page caching for all three. It keeps two populations
apart: every adjacent committed pair, and the subset `compare.pdf` will actually diff. Every
number quoted in the retained documents is over the second.

## Historical note

Detailed investigative probes, generated outputs, intermediate hypotheses, and the
fault-injection history remain available in Git history and were intentionally removed from HEAD
at research closure. See [`../README.md`](../README.md) for the retention policy this followed.
