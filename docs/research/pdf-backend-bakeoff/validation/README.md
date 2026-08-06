# Adversarial validation of the bake-off's hybrid conclusion

Start here. This directory is an independent falsification pass over
[`../RESULTS-HYBRID.md`](../RESULTS-HYBRID.md), run on the assumption that its conclusion
might be wrong. It adds nothing to the spike and changes nothing in it.

**Read in this order:**

| | what it answers |
|---|---|
| 1. [`FINDINGS.md`](FINDINGS.md) | Does the hybrid conclusion survive independent evidence? Fifteen questions, every major result classified, and the architectural claim graded. |
| 2. [`phase2/FINDINGS-EXTENDED-GLYPH.md`](phase2/FINDINGS-EXTENDED-GLYPH.md) | Phase 1 opened a third option the spike never scored. Is it feasible, and is it better? |
| 3. [`phase3/FINDINGS-CROSS-BACKEND.md`](phase3/FINDINGS-CROSS-BACKEND.md) | Phase 2 tied the two seams inside one engine and then claimed engine independence without measuring it. Does the extended rule hold up when a different engine supplies the facts? |

## How the argument got here

Each step exists because the one before it was falsified or left something unmeasured.
None of them is a rewrite of its predecessor; the earlier artefacts and their numbers are
all still in the tree.

| | what happened |
|---|---|
| 1. neutral glyph bake-off | six backends against one contract. Headline withdrawn by its own red team. |
| 2. confirmatory run | pre-registered. Found both PDFium builds produce 302 heading labels production does not. |
| 3. the hybrid hypothesis | `RESULTS-HYBRID.md`: put the engine's characters and word spaces below the seam, keep GPO interpretation above it. |
| 4. adversarial validation | phase 1 here. The hybrid **beats** the shipped glyph rule on adjudicated truth, and the **stated reason** for it is falsified: PDFium's word-space rule is public geometry and is reimplementable above the seam. |
| 5. extended glyph, phase 2 | build that third option and score it. It **ties** the hybrid inside PDFium: 0 disagreements on 72 adjudicated pairs, 53 ok / 0 bad on the heading failure cases. Accuracy stops discriminating. |
| 6. cross-backend test, phase 3 | phase 2 then asserted that the tie *generalises* across engines. It does, measured: 0.9683 from three engines, 1 disagreement in 195,291 pairs, byte-identical text on four of five documents. Phase 3 also found two defects in phase 2's own work. |

## The three verdicts, in one paragraph each

**Phase 1 — SUPPORTED BUT NOT CONFIRMED.** The hybrid seam beats the shipped glyph seam on
72 independently adjudicated word boundaries (0.968 against 0.937), on labels PDFium did
not produce, and the two fail in opposite directions: the glyph rule welds words together,
the engine splits them. But the *stated reason* for the conclusion is falsified. PDFium's
word-space rule is published and is pure geometry over pen origins and font advance widths;
reimplementing it above the seam reproduces the engine's decisions almost exactly. Three
further claims in the report are wrong as written (PyMuPDF's `synthetic` flag, `IsHyphen`
being "available to no other layer", and generated `x0` being `None`).

**Phase 2 — accuracy stops discriminating; the hybrid stays preferred on architecture.** The
extended-glyph alternative is feasible: PDFium supplies its own advances, the fields are
reachable in the browser build with no wrapper work, and three of four backends can emit
them. Built and scored, it ties the hybrid exactly — zero disagreements on the adjudicated
sample, 53 ok / 0 bad on the heading failure cases. The recommendation therefore turns on
cost and ownership, not on a score, and it lands on the hybrid **for a corrected reason**,
with three stated conditions that would flip it.

**Phase 3 — the portability claim is CONFIRMED, and two phase-2 defects are not.** Phase 2's
comparison table asserted "word quality if the backend changes: fixed, the rule is ours".
Built for real, with pdfminer.six and PyMuPDF each answering from their own API and no value
borrowed from PDFium, the same rule scores **0.9683 from all three engines**, disagrees with
none of them on the 72 adjudicated pairs, and disagrees once in 195,291 pairs at page scale.
The mechanism is narrower than the phrasing: over 390,582 endpoints the engines return
**advances identical to 0.0 pt**, so the contract is not normalising a difference, it is
asking for one that does not exist. Phase 3 also found that `pdfium_extended.py` was
consuming PDFium's generated spaces despite its docstring, and that
`contract_extended.font_size` has no defined axis. Neither moves a phase-2 number; both are
recorded rather than repaired.

## What a reviewer should check first

1. **Blinding is enforced by commit order, not by intent.** The frozen sample, then the
   adjudication, then the key join, in that sequence in `git log`. The sample-identity
   digest (`results/v04_sample.sha256`) holds across every re-render.
2. **`FINDINGS.md` §Reliability** — this review reports a defect in its own adjudication
   (six identical stimuli answered 3–3) rather than repairing it silently. Both repairs are
   labelled post-hoc because both move the numbers the same way.
3. **The corrections sections at the end of all three documents** — each phase lists where it
   was wrong first time, including a vacuous pass in its own harness, and phase 3 corrects
   two of its own controls as well as three of phase 2's claims.
4. **The negative controls.** Every phase-3 table has one, because the expected result there
   was a tie and a tie is what a broken harness also produces. The load-bearing ones: the new
   adapter reproduces phase 2's column item for item (N1); perturbing the advances moves the
   answers (N2); feeding the rule the wrong pdfminer field collapses it to 0.6087 (N3); and
   the page-scale sabotage curve is reported in full, including the finding that the decision
   test is nearly blind below a 25 % advance error, which is why the portability claim rests
   on comparing the facts (N12) rather than the decisions.
5. **What is still untested**, listed explicitly in all three: no valid heading-level oracle
   and no fresh structure-rich holdout. Those two are blocking for an ADR, and phase 3
   closes neither.

## Reproduction

Probes are `v01`–`v09` here, `g01`–`g07` in [`phase2/`](phase2/) and `h01`–`h05` in
[`phase3/`](phase3/); raw output is in the `results/` directories. Every number in all three
documents comes from those files; none is transcribed by hand. Run from the repo root with
`.venv/bin/python`, except `phase2/g02_wasm_advance.mjs` and `phase3/h02_pdfjs_percharacter.mjs`,
which need `NODE_PATH=../../probes/js/node_modules node`.

Phase 3 needs the benchmark backends installed
(`probes/requirements.txt`: pdfminer.six 20260107, PyMuPDF 1.28.0). PyMuPDF is AGPL-3.0 and
is a ceiling reference only, per [`../LICENSING.md`](../LICENSING.md); phase 3 scores it and
does not propose it.

## Preservation

The pre-validation spike is tagged **`pdf-bakeoff-prevalidation`** and hashed file-by-file
in [`PRESERVED-MANIFEST.txt`](PRESERVED-MANIFEST.txt), which remains the authority: every
spike artefact can still be verified byte-for-byte against it.

**The trade this section used to describe as unmade has now been made, deliberately.**
Until 2026-08-06 nothing outside this directory was touched, so
`git diff pdf-bakeoff-prevalidation HEAD -- <spike> ':!validation'` was empty, and that
one command proved the audit had not edited the thing it was auditing. The cost was that a
reader arriving at the spike's own front door had no path to the work that partly overturns
it. Three pointers were added, and the check becomes: **exactly three files differ, and
each diff is an added pointer block and nothing else.**

```
git diff --stat pdf-bakeoff-prevalidation HEAD -- \
    docs/research/pdf-backend-bakeoff ':!docs/research/pdf-backend-bakeoff/validation'
```

must list only `README.md`, `RESULTS.md` and `RESULTS-HYBRID.md`. Drop `--stat` to confirm
the content: **additions only, no deletions, no changed line** (23 insertions, 0 deletions
as of this writing). Every other spike file, and the prior content of those three, still
verifies against the manifest and the tag.

The manifest check is the stronger of the two, because it fails loudly rather than
silently. From `docs/research/pdf-backend-bakeoff/`:

```
grep '^[0-9a-f]' validation/PRESERVED-MANIFEST.txt | shasum -a 256 -c
```

112 entries, of which exactly three report `FAILED` and every other reports `OK`. Those
three are the pointer blocks. **A run where nothing fails would mean the check is not
reading the files at all**, which is worth knowing: this command is one of the few here
that has a known-bad case built into it.

**No spike conclusion was edited to agree with this directory.** `RESULTS-HYBRID.md` keeps
its falsified rationale in place and says so at the top, on the same principle that keeps
`RESULTS.md`'s withdrawn headline verbatim below its own audit.
