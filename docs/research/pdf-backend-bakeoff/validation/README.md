# Adversarial validation of the bake-off's hybrid conclusion

Start here. This directory is an independent falsification pass over
[`../RESULTS-HYBRID.md`](../RESULTS-HYBRID.md), run on the assumption that its conclusion
might be wrong. It adds nothing to the spike and changes nothing in it.

**Read in this order:**

| | what it answers |
|---|---|
| 1. [`FINDINGS.md`](FINDINGS.md) | Does the hybrid conclusion survive independent evidence? Fifteen questions, every major result classified, and the architectural claim graded. |
| 2. [`phase2/FINDINGS-EXTENDED-GLYPH.md`](phase2/FINDINGS-EXTENDED-GLYPH.md) | Phase 1 opened a third option the spike never scored. Is it feasible, and is it better? |

## The two verdicts, in one paragraph each

**Phase 1 — SUPPORTED BUT NOT CONFIRMED.** The hybrid seam beats the shipped glyph seam on
72 independently adjudicated word boundaries (0.968 against 0.937), on labels PDFium did
not produce, and the two fail in opposite directions: the glyph rule welds words together,
the engine splits them. But the *stated reason* for the conclusion is falsified. PDFium's
word-space rule is published and is pure geometry over pen origins and font advance widths;
reimplementing it above the seam reproduces the engine's decisions almost exactly. Three
further claims in the report are wrong as written (PyMuPDF's `synthetic` flag, `IsHyphen`
being "available to no other layer", and generated `x0` being `None`).

**Phase 2 — accuracy stops discriminating; recommend the hybrid on architecture.** The
extended-glyph alternative is feasible: PDFium supplies its own advances, the fields are
reachable in the browser build with no wrapper work, and three of four backends can emit
them. Built and scored, it ties the hybrid exactly — zero disagreements on the adjudicated
sample, 53 ok / 0 bad on the heading failure cases. The recommendation therefore turns on
cost and ownership, not on a score, and it lands on the hybrid **for a corrected reason**,
with three stated conditions that would flip it.

## What a reviewer should check first

1. **Blinding is enforced by commit order, not by intent.** The frozen sample, then the
   adjudication, then the key join, in that sequence in `git log`. The sample-identity
   digest (`results/v04_sample.sha256`) holds across every re-render.
2. **`FINDINGS.md` §Reliability** — this review reports a defect in its own adjudication
   (six identical stimuli answered 3–3) rather than repairing it silently. Both repairs are
   labelled post-hoc because both move the numbers the same way.
3. **The corrections sections at the end of both documents** — each phase lists where it
   was wrong first time, including a vacuous pass in its own harness.
4. **What is still untested**, listed explicitly in both: no valid heading-level oracle and
   no fresh structure-rich holdout. Those two are blocking for an ADR.

## Reproduction

Probes are `v01`–`v09` here and `g01`–`g07` in [`phase2/`](phase2/); raw output is in the
`results/` directories. Every number in both documents comes from those files; none is
transcribed by hand. Run from the repo root with `.venv/bin/python`, except
`phase2/g02_wasm_advance.mjs`, which needs
`NODE_PATH=../../probes/js/node_modules node`.

## Preservation

The pre-validation spike is tagged **`pdf-bakeoff-prevalidation`** and hashed file-by-file
in [`PRESERVED-MANIFEST.txt`](PRESERVED-MANIFEST.txt). Nothing outside this directory was
modified or added:

```
git diff --stat pdf-bakeoff-prevalidation HEAD -- \
    docs/research/pdf-backend-bakeoff ':!docs/research/pdf-backend-bakeoff/validation'
```

is empty. That is why the spike's own entry points do not link here — adding a link would
end the property. If you would rather have the cross-link than the guarantee, that is a
deliberate trade and it has not been made.
