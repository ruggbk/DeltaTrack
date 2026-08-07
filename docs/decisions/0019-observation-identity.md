# 19. Identify a parsed observation by its source, its parser revision and its address; never by its text

- Status: Proposed
- Date: 2026-08-06

## Context

Several artifacts in this repository record a judgment about a *parsed node*: the
hand-labeled matching answer key, the PDF anchor goldens, the extraction goldens, and
every research probe that scores a pair of provisions. Each one has to name the thing it
is talking about. Today they name it in three different ways, and one of those ways does
not work.

**Body text is not unique, and the failure is not marginal.** Measured on the committed
corpus with `scripts/probe_observation_identity.py` (58 XML documents, 49,747 nodes):

| | |
|---|---:|
| documents containing at least one duplicated body text | 23 |
| distinct body texts occurring more than once | 385 |
| node occurrences inside a duplicate group | 1,041 |
| largest multiplicity, one text in one document | 9 |

Appropriations bills are assembled from repeated boilerplate, so this is a property of
the genre rather than an accident of one bill. The provision-matching review measured the
same shape independently on a larger union of corpus roots (106 documents: 35 affected,
551 texts, 1,544 occurrences, multiplicity to 12).

**The direction of the failure is what makes it serious.** A join on text fails
*optimistically*. A recall miss against provision X scores as a hit whenever any
boilerplate twin is in the candidate set; a rank-2 target scores as top-1; a wrong
assignment scores as correct. Every collapse flatters the thing being measured. The
review proved this by restoring a content-hash join to a fixture and showing the metrics
score strictly *better* under it.

**`match_path` is not an address either, and is not meant to be.** On the same corpus, 32
of 58 documents carry a duplicated `match_path`, involving 2,832 nodes. That is by
design: it is a blocking key that groups candidates, and treating it as identity is the
natural-key mistake the matching research names explicitly. It is also the shape
[#518](https://github.com/AgoraDMV/DeltaTrack/issues/518) reports.

**An address does already exist on the XML side.** `element_id` (the GPO XML `@id`) is
non-empty and unique for all 49,747 nodes across all 58 documents. Nothing asserts that,
so it holds by observation rather than by construction.

### What went wrong, stated as a gap rather than a fault

`tests/data/similarity_labels.json` stores `text_old` and `text_new` verbatim and carries
no source digest, no parser revision and no node address. Three of its twelve pairs no
longer resolve to any node the current parser emits. Its regeneration script cannot run
at all: `scripts/build_similarity_labels.py` imports `_MOVE_THRESHOLD`,
`_SIMILARITY_THRESHOLD` and `_text_similarity` from `deltatrack.diff_bill`, names that
[#492](https://github.com/AgoraDMV/DeltaTrack/issues/492) moved into
`deltatrack.similarity` without the underscore, so it exits on `ImportError` before doing
anything.

Nothing here means the legislation changed or that the human judgments were wrong. The
source XML is byte-identical to the file that entered git, and the parser as of the
answer-key commit still reproduces all three stored texts from those bytes. What moved is
the parser's *representation*, which re-segments the unit the judgment was about. The
fixture had no way to say which parse it meant, so a representation change silently
redefined its subject.

**Nothing caught it, and could not have.** `tests/test_similarity_labels.py` scores
`pair["text_old"]` — the stored string. It therefore re-verifies that the stored text
still gets the stored score, which is true by construction and stays true forever. It is
a threshold-regression test, correctly, and it was never a drift guard. Nothing else was
either.

This is the second form of the self-confirmation trap [ADR 0009](0009-validation-ground-truth.md)
was written against. 0009 guards the case where a test's *expected values* come from the
same source as the code. The case here is that a test's *subject* comes from the code:
an artifact keyed on the parser's own output confirms whatever the parser now says, and
stays green while the thing it described stops existing.

## Decision

We will identify a parsed observation by **`(source digest, parser revision, node
address)`**, and keep three questions permanently apart.

| question | field | may two distinct nodes share it? |
|---|---|---|
| **observation identity** — which parsed node is this? | `(source_sha256, parser_revision, node address)` | **No.** Asserted, not assumed. |
| **content integrity** — is this still the same text? | `text_sha256` | **Yes, routinely.** That is the measured finding above, not a defect. |
| **cross-version identity** — is this the same provision as that one? | the human's or the matcher's correspondence ruling | It is an **output**, never an input key. |

The three components:

- **Source digest.** SHA-256 of the source bytes. For a file committed under
  `tests/corpus/`, git already pins the bytes, so the digest is *recorded* rather than
  relied on for storage. [ADR 0015](0015-corpus-test-fixtures.md) rejected a checksum
  registry for the committed set on exactly that ground and reserved it "for the mining
  tier should it ever need reproducibility". This record is where that reservation is
  cashed in: any artifact referencing a source outside git must carry the digest.

- **Parser revision.** Derived from the code that emits nodes, **not declared**. A
  SHA-256 over the source of the entry module and every `deltatrack.*` module it
  transitively imports, resolved by AST. Deliberately over-broad; see Consequences.

- **Node address.** The parser-emitted id: `element_id` on the XML side. Unique and
  non-empty within one parse.

`text_sha256` is recorded alongside, for drift detection only. It is never a key.

**Scope.** This governs *stored artifacts that record a judgment about a parsed node* —
test fixtures, goldens, labeled datasets, research probe output. It does not change the
engine's runtime behaviour, and it does not add a field to the canonical diff contract
(see Undecided).

**This is identity within one parse, not across versions.** `element_id` being the address
does not make it a cross-version match key, and this record does not claim it is. The
source audit found the XML `@id` conflict-prone in that role: roughly 59 conflict-free
net-new matches corpus-wide, with 34 of 93 candidates contradicting the path matcher. It
is a guarded low-priority supplement to matching at best. Cross-version identity stays
the matcher's or the human's output, per the table above.

### Alternatives rejected

- **Body text, or a hash of it, as the key.** Rejected on measurement: not unique in 23
  of 58 documents, and it fails optimistically, so every artifact keyed this way reports
  better numbers than the truth. This is the status quo for the answer key.

- **A git commit as the parser revision.** Rejected in both directions. It moves when
  documentation changes, forcing re-verification that buys nothing; and it does *not*
  move for an uncommitted edit to the parser, so a probe run against a dirty tree records
  a revision it did not use. The second direction is the one that matters.

- **A declared constant for the parser revision.** Rejected: it records an intention
  rather than a fact. The review's round-6 follow-up found precisely this shape in its own
  research code — a `target_parser_commit` field no verifier read, so setting it to a
  well-formed but wrong value still certified a universe. A field that names its own
  correctness and is checked by nobody is decorative.

- **A traversal ordinal alone as the address.** Rejected: an ordinal shifts when anything
  earlier in the document changes, which is exactly the edit it would need to survive. An
  element id does not.

- **`match_path` as the address.** Rejected on measurement: duplicated in 32 of 58
  documents, 2,832 nodes involved. It is a blocking key and must stay one.

- **Do nothing; re-derive fixtures on demand.** Rejected: that is the status quo, and
  under the status quo the answer key cannot be re-derived at all.

## Consequences

- **A drift guard becomes writable.** An artifact can now say which parse it meant, so a
  parser change *quarantines* the affected records for re-review instead of silently
  redefining them. Today there is nothing to check, because the fixture carries no field
  to check against.

- **The answer key becomes regenerable**, once the builder is repaired and the fields
  added. That unblocks the ground-truth work originating in #8 and the Study 2 labeling
  pipeline, both of which currently rest on a fixture that cannot be rebuilt.

- **`element_id` becomes load-bearing rather than incidental.** It holds today by
  observation, not by assertion, and `bill_tree` reads it as `el.attrib.get("id", "")` —
  an empty string is representable. Making it an invariant is new work, and any node type
  that cannot supply one needs a deterministic synthesized address (front-matter nodes
  already have one).

- **The parser revision is deliberately over-broad, and that costs work.** The transitive
  module set will include modules that cannot affect node emission, so an unrelated edit
  forces re-verification. That direction wastes effort; the other direction silently
  certifies records derived by different code. The trade is taken knowingly.

- **A committed fixture has to be rewritten** to carry the new fields. That is a
  deliberate change to `tests/data/similarity_labels.json`, not a drive-by edit, and it
  is called out as a decision to be taken rather than assumed (see Undecided).

- **`scripts/build_similarity_labels.py` is currently broken on `develop`** and its repair
  exists only in the provision-matching review branch, which cannot merge while CI is
  unavailable. Implementing this record depends on that repair landing.

- **The PDF pipeline has no node address at all today**, so this record is enforceable on
  the XML side first. That is a real asymmetry, not a temporary one (see Undecided).

- **Nothing about the shipped diff changes.** No canonical field is added, no engine
  behaviour moves, and no consumer of the published schema is affected.

## What remains undecided

Stated explicitly, so a later reader does not mistake silence for a ruling.

1. **Whether provenance reaches the canonical diff contract.** It does not today: the
   canonical `id` is a per-document change sequence (`c-0001`), and `element_id` is not in
   the contract at all. Adding it would be an additive-minor bump under
   [ADR 0006](0006-canonical-diff-contract.md) and needs a real consumer first
   ([#366](https://github.com/AgoraDMV/DeltaTrack/issues/366), or BillTrax). **Not decided
   here, deliberately.**

2. **The PDF node address.** A PDF block carries an `Anchor` of
   `(kind, text, page_number, line_number)` and no id. Whether the address becomes that
   tuple, a synthesized per-parse ordinal, or something else is a genuine open question,
   and answering it badly would re-introduce a text-bearing key. This record is scoped to
   formats whose parser emits an id, and names PDF as the open case.

3. **Whether, and when, the committed answer-key fixture is rewritten** to carry the
   fields. Rewriting a committed fixture that encodes human rulings is a maintainer
   decision.

4. **The drift response policy for committed fixtures.** `pass2-protocol.md` §4 already
   prescribes quarantine-for-re-review rather than auto-refreeze, for research candidates.
   Whether the committed test fixture takes the same policy or fails hard is not settled
   here.

5. **Whether other stored artifacts adopt the contract, and in what order.** The PDF
   anchor goldens key on `(kind, text, page, line)` and carry no source digest or parser
   revision, so a parser change rewrites what "golden" means. That is the same class of
   gap, milder because regeneration is explicit (`UPDATE_GOLDEN=1`). Sequencing is
   deliberately left open.

## Relationship to ADR 0009

**This record amends [ADR 0009](0009-validation-ground-truth.md); it does not replace
it.** 0009's decision stands unchanged: the parser is validated against amounts
independently authored in published committee reports, because a yardstick the parser's
author did not create is the only thing that catches the author's blind spots. Nothing
here weakens that, and committee reports remain the external oracle.

What 0009 does not say is how a *stored* validation artifact names the thing it validated.
Its guard is against expected values drawn from the same source as the code. The gap this
record closes is the adjacent one: an artifact whose *subject* is drawn from the code
confirms whatever the code now emits. 0009 should gain a pointer to this record where it
describes keeping misses visible and hand-traced, since a hand-traced miss is only
recoverable if the node it refers to is still identifiable.

Also related:

- **[ADR 0015](0015-corpus-test-fixtures.md)** — consistent with, and cashes in, its
  reserved checksum-registry clause for the non-committed tier.
- **[ADR 0006](0006-canonical-diff-contract.md)** — unaffected. The contract's shape does
  not change, and item 1 above is where a future change would be argued.
- **A staged provision-matching record (not yet written)** depends on this one: candidate
  recall, ranking and assignment accuracy are only measurable if the observations being
  scored can be named.

## Invariants and tests this decision implies

Each is stated with the direction that can regress. An absence assertion that has never
produced a positive result cannot distinguish "compliant" from "the check is broken", so
each row names how the check is proven capable of firing.

| # | invariant | proven able to fail by |
|---|---|---|
| 1 | Every node a parser emits has a non-empty address, unique within its parse | a fixture node with a blanked or duplicated id must fail the sweep |
| 2 | An artifact whose recorded parser revision is not the checked-out one is **refused**, not silently accepted | mutate the recorded revision to a well-formed but different value; the record must be refused by every metric that consumes it |
| 3 | An artifact whose recorded source digest does not match the file it names is refused | flip one byte of the source |
| 4 | A stored text whose `text_sha256` no longer matches the re-derived node quarantines that record | edit a stored text and assert the record is quarantined, not re-scored |
| 5 | The parser revision is **derived**, not declared: editing a parser module moves it, and restoring the module returns it | the test is itself the falsification: edit `bill_tree.py`, assert movement, restore, assert return |
| 6 | No artifact-reading code joins on body text | plant a text-keyed join in a newly created module and assert the gate flags it, on the fail-closed pattern [ADR 0018](0018-text-triggers-are-financial-only.md) already uses (allowlist checked to name only modules that exist) |
| 7 | The regeneration path actually executes in CI rather than being trusted | **this one starts red**: `scripts/build_similarity_labels.py` exits on `ImportError` on `develop` today |

Two notes on the shape of these:

- Invariant 2 is the one the research programme got wrong first time, in its own code. A
  provenance field that no verifier reads is worse than no field, because it reads as
  compliance. Its test must mutate the field and assert refusal, not merely assert that
  the field is present.
- Invariant 7 is written to start failing on purpose. A regeneration script that has never
  been executed by CI is indistinguishable from one that cannot run, which is the
  condition this record exists to end.

The evidence in Context is reproducible with:

```
PYTHONPATH=src .venv/bin/python scripts/probe_observation_identity.py tests/corpus
```
