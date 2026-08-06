# Results: browser PDF backend bake-off + zero-egress proof

- Status: **research, not a decision.** Input to the delivery-channel question
  ([DeltaTrack#112](https://github.com/AgoraDMV/DeltaTrack/issues/112)) and to a future ADR.
- Run 2026-08-05 against the spec in [`README.md`](README.md), with metrics fixed in
  advance in [`PRE-REGISTRATION.md`](PRE-REGISTRATION.md).
- Reproduction: [`probes/`](probes/). Raw output: [`results/`](results/).

> **Environment caveat, load-bearing for every number below.** Everything was measured on
> **macOS 15 / arm64**, Node 22, Chromium via Playwright 1.60, Pyodide 0.28 (Python 3.14).
> **Nothing was tested on Windows**, which is the platform the target user is on. Results
> that are properties of the *engine* (output parity, relative accuracy, relative speed)
> carry over; results that are properties of the *OS and its security stack* do not.

---

## Executive summary

> **Revised 2026-08-05 after an adversarial audit of this document's own conclusion.**
> An earlier draft opened by calling PDFium-WASM "the best browser backend". That claim
> did not survive being attacked, and the audit that broke it is in
> [`RED-TEAM.md`](RED-TEAM.md). The corrected claim is narrower and, on this evidence,
> better supported.

**The PDF pipeline can run entirely inside a browser, and PDFium-WASM is the only
candidate that reproduces today's production output exactly.** That is a statement about
*drop-in replaceability*, not about extraction quality — and the distinction is
load-bearing, because on every metric that does not use PDFium as its own reference,
PDFium-WASM does not lead.

1. **PDFium-WASM is the only drop-in replacement.** On all 13 terminal pairs the product
   accepts — and on all 15 with the layout guard disabled — it produced canonical diffs
   whose change sets and `amount_entries` are **identical** to native pypdfium2's. The two
   are independently built binaries (PDFium 152.0.7947.0 vs the `embedpdf/runtime` fork)
   whose glyph streams genuinely differ, so this is not an artifact of shared code or
   caching. **But they are the same algorithm**, so agreement is close to expected, and
   this result should be read as "no regression", never as "highest quality".

2. **On independent metrics, pdfminer.six leads and PDFium-WASM ranks 4th of 6.** Scored
   against the XML body text and the XML heading tree — the only references that do not
   take PDFium as ground truth — PDFium-WASM never ranked first in any of eight ablations.
   The ADR 0002 re-examination was more than justified: pdfminer is at least the equal of
   the incumbent on accuracy, is pure Python and MIT, and adds **no binary**. Its cost is
   speed, 37.9 s against 4.6 s on a 1118-page bill.

3. **Two of this bake-off's own conventions favour PDFium, and both are now measured.**
   The `repaired` mode adds **+0.0415** to PDFium's text F1 and nothing to anyone else's;
   `_SPACE_FACTOR = 0.25`, inherited from PDFium-tuned production, is load-bearing only for
   PDFium (at 0.4 its heading F1 collapses 0.586 → 0.206 while PyMuPDF, PDF.js and pypdf
   are unaffected). Neither invalidates the drop-in finding, both invalidate a
   "best-quality" reading.

4. **PDF.js's heading loss is real but its scale was overstated.** `getTextContent()`
   genuinely cannot represent GPO's small-caps account headings — intra-line 14 pt / 11.2 pt
   alternation merged into one item at the first run's size. Against the independent XML
   oracle it recovers headings at F1 0.406 against PDFium's 0.586, so it is worse; but
   PDFium is not the ceiling either, and pdfminer beats both at 0.625. The signal exists in
   `getOperatorList()`; **this bake-off did not build that adapter**, so PDF.js's result
   belongs to one API, not to the library.

5. **The zero-egress claim as published was wrong, and is now corrected.** A second round
   of 19 vectors found **two bypasses of the exact proposed policy**: Speculation Rules
   prefetch and `window.open`. Removing `'unsafe-inline'` from `script-src` closes the
   first (verified non-vacuously). WebRTC also survives CSP and no page-level mitigation
   tested closes it.

6. **This does not say "PDF is solved."** Tier B is not closed, and the corpus is
   narrower than N = 52 implies: **three body-font classes, and the accepted population is
   effectively one**.

### The sentences the spec asked to complete

1. *"The best browser-viable PDF backend is …"* — **the spec's question is the wrong
   shape, and answering it as asked is what produced the overclaim.** Two answers:
   - *For a no-regression migration:* **PDFium-WASM**, identical change sets and
     `amount_entries` to the incumbent on 13/13 accepted pairs (15/15 unguarded).
   - *For extraction accuracy against an independent reference:* **pdfminer.six**, which
     leads on both XML-referenced metrics and adds no binary.
   The choice between them turns on an axis this spike did **not** measure: the bundle-size
   cost of adding 4.6 MB of WASM to an artifact already 17.8 MB.
2. *"It runs in the browser at … startup and … per comparison on the largest bill"* —
   Pyodide boot **1.4 s**, extraction **4.6 s** for a 1118-page bill (pdfminer 37.9 s).
3. *"A full comparison makes zero network requests, and our harness is proven to detect a
   request when one is deliberately introduced"* — **the detection half is proven; the
   zero half is false as originally stated.** Speculation Rules and `window.open` both
   reach the network under the published policy. With `'unsafe-inline'` removed, only
   `window.open` and WebRTC remain, and both are outside CSP's scope by design.
4. *"Its licensing implication …"* — permissive, but the chain has a documented
   inconsistency (npm says MIT, the upstream repo's own `LICENSING.md` says Apache-2.0 for
   `packages/`) and the declared source path no longer exists in that repo. See
   [`LICENSING.md`](LICENSING.md).

---

## Method: what was actually compared

Every backend emits one neutral contract — **glyph facts** — and a single shared
reconstruction layer turns those into the `Line`/`Page` structures the engine consumes.
No backend is graded on how closely it imitates PDFium's text API, which is what the
spec's "the seam must be glyph facts" section requires.

**This measures glyph-fact quality, not "text extraction quality" as a library would
advertise it.** Reconstructing from glyphs discards each backend's own reading-order
logic. That is deliberate — it is the bias being removed — but it means a library could
score differently here than in its own benchmarks.

### Three contract decisions that came out of measurement

| Decision | Why |
|---|---|
| Baseline is the **text-matrix origin**, not the char-box bottom | Clustering on the box bottom splits a 14 pt line from its own descenders (8.4 pt drop against a 7 pt tolerance), turning `heading` into `headin` + a stray `g` |
| Glyphs carry an **`upright`** flag | GPO's rotated gutter watermark otherwise collides with body lines; measured, it destroyed the margin-number match on printed lines 24 and 25 for two backends |
| Undecodable glyphs are kept as **U+FFFD when they carry ink** | Keyed on ink, never on a codepoint value, so it favours no backend |

The third exists because of a real backend difference: **PDFium's glyph API returns `0x02`
for the GPO soft hyphen** while pdfminer, PyMuPDF, PDF.js and pypdf all resolve it to `-`.
Production survives this only because `normalize_raw` special-cases the *text* API's
U+FFFE marker. Every score is therefore reported twice — `strict` (unnamed glyph left as
U+FFFD) and `repaired` (a line-final unnamed glyph read as a hyphen from position alone,
a rule available to all backends equally). The gap between them is the measurement.

**The incumbent's adapter deliberately does not use `get_text_range()`.** Production reads
codepoints from PDFium's bulk text string, which is PDFium's own repair layer; letting the
adapter reach for it would hand the incumbent a fallback no challenger has.

### The calibration gate (Trap 1) passed

The incumbent through the neutral layer: mean text F1 **0.913**, median **0.942**
(repaired). The residual is the documented PDF-vs-XML format gap, not a layer defect —
GPO's `‘‘quoted’’` account names, small-caps headings printed in caps, and section
enumerations the XML encodes structurally rather than as text.

Confirmed independently, and this is the stronger check: **production's own
`extract_clean_pages` and the neutral layer produce identical anchor counts, node counts
and conservation numbers** on every bill tested (165/165, 339/339, 197/197). The layer
introduces no drift.

---

## Gate results

Hard gates. A backend passes or fails; ranking applies only among survivors. Gates 2–3 are
**no-regression** (measured against PDFium); gates 4–5 are **correctness**.

**Scored over the population production accepts.** `compare/pdf.py` declines an unnumbered
(enrolled) layout, so gates 2 and 3 are evaluated over the **42 of 52** documents that are
not enrolled prints, and gates 4 and 5 over the **13 of 15** pairs that survive the same
guard. Scoring a backend on a document the product refuses to answer for measures nothing
about the backend. This is not a softening: it changed one verdict in each direction, and
both are noted below.

| Gate | pdfium-wasm | pdfminer | pdfjs | pypdf | *pymupdf* |
|---|---|---|---|---|---|
| 1 Opens the corpus (52/52) | ✅ | ✅ | ✅ | ✅ | *✅* |
| 2 Line-number integrity | ✅ 1.0000 | ✅ 1.0000 | ✅ 1.0000 | ✅ 1.0000 | *✅ 1.0000* |
| 3 Structural conservation — no regressions | ✅ 0 | ✅ 0 | ✅ 0 | ✅ 0 | *✅ 0* |
| 3b …but heading recovery **vs XML** | ✅ 0.5864 | ✅ **0.6253** | ❌ **0.4058** | ❌ **0.4010** | *✅ **0.6253*** |
| 4 Material diff correctness | ✅ | ✅ | ❌ | ❌ | *✅* |
| 5 `amount_entries` identical to incumbent | ✅ **13/13** | ✅ **13/13** | ❌ 10/13 | ❌ 6/13 | *✅ 13/13* |
| 6 Browser execution | ✅ | ✅ | ✅ | ✅ | *✅* |
| 7 Fully offline | ✅ | ✅ | ✅ | ✅ | *✅* |
| 8 Licensing | ✅ MIT/BSD-3 | ✅ MIT | ✅ Apache-2.0 | ✅ BSD-3 | *❌ AGPL* |
| 9 Performance (1118-page bill) | ✅ 4.6 s | ✅ 37.9 s | ✅ 3.9 s | ✅ | *✅* |

*PyMuPDF is shown in italics throughout: it is a **ceiling reference**, not a candidate.
Its passing marks are not a recommendation.*

**Survivors: PDFium-WASM and pdfminer.six.**

**Two verdicts the accepted-population scoring changed, in opposite directions.**

- **pypdf passes gates 2 and 3 after all.** Over the full 52 it looked like a failure
  (line-number recall 0.988, one conservation regression). All nine of its line-number
  shortfalls and its single conservation regression fall on **enrolled bills**, which
  production declines. Over the accepted 42 it is perfect on both. Its real failure is
  gate 5, and it is not close: 6 of 13.
- **Row 3b is a post-hoc addition, and it is doing the work gate 3 was meant to do.** The
  pre-registered gate 3 reads "no unexplained structural loss". Conservation alone does
  not detect the loss found here: PDF.js and pypdf lose most of the heading tree while
  passing every conservation check, because losing a heading *reparents* its amounts
  without dropping them. Reporting only conservation would have passed two backends that
  lose more than half the headings.

  **It is scored against the XML tree, not against PDFium**, which is a correction the
  red-team audit forced. The first draft scored it as breadcrumb agreement with the
  incumbent, which gives PDFium and its WASM twin 1.0000 by construction and cannot rank
  them. Against the independent reference **pdfminer and PyMuPDF (0.6253) beat PDFium
  (0.5864)** — so this row passes PDFium-WASM but does not crown it. PDF.js and pypdf
  still fail it by a wide margin, which is the finding that survived the audit.

---

## Phase 1: per-document scoring (N = 52 documents, 30 bills)

Zero errors: every backend opened every document.

| Backend | text F1 (repaired) | line-num recall | breadcrumb agreement | native extract, 52 docs |
|---|---|---|---|---|
| pdfium-native *(incumbent)* | 0.9126 | 1.0000 | — (reference) | 142.6 s |
| **pdfminer** | **0.9131** | 1.0000 | 0.9808 | 285.7 s |
| pymupdf *(ceiling)* | 0.9126 | 1.0000 | 0.9808 | 166.7 s |
| **pdfium-wasm** | **0.9126** | 1.0000 | **1.0000** | 138.9 s |
| pdfjs | 0.9126 | 1.0000 | **0.4664** | 82.2 s |
| pypdf | 0.8729 | 0.9875 | 0.4137 | 90.0 s |

**This table is the full 52; the gate table above is the 42 documents production
accepts.** The only figure that moves between them is pypdf's line-number recall,
0.9875 → **1.0000**: all nine of its shortfalls are enrolled prints, which
`compare/pdf.py` declines. Both populations are reported because they answer different
questions — this one "how good are the glyph facts", the gate table "would the product
ship worse than it does today".

**Text F1 does not discriminate.** Five of six backends land within 0.0005 of each other.
A bake-off that measured only text would have called this a tie and picked on speed.

**Breadcrumb agreement does discriminate, sharply**, and it is the metric that maps onto
ADR 0012's heading tree and the department/agency/account financial tables that depend on
it.

> **But breadcrumb agreement takes PDFium as ground truth**, so PDFium and its WASM twin
> score 1.0000 by construction and the column cannot rank them. Scored instead against the
> XML tree's heading labels — a reference with no PDFium in it — the order changes:
>
> | Backend | heading F1 vs **XML** | breadcrumb agreement vs **PDFium** |
> |---|---|---|
> | pdfminer | **0.6253** | 0.9808 |
> | pymupdf *(ceiling)* | **0.6253** | 0.9808 |
> | pdfium-native / pdfium-wasm | 0.5864 | 1.0000 *(by construction)* |
> | pdfjs | 0.4058 | 0.4664 |
> | pypdf | 0.4010 | 0.4137 |
>
> PDF.js is still clearly worst-but-one, so that finding holds. **PDFium is not the
> ceiling**, though: pdfminer and PyMuPDF recover headings better than the incumbent
> against an independent reference. Full method in [`RED-TEAM.md`](RED-TEAM.md).

### The PDF.js finding, in detail

GPO sets account headings in faux small caps: `MILITARY CONSTRUCTION, DEFENSE-WIDE` is
14 pt initials and 11.2 pt body **within one printed line**.

```
PDFium   M(14.0) I(11.2) L(11.2) I(11.2) T(11.2) A(11.2) R(11.2) Y(11.2) C(14.0) O(11.2) …
PDF.js   M(14)   I(14)   L(14)   I(14)   T(14)   A(14)   R(14)   Y(14)   C(14)   O(14)   …
```

`getTextContent()` merges the alternating runs into one item and reports the first run's
size, so the whole heading reads as body-size text. On 118-hr-4366 that costs **21 of 48
accounts and 15 of 18 agencies**. `disableCombineTextItems` does not change it in
pdfjs-dist 6.x (verified: item count identical at 110).

**The signal is discarded, not missing.** `getOperatorList()` — which the adapter already
calls, for font names — carries the exact alternating `setTextMatrix` ops:

```
setFont g_d0_f1 · setTextMatrix [14,0,0,14,191,707]      · showText "M"
                  setTextMatrix [11.2,0,0,10.54,…]        · showText "ILITARY"
                  setTextMatrix [14,0,0,14,252.97,707]    · showText "C"
                  setTextMatrix [11.2,0,0,10.54,…]        · showText "ONSTRUCTION"
```

So **PDF.js is not disqualified on glyph facts; the `getTextContent()` path is.** An
operator-list adapter would recover the signal, at the cost of reimplementing much of
PDF.js's own text layer. **This bake-off did not build one**, so PDF.js's score belongs to
`getTextContent`, and the operator-list route is untested potential rather than a measured
result. That is the single largest piece of unfinished work this spike leaves.

### Two metrics that did not discriminate, reported as such

- **Money conservation** is identical for every backend (17/52) *and identical to
  production*. The 17/52 reflects this probe's stricter counting rule, not a defect in any
  backend or in the layer.
- **Font-role separation** is 0.8002 for all six, because the figure mixes two
  populations: ~0.99 on the 42 numbered prints and **0.000 on the 10 enrolled bills**,
  which carry no margin line numbers at all. Over the population the source inventory
  actually measured, every backend recovers font role equally well, at the ~99 % rate the
  inventory records. **No candidate forecloses the font signal.**

### Metric audit

`token_f1` was changed from order-sensitive LCS to a multiset intersection after seeing
the *runtime* (difflib is quadratic; enrolled bills run to ~180k tokens), not the ranking.
The substitution is audited rather than asserted: over 264 comparisons where both are
computable, mean |Δ| = **0.0035**. The one outlier (0.140) is pypdf, where LCS is *lower* —
the substitution is generous to the weakest backend and so cannot have manufactured the
ranking.

---

## Phase 2: the terminal metric (N = 15 pairs)

### T4 — backend vs incumbent: what it does and does not measure

This holds the **entire downstream pipeline fixed** and varies only the glyph source, so
any difference is attributable to the backend with no adjudication required. It answers
one question well: *would swapping the PDF backend change what a staffer sees today?*

> **It cannot rank PDFium-WASM, and the first draft of this document treated it as though
> it could.** T4's reference is native PDFium; PDFium-WASM is the same algorithm from a
> different build. A perfect score is close to expected and is evidence of *sameness*, not
> of *quality*. T4 was also an **addition to the spec**, introduced mid-spike, and it is
> the single metric on which the original "best backend" conclusion rested.
>
> It is still worth reporting, because drop-in replaceability is genuinely what a
> no-regression migration needs. It is simply not a quality ranking, and nothing below
> should be read as one.

<!-- T4_TABLE -->

Scored on **13 of 15** pairs. 2 declined by the production unnumbered-layout guard (115-hr-5895/4->5, 118-hr-4366/5->6).

| Backend | amounts identical | changes identical | amount F1 | change F1 |
|---|---|---|---|---|
| pdfium-native *(incumbent)* | (reference) | (reference) | — | — |
| **pdfminer** | **13/13** | 6/13 | 1.0000 | 0.9669 |
| pymupdf *(ceiling)* | **13/13** | 7/13 | 1.0000 | 0.9294 |
| pypdf | 6/13 | 2/13 | 0.9304 | 0.6004 |
| **pdfium-wasm** | **13/13** | 13/13 | 1.0000 | 1.0000 |
| pdfjs | 10/13 | 5/13 | 0.9896 | 0.8296 |

<!-- /T4_TABLE -->

### T2 — PDF-derived vs XML-derived, and why it is weaker than the spec assumed

Reported **stratified**, because an unstratified mean mixes three populations and is
dominated by whichever degenerate cases the corpus happens to contain.

**The XML reference is compromised on 8 of the 15 pairs.** Those pairs' XML carries
`<quoted-block>` elements, which the parser drops (tracked as DeltaTrack#11), so the XML
side under-reports content. A PDF-vs-XML disagreement there is presumptively the
*reference's* fault — Trap 2's cause #2 — and attributing it to a backend would be exactly
the error the spec warned about.

<!-- T2_TABLE -->

**`substantive_clean`** (n=2) — real amounts, XML reference **sound** — the informative population

| Backend | mean F1 | min F1 | perfect |
|---|---|---|---|
| pdfium-native *(incumbent)* | 0.3318 | 0.3000 | 0/2 |
| **pdfminer** | 0.3318 | 0.3000 | 0/2 |
| pymupdf *(ceiling)* | 0.3318 | 0.3000 | 0/2 |
| pypdf | 0.1500 | 0.0000 | 0/2 |
| **pdfium-wasm** | 0.3318 | 0.3000 | 0/2 |
| pdfjs | 0.1500 | 0.0000 | 0/2 |

**`substantive_qb`** (n=6) — real amounts, XML reference carries `<quoted-block>` (known parser drop)

| Backend | mean F1 | min F1 | perfect |
|---|---|---|---|
| pdfium-native *(incumbent)* | 0.9921 | 0.9708 | 2/6 |
| **pdfminer** | 0.9921 | 0.9708 | 2/6 |
| pymupdf *(ceiling)* | 0.9921 | 0.9708 | 2/6 |
| pypdf | 0.9011 | 0.5000 | 1/6 |
| **pdfium-wasm** | 0.9921 | 0.9708 | 2/6 |
| pdfjs | 0.9905 | 0.9708 | 2/6 |

**`xml_found_none`** (n=1) — XML found no amounts; F1 is an empty-denominator artifact

| Backend | mean F1 | min F1 | perfect |
|---|---|---|---|
| pdfium-native *(incumbent)* | 0.0000 | 0.0000 | 0/1 |
| **pdfminer** | 0.0000 | 0.0000 | 0/1 |
| pymupdf *(ceiling)* | 0.0000 | 0.0000 | 0/1 |
| pypdf | 0.0000 | 0.0000 | 0/1 |
| **pdfium-wasm** | 0.0000 | 0.0000 | 0/1 |
| pdfjs | 0.0000 | 0.0000 | 0/1 |

**`empty_both`** (n=4) — neither side found amounts; F1 trivially 1.0, no information

| Backend | mean F1 | min F1 | perfect |
|---|---|---|---|
| pdfium-native *(incumbent)* | 1.0000 | 1.0000 | 4/4 |
| **pdfminer** | 1.0000 | 1.0000 | 4/4 |
| pymupdf *(ceiling)* | 1.0000 | 1.0000 | 4/4 |
| pypdf | 1.0000 | 1.0000 | 4/4 |
| **pdfium-wasm** | 1.0000 | 1.0000 | 4/4 |
| pdfjs | 1.0000 | 1.0000 | 4/4 |

<!-- /T2_TABLE -->

**The direction matters more than the magnitude.** Where the XML reference is sound, the
PDF path's **recall of XML-detected money changes is perfect or near-perfect**, and the
shortfall is *precision*: the PDF finds additional amount entries the XML does not. For a
trust-critical tool, over-detection is the safe direction, and much of it is the PDF's
cover-page front matter, which the XML body does not contain.

**T1 (change-set agreement) measures the format gap, not the backend**, and is reported as
context only. Mean F1 ≈ 0.16 across every backend including the incumbent: the two
pipelines segment provisions differently by design (blocks vs elements), which is settled
and not a defect.

### A correction worth recording

The first Phase 2 run **bypassed a production guard**. `compare/pdf.py` declines an
unnumbered (enrolled) layout with `UnsupportedLayoutError`, because every anchor path
gates on a printed line number and an enrolled bill otherwise collapses into one
anchorless block. Calling `diff_pdfs` directly skipped that check and produced exactly the
confident wrong answer the guard exists to prevent — 3468 amount entries against the XML's
0 on `118-hr-4366/5→6`. Both anomalous pairs ended in an enrolled bill. The harness now
applies the same guard and marks those pairs declined, because scoring a backend on a
document the product refuses to answer for measures nothing about the backend.

---

## Phase 3: browser execution, and native parity

Pyodide boot **1.35 s**. On 20 pages of 118-hr-4366:

| Backend | install / load | extract | reconstructed-text SHA |
|---|---|---|---|
| pdfminer | micropip 729 ms | 1.21 s | `3ab923d5…` |
| pypdf | micropip 84 ms | 0.65 s | `5e417f06…` |
| pymupdf *(ceiling)* | package 570 ms | 1.27 s | `3ab923d5…` |
| pdfjs | native JS | 0.50 s (+0.09 s boundary, 1.8 MB) | `3ab923d5…` |
| pdfium-wasm | native WASM | 0.19 s (+0.12 s boundary, 2.8 MB) | `3ab923d5…` |

Two results:

- **Browser output is byte-identical to native** for every backend that runs both ways.
  The property the delivery spike established for the XML path holds for the PDF path.
- **Five of six backends reconstruct byte-identical text**; only pypdf differs.

**pdfminer.six installs under Pyodide despite now depending on `cryptography`**, a Rust
extension. The spec carried that as "verified" from an earlier dependency tree; it was
re-measured rather than assumed.

The JS backends pay a cost that appears in no earlier measurement: moving glyph facts
across the JS/Python boundary, **83 MB (PDF.js) and 132 MB (PDFium-WASM) for a 1118-page
bill**. It is absent from both the native benchmark and the in-JS extraction benchmark,
and it is charged per document.

A `pypdfium2` stub that **raises** on any real call (rather than returning a plausible
value) enforced "the browser path never reaches PDFium". It was never triggered.

---

## Phase 4: zero-egress proof

**Built to fail.** Asserting an absence is the vacuous-pass case, so the harness is judged
by whether it can catch a request, and that is tested rather than assumed.

| Part | Result |
|---|---|
| 1. No-CSP control | **14 HTTP + 5 STUN observed** — the harness can see egress |
| 2. Strict CSP | **0 HTTP**, all 16 vectors confirmed to have run |
| 3. Known-bad control | **caught** — a deliberate beacon under the strict CSP was detected |
| 4. Severed network | page still completes all 16 vectors, 0 HTTP |

Blocked by the strict CSP: `fetch`, `XMLHttpRequest`, `sendBeacon`, `<img>`, remote
`<script>`, remote CSS, `@import`, webfont, WebSocket, `EventSource`, `<iframe>`, dynamic
`import()`, **form submission** (actually submitted, into a hidden iframe — the
predecessor fixture built a form and never called `submit()`), and **worker-originated
fetch**.

### Round 2: nineteen more vectors, and two of them defeat the published policy

The list above is 16 mechanisms chosen by the same person who wrote the policy, which is
exactly the weakness a red-team should attack. A second fixture
([`probes/vectors2.js`](probes/vectors2.js)) adds 19 mechanisms the first never tried:
`<a ping>`, Speculation Rules, `<link rel=prefetch/preload/dns-prefetch/preconnect>`,
`<object>`, `<embed>`, `<video>`, `<track>`, SVG `image`/`use`, CSS `background-image`,
`fetch(keepalive)`, WebTransport, worker `importScripts`, `<iframe srcdoc>`,
`window.open`, and `meta refresh`.

The no-CSP control leaked **14 of 19**, so the harness sees them. Under the **exact policy
this document proposes**, two got through:

| Bypass | Mechanism | Covered by CSP? |
|---|---|---|
| **Speculation Rules** | `<script type="speculationrules">` prefetching a cross-origin URL | Should be, and is not — the inline rule block is admitted by `script-src 'unsafe-inline'` |
| **`window.open`** | new browsing context to a remote URL carrying the marker | **No** — a new context is not a subresource |

**Speculation Rules is fixable and the fix is verified.** Removing `'unsafe-inline'` from
`script-src` blocks it. That was tested non-vacuously: a first attempt showed "0 bypasses"
but also `completed=False, 0 vectors` — the policy had blocked the harness's own inline
bootstrap, so the zero was meaningless. Re-run with an **external** bootstrap, all 19
vectors execute and Speculation Rules is blocked.

**Recommended policy change**, replacing the one published earlier in this document:

```
default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:;
connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none';
frame-src 'none'; worker-src 'none'
```

The engine must then load from external script files rather than inline blocks, which the
single-file artifact shape makes non-trivial — a real cost, not a footnote.

**`window.open` is not fixable by CSP**, and the earlier draft of this document
understated it. It said top-level navigation exfiltration "is also user-visible, because
the page would disappear". **That is false for `window.open`**, which opens a background
context and leaves the original page in place. The residual is therefore larger than
previously written: an attacker with script execution can transmit via `window.open` with
no visual disruption.

### WebRTC survives CSP, and no page-level mitigation closed it

Five STUN datagrams reached the server under the strict policy. CSP has no directive
governing ICE. Three mitigations were measured, not assumed:

| Variant | STUN datagrams | Source port | Blocked? |
|---|---|---|---|
| Baseline | 5 | 63830 | ❌ |
| `<iframe sandbox="allow-scripts">` | 5 | 59497 | ❌ |
| `Permissions-Policy` (`camera`/`microphone`/`display-capture` none) | 5 | 64486 | ❌ |

Distinct source ports confirm three independent attempts rather than one connection's
retransmissions counted three times.

**The predecessor could not have found this.** Its logging server spoke only HTTP, so a
STUN attempt could not have appeared in its log whether or not the browser made one — a
check structurally incapable of firing, which reads identically to a pass.

**Scope of the WebRTC risk, stated rather than hand-waved.** A STUN binding request
carries no document content, so this is not a bulk-exfiltration channel; its value to an
attacker is a covert signal (that a comparison happened, plus whatever can be encoded in a
STUN hostname, i.e. a DNS side channel). Closing it needs a browser-level control
(enterprise policy), not a page-level one.

### Two harness defects fixed, each of which would have produced a false pass

- `context.route("**", abort)` for the severed-network case also aborted the fixture's own
  `file://` load, so the page never executed — and its zero hits would have read as proof
  of no egress.
- Playwright's `wait_for_function` compiles a function in the page and needs
  `unsafe-eval`, which the strict CSP denies. It timed out on a page that had in fact run
  every vector, making a complete run look stalled. Cases now carry `vectors_completed`
  and fail closed.

**CDP request events do not decide the claim.** A request object exists before CSP rules
on it, so CDP showed 8 attempts under a policy the server confirms blocked all of them.
Assert on what the server received.

### The defensible claim, corrected

The claim published in the first draft of this document said the policy "permits no
subresource or background network egress". **Speculation Rules falsified that**, so the
sentence is replaced rather than patched:

> DeltaTrack document processing requires no network resources at any point: with the
> network fully severed, a comparison still completes. Under the corrected policy
> (`script-src 'self'`, no `'unsafe-inline'`), **35 distinct exfiltration mechanisms were
> attempted and 33 produced no request**, verified at the network layer against a control
> proven to observe them and a known-bad build proven to be caught. The two that remain —
> `window.open` and WebRTC — are outside what CSP governs and require a browser- or
> device-level control.

Three things that remain false, stated plainly:

- **"Exfiltration is impossible"** — no.
- **"Top-level navigation is user-visible"** — no. `window.open` leaves the page in place.
- **"Every mechanism CSP governs is blocked"** — only true *after* removing
  `'unsafe-inline'`; it was not true of the policy this document first proposed.

---

## Phase 5: performance

In-browser, on the three largest corpus bills.

| Backend | 60-page sample | **full 1118-page bill** | peak memory (60 pp) |
|---|---|---|---|
| pdfjs | 0.66–0.79 s | **3.9 s** | — (JS heap) |
| pdfium-wasm | 0.36–0.67 s | **4.6 s** | — (JS heap) |
| pypdf | 3.0–5.6 s | not measured | 19–39 MB |
| pymupdf *(ceiling)* | 2.2–8.2 s | not measured | 13–79 MB |
| pdfminer | 6.6–9.9 s | **37.9 s** | 15–43 MB |

**A projection error worth recording.** Extrapolating the 60-page sample linearly put
pdfminer at ~134 s, over the pre-registered 60 s ceiling — it would have been disqualified
on gate 9. Measured at full document length it is **37.9 s**. Per-page cost is
front-loaded (cover matter, font warm-up), so a linear projection from the head of a bill
overstates the total badly. **Gate decisions were re-measured at full length rather than
extrapolated.**

---

## Tier B: not closed

<!-- TIERB -->

Measured on **12** non-corpus documents with no XML reference: the watermarked committee report `CRPT-118srpt198`, the watermarked Senate bill `BILLS-118s4795rs`, and nine House-reported subcommittee prints. The spec asks for the first two by name; the nine are additional **Tier A** print-class variety, as the spec itself classifies them.

| Backend | opened | text identical to incumbent | line numbers identical | mean breadcrumb agreement |
|---|---|---|---|---|
| **pdfminer** | 12/12 | 5/12 | 12/12 | 1.0000 |
| pymupdf *(ceiling)* | 12/12 | 6/12 | 12/12 | 1.0000 |
| pypdf | 12/12 | 0/12 | 11/12 | 0.3284 |
| **pdfium-wasm** | 12/12 | 12/12 | 12/12 | 1.0000 |
| pdfjs | 12/12 | 6/12 | 12/12 | 0.3665 |

<!-- /TIERB -->

**The PDF.js heading collapse is not specific to one bill.** Breadcrumb recovery holds at
0.37 across a different document class (a watermarked committee report) and nine
independently typeset subcommittee prints, closely tracking the 0.47 measured on the
52-document corpus. pypdf behaves the same way, at 0.33. So the small-caps size-merge is a
property of the `getTextContent()` API, not of any one document's typesetting.

**PDFium-WASM is identical to the incumbent on all three measures across all twelve**, and
it is the only backend whose text matches on the 231-page committee report.

One caveat on that table, because the number is vacuous where it looks strongest: **the
committee report yields zero anchors for every backend, the incumbent included**, so its
breadcrumb agreement is 0/0 and contributes nothing. DeltaTrack extracts bill anchors, and
a committee report is not a bill — it has its own parser (`parsers/committee_report.py`).
The breadcrumb discrimination in the table therefore comes entirely from the Senate bill
and the nine subcommittee prints. Text identity and line-number identity on the committee
report are real measurements over 231 pages; its breadcrumb column is not.

The text-identity column is the weakest of the three and should not be over-read: pdfminer
and PyMuPDF match the incumbent's text on only 5–6 of 12 while recovering **every**
breadcrumb and line number. The residual differences are sub-line typographic detail, not
structural loss, which is exactly why breadcrumb agreement rather than text identity is
the gate.

**The repository contains no pre-publication fixtures**, which is the material ADR 0010
says the PDF pipeline exists for. Per the spec's own table, Tier A passing with Tier B
absent licenses this conclusion and no more:

> Browser PDF architecture is technically viable and matches current capabilities **on
> published GPO material**.

It does not license "PDF is solved", and this document does not write that sentence.

**Also out of scope, and named so the gap is not mistaken for coverage:** image-only draft
PDFs, which ADR 0003 flags as the untested hard case and which would need OCR.

---

## The corpus is narrower than N = 52 suggests

Counted by GPO stage code the corpus looks diverse: 10 stage classes across 30 bills. That
overstates it. Counted by **body font**, which is what actually determines the layout a
backend has to read, there are **three** classes:

| Body font | Documents | Notes |
|---|---|---|
| DeVinne | 37 | the standard GPO bill body |
| NewCenturySchlbk-Roman | 10 | enrolled prints — **the class production declines** |
| DeVinne-Italic | 5 | amendment prints |

So the population the product actually accepts is **effectively one typesetting class**,
all GPO-published, all appropriations, all 113th–119th Congress. The top three stage
classes are 62% of the corpus, and one bill (118-hr-4366) supplies 6 documents and 5 of
the 15 terminal pairs.

**Classes with zero representation:** committee prints, chair's marks, discussion drafts
(the whole of Tier B), image-only or scanned PDFs, conference reports, non-appropriations
legislation, and anything typeset before the 113th Congress. A backend that fails on any
of those would not have been detected here.

## Honest statistics

Zero adjudicated material errors across **15 pairs** is consistent, by the rule of three,
with a true material-failure rate as high as **~20 % at 95 % confidence**. The pairs also
concentrate: 118-hr-4366 supplies 5 of 15 and 113-hr-3547 supplies 3, which is why every
table above reports per-bill as well as aggregate.

This is not an argument against the gate. It is the reason Tier B is necessary rather than
optional, and the reason "PDF is solved" is not available on this evidence.

---

## What this changes, and what it leaves open

### The decision tree, resolved — and the branch the spec did not draw

The spec's tree ends at "shippable backend passes → browser architecture remains viable".
It does, and no PDFium-WASM engineering needed funding because the build already exists.

But the tree assumes a single winner, and the evidence does not produce one. It produces
**two viable options on different axes**, and the spec had no branch for that:

| | PDFium-WASM | pdfminer.six |
|---|---|---|
| Reproduces today's output | **exactly** (13/13, 15/15 unguarded) | amounts yes, change segmentation differs |
| Accuracy vs independent reference | 4th of 6 | **1st of 6** |
| Heading recovery vs XML | 0.586 | **0.625** |
| Largest bill, in-browser | **4.6 s** | 37.9 s |
| Added binary | 4.6 MB WASM | **none** |
| Supply chain | single-maintainer fork, source path missing | PyPI, long-established |

**Neither column dominates.** The choice turns on whether the project values
no-regression continuity (PDFium-WASM) or accuracy plus a clean supply chain and no binary
(pdfminer) — and on bundle size, which this spike did not measure.

### Recommended next steps

1. **Measure the bundle.** This is now the highest-value follow-up, ahead of everything
   below, because it is the axis the decision actually turns on and the only one with no
   data. Build both artifacts (Pyodide + PDFium-WASM, and Pyodide + pdfminer) and measure
   size and `file://` load time.
2. **Adopt the corrected CSP** (`script-src 'self'`, no `'unsafe-inline'`) and confirm the
   engine still loads from external script files in the single-file artifact shape.
3. **Extract the neutral seam into production.** This spike's strongest structural finding
   is that `parsers/pdf_text.py` mixes backend repair with domain logic: `normalize_raw`
   exists entirely to undo PDFium text-API damage and **has no counterpart in the glyph
   path**. Splitting it is a follow-up PR and a *finding of this spike*, not part of it.
4. **Decide PDF.js's fate deliberately.** Either build the operator-list adapter and
   re-score it, or record that it is not a candidate. Do not leave it as "PDF.js works",
   which the text-recovery number alone would wrongly support.
5. **Source Tier B fixtures**, and **re-run on managed Windows**. Unchanged in priority
   from the delivery spike.
6. **Resolve the `@embedpdf/pdfium` provenance questions** before shipping it: the npm
   license (MIT) disagrees with the upstream repo's own `LICENSING.md` (Apache-2.0 for
   `packages/`), the declared source directory no longer exists in that repo's main, and
   the engine is a fork of PDFium rather than upstream.

### What would change the recommendation

Stated so the conclusion is falsifiable rather than merely asserted:

- **A Tier B failure.** PDFium-WASM's case rests on published GPO material. If real
  pre-publication documents break it, the recommendation changes, and nothing measured
  here would have predicted that.
- **A Windows result that differs.** Everything here is macOS/arm64.
- **The bundle-size story.** PDFium-WASM adds 4.6 MB of WASM to an artifact the delivery
  spike already measured at 17.8 MB. This spike did not build the combined artifact or
  measure its load time from `file://`, and that is the most obvious unmeasured cost of
  the recommended option. pdfminer adds no binary at all, which is the axis on which it
  could still win despite being ~8x slower.
- **PDFium's vendored third-party licenses.** Flagged as an open item in
  [`LICENSING.md`](LICENSING.md), not cleared.

### One thing this spike did not do

It did **not** build the PDF.js operator-list adapter, so PDF.js's result is a measurement
of `getTextContent()` rather than of PDF.js. Given the operator stream demonstrably
carries the size signal, a fair reading is "PDF.js was not fully tested", not "PDF.js
failed". That distinction matters if bundle size later argues for a JS-native backend over
a 4.6 MB WASM one.
