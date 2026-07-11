# Provision matching across bill versions — research

Research supporting epic [#175](https://github.com/AgoraDMV/DeltaTrack/issues/175) and
issue [#170](https://github.com/AgoraDMV/DeltaTrack/issues/170): how to match the same
provision across two versions of a bill when text alone is not enough (stub→expansion,
reused section numbers, shared boilerplate, deliberate consolidation).

This is a **multi-study program** (see `paper.md` §10). Each study is a self-contained
deliverable that can revise the ones before it.

## Contents

| File | What it is |
|---|---|
| `paper.md` | **Study 1** — the deliverable: problem characterization, method survey, and the measured finding that rare-token containment resolves the stub→expansion pattern word-overlap cannot. Plain-language summary (Part 1) + technical study (Part 2). |
| `paper.html` | Shareable render of `paper.md`. **Generated** — regenerate, don't hand-edit (see below). Not committed. |
| `methodology.md` | The fuller working draft `paper.md` formalizes (signal inventory, method families, head-to-head). |
| `problem-framing.md` | Short naming note: what class of problem this is, so we can borrow solutions. |
| `spike.md` | The structural-signal spike — what works on our corpus. |
| `pass2-protocol.md` | Execution protocol for **Study 2** (expand + re-stratify the labeled dataset): miners, labeling, adjudication, held-out split. |
| `probes/` | Reproducibility scripts — every number in `paper.md` comes from one of these. |

## Reproduce

Run from the repo root with the repo venv:

```
PYTHONPATH=. .venv/bin/python docs/research/provision-matching/probes/<script>.py
```

`paper.md` Appendix A maps each probe to the numbers it produces. The probes read the
XML corpus under `bills/` (fetch via `scripts/fetch_test_assets.py`) and the labeled
answer key at `test_data/similarity_labels.json`.

Regenerate the HTML render after editing `paper.md`:

```
PYTHONPATH=. .venv/bin/python docs/research/provision-matching/probes/build_artifact.py
```

## Next step

Study 1 concludes (§9) that the **blocking prerequisite** before picking cutoffs or a
matcher is Study 2: grow the labeled set from 12 pairs toward the low hundreds, add the
two strata the current set cannot test (high-containment *different* pairs; many-to-one
consolidation), and hold out a true test set. `pass2-protocol.md` is the execution plan.
