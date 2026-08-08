# Downstream harness — contract and dependency plan

**Status: PLAN ONLY. None of the five components is built.** Nothing here is frozen
protocol; it is a mapping of already-frozen rules onto executable contracts, submitted for
review before implementation. Where the frozen rules do not determine an outcome-affecting
choice, the ambiguity is surfaced in §7 rather than resolved.

Frozen inputs this plan assumes, all approved: A19 (neutral skeleton, 8-line regions,
withdrawn C-frame enrichment), A20 (M6 deferred, RQ2 narrowed), A21–A24 (`sci` vs `ngid`,
Model G, text vs segmentation discordance, M0 risk set), A25 (X2-b boundary counterfactual),
A5 + A10 (Rule 1 and the adjudication budget), and **A27** (matching key, C-frame
reservation removed, region-based D-frame budget, Rule 0 outcomes, §8 owner, Rule 3 gate
vector, frozen determinism).

**Every frozen methodology section has an owner** — §4.5 `decide_architecture` (BLOCKED,
§7.1); §5.3–5.4 `build_oracle`; §5.5.1 + §5.8 `build_frames` (frames) and
`decide_architecture` (budget); §5.6 `adjudicator_prompt` + `build_oracle`; §5.7
`build_oracle`; §6 `score_metrics`; §7 `decide_architecture`; §8 `score_metrics`.

---

## 1. Dependency order

```
        run_hybrid ──┐
                     ├──► build_frames ──► build_oracle ──► [HUMAN / AI adjudication]
        run_extended ┘         │                                      │
                               │                                      ▼
                               └──────────────────────────────► score_metrics
                                                                      │
                                                                      ▼
                                                            decide_architecture
```

`adjudicator_prompt.md` is an input to `build_oracle`, not a stage. It must be committed
before any oracle artifact is produced, because it is part of what determines a label.

**Build order: `build_frames` → `adjudicator_prompt` → `build_oracle` → `score_metrics` →
`decide_architecture`.** Each stage's output is a committed JSON artifact, so a later stage
never re-derives an earlier stage's decisions.

---

## 2. `build_frames.py`

**Implements:** §5.8 (two frames, never pooled), A19 (neutral skeleton, 8-line regions,
enrichment withdrawn), A22/A23 (D-frame = union of text / segmentation / anchor discordance),
A23 (M0 comparative risk set).

| | |
|---|---|
| **inputs** | holdout PDF paths + `holdout_membership.json`; `run_hybrid.run`, `run_extended.run` |
| **outputs** | `results/frames.json`: per document → per page → neutral lines (`key`, `baseline`, bbox, `gids`), regions (8 consecutive neutral lines, page-bounded), per-neutral-line `line_state`, per-region C/D membership with the reason each entered |

**Permitted decisions:** JSON layout only. The C-frame draw is **not** a free choice: A27.7
fixes it as `rank by sha256("cframe-select|20260807|(doc_sha256,page,region_ordinal)")`,
first ≤ 8 per document.

**Must NOT decide:** which lines are neutral (that is `eligible` + `cluster`, frozen);
region size or alignment; any use of text to form a region; any enrichment predicate
(withdrawn by A19); **any amount-bearing reservation (REMOVED by A27.2)**; whether a
jointly-absent line enters the D-frame (it does not); the selection seed or ranking rule.

### Invariants

- **I1** C-frame regions are enumerated from the **neutral skeleton only**. Enumerating from
  emitted lines would make a jointly-dropped line unsamplable and a shared failure invisible.
- **I2** the skeleton is byte-identical under both arms (`x13` already asserts this).
- **I3** `BOTH_ABSENT` lines are in the region grid and in `frames.json`, are **excluded**
  from the M0 risk set, and **cannot alone** put a region in the D-frame.
- **I4** a D-frame region records the predicate(s) that caused **the region** to enter, and
  separately the specific neutral lines that were discordant. A non-discordant line inside a
  D-frame region must never be recorded as individually qualifying — the region is the
  membership unit, the line is the evidence.
- **I5** regions never cross pages.

### Controls

| control | what fact makes it fail |
|---|---|
| skeleton identity H vs X | any page where the two runners' `(key, gids)` lists differ |
| region partition is total | a neutral line belonging to zero or ≥2 regions |
| synthetic jointly-dropped body line | it fails to appear in any C-frame-eligible region |
| synthetic chrome-only page | any of its lines enters the D-frame |
| **negative:** injected merge/split on one arm | that region does **not** enter the D-frame |
| **negative:** injected text change on one arm | that region does **not** enter the D-frame |
| **negative:** anchor set differs, text identical | that region does **not** enter the D-frame |
| **negative:** a concordant line inside a D-frame region | it is recorded as individually qualifying (I4) |
| determinism | the same commit + inputs select a different C-frame set or order |

---

## 3. `adjudicator_prompt.md`

**Implements:** §5.4 (the adjudicator sees only the region), §5.5.1 (human for D-frame),
§5.6 (negative controls indistinguishable), A20 (RQ2 narrowed).

**Must contain:** the task, the region image, and nothing else identifying an architecture.
**Must NOT contain:** any H or X text, any architecture name, any hint that a region is a
control, or any question about amount→account attribution (M6 is deferred; asking would
collect data the study may not use and could bias heading answers).

**Asked for:** heading occurrences present, their exact printed text, their immediate parent,
a coarse leaf/container role, and — per A27.1 — **enough source position to name the
occurrence key**: which physical line of the region the occurrence starts on, and its order
on that line. Nothing else.

| control | what fact makes it fail |
|---|---|
| prompt contains no architecture output | a grep for H/X text or arm names hits |
| N-A altered-PDF region | the adjudicator transcribes the unaltered text, i.e. cannot see the failure class → M2/M3 void |
| N-C heading-free region | a heading is reported → precision claims void |
| R1 repeat at a different scale | heading-text agreement < 0.90 → text metrics void |

---

## 4. `build_oracle.py`

**Implements:** §5.4, §5.7 (provenance), §5.6 (controls shuffled in), A19 (regions are
neutral), A24.2 (region bbox comes from the skeleton, which now excludes U+0020).

| | |
|---|---|
| **inputs** | `frames.json`; the PDFs; `adjudicator_prompt.md` |
| **outputs** | `results/oracle_stimuli.json` (per region: document sha256, page, **bbox in PDF points**, renderer name+version, DPI, **PNG sha256**, blind id) and the rendered PNGs; later `results/oracle_key.json` mapping blind id → region, committed **before** adjudication |

**Permitted:** render DPI; blind-id scheme. Shuffle order, the 25-item audit draw and the
R1 10 % repeat draw are **fixed** by A27.7's namespaces `blind-order`, `cframe-audit` and
`r1-repeat`.

**Must NOT:** render from any architecture's text; let a region's H/X content influence
cropping; reveal control status; write the key after adjudication has begun.

### Invariants

- **I6** the renderer reads **PDF geometry only**. No arm's text reaches it.
- **I7** every stimulus carries its PNG sha256, so a later re-render is *detected*.
- **I8** `oracle_key.json` is committed strictly before `oracle_adjudicated.json` exists
  (F6 already checks this ordering by git).

| control | what fact makes it fail |
|---|---|
| re-render determinism | same region renders to a different PNG hash |
| bbox ↔ skeleton agreement | a rendered crop omits a neutral line the region claims |
| **negative:** shuffle the key | adjudications still align to the right regions (would prove the key is not load-bearing, i.e. the join is fake) |

---

## 5. `score_metrics.py`

**Implements:** §6 (M0–M9 minus M6), A19 (denominators), A20 (RQ2 narrowed), A22/A23 (M0
components, risk set, D-frame), A3/A4 + `m3_boundaries` (M3), §5.8 cross-engine control,
A24.2 reporting.

| | |
|---|---|
| **inputs** | `frames.json`, `oracle_adjudicated.json`, `oracle_key.json`, `x09` cross-engine result |
| **also owns** | the **§8 statistical contract** (A27.5) |
| **outputs** | `results/metrics.json`: M0a/M0b/M0-any/M0c + raw components, M1–M5, M7, M9, per-document and pooled, each with its content-bearing denominator and any `PDFIUM-CONDITIONED FRAME` label |

### The M0 block, exactly

```
risk set      neutral lines with state != BOTH_ABSENT
M0a           |TEXT_DISCORDANCE|            / |risk set|
M0b           |SEGMENTATION_DISCORDANCE|    / |risk set|
M0-any        union, never a sum            / |risk set|
M0b_defined   lines where SEGMENTATION_DEFINED (C(N) non-empty)
M0b_rate_on_defined  |SEGMENTATION_DISCORDANCE| / |M0b_defined|
M0c           |regions with ANCHOR_DISCORDANCE| / |regions|   -- never pooled with the above
both_absent   raw count, reported, never in a denominator
```

**Reporting rule carried forward from the A23 review:** `M0b_segmentation_rate` is over the
full risk set; only `M0b_rate_on_defined` may be described as "the fraction of comparable
groupings that disagree". `score_metrics` must emit both and must not emit a single "M0b".

### The §8 block (A27.5)

```
event          per DOCUMENT: "has >= 1 heading-level H/X discordance"
estimand       pi = P(a document from the target population shows that event)
bound          exact one-sided 95% Clopper-Pearson upper bound on pi, unit = DOCUMENT
zero events    closed form 1 - 0.05**(1/N); NO bootstrap (degenerate, measured in 8.1)
non-zero       bootstrap permitted, reported alongside
paired         per-document paired differences; UNWEIGHTED mean over documents;
               per-document detail is mandatory, never collapsed to one number
forbidden      any per-heading probability, any heading-as-iid-trial denominator
```

**Must NOT decide:** to pool M0c with the line rates; to weight the components into a
composite; to drop `both_absent` from the report; to let M3 read a segmentation label
(M3 consumes **projected text + oracle** only).

### Invariants

- **I9** every M0a/M0b discordant line's region is in the D-frame (same predicates decide
  both — no divergent eligibility sets).
- **I10** M1 recall's denominator is the **adjudicated** enumeration, never the emitted one.
- **I11** a metric whose content-bearing denominator is zero is reported `VACUOUS`, never as
  agreement.
- **I12** M9 is computed per document per architecture and can reject an arm outright (§7.2
  rule 0) before any other metric is consulted.
- **I13** cross-engine: a document below **0.95** (or any sampled page below **0.75**) labels
  **every RQ1 and RQ2 result computed on it** `PDFIUM-CONDITIONED FRAME`; failure on **more
  than ⅓** of sampled documents applies the qualification to **both** headlines. Never blocks.

| control | what fact makes it fail |
|---|---|
| S1 liveness (advances × 1.25) | M0 does **not** rise → the comparator is not live and M0 is not reportable |
| M3 weld/space fixture | `FAMILYHOUSING` vs `FAMILY HOUSING` does not reach M3 as `X_CORRECTS` |
| M3 insulation | a split-only difference fabricates a weld/split against a clean oracle |
| **negative:** delete agency anchors | M4 does **not** fall further than M1 |
| **negative:** shift heading baselines one line-height | M4 does **not** fall |
| **negative:** inject an `R E P O R T` page | M7 does **not** detect it |
| M0 denominator | a `BOTH_ABSENT` line appears in any M0 denominator |
| vacuity | a zero-denominator metric is printed as a rate |
| **§8 independence** | the bound computed on `N` documents equals the bound computed on `H` headings when `H != N` — i.e. headings were treated as iid trials. §8.1's own 0.1926 vs 0.00498 (39×) is the fixture |
| **§8 zero-event** | a bootstrap is reported at zero events, or the closed form is not `1 - 0.05**(1/N)` |
| **§8 pairing** | the paired mean is weighted by heading count instead of unweighted over documents |

---

## 6. `decide_architecture.py`

**Implements:** §7.2 rule 0 (M9), A5 rule 1 as amended by A20, A10 (budget), §7.2 rule 3.

**Rule 1 after A20 — choose X only if ALL hold, on a FULL census:**

```
1. X_CORRECTS   >= 5      heading occurrences
2. X_REGRESSES  == 0      heading occurrences
3. no heading whose immediate parent is correct under H and wrong under X   (M4)
   [the M6 condition is STRUCK by A20]
```

**Budget, per A10 as unit-fixed by A27.3:** the adjudication item is a **REGION**. Enumerate
the complete D-frame region census first. **≤ 60 regions** → adjudicate the full census and
Rule 1 may be evaluated. **> 60 regions** → Rule 1 cannot choose X; the outcome is
`INSUFFICIENT_COMPARATIVE_EVIDENCE`, and a 60-region sample is descriptive only. §5.8's
120-region clause is superseded; **Rule 1 never runs on a 60- or 120-region sample.**

**Rule 0 (M9) runs FIRST and has its own outcomes (A27.4):** `EXTENDED_BY_RULE_0_M9` when H
has an asymmetric M9 loss and X none; `HYBRID_BY_RULE_0_M9` for the mirror; and when **each**
arm has an asymmetric loss on different documents, **both are rejected** —
`INSUFFICIENT_COMPARATIVE_EVIDENCE`, with no invented comparison by count or severity.

**Rule 3 gate vector (A27.6), each an explicit inspectable status:** R1, N-A, N-B, N-C, S1,
confirmatory X2-a, confirmatory X2-b, M9 evaluability, §4.5 adequacy. Any failure →
`INSUFFICIENT_COMPARATIVE_EVIDENCE`. x09 is a **reporting qualification only**.

**Three outcomes, never collapsed:**

| outcome | meaning |
|---|---|
| `EXTENDED_BY_RULE_0_M9` | H lost a document's heading tree, X did not |
| `HYBRID_BY_RULE_0_M9` | X lost a document's heading tree, H did not |
| `EXTENDED_BY_RULE_1` | X met every condition on a full census |
| `HYBRID_BY_PRIOR` | the pre-stated architectural prior stands; comparative evidence did not overturn it |
| `INSUFFICIENT_COMPARATIVE_EVIDENCE` | Rule 1 could not be evaluated — census over budget, or a control failed |

**Must NOT:** write "H is more accurate" on an X failure. H survives **by prior**, only while
the study is valid and X fails its win conditions. The decider must emit the outcome enum and
a pre-committed sentence, and must refuse to emit any comparative-accuracy claim about H.

| control | what fact makes it fail |
|---|---|
| synthetic X win (6 corrects, 0 regressions, no M4 regression) | outcome is not `EXTENDED_BY_RULE_1` |
| synthetic 5 corrects **and 1 regression** | outcome is `EXTENDED_BY_RULE_1` (must be insufficient) |
| synthetic 5 corrects **and 1 M4 regression** | outcome is `EXTENDED_BY_RULE_1` |
| synthetic census of **61 regions** | outcome is anything other than `INSUFFICIENT_COMPARATIVE_EVIDENCE` |
| synthetic asymmetric M9 loss for H only | outcome is not `EXTENDED_BY_RULE_0_M9` |
| synthetic asymmetric M9 loss on BOTH arms, different documents | outcome is not `INSUFFICIENT_COMPARATIVE_EVIDENCE` (a severity comparison was invented) |
| any Rule 3 gate set to FAIL | outcome is not `INSUFFICIENT_COMPARATIVE_EVIDENCE` |
| x09 set to FAIL | the outcome changes at all (it must only add a label) |
| synthetic empty census | outcome is not `HYBRID_BY_PRIOR`, or the text claims H won empirically |
| **wording gate** | the rendered conclusion contains an empirical-superiority claim for H |
| M9 one-arm loss | the losing arm is not rejected outright before other metrics |

---

## 7. Ambiguity register

### RULED by A27 — no longer open

| was | ruling |
|---|---|
| 7.1 M1–M4 matching key | **A27.1** — source-position key `(doc, page, start_neutral_line_key, occurrence_ordinal_on_line)`; no text similarity, no order-within-region; unmappable → `UNMATCHED` |
| 7.2 40 % amount reservation | **A27.2** — REMOVED; plain uniform C-frame, ≤ 8 regions/document |
| 7.3 60 items vs 120 regions | **A27.3** — the item is a **region**; full census enumerated first; ≤ 60 → adjudicate all, Rule 1 evaluable; > 60 → `INSUFFICIENT_COMPARATIVE_EVIDENCE`, sample descriptive only |

### RESOLVED by measurement — 7.4 anchor→neutral bridge

**Proven, not argued** (`x14_anchor_bridge.py`, `results/x14_anchor_bridge.json`):

```
Anchor(page_number, line_number)   <- line_number is the GPO PRINTED margin number
  -> the unique index i in Page.print_lines carrying that margin number
  -> run_hybrid.emitted_lines(...)[i]    same index, equality re-asserted locally
  -> EmittedLine.cells -> ngid           neutral ink identity (A24.2)
  -> owning NeutralLine -> region ordinal
```

| document | anchors | placed uniquely | unplaceable |
|---|---:|---:|---|
| `114-hr-2029/4` | 11 | **11** | none |
| `118-s-4795/1` | 16 | **16** | none |

No heading text is consulted at any step. Four negative controls prove the bridge **refuses
rather than guesses**: a margin number appearing twice on a page → `AMBIGUOUS_MARGIN_NUMBER_ON_PAGE`;
a margin number on no print line → `NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER`; an emitted line
carrying no neutral ink → `EMITTED_LINE_CARRIES_NO_NEUTRAL_INK`; and a clean anchor places.

**Smallest instrumentation still needed for `build_frames`:** `run_hybrid.run()` returns
`{page_number, chars, emitted, neutral}` and does **not** expose the production `Page`, so it
cannot supply `print_lines` or the anchor set. The proposed change is additive and
provenance-only — add `page` (from the frozen `reconstruct_hybrid.reconstruct_page`) and
`anchors` to that dict, changing no existing key. **Anti-drift gate:** `x14`'s
index-for-index `print_lines` ↔ `emitted_lines` assertion must run over every page the
harness consumes, not just page 1. Not made in this pass.

### STILL OPEN — §4.5 adequacy *(methodological; blocks `decide_architecture` only)*

See §7.1 below. **This is the one unresolved outcome-affecting ambiguity.**

### 7.1 §4.5 adequacy — two distinct gaps

§4.5, frozen:

| condition | consequence |
|---|---|
| ≥ 7 of 8 strata **and** ≥ 800 emitted heading occurrences | supports a generalisation claim |
| 5–6 strata filled | "extends to the classes actually sampled" |
| < 5 strata **or** < 300 heading occurrences | **inadequate**; RQ2 not claimed, RQ1 bound only |

**Gap A — "emitted heading occurrences", whose count?** H and X can differ, and M9 exists
precisely because X can lose a document's heading tree entirely.

| reading | effect |
|---|---|
| H's count | an X failure cannot void the study, but adequacy is measured by the incumbent — and if H is the weaker finder the holdout is understated |
| X's count | **an arm's own failure could declare the holdout inadequate and void the study.** This is the exact hazard §7.2 rule 0 forbids: "no frozen document may be removed from the denominator by its own result" |
| `min(H, X)` | strictly worse than either: **both** arms' failures shrink it |
| `max(H, X)` | symmetric, and no single arm's failure can shrink it |
| union of A27.1 occurrence keys over both arms | symmetric, ≥ `max`, and uses the identity key A27.1 just froze |
| the adjudicated count | architecture-independent, but **unavailable** — the oracle covers only sampled C-regions, not the whole holdout, so it cannot yield a document-wide count |

**Recommendation: the union of A27.1 occurrence keys over both arms.** §4.5 asks an
**adequacy** question — does this holdout *contain* enough heading structure to generalise
from — not an accuracy question. Structure demonstrated by either arm is structure the
documents possess, so the union is the tightest architecture-symmetric measure of it, and it
inherits the "no document removed by its own result" principle. It is capped only by a
**shared** miss, which is honest: if neither arm found the structure, the study has no
evidence it is there.

**Gap B — the rows are not exhaustive, and they overlap.** `≥ 7 strata` with **300–799**
occurrences matches **no row**. And `5–6 strata` with `< 300` occurrences matches **both**
row 2 and row 3, with no precedence given.

**Recommendation: make it exhaustive and ordered**, changing no threshold —

```
1. if strata < 5 OR occurrences < 300      -> INADEQUATE
2. elif strata >= 7 AND occurrences >= 800 -> GENERALISABLE
3. else                                    -> LIMITED ("extends to the classes actually
                                              sampled", unfilled strata named in the headline)
```

This routes ≥ 7 strata / 300–799 to `LIMITED`, and resolves the 5–6 / < 300 overlap in favour
of `INADEQUATE`, which is the conservative reading of an `OR`-joined failure condition.

**What it changes:** Gap A moves the occurrence count and therefore which row fires; Gap B
decides the outcome for a whole region of the input space that currently has none. Either can
flip `§4.5 adequacy` in the Rule 3 gate vector, i.e. flip the study to
`INSUFFICIENT_COMPARATIVE_EVIDENCE`. **Neither is taken here.**

### 7.2 `X_CORRECTS` unit — *implementation-only, closed*

A3 fixes the M3 decision unit as the heading occurrence and Rule 1 counts heading
occurrences; they agree. `decide_architecture` counts `heading_outcome` results and never
boundary-level WELD/SPLIT tallies, which would inflate both counters. Recorded as a build
check, not an ambiguity.

---

## 8. Recommended implementation slice

**None yet.** §4.5 (Gap A and Gap B) is an unresolved outcome-affecting ambiguity, and the
standing instruction is to stop at one rather than pick to make the harness executable.

It blocks only `decide_architecture`, so **once §4.5 is ruled** the recommended first slice
is unchanged from A26 and now unblocked by A27.1:

> **`build_frames.py` alone, DEVELOPMENT only, with I1–I5 and its nine controls**, plus the
> additive `run_hybrid.run()` provenance change and its anti-drift gate.

It consumes only frozen, tested inputs (`run_hybrid`, `run_extended`, `neutral_identity`),
produces the artifact every later stage reads, and every one of its controls is constructible
synthetically with no oracle and no holdout.
