# Proposed pre-registration: narrow confirmatory run

- Status: **proposal. Nothing has been run against it.** Written 2026-08-05 after the
  [post-spike adversarial audit](RESULTS.md#post-spike-adversarial-audit-2026-08-05).
- Supersedes nothing. [`PRE-REGISTRATION.md`](PRE-REGISTRATION.md) remains the record of
  what the exploratory spike committed to, including the places it drifted.

## Why a second, narrower run

The exploratory spike answered its question and then failed its own audit on the framing.
The audit found nine post-registration methodology changes, two of which moved gates and
one of which *created* the metric the headline rested on. None of that was concealed, but
it means **the spike's numbers are exploratory, not confirmatory**, and they should not be
cited as though a protocol had been fixed in advance.

This proposal exists to make the three claims separable and pre-committed. It deliberately
does **not** re-open the backend field: pypdf and PyMuPDF are settled (failed and
policy-excluded respectively), and re-running them would only add noise.

**The single most important design rule here:** the three concerns below use different
references and license different conclusions, and the exploratory run conflated them. They
are never combined into a single score, a single table, or a single verdict.

| Concern | Reference | Licenses the conclusion |
|---|---|---|
| **A. Production migration parity** | today's pypdfium2 output | "safe to swap without changing what staffers see" |
| **B. Independent document accuracy** | XML, never PDFium | "extracts the document correctly" |
| **C. Security / egress** | network-layer observation | "cannot transmit under policy X" |

**A cannot support a B conclusion.** That substitution is exactly what produced the
withdrawn headline, and it is the failure this document exists to prevent.

---

# Concern A — production migration parity

**Question.** If we replace pypdfium2 with candidate X, does any staffer-visible output
change?

**Candidates.** `pdfium-wasm`, `pdfminer`. (PDF.js only if the operator-list adapter of
Concern B is built.)

**Reference.** Native pypdfium2 through the identical downstream pipeline.

### Frozen population

- **All 15 consecutive corpus pairs**, reported in two strata that are **both** always
  shown: the **13** production accepts and the **2** it declines
  (`115-hr-5895/4→5`, `118-hr-4366/5→6`).
- Membership is derived at runtime from `compare/pdf.py::_is_unnumbered_layout`, not
  hardcoded. If production's guard changes, the strata change with it and the run says so.
- **Rationale for freezing both:** the exploratory run narrowed the population after
  seeing results. Pre-committing to reporting both removes that degree of freedom.

### Frozen metrics

| ID | Metric | Definition |
|---|---|---|
| A1 | Amount identity | `Counter[(old,new,kind)]` over all `amount_entries` equals the incumbent's, exactly |
| A2 | Change identity | `Counter[(change_type, norm(old), norm(new))]` equals the incumbent's, exactly |
| A3 | Amount F1 | precision/recall/F1 of the same multiset, for when A1 fails |
| A4 | Full-text identity | SHA-256 of `pdf_full_text` output equals the incumbent's |

`norm()` is frozen as the current `score_phase2.norm_text`: whitespace runs,
`normalize_glyphs`, soft-hyphen rejoin, margin line numbers, U+FFFD removal. **Widening it
later is a protocol violation**, because every widening inflates agreement.

### Frozen gates

| Gate | Threshold |
|---|---|
| A-1 | A1 holds on **15/15** pairs |
| A-2 | A2 holds on **15/15** pairs |
| A-3 | A4 holds on **52/52** documents |

**Pass = all three.** A candidate failing A-2 but passing A-1 is reported as *"money-safe,
segmentation-divergent"* — a real and useful intermediate state, not a pass.

### Repair mode

**Frozen: report `strict` and `repaired` separately for every metric. `strict` is the
headline.** The exploratory run defaulted to `repaired`, which lifts PDFium's text F1 by
+0.0345 and no other backend's at all. Concern A is largely mode-insensitive (A1/A2 are
identical in both), so this costs nothing here and keeps one convention across all three
concerns.

---

# Concern B — independent document accuracy

**Question.** Which backend reads the document most correctly, judged without reference to
PDFium?

**No metric in this section may take a PDFium-derived value as ground truth.** That
includes breadcrumb agreement, line-number recall referenced to the incumbent, and T4.
If a proposed metric cannot be computed without running PDFium, it does not belong here.

### Frozen population

- The **42 non-enrolled corpus documents** (production-accepted), reported as the primary
  population.
- The **10 enrolled documents** reported separately and never merged in — production
  declines them, and including them is what made pypdf look like a gate-2 failure.
- **Stratified by body font** (`DeVinne` 37 / `NewCenturySchlbk-Roman` 10 /
  `DeVinne-Italic` 5), because the audit found the corpus is effectively one typesetting
  class and an aggregate hides that.
- **Per-bill results are mandatory**, not optional: one bill supplies 6 of 52 documents.

### Frozen metrics

| ID | Metric | Reference | Definition |
|---|---|---|---|
| B1 | Text F1 | XML body | Multiset token F1 after `align_to_body` edge-trim. Both frozen as implemented today |
| B2 | Heading F1 | XML tree | **Level-agnostic**: PDF anchors of kind {account, agency, grouping} against XML labels of level {account, agency, heading}, normalized upper-case, commas and periods stripped |
| B3 | Line-number recovery | the printed page | Exact `(page, line)` set vs the page's own margin numbers, **not** vs the incumbent |
| B4 | Amount presence | independent extractor | Sampled amounts must appear in PyMuPDF `get_text()` of the side claimed |

**B2 is level-agnostic by pre-commitment, and this is load-bearing.** During the audit a
level-by-level comparison produced a *false reversal* (PDFium appearing to over-detect
accounts 46-to-27) because the two pipelines assign different level names to the same
objects — the XML's `agency` holds `Military construction, air force`, which the PDF calls
an `account`. Freezing level-agnostic scoring removes that trap in advance.

### Frozen gates

Concern B produces a **ranking with confidence intervals, not a pass/fail.** Accuracy here
is comparative and the corpus is too narrow for absolute thresholds.

- Report B1–B3 as mean ± bootstrap 95% CI over documents (10,000 resamples, seed 20260805).
- **A backend leads only if its CI does not overlap the runner-up's.** The exploratory run
  reported pdfminer at 0.9131 and PDFium at 0.9126 as though that ordering meant something;
  it almost certainly does not.
- B4 is a floor, not a ranking: **zero** sampled amounts may be absent from the source.

### Mandatory parameter-sensitivity tests

The audit found one constant inside the "neutral" layer that is load-bearing **only for
PDFium**. Sensitivity is therefore part of the protocol, not a follow-up.

| Parameter | Sweep | Pre-committed interpretation |
|---|---|---|
| `_SPACE_FACTOR` | 0.15, 0.20, **0.25**, 0.30, 0.40 | A backend whose B2 moves by >0.05 across the sweep is **parameter-fragile**, and that is reported next to its score |
| `_BASELINE_TOL` | 0.1, 0.3, **0.6**, 1.2, 2.0 | same rule |
| `_CHROME_SIZE_RATIO` | 0.0 (off), 0.45, **0.55**, 0.65 | same rule |
| `upright` filter | on / off | same rule |
| repair mode | strict / repaired | same rule |

**Pre-committed conclusion rule:** the headline ranking is the one at the **default column**
(bold), but *"backend X leads"* may only be written if X also leads at **≥ 4 of 5** settings
of every parameter. A lead that exists only at the tuned default is reported as
*"leads at the default parameterization only"*.

Rationale: `_SPACE_FACTOR = 0.25` was inherited from PDFium-tuned production, and at 0.40
PDFium's B2 collapses 0.586 → 0.206 while PyMuPDF, PDF.js and pypdf are unchanged. Any
claim resting on a single parameter setting is not a finding.

---

# Concern C — security / egress

**Question.** Under a specific, named policy, which mechanisms can transmit document
content?

### Frozen policy under test

```
default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:;
connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none';
frame-src 'none'; worker-src 'none'
```

Note `script-src 'self'` **without** `'unsafe-inline'`. The exploratory policy included it
and was defeated by Speculation Rules as a direct result.

### Frozen vector set

The union of [`vectors.js`](probes/vectors.js) (16) and [`vectors2.js`](probes/vectors2.js)
(19) — **35 mechanisms**, enumerated in those files rather than restated here so the list
cannot drift from the code.

**Adding vectors later is encouraged and is not a protocol violation** — the vector list is
a floor, not a ceiling. Removing one is.

### Frozen validity conditions

A run is **void**, not merely negative, unless all four hold. Each exists because the
exploratory run hit the corresponding failure:

1. **Control leaks.** The no-CSP control must be observed to transmit on **≥ 12 of 35**
   vectors. A harness that cannot see egress cannot report its absence.
2. **Known-bad caught.** A build carrying the policy plus one deliberately permitted beacon
   must be detected.
3. **Vectors ran.** The fixture must report `DONE` and a vector count equal to the frozen
   set. *(A `script-src` variant once reported "0 bypasses" with 0 vectors executed — the
   policy had blocked the harness's own bootstrap. That is a void run, not a pass.)*
4. **Observation at the network layer.** The server's received-request log decides.
   CDP request events are recorded but **never** decide, because a request object exists
   before CSP rules on it.

### Frozen reporting

Three buckets, always all three, because collapsing them is how the withdrawn claim was
written:

| Bucket | Meaning |
|---|---|
| **Blocked** | attempted, no request reached the server |
| **Bypasses policy** | reached the server; CSP was expected to cover it |
| **Outside CSP** | reached the server; CSP has no directive for it (`window.open`, WebRTC, top-level navigation) |

**Pre-committed claim template**, with blanks the run fills and no adjectives:

> Under policy P, of N attempted mechanisms, B produced no request, X bypassed the policy,
> and Y are outside what CSP governs. Verified against a control observed to transmit on C
> vectors and a known-bad build confirmed caught.

**The phrase "permits no subresource or background network egress" is retired** and may not
appear. So is any unqualified "zero egress".

---

---

# Concern D — performance, and why it needs its own protocol

The exploratory run's gate-9 verdict for pdfminer **did not reproduce**: 37.9 s first,
69.2 s on re-run, against a 60 s ceiling. Bare repeat trials of pdfium-wasm show CPU time
≈ wall time, so the difference is machine state, not starvation. Absolute timings in this
spike are not reproducible to better than ~1.5×.

### Frozen protocol

- **Idle machine.** Load average < 1.0 at start, verified and recorded with the results. No
  other probe, no browser, no games. A run that starts above that threshold is void.
- **Minimum of 5 trials**, not mean — the minimum is the robust estimator for "how fast can
  this go" under residual noise. Report min, median and spread.
- **Record CPU time alongside wall time.** Where they diverge materially the run is
  contended and void.
- **One backend at a time**, never concurrently.

### Frozen gates

| Gate | Threshold |
|---|---|
| D-1 | Largest corpus document (`119-hr-1/1`, 1118 pp) extracts in **< 60 s**, min-of-5, in-browser |
| D-2 | Within **3×** the incumbent's native full-document time, min-of-5 |

**Pre-committed:** a candidate whose min-of-5 straddles the ceiling is reported as
`UNRESOLVED`, never rounded to a pass or a fail. That is the state pdfminer is in today,
and pretending otherwise is what this rule prevents.

**Relative claims survive contention and may be made from the exploratory data**
(pdfium-wasm ≈ pdfjs, pdfminer 8–10× slower). **Absolute threshold claims may not.**

---

# Cross-cutting rules

1. **No composite score.** Not across A/B/C, not within B. The exploratory spike avoided
   this correctly and it stays.
2. **Deviations are logged in-band.** Any change after this document is fixed gets a row in
   a `DEVIATIONS` table in the results, with: what changed, when relative to first seeing
   results, why, and which rankings or gates moved. The exploratory run reconstructed that
   table retrospectively; this one accumulates it as it goes.
3. **Seeds fixed:** 20260805 for every sample and bootstrap.
4. **Environment recorded** with the results, and re-stated next to any number quoted
   elsewhere. Still macOS/arm64 until someone runs it on Windows.
5. **Raw outputs are immutable.** Published tables are generated from them
   ([`fill_results.py`](probes/fill_results.py)), never transcribed.

## What this run cannot settle, by construction

Named here so the next reader does not have to rediscover it:

- **Tier B.** No pre-publication fixtures exist in the repo. Until they are sourced, no run
  under this protocol can speak to committee prints, chair's marks or discussion drafts —
  the material ADR 0010 says the PDF pipeline exists for.
- **Bundle size**, which the audit identified as the axis the PDFium-WASM vs pdfminer
  decision actually turns on. It needs an artifact build, not a scoring run.
- **Windows.**
- **PDF.js's true capability**, unless the operator-list adapter is built first. Its current
  result belongs to `getTextContent()`, not to the library.
