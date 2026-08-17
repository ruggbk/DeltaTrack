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
 "commits": ["7b08b6f"],
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
 "affects_metric_values": false,
 "affects_architecture_decision": false,
 "non_confirmatory_paths": ["cross-engine qualification channel (A45-dependent)"],
 "files_touched": ["probes/continuation_provenance.py", "probes/x04_freeze_check.py",
                   "probes/cross_engine_control.py", "probes/score_metrics.py"],
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
