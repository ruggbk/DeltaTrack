# Pass 2 Protocol — Expand and Re-Stratify the Provision-Matching Labeled Dataset

**Status:** DRAFT for review. No dataset-building until Will approves.
**Context:** Study 2 of the provision-matching program (DeltaTrack #170 / #8). Prerequisites and
the numbers it builds on are in `plans/paper.md` §8–§10 and memory note
`project_issue_56_similarity_thresholds` (AUTHORITATIVE UPDATE block). This document is the
labeling protocol §9 called for.
**Date:** 2026-07-10.

---

## 1. Purpose and the one design decision that matters

Pass 1 established that rare-token containment resolves the stub→expansion pattern no word-overlap
cutoff can reach (honest unique win: 2 pairs over a re-tuned baseline), and that the 12-pair set
**structurally cannot test containment's own false-keep failure mode** — every "different"-labeled
pair sits at containment ≤ 0.528 while the keep bar is 0.70. Pass 2 fixes the dataset so a cutoff
can be *calibrated* and *validated*, not just sanity-checked.

The core decision is **not "more labels."** It is **separating two subsets with different sampling
disciplines**, because the current fixture is a *challenge set* being read as an *evaluation set*
(the paper already caught that "6/12 is partly by construction"):

| subset | sampling | answers | must NOT be used for |
|---|---|---|---|
| **Challenge set** | targeted / disagreement mining, incl. the two missing strata | "Does the matcher handle failure mode X *at all*?" | estimating real-world accuracy (its base rate is rigged) |
| **Estimation set** | **random** draw from the real matched-changed decision population | "What precision/recall would a staffer actually see?" | stress-testing rare modes (it contains few by design) |

Every metric Pass 2 reports is tagged with which subset it came from. This is the honest version of
what the 12/12 tried to be.

---

## 2. Artifacts (four, cleanly separated)

Today's `scripts/build_similarity_labels.py` fuses mining + human labels + freezing into one
hand-written file. That does not scale to ~150 pairs. Split into:

1. **Miners** (`probes/mine_*.py`, reproducible) → emit *unlabeled candidate
   pools* per stratum as JSON. Each candidate carries stable identity (`bill`, `version_old`,
   `version_new`, `match_path`, `change_type`, a `text_sha256` of old+new), provenance
   (`miner`, `stratum`, `sampling`), and the measure scores **stored for later analysis only, never
   shown to the labeler**.
2. **Labeling worklist generator** → renders each candidate blind to the scores (see §5), collects
   `label` / `confidence` / `rationale` into a worklist JSON.
3. **Frozen fixture** (committed, schema-extended from today's `test_data/similarity_labels.json`)
   → text re-derived byte-identical from the corpus as today, plus the Pass 2 fields (§4). The
   existing 12 pairs migrate in unchanged (tagged `challenge` / their bills' split per §6).
4. **Baseline + eval harness** (`probes/eval_pass2.py`) → fits the re-tuned
   word-overlap baseline on dev bills only, evaluates candidate rules on held-out, reports the two
   subsets separately + the generalization gap (§7).

**Reuse, don't rebuild:** `probe_consolidation.py` (many-to-one clusters) and
`probe_review_gameability.py` (cross-bill short-cite-vs-large pairs) already emit exactly the two
missing strata; they become miners with a JSON-emit mode. New code: the random-population sampler,
the failure-mode tagger, the worklist generator, the extended fixture builder, the eval harness.

---

## 3. Strata and MVP quotas (~150 labeled pairs)

Structure is fixed; these absolute numbers are the ~150 MVP tier. The two missing strata are
priority zero (currently at literal zero). Existing 12 pairs fold into the challenge counts.

| stratum | subset | target | miner | why |
|---|---|---:|---|---|
| **High-containment-DIFFERENT** | challenge | **30** | consolidation clusters + gameability | the false-keep mode the paper hinges on; the set's top gap |
| **Many-to-one consolidation** | challenge | **25** | consolidation clusters | ground truth for "absorbed vs coincidentally contained"; needed to represent consolidation at all |
| **Random estimation sample** | estimation | **70** | population sampler | first honest population precision/recall |
| **Failure-mode fill** (boilerplate, stub→expansion, reused-number, genuine renumber, cross-agency relocation, amount-only) | challenge | **~25** (incl. existing 12) | disagreement + failure-mode tagger | keep per-mode coverage non-degenerate; ≥3 per mode |

**Estimation-set population, defined precisely:** all matched-changed decisions the current matcher
produces (each `modified` node + each `removed`/`added` pair it considered as a split candidate)
across adjacent version pairs in **all** usable bills. Sample **within each split separately** (dev
and held-out each get their own estimation subset — §6/§7 need both). Stratify by leaf-level
(account/section/subsection); add an engine (XML/PDF) stratum **only if** PDF decisions actually
exist at population scale (verify first — the corpus is XML-dominant and PDF may contribute ~0
matched-changed decisions; do not assert a stratum that cannot be filled). No measure-based
filtering. This is the only unbiased source of a real-world precision/recall.

**Underpowered by design at MVP, stated up front.** 70 estimation pairs, split across dev/held-out
and stratified, gives a *wide* confidence interval and may contain ~zero instances of the rare
error modes (that is what the challenge set is for). The estimation number is **directional** at
this scale; tightening it is Study 3's job. Report the CI, do not over-read a point estimate.

**Bill-type coverage — a hard corpus limit, not a choice.** The usable matching pool (bills with
≥2 versions) is **17 bills, all House: 16 appropriations + 119-hr-1 (reconciliation), the only
non-appropriations and only consolidation-bearing bill** (verified 2026-07-10). So:
- The estimation sample is appropriations-dominated and stays proportional (it must, to be
  representative).
- **Cross-bill-type generalization cannot be measured in Pass 2** and is deferred to Study 3. Any
  non-appropriations *held-out* presence is *conditional* on processing the ~13 zips yielding a
  multi-version non-appropriations bill — verify before promising it; most zip contents (resolutions,
  single-version Senate bills) are unusable for matching.

---

## 4. Fixture schema (extends today's record)

Every field on the current record is retained. Added:

```jsonc
{
  // ...existing fields (id, bill, version_old/new, match_path, display_path_*,
  //    change_type, decision, label, text_old, text_new, rationale, _observed_similarity)...
  "stratum": "high-containment-different",   // one of the §3 strata
  "sampling": "challenge",                     // challenge | estimation
  "split": "dev",                              // dev | held-out  (assigned by BILL, §6)
  "confidence": "high",                        // high | medium | low  (labeler's)
  "labeler": "will",                           // primary labeler id
  "adjudication": null,                        // null | {llm_label, agreed: bool, resolved_by, note}
  "miner": "mine_consolidation",               // provenance
  "text_sha256": "…",                          // drift guard for the re-derived text
  "measures": { "word_overlap": 0.43, "containment": 0.86, "cosine": 0.31 }  // analysis-only, NEVER shown at label time
}
```

`_observed_similarity` stays for continuity; `measures` is the fuller analysis-time record. The
build asserts `text_sha256` matches the freshly re-derived corpus text, so drift fails loudly.

**Drift policy — a mismatch invalidates the label, it does not auto-refreeze.** This repo actively
changes `normalize_bill`/`diff_bills`; a legitimate parser change alters the re-derived text. On a
`text_sha256` mismatch the pair is **quarantined for re-review** (the human confirms the label still
holds for the new text) — it is never silently re-frozen, because the label was assigned to the old
text and may no longer apply.

---

## 5. Labeling protocol (blind to scores, sighted on context)

The anti-circularity guard: validating a measure against labels the measure influenced is
worthless. So at label time the human sees **text + structural breadcrumb (division › agency ›
account › section) + bill/version metadata**, and does **not** see word-overlap / containment /
cosine scores or the current matcher's decision.

The nuance that is deliberate, not a leak: structural *context* IS shown, because it is the
ground-truth-establishing signal a human legitimately uses and is exactly #170's thesis (context
disambiguates where body similarity fails). Only the scores-under-test are hidden.

Per candidate the labeler records:
- `label` ∈ {same, different}. For consolidation candidates: {genuinely-absorbed,
  coincidentally-contained}.
- `confidence` ∈ {high, medium, low}.
- `rationale`: one or two sentences. **Mandatory** for any medium/low confidence pair.

**Decision standard (written down so "ground truth" is a documented standard, not one gut call):**
- *Same* = the two texts are the same provision continued/edited across versions (same subject,
  same statutory target, same account/authority), regardless of how much text was added or removed.
- *Different* = distinct provisions that happen to share boilerplate, a citation, or a reused
  section number.
- *Genuinely-absorbed* (consolidation) = the old provision's statutory target actually appears,
  substantively, inside the new section — not merely a shared citation string.
- *Coincidentally-contained* = the containment score is driven by a shared boilerplate citation
  with no substantive continuation.

**Label-space mapping for the false-keep metric (§7):** *coincidentally-contained* is the
false-keep positive (a "different" that scores high containment); *genuinely-absorbed* is a true
many-to-one "same." The consolidation labels feed the false-keep test under this mapping and are
also reported in their own bucket.

**Mining-by-the-measure is not circular** as long as the *label* is independent (human rules on
substance) and *tuning never sees the held-out labels* (§6). Targeting high-containment pairs is
standard hard-negative mining; the challenge set's rigged base rate is disclosed (§1), not hidden.

---

## 6. Held-out split — by BILL, not by pair

Pairs from one bill share vocabulary and drafting style; pair-level holdout leaks. Split by whole
bill (continues the leave-one-bill-out discipline the paper already validated).

- Designate **~1/3 of the 17 usable bills as locked held-out test bills** (~5–6 bills). **All**
  their pairs — challenge and estimation — are held out and touched **once, at the end**.
- Cutoffs and any learned weighting are fit **only** on dev bills. The re-tuned word-overlap
  baseline is fit the same way, on the same dev bills, so the comparison is like-for-like.
- Report **generalization gap = dev accuracy − held-out accuracy**, per subset.
- The existing 12 pairs come from 4 bills already "seen" in Pass 1 → their bills go to **dev** (do
  not launder a seen bill into the held-out estimate).

**Which strata can actually be held out (a corpus constraint, not a design choice):**
- **High-containment-different CAN be held out** — the gameability miner pairs a short provision in
  one bill against a large one in another, so these pairs can be built from held-out bills.
- **Consolidation CANNOT be held out at MVP** — it exists only in 119-hr-1, which is a seen bill
  forced to dev. So the consolidation false-keep metric has a dev number but **no held-out
  counterpart**; its generalization is untested until a second consolidation-bearing bill enters the
  corpus (Study 3+). State this limitation in the §9.7 report; do not paper over it.

---

## 7. Baseline and evaluation harness

- **Baseline = re-tuned word-overlap.** Grid-search the split/move cutoffs on dev bills only;
  freeze the best pair; that is the number every future study quotes (kills the misleading "6/12 at
  production cutoffs"). Report it beside every candidate rule.
- **Metrics, per subset, per split:** precision/recall/accuracy for same-vs-different; a separate
  bucket for the consolidation labels. Report accuracy **both with and without** the low-confidence
  pairs — excluding them is a researcher degree of freedom, so it must be shown, not assumed.
- **The false-keep test that the current set cannot run — read it correctly.** Two distinct numbers,
  and conflating them repeats Pass 1's "12/12 by construction" error:
  - *Challenge-set number:* containment's error rate on the adversarially-mined
    high-containment-different pairs. This is a **worst-case failure-existence probe** — "does the
    false-keep mode exist and how severe" — **not** a precision. It is enriched for the failure by
    construction; never quote it as containment's precision.
  - *Population precision-in-regime:* containment's precision among score ≥ 0.70 pairs **in the
    random estimation set**. This is the honest go/no-go — but it is power-limited at MVP (§3), so
    it is directional and may rest on few high-regime points. Report its support count alongside it.
- **No silent caps:** if any miner truncates a candidate pool (top-N per cluster, sampling), the
  harness logs what was dropped.

---

## 8. Adjudication (solo + LLM second-opinion)

- Will is the primary labeler for all pairs.
- An LLM independently labels the **same** pairs **blind to Will's label and to the scores**, under
  the §5 decision standard.
- Disagreements are surfaced to Will with both rationales; Will's ruling is final and recorded in
  `adjudication` (`{llm_label, agreed, resolved_by: "will", note}`).
- Agreement rate is reported as a rough inter-annotator signal (not a Cohen's kappa with a second
  human, but better than solo-unchecked). Persistent-disagreement pairs are flagged `confidence:
  low` and reported both in and out of the headline accuracy (§7).
- **Correlated-error caveat — the load-bearing one.** The LLM can fail the *same way* the measure
  under test does: an LLM reasoning about shared statute citations may rule "same" precisely where
  containment false-keeps on a shared cite. So **high Will-LLM agreement is weak evidence** (it may
  be two correlated errors), while **low agreement is the informative signal** (it flags a genuinely
  hard pair for Will). Use the LLM as a disagreement-flagger, not a validator; never treat agreement
  as confirmation that a label is correct.
- The LLM is a *second opinion*, never the ground truth — it proposes, Will disposes.

---

## 9. Acceptance criteria for the Pass 2 dataset

The dataset is done when:
1. Both missing strata are populated at quota (≥30 high-containment-different, ≥25 consolidation),
   so the false-keep mode is testable.
2. The estimation set is a genuine random draw from the defined all-bills population, sampled
   within each split (documented sampler, seed, no measure filtering).
3. Every bill is assigned dev or held-out; no bill spans both. (Cross-bill-**type** held-out is
   **not** a Pass-2 criterion — the corpus cannot support it, §3/§6; deferred to Study 3.)
4. High-containment-different is present in **both** dev and held-out; consolidation is present in
   dev only, and its missing held-out counterpart is documented (§6), not silently omitted.
5. Every pair has label + confidence; every medium/low-confidence pair has a rationale; every pair
   has an LLM second opinion with agreement recorded.
6. The fixture rebuilds from the corpus with `text_sha256` assertions passing; any drift-quarantined
   pair is re-reviewed, not auto-refrozen (§4).
7. The re-tuned baseline is frozen and reported. Both false-keep numbers run and are labeled
   correctly — the challenge-set failure-existence probe and the estimation-set population precision
   (with its support count), never conflated (§7).
8. A short `docs/`-or-`plans/` writeup records the sampler, quotas hit vs targeted, the agreement
   rate, the estimation-set CI, and every stratum or metric that fell short (consolidation held-out,
   engine stratum, cross-type) — stated as limitations, not omitted.

---

## 10. Sequencing (what happens after this review)

1. **Will reviews this protocol; fresh-eyes pass applied.** ← gate.
2. Process the ~13 unextracted `bills/*.zip` (cheap) **and check how many yield ≥2 matchable
   versions** — this determines whether any non-appropriations bill can enter the pool at all. Do
   not assume it will; most zip contents are single-version or resolutions. Cross-type coverage is
   a bonus here, not a Pass-2 requirement.
3. Build/convert the miners → emit candidate pools. Will reviews a sample of candidates before
   labeling.
4. Labeling worklist → Will labels + LLM second opinion → adjudicate disagreements.
5. Build the frozen fixture; run the eval harness; write the §9.7 report.
6. Study 3 (cross-type generalization) consumes this dataset; nothing downstream is calibrated until
   §9 acceptance is met.

**Not in scope for Pass 2:** choosing the final matcher, measuring the structural-hybrid half
(Study 4), representing consolidation in the diff output (Study 5). Pass 2 produces the *ruler*,
not the verdict.
