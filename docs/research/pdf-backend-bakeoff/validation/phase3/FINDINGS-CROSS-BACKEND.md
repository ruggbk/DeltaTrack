# Phase 3 — does the extended-glyph rule survive a change of engine?

- Run 2026-08-06. **Phase 1 (`../FINDINGS.md`) and phase 2 (`../phase2/FINDINGS-EXTENDED-GLYPH.md`)
  are unchanged; their result files are untouched.** This is a new subphase.
- Probes are `h01`–`h05` here; raw output in [`results/`](results/).
- The question phase 2 left open. Phase 2 measured field *availability* on three backends
  and *accuracy* on one, then wrote into its comparison table:

  > word quality if the backend changes: **fixed, the rule is ours**

  and into its flip conditions:

  > under hybrid the measured quality swing is 16 points; under extended glyph it is zero.

  Neither sentence had been measured. Both are tested here.

**Answer: confirmed, and the mechanism is not the one the phrasing implies.** The same
`wants_space` fed each engine's own facts gives the same answer on 195,290 of 195,291
adjacent pairs, and produces byte-identical reconstructed text from all three engines on
four of five documents. But the extended contract is not *normalising* a difference between
engines. Over 390,582 glyph endpoints the three engines return **advances that are
identical to 0.0 pt**, because all three read the same widths from the same embedded font
programs. The rule ports because the facts do not differ, which is a stronger property than
"our rule smooths the engines out", and a narrower one.

Phase 3 also found **two defects in phase 2's own work**, one of which falsifies a sentence
in `pdfium_extended.py`'s docstring. Both are in [§5](#5-h5--the-two-divergences-diagnosed).

---

## 1. H1 — what each backend's "advance" actually is

Tested against the **installed source**, then by value. Phase 2's `g03` reached the right
field for pdfminer by a wrong reason, and the reason is what a reader carries elsewhere.

| backend | the value | what the source says it is |
|---|---|---|
| PDFium 5.12.1 | `FPDFFont_GetGlyphWidth(font, cp, size)` | the font's glyph width at that size, charcode reverse-mapped from Unicode |
| pdfminer.six 20260107 | `LTChar.width` | `layout.py` builds the box as `(0, descent+rise, self.adv, ...)` then applies `matrix`. It is an **advance box**; pdfminer computes no ink bounds at all. After the transform, `x0` is the pen and `width` is the advance **in page space** |
| pdfminer.six | `LTChar.adv` | `textwidth * fontsize * scaling`, the advance in **text space**. `pdfdevice.render_string_horizontal` walks the pen with exactly this value |
| PyMuPDF 1.28.0 | `get_texttrace()` `chars[i][3]` | `jm_trace_text_span`: `adv = fz_advance_glyph(font, gid, wmode) * fsize`, then `x1 = origin.x + adv`. The rectangle is **constructed from the advance**, at the origin |

### The correction to `g03`

`g03` recorded "**pdfminer's `LTChar.adv` is in em units, not points**". Read as a statement
about the library that is wrong. `.adv` is in text-space points. It looks like em units on
this corpus only because GPO writes `Tf 1` and carries the type size in the text matrix, so
`fontsize` is 1 and `matrix[0]` is 8 to 14.

Measured on the five documents the frozen sample draws from:

| document | text-matrix `a`, median | `width / adv`, median | `.adv` predicts origin delta | `.width` | `.adv × matrix[0]` |
|---|---|---|---|---|---|
| `114-hr-2029/4` p99 | 14.0 | 14.0 | **0 testable pairs** | 805/805 | 805/805 |
| `118-hr-4366/5` p26 | 14.0 | 14.0 | 0 | 922/922 | 922/922 |
| `116-hr-1865/6` p1 | 8.0 | 8.0 | 0 | 1353/1366 | 1353/1366 |
| `118-s-4795/1` p5 | 14.0 | 14.0 | 0 | 970/970 | 970/970 |
| `CRPT-118srpt198` p1 | 10.0 | 10.0 | 0 | 822/822 | 822/822 |

`width / adv` equals the text-matrix horizontal scale on every document, and
`.adv × matrix[0]` reproduces `.width` pair for pair. So `.adv` is not the wrong quantity,
it is the **untransformed** one, and `.width` is the field the rule needs because the rule
works in page space. `g03`'s field choice stands; its stated reason does not.

**C3 (separability).** If `width == adv` on this corpus the probe could not tell the two
apart and would have to say so. The ratio is 8 to 14 on every document, never 1.

### The correction the review expected for PyMuPDF, which did not materialise

The review flagged `chars[i][3]` as possibly a character **ink** box, which would make
`bbox[2] - origin[0]` an ink width and PyMuPDF **UNSUPPORTED**. Two controls say otherwise:

- **C1.** For every upright character of all five documents, `bbox[0] - origin[0]` is
  **0.0 pt exactly**. An ink box cannot satisfy that: nearly every glyph has a non-zero
  left side bearing.
- **C5.** The trace advance was checked against `Font.glyph_advance` on the **embedded font
  program**, extracted from the PDF by PyMuPDF itself. Agreement **1.0** over 987, 1130,
  1633, 1215 and 967 characters. Two independent PyMuPDF routes to the same metric; no
  other engine consulted.

  This is the avenue the review named. Phase 2's `g03` had reported `pymupdf.Font(fontname=…)`
  as unable to instantiate GPO's DeVinne faces, which is true, and concluded the font path
  was closed. It is not: `extract_font(xref)` gives the embedded program and
  `Font(fontbuffer=…)` instantiates it. **PyMuPDF is SUPPORTED, on two routes.**

**A control on the control.** PDFium's *ink* width was run through the identical identity
test and predicts the origin delta at only 0.31 to 0.58. The test does discriminate an
advance from ink, so the 1.0 rates above are not an artefact of a loose tolerance.

---

## 2. H2 — PDF.js, and a correction to why it fails

Phase 2 recorded PDF.js as failing "for the same per-character-granularity reason ADR 0003
already records". That is the right verdict from the wrong evidence, and the wrong evidence
is the optimistic-API kind that nearly produced false negatives for pdfminer and PyMuPDF.

`getTextContent()` is item-level (12.8 to 13.9 characters per item), which is what `g03`
measured. `getOperatorList()` is not:

| document | `showText` glyph objects | carry a per-character `width` | carry any position field |
|---|---|---|---|
| `114-hr-2029/4` p99 | 1,137 | **1,137 (coverage 1.0)** | 0 |
| `118-hr-4366/5` p26 | 1,306 | **1,306 (1.0)** | 0 |
| `CRPT-118srpt198` p1 | 1,094 | **1,094 (1.0)** | 0 |

Glyph objects expose `unicode`, `originalCharCode`, `fontChar`, `isSpace`, `isInFont`,
`vmetric` and `width`. The width is a real per-character font advance in 1/1000 em, and it
agrees with the other engines (`'9'` is 519, `'H'` 870, `'R'` 815).

**So PDF.js has one of the two facts and not the other.** No API exposes a per-character
pen origin. It exists only inside PDF.js's text-state machine, and a consumer wanting it
would have to interpret the text-showing operators itself: on these three pages that is
7 to 21 `setTextMatrix`, 14 to 50 `setLeadingMoveText`, 24 to 52 `setWordSpacing`, 1 to 5
`setCharSpacing`, 13 to 53 `setFont`, plus `nextLine` and `beginText`/`endText`. That is a
PDF text interpreter, not an adapter.

**Verdict unchanged (PDF.js cannot emit the extended contract), reason corrected: the
missing fact is the ORIGIN, not the granularity of the advance.**

---

## 3. H3 — the frozen 72-pair sample, every backend

Phase 1's sample, adjudication unchanged and not reopened. All 72 pairs relocated in
PDFium; **0 unmapped in any backend**. The join is by pen origin (codepoint, `|Δx| ≤ 0.05` pt,
`|Δbaseline| ≤ 0.6` pt, unique match required), which is safe because H1 measured the
engines' origins as agreeing to under 2e-4 pt.

| backend | backend's own text decision | extended-rule decision | independently adjudicated accuracy | coverage |
|---|---|---|---|---|
| PDFium | 0.9275 / **0.9683** | 0.9275 / **0.9683** | tied with its own decision, 0 disagreements | 69/69 |
| pdfminer.six | 0.8065 / **0.8065** | **0.9275 / 0.9683** | **+16.2 pts over its own decision** | 69/69 ext, 62/69 own |
| PyMuPDF | 0.8116 / **0.8413** | **0.9275 / 0.9683** | **+12.7 pts over its own decision** | 69/69 |
| PDF.js | n/a | unsupported (no pen origin) | n/a | 0 |

Two numbers per cell: as adjudicated, then with phase 1's inconsistent class dropped, which
remains labelled **post-hoc**. Three of the 72 are UNREADABLE and excluded, as in phase 1.
pdfminer's *own* column keeps phase 1's frozen coverage of 62/69; the 7 it could not locate
were not scored then and are not scored now.

### Pairwise disagreement

| comparison | disagreements |
|---|---|
| PDFium-extended vs pdfminer-extended | **0 / 72** |
| PDFium-extended vs PyMuPDF-extended | **0 / 72** |
| pdfminer-extended vs PyMuPDF-extended | **0 / 72** |
| PDFium-extended vs PDFium's own text | 0 / 72 |
| pdfminer-extended vs pdfminer's own text | **12 / 65** |
| PyMuPDF-extended vs PyMuPDF's own text | **8 / 72** |

The three extended paths are unanimous. The rule agrees with PDFium's own text assembly on
all 72, which is expected, since it is a port of PDFium's heuristic. It disagrees with
pdfminer's on 12 of 65 and with PyMuPDF's on 8 of 72, and on both of those the extended
answer is the more accurate one (0.9683 against 0.8065 and 0.8413).

### By stratum

| stratum | n | PDFium-ext | pdfminer-ext | PyMuPDF-ext | pdfminer own |
|---|---|---|---|---|---|
| backend_disagree | 6 | 1.0 | 1.0 | 1.0 | 0.0 |
| body_prose | 7 | 1.0 | 1.0 | 1.0 | 1.0 |
| explicit | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| generated | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| **narrowest_generated** | 8 | **0.75** | **0.75** | **0.75** | 0.75 |
| **near_threshold** | 8 | **0.875** | **0.875** | **0.875** | 1.0 |
| no_space_wide | 8 | 1.0 | 1.0 | 1.0 | 0.6 |
| small_caps | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| **widest_intra** | 8 | **0.75** | **0.75** | **0.75** | 0.667 |

The hard strata do not disappear into the aggregate: the three extended paths are equally
wrong in the same places, which is what a shared rule on shared facts should look like.

### Controls

| control | result | reads as |
|---|---|---|
| **N1** adapter vs phase 2's `g04`, item by item | **0 mismatches** | the new adapter reproduces phase 2's column, computed by different code |
| **N2** advances ×1.25 | 0.9275 → **0.8986** (all three backends) | the rule is reading the advance |
| **N2** advances ×0.75 | 0.9275 → **0.7971** (all three) | as above, larger effect |
| **N3** pdfminer fed `.adv` instead of `.width` | 0.9275 → **0.6087**, 27 spurious splits | the harness can see the field choice; a wrong field collapses |
| **N4** coverage | 72/72 relocated, 0 unmapped per backend | no silent partial match |
| **N5** the facts themselves | max &#124;Δorigin_x&#124; **1.9e-4 pt**, max &#124;Δadvance&#124; **0.0 pt** over 144 endpoints | the mechanism |

---

## 4. H4 — the same question at a scale that could detect a rare divergence

Zero disagreements on 72 pairs is consistent with a divergence rate up to about 4 % at
95 % confidence, so the 72-pair result cannot carry a portability claim on its own. H4
trades truth for power: every adjacent same-baseline pair on 24 pages of each of the five
documents, no oracle, agreement only.

| | |
|---|---|
| pairs PDFium saw | 200,684 |
| pairs all three engines report at the same pen origin | 196,105 (**join coverage 0.977**) |
| shared key but a different following glyph, excluded | 814 |
| **pairs compared** | **195,291** |
| **word-boundary disagreements** | **1** |

Reconstructed text, all three engines through the same reconstructor:

| document | PDFium vs pdfminer | PDFium vs PyMuPDF |
|---|---|---|
| `114-hr-2029/4` | **byte-identical** | **byte-identical** |
| `118-hr-4366/5` | **byte-identical** | **byte-identical** |
| `116-hr-1865/6` | token F1 0.999861 | **byte-identical** |
| `118-s-4795/1` | **byte-identical** | **byte-identical** |
| `CRPT-118srpt198` | **byte-identical** | **byte-identical** |

### What bounds this result, stated because the control says so

**N7, the sabotage curve.** One engine's advances scaled, then compared against PDFium's:

| scale | disagreements / 198,400 | rate |
|---|---|---|
| ×1.05 | 13 | 0.00007 |
| ×1.10 | 61 | 0.00031 |
| ×1.25 | 910 | 0.0046 |
| ×0.75 | 61,033 | **0.31** |

**The decision test is nearly blind to a small advance error.** A systematic 5 % difference
between two engines would move 7 pairs in 100,000, which this comparison would report as
"essentially identical". So "1 disagreement in 195,291" would, on its own, be weak evidence.

**N12 removes that limit by measuring the inputs instead of the outputs.** Over **390,582
glyph endpoints**, with the advance available on both sides of every single one:

| comparison | max &#124;Δ origin_x&#124; | max &#124;Δ advance&#124; |
|---|---|---|
| PDFium vs pdfminer.six | 2.1e-4 pt | **0.0 pt** |
| PDFium vs PyMuPDF | 1.2e-3 pt | **0.0 pt** |

The engines do not return *similar* advances, they return the *same* advances. This is the
finding, and it reframes the claim: the extended contract asks for a quantity on which
these engines have nothing to disagree about, because each is reading the same width array
out of the same embedded font program.

**N8** guards against crediting an engine that simply emitted less: glyph inventories are
diffed per document. The only codepoint not reported by all three is U+FFFD (120 to 294 per
document), which PDFium alone carries. That difference is neutralised by `repaired=True`,
the same mode `g05` uses, which turns the carrier into `-` before `rejoin_soft_hyphens`.

---

## 5. H5 — the two divergences diagnosed

### D1 — CONTRACT INSUFFICIENCY: `font_size` has no defined axis

The single disagreement in 195,291 pairs is `.` followed by `R` on page 1 of
`116-hr-1865/6`. All three engines report the **same** origins (129.196, 134.512) and the
**same** advances (3.336, 8.664). The divergent input is `font_size`:

```
text matrix (12.0, 0.0, 0.0, 13.0)      GPO condenses display type: 12 wide, 13 tall

PDFium    FPDFText_GetFontSize x sqrt(a^2+b^2)  -> 12.0   the HORIZONTAL scale
PyMuPDF   |transform_vector((1,0), trm x ctm)|  -> 12.0   the HORIZONTAL scale
pdfminer  LTChar.size = transformed box HEIGHT  -> 13.0   the VERTICAL scale
```

`wants_space` normalises each advance to 1/1000 em by dividing by `font_size`, and
`_normalize_threshold` then **buckets** that value at 400/700/800. The advance is 722 em by
PDFium's size and 666 em by pdfminer's, which crosses the 700 boundary, so the threshold is
`w/5` (1.733 pt) for two engines and `w/4` (2.166 pt) for the third. The observed gap is
1.980 pt and falls between them.

**Category: contract insufficiency, not an adapter bug.** Every adapter reports its own
engine's own documented size. The extended contract inherited `font_size` from
`contract.Glyph`, where it fed `_SPACE_FACTOR × size` and scaled smoothly, so the axis
never mattered. The ported PDFium rule makes it select a divisor, and there it does.

Blast radius, measured rather than assumed: **5,722 of 197,573 pairs (2.9 %)** have an
engine-to-engine `font_size` difference, and exactly **one** of them changes the answer.

**N9, the fix, derived inside pdfminer.** `LTChar.size` is `fontsize × |matrix[3]|`; the
advance axis is `fontsize × |matrix[0]|`; both matrix entries are on the object. Rebuilding
every pdfminer glyph with `size × |matrix[0]| / |matrix[3]|`:

| document | text identical to PDFium, as built | after axis correction |
|---|---|---|
| `114-hr-2029/4` | yes | yes |
| `118-hr-4366/5` | yes | yes |
| `116-hr-1865/6` | **no** | **yes** |
| `118-s-4795/1` | yes | yes |
| `CRPT-118srpt198` | yes | yes |

Closed at the output, not only at the pair. Nothing was tuned: no constant moved, and the
correction is a coordinate-axis choice available in pdfminer's own API. **It is recorded,
not applied to phase 2.**

### D2 — ADAPTER BUG: `pdfium_extended.py` emits PDFium's generated spaces

`pdfium_extended.py`'s docstring states:

> it never reads `get_text_range()`, never asks whether a character was generated, and
> **never consumes a space the engine decided to insert**. It asks only for facts about
> marks that are on the page.

The first clause holds. The second does not, and not asking is not the same as not
consuming. The adapter copies every character on PDFium's text page, PDFium's text page
contains **generated** space characters, and `reconstruct_extended._line_text` emits
`chr(32)` for each of them before the geometric rule is ever consulted.

| document, 24 pages | space glyphs in the contract | | | PDFium's spaces by provenance | |
|---|---|---|---|---|---|
| | PDFium | pdfminer | PyMuPDF | generated | explicit |
| `114-hr-2029/4` | **5,000** | 592 | 592 | **4,445** | 555 |
| `118-hr-4366/5` | 5,090 | 4,482 | 4,482 | 642 | 4,448 |
| `116-hr-1865/6` | 10,706 | 10,530 | 10,530 | 235 | 10,471 |
| `118-s-4795/1` | 5,138 | 4,499 | 4,499 | 684 | 4,454 |
| `CRPT-118srpt198` | 9,112 | 8,896 | 8,896 | 251 | 8,861 |

On `114-hr-2029/4` the content stream supplies 555 spaces and PDFium synthesises 4,445, so
on that document the phase-2 extended reconstruction was taking **eight of every nine word
boundaries straight from the engine**.

**What it did and did not contaminate.**

- `g04` is **unaffected**. It walks ink pairs and never reads a space glyph, so phase 2's
  adjudicated tie is real. H3's N1 control confirms this independently.
- `g05` and `g06` ran through `reconstruct_extended` and **were** on the contaminated path.

**The corrected contract, and the result.** A space carries no ink, so no space belongs in a
contract of "marks on the page". Dropping every U+0020 from every backend and letting the
rule decide all boundaries:

| | extended, as phase 2 built it | extended, no space glyphs |
|---|---|---|
| four named heading failure cases | 53 ok / 0 bad | **53 ok / 0 bad** |
| reconstructed text, all 5 documents | — | **identical to the loose run** |
| cross-engine token F1 | 1.0 (4 docs), 0.999861 | 1.0 (4 docs), 0.999861 |
| **N10** tokens gained/lost by dropping stream spaces | — | 0 on four documents, −1 on one |

**The design defect is real and its effect on phase 2's numbers is nil.** The geometric rule
independently recovers every boundary the generated spaces were supplying, which is the
property the design claimed and had not demonstrated. Removing them is also the answer to
the awkward part of the design: the clean way to exclude engine-invented spaces without
`FPDFText_IsGenerated`, the Experimental predicate the extended design exists to avoid, is
simply not to carry U+0020 at all, and that costs nothing.

---

## 6. What this changes in phase 2's comparison

| | phase 2 wrote | phase 3 measured |
|---|---|---|
| backends that can emit the contract | 3 of 4 | **3 of 4, confirmed by construction rather than by field probe**; PyMuPDF on two independent routes |
| PDF.js failure reason | item granularity | **no per-character pen origin**; the advance *is* available at 1.0 coverage |
| pdfminer's advance field | `.adv` is em units | `.adv` is text-space points; `.width` is its page-space transform. Field choice unchanged |
| "word quality if the backend changes: fixed" | asserted | **supported**: 0.9683 from all three engines, 0 pairwise disagreements on 72 adjudicated pairs and 1 in 195,291 at page scale |
| "under hybrid the swing is 16 points" | asserted from pdfminer alone | **measured on two engines**: pdfminer 0.8065, PyMuPDF 0.8413, against PDFium's 0.9683. Swing of 16.2 and 12.7 points |
| the reason it ports | the contract normalises engines | **the engines already agree**: max &#124;Δadvance&#124; 0.0 pt over 390,582 endpoints |
| `pdfium_extended` consumes no engine space | stated in its docstring | **false as built**; corrected contract scores identically |

**This is the review's Outcome A.** Extended segmentation stays at PDFium accuracy across
engines. So the architectural argument in phase 2's §"the architectural comparison" now has
a measured row where it had an asserted one, and the row favours extended glyph.

It does not settle the decision, for the reason phase 2 already gave: engine independence is
option value that ADR 0002 has declined. What phase 3 changes is that the option value is
now **priced**, not assumed. The hybrid's cost of a future engine change is 12.7 to 16.2
points of word-boundary accuracy on adjudicated truth. The extended contract's is zero, plus
one ported heuristic, one fallback constant, and one contract field (`font_size`) that needs
its axis specified.

---

## 7. Corrections this phase makes to earlier claims

To phase 2:

1. **`g03`'s pdfminer reason.** `.adv` is not in em units; it is the text-space advance. The
   field chosen (`.width`) was right.
2. **`g03`'s PyMuPDF font path.** `pymupdf.Font(fontname=…)` cannot instantiate GPO's faces,
   which `g03` recorded correctly, but `extract_font(xref)` + `Font(fontbuffer=…)` can, so
   the font route is open and corroborates `get_texttrace()` at rate 1.0.
3. **`g03`'s PDF.js reason.** Granularity is the limitation of `getTextContent()` only.
   `getOperatorList()` gives a per-character advance at coverage 1.0. The blocker is the
   pen origin.
4. **`pdfium_extended.py`'s docstring.** "Never consumes a space the engine decided to
   insert" is falsified by the adapter's own output; the generated spaces are copied through.
   `g05` and `g06` ran on that path. `g04` did not.
5. **`contract_extended.py`'s neutrality claim.** "No backend is asked to reproduce another's
   conventions" is true of `origin_x` and `advance` and **not** of `font_size`, which the
   ported rule made load-bearing and which the contract does not define on an axis.

To phase 3's own first pass:

6. **H4's first text comparison ran without `repaired=True`** and reported token F1 0.95,
   which was PDFium's U+FFFD soft-hyphen carriers being scored as a spacing difference. The
   `g05` mode gives 1.0. The N8 inventory diff exists so that error cannot recur silently.
7. **H4's first sabotage control was a single ×1.10 point** and fired 0 to 48 times per
   document. That is not evidence the comparison can see a divergence. It is now a curve,
   and the curve says the decision test is insensitive below about ×1.25, which is why N12
   (comparing the facts) carries the portability claim instead.

---

## 8. Evidence still blocking an ADR

Unchanged from phases 1 and 2. Phase 3 closes none of them:

1. **A valid heading-level oracle.** Still a parser known to drop `<quoted-block>`.
2. **A fresh, structure-rich holdout**, membership and hashes frozen before scoring. Phase 3
   scores the same five development documents phase 1 drew its sample from, deliberately,
   so the frozen sample stays the frozen sample. Nothing here generalises past them.
3. **Blinded heading adjudication.**
4. **The corpus-scale display-split scan** (phase 2's flip condition 1).
5. **An API-stability plan** for whichever set is adopted.

Phase 3 adds two of its own:

6. **`font_size`'s axis must be specified in the contract** before either design ships. It
   is one line of definition and it is currently undefined; D1 shows it is load-bearing.
7. **The extended contract must exclude U+0020** if the design is adopted, and the exclusion
   needs a test, because D2 shows an adapter can satisfy the docstring's *letter* while
   passing the engine's decision through.

Items 1 and 2 remain blocking.

---

## 9. Recommendation

**Hybrid remains the preferred candidate on the evidence measured so far**, and phase 3
narrows the gap rather than closing it. Accuracy is tied within PDFium (phase 2) and now
tied across engines (phase 3), so accuracy still does not decide it. What phase 3 changes:

- extended glyph's engine independence is **demonstrated**, not asserted, and priced at the
  12.7 to 16.2 points hybrid would give up if ADR 0002 were reopened;
- extended glyph carries **one more unspecified contract field** than phase 2 recorded
  (`font_size`'s axis), which is a real cost on its side of the ledger;
- the "one ironic magic constant" cost is unchanged, and D2 removes a different one: the
  design does not need the engine's spaces, so nothing about it depends on `IsGenerated`.

The heading oracle and the fresh holdout remain blocking for an ADR, so no recommendation
here should be read as "adopt". The defensible statement is the phase-2 one with phase 3's
row substituted for its assertion:

> The engine's word-boundary decision is at least as good as anything DeltaTrack would
> write, measured by writing it and finding zero disagreements. Writing our own buys engine
> independence that ADR 0002 has already declined, and phase 3 has now measured what that
> independence is worth rather than assuming it.

---

## Reproduction

Run from the repo root with the worktree venv. `h02` needs the phase-1 node tree:

```
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h01_advance_semantics.py
cd docs/research/pdf-backend-bakeoff/validation/phase3
NODE_PATH=../../probes/js/node_modules node h02_pdfjs_percharacter.mjs <pdf> <page>
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h03_score_cross_backend.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h04_page_scale_agreement.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h05_diagnose_divergence.py
```

Versions: pypdfium2 5.12.1 (PDFium 152.0.7947.0), pdfminer.six 20260107, PyMuPDF 1.28.0
(MuPDF 1.29.0), pdfjs-dist 6.2.108, Python 3.12.12, macOS / arm64. Every number in this
document comes from `results/`; none is transcribed by hand.
