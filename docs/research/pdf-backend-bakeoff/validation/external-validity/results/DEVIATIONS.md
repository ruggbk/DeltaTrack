# Deviations

`PRE-REGISTRATION.md` section 11 register. Rows are appended **when they happen** and carry:
what changed old to new; when and at what stage; **whether results were already visible, and
which**; why; and which scores, rankings or gates it could move.

Section 4.7 governs the consequence: a change made after execution starts is a deviation, and
**every affected score is re-labelled non-confirmatory**. "Affected" means *value-dependent*,
not merely *enabled*. Labelling every result non-confirmatory because a repair made the
pipeline runnable at all would destroy the distinction the register exists to record.

The machine-readable form of this ruling is [`CONTINUATION.json`](CONTINUATION.json), which is
what the apparatus reads. This document is the reasoning; that file is the authority.

---

## A47 — POST-BOUNDARY CONTINUATION / DEVIATION RULING

```json
{"id": "A47", "kind": "POST-BOUNDARY CONTINUATION",
 "commits": ["9ce9b6e", "cc69fc5", "381c2f6", "abbe780", "8f28719", "5a33e19"],
 "prior_boundary_commit": "89360b30de480231efdc89157443779d45b37db2",
 "population_status": "EXPOSED",
 "results_already_visible": {
  "d_frame_census_regions": 13992,
  "s1_documents_firing": "17/17",
  "p_head_documents": 12,
  "p_head_pages": 2864,
  "frames": "17/17 members, 4190 pages"
 },
 "affects_membership": false,
 "affects_scoring_rule": false,
 "affects_metric_values": true,
 "affects_architecture_decision": true,
 "affects_architecture_outcome_enum": false,
 "narrowing": "affects_scoring_rule is FALSE because no frozen rule changed; A48 repairs the implementation of A27.3. affects_metric_values is TRUE because A48 changes which routes R1 is REQUIRED to score, so r1_reliability's value can move. affects_architecture_decision is TRUE only for the artifact's ATTRIBUTION field: the outcome ENUM is invariant to A48 at D>60, while decided_by can flip between BUDGET_A10_A27_3 and RULE_3_GATE where Rule 0 does not decide. A48 can NEVER move a Rule 0 outcome or its attribution.",
 "non_confirmatory_paths": ["cross-engine qualification channel (A45-dependent)"],
 "files_touched": ["probes/continuation_provenance.py", "probes/x04_freeze_check.py",
                   "probes/cross_engine_control.py", "probes/score_metrics.py",
                   "probes/x27_score_metrics.py", "probes/x30_continuation_boundary.py",
                   "probes/x30_labelling_fixture.py"],
 "also_touched_outside_study_tree": ["pyproject.toml", "uv.lock"],
 "why_not_an_amendment": "PRE-EXECUTION-AMENDMENTS.md requires confirmatory_output_at_time == 'none' on every record; a truthful post-boundary record cannot assert that without misleading a reader. Sections 4.7 and 11 already designate this register."}
```


**This is not a pre-execution amendment, and it is deliberately not recorded as one.**
`PRE-EXECUTION-AMENDMENTS.md` is the pre-execution ledger: `x04.parse_amendments` requires
every record in it to carry `confirmatory_output_at_time == "none"`, and rejects the file
otherwise. A truthful post-boundary record cannot meet that condition without asserting
something false. Sections 4.7 and 11 already designate this register for changes made after
execution starts, and `F9_IGNORE` already exempts it from the ledger's own accounting, so the
frozen protocol's existing structure is the correct home. No new register was invented.

### A47.1 — the inaugural execution and its boundary

The inaugural confirmatory execution of this frozen study crossed its one-way boundary at

    89360b30de480231efdc89157443779d45b37db2

on branch `worktree-pdf-study-confirmatory-run`. That branch was archived externally and is
**not present on `origin`**, and the boundary commit is **not a reachable git object on
`develop`**. Its absence from the current branch is an artifact of archival and branch
deletion. **It is not evidence that the boundary was never crossed**, and the population is
not restored to a pre-execution state by it.

Corroboration is the archive bundle
`pdf-external-validity-run1.bundle`, SHA-256
`1ced656958c056ddc98bc4c2d1e53a91b4846e1f9e2ddabdf2e9ae1674ac4bb1`, containing
`refs/heads/worktree-pdf-study-confirmatory-run`, together with the closure report at SHA-256
`fcc0e171e157a61a1483798570d09d98308f3d82f835155010ba5e7a194a8277`.

### A47.2 — the population is EXPOSED

**All 17 frozen holdout members underwent H/X extraction during Run 1.** This is not an
inference from the run's ambition; it is the canonical code path.
`execute_study.build_document_frame_for` calls `run_hybrid.run(...)` for the H arm and
`run_extended.run(...)` for the X arm, once per descriptor, and `write_frames` ran it over the
complete frozen population: **17 of 17 members, 4,190 pages**, `PAGE_LIMIT = None`.

### A47.3 — results already visible, and which

Section 11 requires this list explicitly. At the time of writing, these result-bearing facts
about the frozen population are known to anyone amending the study:

| quantity | value |
|---|---|
| D-frame region census | **13,992** (budget 60, so Rule 1 **cannot** choose corrected extended glyph; `INSUFFICIENT_COMPARATIVE_EVIDENCE`) |
| S1 liveness control | **17 / 17 documents firing** |
| P-head | **12 documents / 2,864 pages** |
| Canonical frames | 17/17 frames, 4,190 pages, SHA-256 `e33d9f79…1706` |

Everything after that point is **absent**. Run 1 stopped before the canonical
`cross_engine_control.json`, before `score_metrics`, before the oracle key, before any
adjudication by any human or AI, before `scores.json`, and before `decide_architecture`. **No
architecture decision was reached or may be drawn**, including `HYBRID_BY_PRIOR`.

### A47.4 — what a continuation may claim

**Permitted:** the same 17 members may be used to **complete the inaugural execution** as a
transparently qualified continuation following a post-boundary apparatus deviation.

**Forbidden:** representing that work as a fresh, pristine, or independent confirmatory
execution. The holdout has been measured; a second measurement of it is a continuation of the
first, not a replication of it.

A genuinely fresh confirmatory claim would require a **new study and a new freeze over a new
unseen population**. That is out of scope here and is not authorized by this ruling.

The invariant the pre-execution ledger protects is that no change *"can have been selected for
the answer it produces"*. That guarantee no longer holds at full strength for any change made
from Run 1 onward, because the amender has seen the quantities in A47.3. This ruling does not
repair that; it discloses it, which is the only available remedy.

### A47.5 — A45 is a post-boundary result-bearing repair

A45 (PR #637) repaired the canonical cross-engine handoff **after** the boundary at
`89360b30` had been crossed and after the holdout had been opened. It is recorded in the
pre-execution ledger as a `SUBSTANTIVE` amendment carrying `confirmatory_output_at_time:
"none"`. Under that file's own definition, where "confirmatory output" means the canonical
score artifact, that classification is **literally defensible**: Run 1 never produced
`scores.json`.

It is nonetheless **chronologically misleading on its own**, and this ruling supplies the
missing context rather than rewriting the ledger. The ledger is append-only, and editing a
past entry to make the history read better would be the defect, not the fix. A45's entry
stands; **read it as qualified by this section.** A45 is not reopened: the tuple-authority
repair is correct on its own merits and remains closed.

**Consequence under 4.7:** every result **value-dependent** on A45 is
**NON-CONFIRMATORY**. That is the qualification channel, enumerated in A47.6.

### A47.6 — the A45-affected surface, traced rather than assumed

The dependency was traced through the real code, not taken from the expected shape:

    cross_engine_control._control_record        document_sha256 from the authority-checked descriptor
      -> cross_engine_result                    verified_sha256, then
      -> methodology_contracts.cross_engine_pages(sha, pages)
                                                ranks the sample over (document_sha256, page_number)
      -> sampled_pages                          WHICH PAGES ARE MEASURED
      -> x09 gate verdict -> row["passed"]
      -> row["qualification"]                   PDFIUM-CONDITIONED FRAME, or None
      -> score_metrics.qualification()          per_document, both_headlines_qualified,
                                                headline_qualifications RQ1 / RQ2
      -> attached to every per-document surface  qualification, M0, M7, M9,
                                                headings_by_frame, paired_differences,
                                                section 8 event rows
      -> decide_architecture                    REPORTING BLOCK ONLY

The path is **wider than the four-step summary** it is usually described by, because
`score_metrics` deliberately attaches the label to every applicable result surface rather than
to one parent block. It is nonetheless confined to the **qualification channel**.

**Verified NOT affected**, each checked at the source:

| surface | why it is unaffected |
|---|---|
| metric **values** | the qualification is an additive sibling key (`{**block, "qualification": …}`); no metric value is derived from it |
| the **architecture decision** | A27.6 keeps cross-engine out of the Rule 3 gate vector; `decide_architecture` carries it in a reporting block and `decision_blocking` is `False` |
| **denominators** | the artifact is exact-set-equality checked against the scored frames; it does not move the frames denominator |
| **population** | membership unchanged at 17 |

**Availability is not value-dependence.** Without A45, `score_metrics` cannot run at all, so
every score is *enabled* by A45. Only the qualification channel is *valued* by it. Section
4.7 labelling follows value dependence. This is exactly the distinction that stops a single
apparatus repair from voiding an entire run.

### A47.7 — A46 is disclosed, with no result consequence assigned

A46 (PR #640) retired design-era working material after the boundary was crossed. It is
disclosed here chronologically for the same reason A45 is.

**No non-confirmatory consequence is assigned**, because no causal path was found from the
cleanup to any reported quantity, gate, population, architecture decision, or reproducibility
property. The two removed probes own no live invariant: `x06_m6_feasibility` measured M6,
which **A20 STRUCK**, and `x19_raster_edge_diagnostic` states no pass threshold by
construction. Every removed evidence artifact was re-run and rewrote byte-identically before
deletion. G5's result-bearing surface remains 15 files with no member touched.

If a causal path is later demonstrated, this section is the place to append it.

### A47.8 — which gates this could move

| gate | effect |
|---|---|
| `x04` F1–F11 | none; freeze integrity is unchanged and still COMPLETE |
| `x04` **F12** (new) | the continuation record must exist, be committed, and describe **this** frozen population |
| `x04` **G7** (new) | result-bearing toolchain versions must match those Run 1's reproducibility claim is scoped to |
| `x04 --authorize-execution` | **REFUSED** while the population is EXPOSED; a pristine boundary can no longer be created for these 17 members |
| metrics / scores | no value moves; the qualification channel additionally carries `confirmatory_status` |
| architecture decision | none (A27.6) |

### A47.9 — toolchain drift, recorded as part of this ruling

Run 1's byte-identical rebuild claim is scoped to macOS/arm64, Python 3.12.12, pypdfium2
5.12.1 and PyMuPDF 1.28.2. Investigation found that scoping **was not enforced**:

- `pypdfium2` is pinned exactly at 5.12.1 in `uv.lock`, and floored at `>=5.12.1` in
  `pyproject.toml`. The floor alone would admit a newer engine; the lock is what binds.
- **`pymupdf` appears in neither `pyproject.toml` nor `uv.lock`**, while being imported by
  nine study probes, two of which are on the G5 result-bearing surface
  (`cross_engine_control.py`, `control_fixtures.py`). It was an **ambient, unpinned,
  result-bearing dependency**.

  This is stronger than "unpinned", and it was verified rather than inferred. A clean
  `uv sync` in this repository does **not** install PyMuPDF, and the documented invocation
  form fails outright:

      $ uv run python probes/x27_score_metrics.py
      File "probes/build_oracle.py", line 41, in <module>
          import pymupdf
      ModuleNotFoundError: No module named 'pymupdf'

  So the study's own result-bearing probes are **not runnable in the project's declared
  environment at all**. Run 1 was executed against an interpreter carrying PyMuPDF from
  outside the project's dependency management, at a version nothing recorded except the
  closure report's prose. Whoever runs the continuation must do the same, and the version
  they happen to have is what decides the oracle stimuli and the cross-engine qualification.

PyMuPDF is not incidental here: it renders the oracle stimuli that adjudication reads, and the
cross-engine control re-measures through it to decide the PDFIUM-CONDITIONED FRAME
qualification. A silent version change is therefore result-bearing on both surfaces. G7 makes
the drift detectable at gate time instead of invisible.

### A47.10 — the continuation record was certifying itself, and now does not

**Found by trying to falsify the authority rather than to confirm it.** F12 checked that the
record was committed, well-formed, and described the frozen population. Two of its three
historical identity fields were anchored to facts outside the record:

| field | independent fact it is checked against |
|---|---|
| `population.population_freeze_commit` | `POPULATION_FREEZE_COMMIT`, pinned in `x04` |
| `population.membership_blob` | the live blob of the committed manifest |
| `prior_execution.boundary_commit` | **nothing** |

The third is the one the whole ruling rests on, and it was the one nothing checked. Because
Run 1's branch was archived and deleted, the boundary commit is **not a reachable git object
on `develop`**, so no other repository fact contradicts a rewrite of it. **Measured**: an
otherwise valid, committed, internally consistent record with `boundary_commit` replaced left
F12 **GREEN** and the population still reported EXPOSED under a fabricated boundary.

**Repair, deliberately the smallest one.** The commit is now **pinned in `x04`** as
`PRIOR_EXECUTION_BOUNDARY`, exactly as `POPULATION_FREEZE_COMMIT` is pinned and for the reason
that constant's own comment already gives: a historical fact must not be derived from the
thing it is supposed to constrain. No registry, no signing, no provenance framework.

**Isolation proof.** With the pin in place the mutation is refused; with *only* the pin
neutralised and every other check left standing, the identical record is **accepted**. The pin
is therefore the sole reason for the refusal.

**What would make the repaired check fail.** A single commit editing **both** `x04`'s pinned
constant **and** the record. That is no longer an ordinary artifact mutation: it edits a
protected file, so F9 requires it to be declared commit-by-commit in a register, and it
appears in review as a change to gate code rather than to data. The check is not proof against
a determined coordinated edit, and does not claim to be; it removes the *single-artifact*
rewrite, which is what self-certification meant here.

### A47.11 — the PyMuPDF defect is fixed, not only detected

A47.9 recorded that PyMuPDF was undeclared and that G7 could detect the wrong version but
could not supply the right one. That is now closed at the source:

- `pymupdf==1.28.2` is declared in `[dependency-groups].dev` and locked.
- It is **not** added to the published engine dependencies: shipping DeltaTrack to diff two
  bill versions must not install a second PDF engine (#367).
- G7's exact-version assertion is unchanged.

**Verified from the declared environment**, not argued: a clean `uv sync` installs it,
distribution metadata reports `1.28.2`, and `uv run python probes/x27_score_metrics.py` — the
exact invocation that previously died on `ModuleNotFoundError` — now runs to **194/194**.

The 193/194 previously reported for that suite was an artifact of an ad-hoc interpreter that
lacked the declared environment; the failing control is the renderer-free child-interpreter
probe, which cannot be meaningful in an environment that was never constituted correctly. No
x27 control was edited to achieve this.

### A47.12 — the §4.7 status was self-supplied, and is now an invariant

**The defect.** §4.7 makes NON-CONFIRMATORY a **requirement** that A45-dependent results are
validated against. The machinery instead treated it as a **value the study supplied**:
`CONTINUATION.json` carried the status, `a45_status()` returned that field verbatim, the
cross-engine producer stamped whatever came back, the scorer required only that the field
**exist**, and x30 took its expected value from the same record. Authority, result and oracle
could therefore move together.

**Measured before repair**, with the record's status changed to `"CONFIRMATORY"` and treated
as committed. All five steps failed open:

| step | as found |
|---|---|
| A `continuation_state()` / F12 | **GREEN** |
| B `a45_status()` | returned **`CONFIRMATORY`** |
| C real cross-engine producer | **stamped `CONFIRMATORY`** into an artifact |
| D `score_metrics` | **accepted it**; the scored row carried `qualification_status='CONFIRMATORY'` |
| E x30 oracle | **would have moved with the record** |

A post-boundary deviation would have been reported as confirmatory with every gate green.

**Repair, at four boundaries, each independent of the record.**

| boundary | what now holds |
|---|---|
| accessor | `a45_status()` **validates** the claim against `NON_CONFIRMATORY` and returns the **constant**, raising `A45_STATUS_MISMATCH` otherwise |
| authority | `continuation_state()` calls it, so a record claiming another status **fails F12** |
| producer | stamps through the accessor, so it **cannot emit** a fabricated status |
| scorer | `WRONG_CONFIRMATORY_STATUS` refuses a **present but incorrect** value, not only a missing one |

The scorer holds its own constant, `REQUIRED_CONFIRMATORY_STATUS`, because its frozen consumer
allowlist forbids importing the provenance module, and an expectation imported from the thing
under test is not an expectation. x30 asserts the two constants agree so they cannot drift.

**Post-repair, the same mutation is closed at every step:** F12 fails, the accessor raises, the
producer writes no artifact, and the scorer refuses. The record may still carry the
human-readable status; it may no longer decide it.

**Redundancy removed.** The presence-only scorer control was replaced rather than kept
alongside the new one: it proved only that `_require` fires, while the mutation that actually
produced a mislabelled result was a nonempty wrong value. One control now covers both shapes.

---

## A48 — POST-BOUNDARY APPARATUS DEVIATION

```json
{"id": "A48", "kind": "DEVIATION",
 "commits": ["55c35c04", "090716f8", "8a201a6f"],
 "classification": "POST-BOUNDARY APPARATUS DEVIATION",
 "made_after_boundary": "de60dddf906bc4b01e5ffbe9af4d3e833a9a2be7 (continuation boundary)",
 "results_already_visible": {
  "d_frame_census": 13992,
  "oracle_route_composition": "ai_route 122 / human_route 15417 / c_audit 25 / controls 20",
  "cross_engine": "17/17 measured, n_qualified 0, qualification_applies false",
  "s1_documents_firing": "17/17",
  "p_head_documents": 12,
  "p_head_pages": 2864
 },
 "affects_membership": false,
 "affects_scoring_rule": false,
 "affects_metric_values": false,
 "affects_architecture_decision": false,
 "files_touched": ["probes/methodology_contracts.py", "probes/build_oracle.py",
                   "probes/score_metrics.py", "probes/decide_architecture.py",
                   "probes/x21_build_oracle.py", "probes/x28_decide_architecture.py",
                   "probes/x31_dframe_budget_routes.py",
                   "probes/x27_score_metrics.py"],
 "why_not_an_amendment": "Made after the continuation boundary was committed, with the realized census and route composition already visible. PRE-EXECUTION-AMENDMENTS.md requires confirmatory_output_at_time == 'none' on every record and is the PRE-execution ledger."}
```

**This repair was made with the realized result in view, and says so.** The D census of
13,992 and the full oracle route composition were already committed and visible when it was
written. It is not a pre-execution amendment and is not recorded as one. A47 is unchanged.

### A48.1 — the defect

A27.3 fixes the D-frame budget: **≤ 60 regions** → human-adjudicate the complete census and
Rule 1 may be evaluated; **> 60 regions** → **Rule 1 cannot choose X**, the outcome is
`INSUFFICIENT_COMPARATIVE_EVIDENCE`, and a 60-region sample is permitted for **descriptive
diagnosis only**.

The budget had exactly one owner, `decide_architecture.D_FRAME_REGION_BUDGET`, applied at
**decision step 4**. Every upstream component derived "required route" from **raw frame
membership** instead:

| site | behaviour |
|---|---|
| `build_oracle.StimulusSpec.frame_routes` | `D in frames` → human, unconditionally |
| `human_answer_purposes` | `D in frames` → `PURPOSE_D_DECISION`, unconditionally |
| `build_oracle.validate_adjudicated` | every route named in the key must have an answer |
| `score_metrics.validate_inputs` | calls that validator **before any metric exists** |
| `score_metrics._required_r1_routes` | a second frame→route implementation, same defect |

So a census of 13,992 made **15,372** human answers a hard prerequisite for producing *any*
metric, for a route A27.3 had already made non-decision-bearing. The evidence gate sat
upstream of the rule that excused the evidence.

**Measured before repair**, on real machinery with synthetic material at D = 61: dropping only
the human answers whose sole purpose was the Rule 1 D decision produced
`ADJUDICATION_ROUTE_MISSING`.

### A48.2 — the reading, and the one owner

Read with A36.6: a repeat inherits its primary's **required** routes, and "required" means
**result-bearing**. A route A27.3 has made non-decision-bearing is therefore not required, it
creates no human R1 arm, and it is **absent rather than `NOT_EVALUABLE`**.

The budget and its predicate now have a single executable owner,
`methodology_contracts.d_decision_route_required`, and the frame→route map has a single owner,
`build_oracle.frame_required_routes`, which `score_metrics` calls rather than restating.
`decide_architecture` **re-exports** the constant instead of redefining it. `build_oracle`
reads the realized census from the same committed `counts["d_frame_census"]` the decider reads,
so the two cannot be looking at different censuses.

**Nothing else moves.** The numeric budget, D membership, the full census and its reporting, C
membership and selection, C/D overlap, truth-source semantics, R1 selection identities and
thresholds, C-audit selection, controls, metric definitions, Rule 0, Rule 1, Rule 3 and the
decision ordering are untouched. The optional 60-region descriptive sample remains omitted.

### A48.3 — realized consequence

Derived from the already-committed real key, without opening any image:

| | before | after |
|---|---|---|
| AI route | 122 | **122** |
| human route | 15,417 | **45** (25 C-audit + 20 human-route controls) |
| R1 required-route population | ai + human | **AI only, 6 pairs**; 1,395 D-only repeats require no route |

### A48.4 — section 4.7 status

A48 changes **which adjudication inputs are consumed**, so it is value-bearing for anything
computed from that set. It takes the same §4.7 status **class** as A45/A47 but its **own
literal**, because the A45 label names A45 and this is a different deviation:

    NON-CONFIRMATORY (PRE-REGISTRATION 4.7 -- A48 post-boundary deviation)

Held as a constant in `score_metrics` and in `decide_architecture`, never read from this
document or any other mutable record, so nothing under test supplies its own expected
provenance. Applied to `r1_reliability` only where A48 actually moved it (census over budget)
and to the decision artifact's **attribution** only where `decided_by` turns on that R1 gate.

**The final architecture outcome enum is invariant to A48.** Demonstrated executably over the
real decider across all four Rule 0 states at D > 60: with R1 forced to PASS and to FAIL the
outcome is identical in every state (`EXTENDED_BY_RULE_0_M9`, `HYBRID_BY_RULE_0_M9`, or
`INSUFFICIENT_COMPARATIVE_EVIDENCE`). At D > 60 Rule 1 cannot choose X, so the enum is fixed by
the committed M9 facts and the census alone. The decider was **not** reordered and no rule was
changed to obtain this; it is a property of the frozen ordering.

### A48.5 — the committed oracle key

The key committed at `7afbc344` is semantically wrong in **private route metadata only**:
`adjudication_routes`, `human_answer_purposes`, `n_human_tasks`, and the key-level
`human_route` / `human_tasks` counts.

**Proven by executable control**, building the same synthetic population twice with only the
predicate differing: blind ID set, presentation order, canonical and base identities, R1 base
identities, C/D membership, C-audit selection, repeat flags, bboxes, DPI, `png_sha256`,
region–line bijection, image names, control kind and variant, `prompt_sha256`, **every PNG
byte**, and the **entire blind artifact byte-for-byte** are identical. Only the three
per-stimulus route fields and the two human counts differ.

The real key was **not** regenerated and **not** hand-edited in this round.

### A48.6 — an A47.12 regression found and fixed

`x28_decide_architecture` could not run at all on `develop`: A47.12 made
`confirmatory_status` a required, value-checked field on the cross-engine artifact, and x28's
own fixture predated it, so the entire architecture-decider suite failed at input validation.
Reproduced on clean `86e48de`. The fixture now carries the scorer's own constant. No decider
rule was touched.

### A48.7 — closure review: the first repair had only reached validation and R1

**Chronology, recorded exactly.** The first A48 pass conditioned route *derivation*
(`frame_routes`, `human_answer_purposes`, `_required_r1_routes`) and its control asserted
through a helper that ran `validate_adjudicated` plus `r1_reliability`. That helper was named
`full_path`, and it was not: `score_metrics.score` went on walking
`(D_FRAME, PURPOSE_D_DECISION)` in `heading_metrics` and demanding a human answer for **every**
D primary. So the 45-item workload had never traversed the result-bearing scorer, and the
control read green because it never called it.

Closure review caught this before merge. **Execution was still blocked throughout and no
adjudication had occurred**, so nothing was scored on the false-green.

**Measured before the second repair**, through the real `SM.score` at D=61 with exactly the
A48-required adjudication (all required AI, 25 C-audit human, 20 control human, no D-only
human): `ADJUDICATION_ROUTE_MISSING {route: 'human'}`.

**Repairs.**

1. `heading_metrics` consumes the D estimand only while the D route is result-bearing. The D
   rows are **omitted, not zeroed**: a zero M1–M5 block would assert the arms were measured and
   agreed on nothing, which this run never gathered. The payload states which it is, in
   `d_estimand_status`.
2. **The key may no longer self-certify its A27.3 state.** `validate_inputs` re-derives the
   census by summing each committed frame's producer-declared `counts["d_frame_census"]`,
   requires exact equality with `oracle_key["d_frame_census"]`, and requires the key's
   `d_decision_route_required` to equal `MC.d_decision_route_required(committed census)`.
   D membership is not re-derived from region contents; the committed counts remain the
   producer's census. A coordinated key claiming 61 over a real 60-region census is refused
   (`D_CENSUS_MISMATCH` / `D_BUDGET_CLAIM_MISMATCH`) before any metric is produced. This
   matters because a true census of 60 is exactly where Rule 1 **may** select X.
3. `build_oracle` **fails closed** on a frame with no declared `d_frame_census`. Absent is not
   0: 0 is within budget and would silently excuse Rule 1's evidence.

The helper is renamed `validation_and_r1` and kept only where validation and R1 really are the
semantics under test. The end-to-end arms call the real scorer and the real decider.

**`decided_by` is not invariant, and the enum-invariance claim needed this qualification.**
Re-measured across all Rule 0 states at D>60: the outcome **enum** is identical under R1 PASS
and R1 FAIL, as previously reported, but the **attribution** is not. Where Rule 0 decides,
`decided_by` is `RULE_0_M9` either way. Where Rule 0 does not decide, the enum is
`INSUFFICIENT_COMPARATIVE_EVIDENCE` either way while `decided_by` flips between
`BUDGET_A10_A27_3` (R1 PASS) and `RULE_3_GATE` (R1 FAIL). A48 changes R1's required-route
composition, so it can move that attribution. Reported rather than smoothed over.
