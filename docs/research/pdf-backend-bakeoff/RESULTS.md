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

**There is a permissively licensed PDF backend that produces byte-identical DeltaTrack
diffs entirely inside a browser: PDFium-WASM.** It is the same engine the project already
depends on, compiled to WebAssembly, and it is already published as an MIT-licensed
package wrapping BSD-3 PDFium.

1. **PDFium-WASM reproduces the incumbent exactly.** Across all 15 terminal pairs it
   produced canonical diffs whose change sets and `amount_entries` are **identical** to
   native pypdfium2's. Not "close" — identical. Swapping the backend changes nothing a
   staffer reads.

2. **The spec's hardest expected question dissolved.** It anticipated needing to price a
   PDFium-WASM engineering effort against PyMuPDF's ceiling. A credible build already
   exists (`@embedpdf/pdfium`, 4.6 MB), already exports the four FFI entry points the
   glyph sidecar needs, and works. **The gap PyMuPDF exists to price is essentially
   zero**, so there is nothing to fund and no reason to revisit the AGPL question.

3. **pdfminer.six is a genuine runner-up and the ADR 0002 re-examination was justified.**
   Asked the question ADR 0002 never asked — not "is it a good text extractor" but "is it
   a good glyph-geometry source" — it matches the incumbent on every `amount_entries`
   comparison and leads on raw text recovery. It is pure Python, MIT, installs under
   Pyodide. Its cost is speed: 37.9 s on a 1118-page bill against PDFium-WASM's 4.6 s.

4. **PDF.js loses on a signal a text-only bake-off would never have seen.** Its text
   recovery matches the incumbent, but `getTextContent()` **cannot represent GPO's
   small-caps account headings**, which are intra-line size changes. It merges the
   alternating 14 pt / 11.2 pt runs into one item and reports the first run's size, so the
   size band ADR 0012's heading recovery depends on collapses. The signal is not absent
   from PDF.js — `getOperatorList()` carries it exactly — but it is absent from the API
   this bake-off measured.

5. **`file://` provides no egress protection; a strict CSP provides a lot but not all.**
   Fourteen subresource vectors are blocked. **WebRTC is not**, and no page-level
   mitigation tested closes it. The predecessor's "CSP blocked all ten" result was
   measured with an HTTP-only listener that could not have observed a STUN attempt either
   way.

6. **This does not say "PDF is solved."** Tier B is not closed: the repository contains no
   pre-publication fixtures, which is precisely the material ADR 0010 says the PDF
   pipeline exists for.

### The sentences the spec asked to complete

1. *"The best browser-viable PDF backend is …"* — **PDFium-WASM**, scoring **identical**
   change sets and `amount_entries` to the incumbent on all 15 pairs. No adjudication was
   needed, because holding the pipeline fixed and varying only the glyph source leaves no
   other cause for a difference.
2. *"It runs in the browser at … startup and … per comparison on the largest bill"* —
   Pyodide boot **1.4 s**, extraction **4.6 s** for a 1118-page bill.
3. *"A full comparison makes zero network requests, and our harness is proven to detect a
   request when one is deliberately introduced"* — **true for every mechanism CSP
   governs, and proven by a known-bad control.** Not true for WebRTC.
4. *"Its licensing implication …"* — MIT wrapper over BSD-3 PDFium; see
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

| Gate | pdfium-wasm | pdfminer | pdfjs | pypdf | *pymupdf* |
|---|---|---|---|---|---|
| 1 Opens the corpus (52/52) | ✅ | ✅ | ✅ | ✅ | *✅* |
| 2 Line-number integrity | ✅ 1.000 | ✅ 1.000 | ✅ 1.000 | ❌ 0.988 | *✅ 1.000* |
| 3 Structural conservation | ✅ | ✅ | ✅ | ❌ | *✅* |
| 4 Material diff correctness | ✅ | ✅ | ⚠️ | ❌ | *✅* |
| 5 `amount_entries` | ✅ 15/15 | ✅ 15/15 | ❌ 12/15 | ❌ 6/15 | *✅ 15/15* |
| 6 Browser execution | ✅ | ✅ | ✅ | ✅ | *✅* |
| 7 Fully offline | ✅ | ✅ | ✅ | ✅ | *✅* |
| 8 Licensing | ✅ MIT/BSD-3 | ✅ MIT | ✅ Apache-2.0 | ✅ BSD-3 | *❌ AGPL* |
| 9 Performance | ✅ 4.6 s | ✅ 37.9 s | ✅ 3.9 s | ✅ | *✅* |

*PyMuPDF is shown in italics throughout: it is a **ceiling reference**, not a candidate.
Its passing marks are not a recommendation.*

**Survivors: PDFium-WASM and pdfminer.six.**

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

**Text F1 does not discriminate.** Five of six backends land within 0.0005 of each other.
A bake-off that measured only text would have called this a tie and picked on speed.

**Breadcrumb agreement does discriminate, sharply**, and it is the metric that maps onto
ADR 0012's heading tree and the department/agency/account financial tables that depend on
it.

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

### T4 — backend vs incumbent, the load-bearing measurement

This holds the **entire downstream pipeline fixed** and varies only the glyph source, so
any difference is attributable to the backend with no adjudication required. It answers
the question the delivery decision actually turns on: *would swapping the PDF backend
change what a staffer sees?*

<!-- T4_TABLE -->

### T2 — PDF-derived vs XML-derived, and why it is weaker than the spec assumed

Reported **stratified**, because an unstratified mean mixes three populations and is
dominated by whichever degenerate cases the corpus happens to contain.

**The XML reference is compromised on 8 of the 15 pairs.** Those pairs' XML carries
`<quoted-block>` elements, which the parser drops (tracked as DeltaTrack#11), so the XML
side under-reports content. A PDF-vs-XML disagreement there is presumptively the
*reference's* fault — Trap 2's cause #2 — and attributing it to a backend would be exactly
the error the spec warned about.

<!-- T2_TABLE -->

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

### The defensible claim

> DeltaTrack document processing executes under a browser policy that requires no network
> resources, permits no subresource or background network egress, and is continuously
> tested against deliberate exfiltration attempts across every mechanism CSP governs —
> with a known, measured exception for WebRTC, which CSP does not govern and which needs a
> browser-level control to close.

"Exfiltration is impossible" remains false. Top-level navigation exfiltration is also
still uncovered (`navigate-to` was removed from the CSP spec), though it is user-visible.

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

**The repository contains no pre-publication fixtures**, which is the material ADR 0010
says the PDF pipeline exists for. Per the spec's own table, Tier A passing with Tier B
absent licenses this conclusion and no more:

> Browser PDF architecture is technically viable and matches current capabilities **on
> published GPO material**.

It does not license "PDF is solved", and this document does not write that sentence.

**Also out of scope, and named so the gap is not mistaken for coverage:** image-only draft
PDFs, which ADR 0003 flags as the untested hard case and which would need OCR.

---

## Honest statistics

Zero adjudicated material errors across **15 pairs** is consistent, by the rule of three,
with a true material-failure rate as high as **~20 % at 95 % confidence**. The pairs also
concentrate: 118-hr-4366 supplies 5 of 15 and 113-hr-3547 supplies 3, which is why every
table above reports per-bill as well as aggregate.

This is not an argument against the gate. It is the reason Tier B is necessary rather than
optional, and the reason "PDF is solved" is not available on this evidence.

---

## What this changes, and what it leaves open

### The decision tree, resolved

The spec's tree ends at "shippable backend passes → browser architecture remains viable".
It does, and by the cheaper branch than expected: the branch labelled *"PDFium-WASM
needed → engineering justified"* turned out to need no engineering, because the build
already exists.

### Recommended next steps

1. **Extract the neutral seam into production.** This spike's strongest structural finding
   is that `parsers/pdf_text.py` mixes backend repair with domain logic: `normalize_raw`
   exists entirely to undo PDFium text-API damage and **has no counterpart in the glyph
   path**. Splitting it is a follow-up PR and a *finding of this spike*, not part of it.
2. **Decide PDF.js's fate deliberately.** Either build the operator-list adapter and
   re-score it, or record that the browser PDF path is PDFium-WASM and PDF.js is not a
   candidate. Do not leave it as "PDF.js works", which the text-recovery number alone
   would wrongly support.
3. **Source Tier B fixtures.** Public committee prints (`CPRT-*` on govinfo) are the best
   available proxy; real chair's marks need a congressional contact.
4. **Re-run on managed Windows.** Unchanged from the delivery spike, and still the
   highest-value follow-up for anything OS-dependent.
5. **Take the WebRTC finding to whoever writes the IT story.** It changes a claim that was
   previously believed absolute into one that is precise and defensible.
