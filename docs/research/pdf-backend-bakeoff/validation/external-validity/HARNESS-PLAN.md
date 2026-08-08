# Downstream harness — contract and dependency plan

**Status: PLAN ONLY. None of the five components is built.** Nothing here is frozen
protocol; it is a mapping of already-frozen rules onto executable contracts, submitted for
review before implementation. Where the frozen rules do not determine an outcome-affecting
choice, the ambiguity is surfaced in §7 rather than resolved.

Frozen inputs this plan assumes, all approved: A19 (neutral skeleton, 8-line regions,
withdrawn C-frame enrichment), A20 (M6 deferred, RQ2 narrowed), A21–A24 (`sci` vs `ngid`,
Model G, text vs segmentation discordance, M0 risk set), A25 (X2-b boundary counterfactual),
A5 + A10 (Rule 1 and the adjudication budget).

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

**Permitted decisions:** the seeded uniform C-frame draw (≤ 8 regions/document); ordering of
regions within a document; JSON layout.

**Must NOT decide:** which lines are neutral (that is `eligible` + `cluster`, frozen);
region size or alignment; any use of text to form a region; any enrichment predicate
(withdrawn by A19); whether a jointly-absent line enters the D-frame (it does not).

### Invariants

- **I1** C-frame regions are enumerated from the **neutral skeleton only**. Enumerating from
  emitted lines would make a jointly-dropped line unsamplable and a shared failure invisible.
- **I2** the skeleton is byte-identical under both arms (`x13` already asserts this).
- **I3** `BOTH_ABSENT` lines are in the region grid and in `frames.json`, are **excluded**
  from the M0 risk set, and **cannot alone** put a region in the D-frame.
- **I4** every neutral line in a D-frame region carries the reason it qualified (`text`,
  `segmentation`, `anchor`).
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

---

## 3. `adjudicator_prompt.md`

**Implements:** §5.4 (the adjudicator sees only the region), §5.5.1 (human for D-frame),
§5.6 (negative controls indistinguishable), A20 (RQ2 narrowed).

**Must contain:** the task, the region image, and nothing else identifying an architecture.
**Must NOT contain:** any H or X text, any architecture name, any hint that a region is a
control, or any question about amount→account attribution (M6 is deferred; asking would
collect data the study may not use and could bias heading answers).

**Asked for:** heading occurrences present, their exact printed text, their immediate parent,
and a coarse leaf/container role. Nothing else.

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

**Permitted:** render DPI; shuffle order (seeded); blind-id scheme.

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

**Budget, per A10:** if the D-frame census contains more adjudicable heading occurrences than
the pre-set human budget (§5.5.1: **60 items**), **Rule 1 cannot choose X** and the outcome
is `INSUFFICIENT_COMPARATIVE_EVIDENCE`. A seeded 60-item sample may be adjudicated for
**descriptive diagnosis only**; the `≥5 / ==0` thresholds are never applied to it.

**Three outcomes, never collapsed:**

| outcome | meaning |
|---|---|
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
| synthetic census of 61 adjudicable items | outcome is anything other than `INSUFFICIENT_COMPARATIVE_EVIDENCE` |
| synthetic empty census | outcome is not `HYBRID_BY_PRIOR`, or the text claims H won empirically |
| **wording gate** | the rendered conclusion contains an empirical-superiority claim for H |
| M9 one-arm loss | the losing arm is not rejected outright before other metrics |

---

## 7. Ambiguities exposed by this mapping

**None of these is resolved here.** Each would change a reported number or the decision.

### 7.1 M1–M4 matching key under A19 — *methodological, highest severity*

§6 matches emitted heading occurrences to adjudicated ones **"by printed-line position"**.
Printed lines are an architecture output; A19 moved the unit to neutral lines and specified
only that the **denominators** become "headings matched within neutral regions". The
**matching key itself** is not restated in neutral terms.

Competing readings: (a) match by **neutral line ordinal** — the direct A19 analogue;
(b) match by **order of occurrence within the region**; (c) match by text similarity —
excluded elsewhere as circular, but it is what "position" degrades to when the arms disagree
about how many lines there are.

**Affects:** which emitted heading pairs with which adjudicated heading, hence M1 precision
and recall, M2, M3's per-heading outcome, and therefore `X_CORRECTS` / `X_REGRESSES` — i.e.
Rule 1 directly. The arms can disagree about line count exactly where the D-frame lives, so
this is not a corner case.

### 7.2 The 40 % amount-bearing C-frame reservation after A20 — *methodological*

§5.8 reserves **40 % of C-regions** for amount-bearing pages, stated purpose: "so M6 has a
population on which it can fire". A20 **deferred M6**; A19 explicitly **retained** the clause
as "a content stratification, not a heading classifier".

So a frozen clause now constrains 40 % of a scarce adjudication budget to serve a metric the
study may not report. Keeping it spends C-frame precision on RQ2's heading claims for no
consumer; dropping it changes the C-frame population against a retained clause.

**Affects:** which regions are adjudicated, hence M1–M5 denominators and every RQ2 figure.

### 7.3 D-frame subsampling: 60 items vs 120 regions — *methodological, narrower*

§5.5.1 sets a **60-item** human budget; §5.8 says a census over **120 regions** is subsampled
with seed 20260807; A10 supersedes §5.5.1 and A5 but does **not** name §5.8.

Reading A10's purpose ("no threshold on a sample"), the item count must be taken over the
**full** census, with §5.8's region subsample serving description only. But if §5.8's
subsample were applied *first*, the 60-item budget could never be exceeded and X could win on
a sample — the exact outcome A10 forbids. The interaction is not written down.

**Affects:** whether the outcome is `EXTENDED_BY_RULE_1` or
`INSUFFICIENT_COMPARATIVE_EVIDENCE` on a large census.

### 7.4 Anchor placement into a region — *implementation-only*

`extract_anchors(pages) -> list[Anchor]` runs over production `Page` objects and reads
`Page.lines` (the `_merge_print_lines` output), while A22 froze the emitted unit as
`Page.print_lines`. `Page.merge_ranges` maps merged lines back to printed lines, so an anchor
should be placeable on a neutral region by identity — but this needs confirming against the
`Anchor` fields before `build_frames` relies on it. If `Anchor` does not carry enough to
reach a printed line, anchor discordance is not implementable as specified and this becomes
methodological.

### 7.5 `X_CORRECTS` unit vs the M3 decision unit — *implementation-only*

A3 fixes the M3 decision unit as the **heading occurrence**, and Rule 1 counts heading
occurrences. These agree; the plan records the check so that `decide_architecture` counts
`heading_outcome` results and never boundary-level WELD/SPLIT tallies, which would inflate
both counters.

---

## 8. Recommended first implementation slice

**`build_frames.py` only, on DEVELOPMENT material, with I1–I5 and its seven controls** —
and *only after* §7.1 is ruled on, because the matching key changes what a "region" has to
carry for the later stages.

It is the right first slice because it consumes only already-frozen, already-tested inputs
(`run_hybrid`, `run_extended`, `neutral_identity`), produces the artifact every later stage
reads, and its negative controls are constructible synthetically without an oracle. No
adjudication, no scoring and no decision logic is required to prove it correct.

§7.2 and §7.3 can be ruled on in parallel; neither blocks `build_frames`. §7.2 blocks
`build_oracle` (it decides which regions are drawn). §7.3 blocks only
`decide_architecture`.
