# Methodology review — adversarial challenge to Study 1 and the Study 2 protocol

**Status:** Round 2 complete; **human labeling stays gated.** This document is the deliverable that
`pass2-protocol.md` §10.1 gates on, extended to cover an independent adversarial review of Study 1.
**Date:** 2026-08-06 (round 1), 2026-08-06 (round 2). **Reviews:** `paper.md` (Study 1),
`pass2-protocol.md` (Study 2), `probes/`, and — in round 2 — *this document itself*.
**Supersedes nothing.** It records what survived challenge, what did not, and what neither side saw.

Every claim below was tested against the code and the corpus rather than argued from the documents.
Where a criticism could be decided empirically, a probe decides it, and the probe is committed.
Failed falsification attempts are reported alongside successful ones.

**How to read this document.** It has two layers and the evolution is deliberately visible.

- **Round 1** (§"The eleven claims", §A–§E) is the original review. Its text is **unedited**.
  Where round 2 changed a conclusion, the round-1 section carries a **`↪ Round 2`** pointer and
  the reasoning lives in the round-2 section, not in a rewrite.
- **Round 2** (§R2) is a second adversarial review, which took this document as its target. Twelve
  criticisms; four hold as stated, six hold in part, and in two cases the attempt to falsify them
  succeeded. Two of the twelve overturn conclusions round 1 reported with more confidence than the
  evidence carried, and one of those — the cause of the label drift — inverts round 1's diagnosis.

Round 2's own summary of what changed, in one paragraph: the three drifted observations did **not**
decay, and neither did the source; the parser's representation of byte-identical legislation
changed, which is a different defect with a different remedy (§R2-6). The headline comparison
between in-bill and cross-bill false-keep availability was constructed from three incompatible
quantities and had to be re-run; the direction survives in aggregate but not once the one bill
dominating it is removed (§R2-2). And the round-1 design's suggestion list still could not
establish whether a counterpart exists, which is now demonstrated on the corpus rather than argued
(§R2-1).

---

## Read this first — the environment these results were produced in

**The corpus the probes read moved after Study 1 was written, and the probes did not move with it.**
Fixture-relocation #308 split the bill XML into two roots; `bills/` became the disposable working
tree. Measured today on `develop`:

| root | bills with XML | XML versions | bills with ≥2 versions |
|---|---:|---:|---:|
| `bills/` (what every Study 1 probe reads) | 20 | 71 | 13 |
| `tests/corpus/` | 31 | 58 | 12 |
| **union** | **34** | **106** | **18** |
| *`paper.md` §5 reports* | *31* | *102* | *17* |

So Study 1's probes, run today and unmodified, silently measure a corpus about a third smaller in
the multi-version bills every adjacent-pair number depends on. **Every number in this review was
produced on the union**, via a new `probes/corpus_roots.py`, which is a slight superset of Study 1's
corpus rather than a subset of it. Where a number here differs from `paper.md`, assume the corpus
difference is a contributing cause and re-check before treating the delta as a finding.

This caveat is load-bearing for the whole document, not a footnote: it invalidates any comparison
that pits a number in this review against a number in `paper.md` without re-running both.

---

## The finding neither the study nor the review raised

> **↪ Round 2 (§R2-6).** The word "decayed" throughout this section is wrong, and the round-2
> experiment says which link actually moved. The source XML is byte-identical to the file that
> entered git, and the parser *as of the answer-key commit* still reproduces all three stored texts
> from today's bytes (`probe_r7_provenance.py`). So the legislation did not change and the human
> judgments were never invalidated; the **parser's representation** changed, which re-segments the
> unit the judgment was about. Read this section as **representation drift**. The observable facts
> below all stand; the diagnosis and the remedy change.

Before the eleven claims, the result that changes the most: **Study 1's flagship case no longer
reproduces from the corpus, and re-deriving it inverts the paper's headline conclusion.**

The answer key stores `text_old`/`text_new` verbatim. That makes every probe that scores those
strings reproduce Study 1's numbers exactly and forever — including after the pipeline that produced
the strings has changed underneath them. It has changed.

`probe_r2_label_drift.py`, section 1: **3 of 12 labels no longer resolve to any node the current
parser emits** (`contested-2-corps-110`, `anchor-diff-sec252`, `extreme-alien-snap-10012`).

For Alien SNAP — the paper's Example A, its §6.2 unique win, and one of the two pairs the entire
"2-pair irreducible gain" rests on:

| | old side | new side | word-overlap | containment | §6.2 rule verdict |
|---|---:|---:|---:|---:|---|
| stored label (Study 1) | 81 chars | 2,242 | 0.078 | **1.000** | keep → correct |
| re-derived from today's parser | **1,443 chars** | 2,242 | 0.117 | **0.428** | split → **wrong** |

The 81-character stub exists in **no version** of 119-hr-1 under the current parser (verified across
all five — round 1 asserted this without a reproducer; `probe_r2` §4 now prints the per-version
provenance for all twelve labels, see §R2-7). Today's parser rolls the amendment's sub-paragraphs
into the section body, so the old side is already 1,443 characters and the stub→expansion signature
is gone. Containment 0.428 sits below the 0.70 keep bar, so the measure the study recommends
**would now false-split the case the study cites as its proof.**

And the production engine still gets it wrong today, for a different reason. `diff_bills` on
119-hr-1 v1→v2 emits at `sec. 10012`:

```
removed   old_len=1443   'Alien SNAP eligibility'
added     new_len=2242   'Alien SNAP eligibility'
moved     133 -> 133     'Emergency food assistance'  (correctly relocated to sec. 10013)
```

The two Alien SNAP nodes **carry identical headers**, and the v1 tree has a `match_path` collision
(two sections at `sec. 10012`). So on this pair, as it exists now: text containment fails, and header
equality would succeed. That is the exact opposite of the reading §7 builds on it. Note also that the
original labeler's own rationale said so — *"The identical section header ('Alien SNAP eligibility')
is the signal that would keep it linked"* — and the paper's §6.3/§7 framing did not carry that
forward.

**Scope discipline:** this is one pair, re-measured. It does not establish that structure beats text
in general. It does establish that the single exemplar the text-only reading leans on hardest no
longer supports it, and that Study 2 must re-derive its labels before calibrating anything.

**Independently confirmed by the repo's own regeneration path.** `scripts/build_similarity_labels.py`
re-derives every label's text from `tests/corpus/`, so it is the authority on whether the key still
rebuilds. It does not. Two defects, in order:

1. It is broken by the same #492 rename as the probes (`_MOVE_THRESHOLD`, `_SIMILARITY_THRESHOLD`,
   `_text_similarity`), so it exits on `ImportError` before doing anything. Unlike the probes it
   lives in `scripts/`, which *is* linted, and it still went unnoticed. **Fixed in this branch.**
2. Once it runs, it fails on the first drifted pair:

```
LookupError: modified ('corps of engineers—civil',
                       'general provisions—corps of engineers—civil', 'sec. 110') not found
```

That is `contested-2-corps-110`, one of the exact three pairs `probe_r2` independently flagged. The
cause is visible in `probe_r2` section 3: the engine no longer emits a `modified` record at that
path, it emits `added` + `removed`. So the drift is behavioural as well as textual.

**Three independent observations agree** — the stored text does not resolve to a node; the engine's
change type at that path has changed; and the fixture builder cannot rebuild the key. So the answer
key is currently **unregenerable**, and has been since at least the #492 refactor.

**Why nothing caught it.** `tests/test_similarity_labels.py` passes, and passing is consistent with
the key being decayed. Its own docstring says so: *"Self-contained: no `bills/` dependency."* It
scores `pair["text_old"]` — the frozen string — so it re-verifies that the stored text still gets the
stored score, which is true by construction and stays true forever. It is a threshold-regression
test, correctly, and it is not a drift guard. Nothing else was.

`pass2-protocol.md` §4 already has the right policy for this — a `text_sha256` mismatch quarantines a
pair for re-review rather than auto-refreezing. Two gaps: the policy was written for *future*
candidates and was never run against the *existing 12*, and the current fixture carries no
`text_sha256` field at all, so there is nothing for it to check.

---

## The eleven claims

### 1. The implemented "containment" may not be asymmetric

**Verdict: CONFIRMED as to the description. REJECTED as to the consequence.**

**Evidence.** Seven byte-identical copies of the measure exist across the probes
(`mine_common.py:45`, `probe_b1_tfidf.py:78`, `probe_b1_validate.py:67`, `probe_b2_multisignal.py:64`,
`probe_generalization.py:62`, `probe_consolidation.py:52`, `probe_review_gameability.py:78`). All
compute `sum(min(a[t],b[t])) / min(mass_a, mass_b)`. Both numerator and denominator are symmetric.
`probe_r1_containment_direction.py`:

```
max |contain(a,b) - contain(b,a)| over the 12 labeled pairs : 0.000e+00
max |contain(a,b) - contain(b,a)| over 20,000 random vectors : 0.000e+00
```

It is a **tf-idf-weighted overlap coefficient** (Szymkiewicz–Simpson), not a directional measure, and
**not a Tversky index for any fixed (α,β)**. Algebraically it is exactly `max(B, C)` — the maximum of
the two directional containments (`max |A − max(B,C)| = 0.000e+00`), because dividing by the smaller
mass yields the larger quotient.

Containment is **absent from production entirely** — `src/deltatrack/similarity.py` is word-overlap
only. This is a research-probe measure, so the mislabel has no runtime consequence today.

**The consequence does not follow.** `A ≡ B` on exactly the 7 of 12 pairs whose old side is lighter —
which is the definition of stub→expansion. Benchmarked on the same data (margin = min same − max
different; no threshold fitted):

| variant | margin | alone (resub) | §6.2 rule @ published cutoffs | 2-signal LOBO |
|---|---:|---:|---:|---:|
| **A current (min-side)** | **+0.440** | 12/12 | **12/12** | 11/12 |
| **B old-side (Tversky α=1, β=0)** | **+0.440** | 12/12 | **12/12** | 11/12 |
| C new-side (α=0, β=1) | −0.388 | 10/12 | — | 9/12 |
| D Tversky α=β=1 (Jaccard) | −0.206 | 10/12 | — | 9/12 |
| D Tversky α=β=0.5 (Dice) | −0.311 | 10/12 | — | 9/12 |
| D Tversky α=1, β=0.1 | −0.103 | 11/12 | — | 9/12 |

The genuinely directional measure reproduces the published 12/12 **identically**, and no swept
Tversky beats it. So the stub→expansion result **does not depend on directionality at all**, and the
property that produced the gain is not asymmetry — it is *normalising by the lighter side's rare-token
mass instead of by both sides*, which cosine does not do.

Where A and B differ, all three cases are `different`-labeled pairs and B scores **lower** (safer):
contested-3 0.365→0.202, contested-2 0.426→0.307, contested-1 0.439→0.346. Since `A = max(B,C) ≥ B`,
B is never more permissive. The 12 pairs cannot separate them; §6.4's 60 reverse-direction candidates
are where they would diverge operationally.

**Impact.** No measured result changes. The theory section is wrong in ~6 places.

**Action — wording correction, plus one implementation decision deferred.** Rewrite the theory around
the measured object. Do **not** switch to B on this evidence: the 12 pairs tie, and the case for B is
currently theoretical. Log it as a Study 4 comparison on the reverse-direction population.

Sites to correct: `paper.md` §Abstract ("a weighted Tversky index"), §3 Family A ("ask an asymmetric
question", the α/β parenthetical), §5 ("asymmetric"), Part 1 ("a one-directional question we call
containment"), footnote [^3]; `probe_b1_tfidf.py:13` docstring ("asymmetric, stub-friendly").

---

### 2. Pass 2's estimation population may be conditioned on the current matcher

**Verdict: CONFIRMED, and the protocol's own framing is already half-right.**

**Evidence.** `pass2-protocol.md` §3 defines it exactly as challenged: *"all matched-changed decisions
the current matcher produces (each `modified` node + each `removed`/`added` pair it considered as a
split candidate)"*. `move_candidates()` (`similarity.py:91`) only returns pairs at or above the
threshold, so a pair that never reaches it was never "considered" and cannot be sampled.

The size of the blind spot is measurable. On 119-hr-1 v3→v4 (`probe_consolidation.py`, current
corpus): 516 removed provisions survive the word-overlap move rescue with **0** re-pairable at ≥0.6.
Every true counterpart among those 516 is invisible to a sampler defined over considered pairs.

**What the population can legitimately support.** It is an unbiased sample of **the decisions the
current matcher emits**. From it you can honestly estimate: the precision of `modified` decisions, the
precision of `moved` decisions, and the error rate of the split/keep call *among pairs the matcher
paired*. Those are real, useful, staffer-visible quantities.

**What it cannot support.** Any recall statement, because the denominator (true counterparts) is not
sampled. So §3's *"This is the only unbiased source of a real-world precision/recall"* is wrong on the
recall half, and §7's "population precision-in-regime" is correctly named but sits in a population
that is itself matcher-conditioned.

The protocol's **challenge/estimation split (§1) survives fully** — it is the right distinction, and
it already anticipates most of this criticism. What is missing is a third thing: an *anchor-sampled*
set.

**Impact.** No Study 1 conclusion changes. Study 2 cannot claim recall as drafted.

**Action — protocol redesign (blocking).** Change the ground-truth unit from *decision* to *anchor*,
as the review proposes. Design in §B below.

---

### 3. The Study 1 generalization claim may be too strong

**Verdict: PARTLY CONFIRMED. The cross-type half is not supportable; the across-bills half is,
weakly, and is now further weakened by drift.**

**Evidence.** The answer key spans 4 bills, distributed **114-hr-2029: 1, 115-hr-5895: 4,
118-hr-4366: 6, 119-hr-1: 1**. So:

- **What LOBO demonstrates.** That the *containment values* stay separated when the rarity weights
  and the cutoff are refit without one bill. The paper states this correctly.
- **What it does not.** With 4 folds and this distribution, the 119-hr-1 fold tests on **exactly one
  pair**. A one-pair fold cannot estimate a generalization gap; it is a single Bernoulli draw.
- **Selection before LOBO.** §5 records that 6 of 12 were chosen *because the baseline misclassifies
  them*, and §8.3 already discounts the 6/12 for it. The measure, the two cutoffs, and the rule form
  were all chosen with all 12 pairs visible, so LOBO re-fits only the cutoffs — the *measure* choice
  is never held out. LOBO therefore bounds cutoff transfer, not method-selection overfitting.
- **The reconciliation evidence is one challenge exemplar, not a cross-type test.** It is a single
  pair (`extreme-alien-snap-10012`), deliberately selected as an extreme, from the one non-approps
  bill. And per the drift finding above, **that pair no longer reproduces**: its containment is 0.428
  today, not 1.000. So the sentence *"the measure generalizes across bills and across the
  appropriations→reconciliation boundary"* now rests on a data point that has inverted.

**Impact.** §6.5's "Reading" and the Part 1 bullet "the separation held up across the (few) bills we
could test — including one bill of a different type" both overstate. The Abstract's *"The measure
generalizes across the bills we tested"* is defensible for the 3 appropriations bills only.

**Action — wording correction (blocking, because Study 3 inherits it).** Justified wording:

> On the three appropriations bills with more than one labeled pair, rare-token containment's
> separation survives refitting the cutoff without any one bill. The corpus contains one
> reconciliation pair, selected as an extreme case; it is a single challenge exemplar and is not a
> cross-type generalization test. Cross-type generalization is untested.

---

### 4. The "full corpus census" may not validate accuracy

**Verdict: CONFIRMED.**

**Evidence.** `probe_b2_multisignal.py` collects `to_split` (base keeps, new rule splits) and
`to_keep` (base splits, new rule keeps) — pairs where the two rules **disagree**. `probe_b1_validate.py`
does the same with `new_splits`/`new_keeps` at a 0.55 bar. Neither reads any label; the corpus has no
exhaustive SAME/DIFFERENT truth.

- **Can they detect errors both methods make identically? No — by construction.** A pair where
  word-overlap and containment both say "keep" and both are wrong falls in neither bucket and is never
  printed. The census is structurally blind to shared error, which is the error class most likely to
  survive into production, since both measures are word-based.
- **Can they support "text carries most of the accuracy gain"? No.** That is a comparison against a
  structural alternative, and no head-to-head was run. `paper.md` Appendix A itself records that
  `probe_classifier.py` (structural-only) scores **12/12 on the same 12 pairs** — so the labeled set
  cannot separate text from structure at all. §6.3's own honesty note says the structural rescues are
  "asserted"; the Abstract and the §Scope "settled enough to build on" bullet then promote it to
  settled.

**Reclassification.** Of the corpus-level claims:

| claim | actual evidential status |
|---|---|
| "25 of 1,287 decisions change" | **directly measured** (a disagreement count) |
| "~19–20 clearly correct, ~3 wrong, ~2–3 borderline" | **human-inspected**, unblinded, single rater, n=25 |
| "containment's failure modes are real" | **human-inspected**, and independently corroborated (C7) |
| "text carries most of the accuracy gain" | **inferred**, and contradicted by structural-only 12/12 |
| "the corpus census validates the rule" | **not established** — it censuses disagreement, not correctness |

**Impact.** §6.2's "Corpus census" paragraph, the §Scope settled-bullet, and the Abstract's "the text
measure alone carries the gain" all need restating. The 25-change count itself stands.

**Action — wording correction + rename.** Call these **disagreement analyses**, not censuses. Demote
"text carries most of the gain" from *settled* to *not yet measured*, alongside the structural half it
is contrasted with — the honest statement is that **the labeled set cannot distinguish them.**

---

### 5. The IDF definition itself may create artifacts

**Verdict: REJECTED for the ranking. CONFIRMED for the calibration — which the paper already says.**

> **↪ Round 2 (§R2-5).** Scope correction: every score here is computed on the fixture's **frozen
> strings**, so as written this was a claim about historical observations. `probe_r5` §2b now
> repeats the analysis over only the nine pairs whose stored text still resolves in the current
> parse. Every margin is unchanged to three decimals, so the result does **not** rest on the three
> quarantined records — but the claim is now scoped by a probe rather than by assumption, and the
> five variants are frozen for re-running after re-adjudication.

**Evidence.** `probe_r5_idf_ablation.py`, five preregistered DF definitions over one held-constant
corpus (34 bills), measure and 0.70 bar held constant:

| variant | documents | max different | min same | margin | 0.70 bar still works |
|---|---:|---:|---:|---:|:--:|
| V1 per-version (Study 1) | 65,502 | 0.526 | 0.929 | **+0.404** | yes |
| V2 dedup bodies per bill | 37,959 | 0.529 | 0.929 | **+0.400** | yes |
| V3 one document per bill | **34** | 0.632 | 0.956 | **+0.324** | yes |
| V4 numerics dropped | 65,502 | 0.672 | 0.985 | **+0.313** | yes |
| V5 citations dropped | 65,502 | 0.488 | 0.915 | **+0.427** | yes |

**Every variant preserves the ordering and the keep bar**, including V3, which collapses the corpus
from 65,502 documents to 34 — an extreme stress that should break a fragile rarity model and does not.
So on this evidence rarity is acting robustly as identity evidence, and the headline separation is
**not** an artifact of one tokenizer or one corpus definition.

Two hypothesised effects ran backwards:

- **Citations do not dominate.** Removing them *improves* the margin (+0.427, the best of the five).
  On the 12 pairs, containment is not citation-carried. (This says nothing about the false-keep mode,
  which the 12 pairs structurally cannot test — §8.2 — and where C7 shows citations do matter.)
- **Numbers carry discriminative signal.** Dropping them is the *worst* variant (+0.313) and pushes
  `contested-5-ag-to-hhs` (different) to 0.672, within 0.03 of the keep bar.

**What is confirmed:** absolute values move by up to 0.24 across variants (contested-3: 0.377→0.618).
A cutoff fixed under one definition is not portable to another. That is `paper.md` §8.4 restated, and
it reinforces it.

One real artifact, found by C6 rather than the ablation: bodies that are a single token (literally
`"$0."`) score containment 1.000 against anything sharing that token. V4 is the only variant that
neutralises it. This is narrow but it lands in the financial stratum, so it matters (see C6).

**Impact.** Strengthens Study 1's measure claim; changes nothing about the cutoffs.

**Action — no change to the measure.** Record the ablation as a robustness result. Add a minimum-token
floor to the *financial* miner rather than changing the global tokenizer.

---

### 6. The financial-line miner may exclude severe false-splits

**Verdict: CONFIRMED for the discovery floor (severe, quantified). REJECTED in practice for the text
source, though the latent coupling is real.**

> **↪ Round 2 (§R2-3).** The 240 is a **discovery population**, not a set of known correspondences:
> removed financial provisions in a version pair that also has at least one added financial
> provision. Some correspond to nothing. So 84.6% is the share of that population the miner cannot
> reach — a fact about the sampling frame. How many are genuine missed correspondences is unknown
> until labeled. The methodological conclusion is unaffected. The PR description's "hides 203 of
> 240 **eligible cases**" overstated it and is corrected.

**Evidence — the floor.** `mine_financial_lines.py:53` sets `SPLIT_SIM = 0.50` and line 139 gates
candidate discovery on `_text_similarity(ro, an) >= SPLIT_SIM`. `probe_r3_financial_miner.py` over the
union corpus (71 adjacent version pairs):

```
removed financial nodes with >=1 added financial partner available : 240
  best word-overlap >= 0.5 -> miner CAN see them    :  37 (15.4%)
  best word-overlap <  0.5 -> miner CANNOT see them : 203 (84.6%)
Of the invisible ones, with a strong containment partner (>= 0.70): 40
```

**The floor removes 84.6% of the population from discovery**, and 40 of the excluded have a strong
independent-signal partner — the severe-false-split shape the stratum exists to sample. Tanker appears
directly in the invisible set (`118-hr-4366 word=0.48 contain=0.936 [maritime administration/tanker
security program]`), confirming the review's specific example. The exclusion is not incidental: the
miner filters on the *same quantity whose failure it is studying*, so the worse the false split, the
less likely it is to be sampled.

**Evidence — the text source.** Production reads `amount_source_old/new` (`diff_bill.py:689,736`); the
miner reads `old_text/new_text`. I tried to falsify the claim that this matters and **succeeded**:
over **67,983 change records, 0 disagree**. `NodeDiff` documents this as a deliberate no-op pinned by
`TestAmountSourceCorpusRegression`. So there is no current measurement error. The coupling is still
wrong — the fields exist because the renderings *did* diverge (#365), and nothing pins the *miner* the
way the engine is pinned — but it is a latent-defect finding, not an active one.

**Impact.** The financial stratum as mined is not fit for its stated purpose. `pass2-protocol.md` §0's
"34 found, mostly 119-hr-1" is a count of what survived the floor, not of what exists.

**Action — implementation change (blocking, before any financial labeling).**
1. Make discovery signal-independent: retrieve candidates by **union** of word-overlap, containment,
   and same-account structural path; record which retriever(s) found each. Never gate discovery on the
   measure under evaluation.
2. Read `amount_source_old/new`, matching production.
3. Add a minimum-token floor so single-token bodies (`"$0."`) cannot reach containment 1.0.
4. Re-mine and re-report the population; the current 34/80 split numbers do not survive.

---

### 7. Cross-bill high-containment negatives may prove vulnerability but not prevalence

**Verdict: CONFIRMED on the logic — and the direction of the error is the opposite of the one
implied.**

> **↪ Round 2 (§R2-2). The "opposite direction" conclusion was not established by the evidence
> below.** The two numbers in the table differ in three ways at once — per-comparison vs
> per-anchor, unmatched candidate-set size, and (unnoticed by either round) **two different rarity
> models**. `probe_r6_rate_parity.py` re-runs it with all three held constant. The direction does
> survive in aggregate: 0.412% vs 0.054% per comparison, CIs disjoint. It does **not** survive
> removing 119-hr-1, which supplies 24 of the 27 hits: 0.592% [0.271, 1.285] vs 0.281%
> [0.217, 0.364], overlapping. And "0/976" was never evidence of a low cross-bill rate — at the
> measured control rate, 976 draws expect 0.53 hits, so zero is the likeliest single outcome.
> Cite §R2-2's numbers, not this table's.

**Evidence.** The construction is as described: `probe_review_gameability.py` and
`mine_high_containment_different.py` pair a short provision in bill A against a long one in bill B.
Production never does this — a move candidate is drawn only from the removed/added sets of one
adjacent version pair of one bill. So the cross-bill rate is not an operational false-positive rate.
That much is straightforwardly right.

But running the **identical construction inside the production neighbourhood**
(`probe_r4_production_neighborhood.py`) inverts the expected relationship:

| construction | population | rate at containment ≥ 0.70 |
|---|---|---:|
| cross-bill random (existing probe) | 4,000 random short×long pairs | 10/4,000 = **0.2%** |
| cross-bill random, **cited** shorts | 976 pairs | **0/976 = 0.0%** |
| **production neighbourhood** | 77 short(cited) removed provisions | **27/77 = 35.1%** have ≥1 such partner |

The random cross-bill probe finds **zero** hits among cited shorts; its 10 hits are degenerate
boilerplate (`"For other joint items, as follows:"`, `"In this division:"`). Inside one bill, where
drafting vocabulary, account names and statute targets are shared, **rare-token coincidence is far
more likely, not less.** The cross-bill mine is therefore an *easier* case than production, not a
worst case.

The `~1,330 pairs corpus-wide` figure (`pass2-protocol.md` §0) is a **count produced by targeted
blocked search over `bills_corpus`**, not a rate and not a sample. It supports "the failure mode
exists and is findable at scale". It supports nothing about frequency.

**Caveat, stated because it bounds the conclusion.** The 27/77 are **not labeled false keeps**. They
are pairs where a spurious keep is *available*. 119-hr-1 supplies 24 of the 27 and is the known
consolidation bill, where many will be genuine "absorbed into" relations. 118-hr-4366 supplies 3, and
those read as clear false keeps on inspection (`"None of the funds in this Act or any other Act shall
be used to enforce…"` matched to grant appropriations). Ruling these is exactly the labeling work.

**Impact.** The adversarial set stays, correctly characterised. The prevalence question was
unanswered and now has a first, unlabeled answer that raises rather than lowers concern.

**Action — keep the set, relabel the claim, adopt the new probe.** Describe the cross-bill mine as
*failure-existence / hard-negative mining*. Add `probe_r4` to the standing probe set and make the
production-neighbourhood pairs a labeled stratum — they are more operationally relevant than the
cross-bill ones.

---

### 8. Consolidation mining may be circular with respect to containment

**Verdict: CONFIRMED, quantified.**

**Evidence.** `mine_consolidation.py:73-82` computes, for each removed provision, its best added
target **by containment**, then keeps it only if `c >= 0.70 and wr < 0.60`. So a candidate must be
retrieved by containment to exist, and the label set can only ever answer *"among consolidation
candidates containment retrieved, which are genuine?"* — precision among retrieved. Two further
narrowings compound it: only the single **argmax** target is emitted (a genuine many-to-one whose true
target is not the argmax is lost), and `wr < 0.60` removes anything word-overlap already caught.

The blind spot has a size. On 119-hr-1 v3→v4 (`probe_consolidation.py`, current corpus): **516**
leftover removed provisions, of which containment recovers **271**. The other **245 (47.5%)** are
unobservable to any label set built this way. Consolidation **recall is not estimable** from the
current design — only precision-among-retrieved.

> **↪ Round 2 (§R2-4).** Stated exactly: those 245 are **excluded from the annotation
> population**, not 245 known consolidation relationships. Some correspond to nothing. The
> sentence above already says "unobservable to any label set built this way", which is the correct
> framing and survives; the PR description's "makes 47.5% **of relationships** unobservable" does
> not, and is corrected. The conclusion — no denominator, so no recall — is unchanged either way,
> because it follows from the exclusion alone.

**Impact.** `pass2-protocol.md` §9.1's acceptance criterion ("≥25 consolidation") can be met while
recall stays unmeasured. §7's consolidation numbers are precision-like only.

Note also that the §6.4 figures have drifted with the parser: paper reports 493 removed / 265
recovered / 74 one-to-one / 41 many-to-one / 88 reverse; current run gives **516 / 271 / 66 / 42 / 60**.

**Action — bounded exhaustive annotation (blocking for any consolidation recall claim).** Do not
enlarge the whole stratum. Take **one bounded subtree** of 119-hr-1 v3→v4 (one committee/title with
roughly 30–50 removed provisions) and annotate correspondence exhaustively: for each removed
provision, its counterpart(s) among all added provisions in that subtree, retrieved for the human by a
**union** of containment, word-overlap, and structural path so no single measure gates discovery.
That yields a genuine recall denominator at a cost of tens of items, not hundreds, and it is the only
way to state a consolidation recall number at all.

**Relationship vocabulary.** The evidence supports needing **one-to-one, one-to-many, many-to-one,
none, uncertain**. `many-to-many` is not yet evidenced in our corpus — do not add it speculatively.

---

### 9. Labelers may be score-blind but hypothesis-primed

**Verdict: PARTLY CONFIRMED — the priming is real, already disclosed, and its measurable harm is
bounded. The genuine defect is a different one: the label space has no escape hatch.**

**Evidence.** The blindness work is substantial and should be preserved: scores stripped
(`make_worklist.py`), stratum name never shown, one card at a time, forced rationale on medium/low
confidence, and an automated leak guard (`blindness.py`, `leaks_in`) tested by
`tests/test_pass2_labeler.py`. `make_form.py:37-50` confirms the stratum-conditional question:

- high-containment-different → *"Are these the same provision carried across versions, or two different provisions?"* → `same` / `different`
- financial-line → *"…same account/line (an amount edit of one line), or two different lines?"* → `same` / `different`
- consolidation → *"Is the OLD provision genuinely absorbed into the NEW section, or only coincidentally sharing a citation?"* → `genuinely-absorbed` / `coincidentally-contained`

`pass2-protocol.md` §5 already discloses this precisely, including that it is *correlated* framing
across the human and LLM labelers, and already floats a uniform question as a future simplification.
So this is a known, documented design choice, not a hidden bias.

**Why the harm is bounded.** §5's mapping folds `coincidentally-contained` into the false-keep
positive and `genuinely-absorbed` into "same", so the same/different metric is recoverable from the
consolidation labels regardless of the wording. All four decision standards are shown to every
reviewer, so the *concepts* are not stratum-private.

**The real defect.** The consolidation question is a **forced binary between two hypothesis-laden
options**. A candidate that is simply *unrelated* — neither absorbed nor sharing a citation — has no
correct answer, and the reviewer must file it under "coincidentally contained", which presupposes a
shared citation that may not exist. There is no `none`, no `unrelated`, and no `uncertain`
(`confidence: low` is a separate axis and does not mean "no answer fits"). Given C8, where the miner
retrieves by containment and 47.5% of relationships are unobservable anyway, a label space that cannot
express "no relationship" is the more consequential problem.

**Action — targeted UX change (blocking, small).** Do **not** restructure into a two-stage relationship
label on this evidence; the present same/different categories are adequate for the two same/different
strata and the change would cost the existing blindness guarantees. Instead:
1. Add `unrelated` and `uncertain` to the consolidation label space.
2. Adopt the uniform question §5 already proposes for the two same/different strata.
3. Keep everything else — the blindness machinery is the strongest part of this pipeline.

---

### 10. Check the literature inference about text-only success

**Verdict: PARTLY CONFIRMED. The citation is accurate; one inference drawn from it is not.**

**Evidence.** `paper.md` handles Kim et al. carefully in most places. §3 Family D explicitly offers
both readings and declines to resolve ("Two honest reads of that fact coexist… we flag it rather than
resolve it"), and footnote [^5] describes the work accurately (4,721 hand-labeled subsection pairs,
BERT/Legal-BERT, no positional features).

The overreach is in §3 Family A and §7, where Kim et al. is enlisted as one of "two data points [that]
cut against needing [structural confirmers] at all". That conflates two different propositions:

- **Supported:** semantic text models are viable for detecting relationships between legislative texts.
- **Not supported:** structural context has no marginal value for DeltaTrack's cross-version
  provision-identity problem.

They differ in task and in evidence type. Kim et al. classify *bill-pair similarity* on hand-labeled
subsection pairs; DeltaTrack must *resolve identity across consecutive versions of one bill*, where
the confusable negatives are boilerplate twins and reused section numbers inside the same document —
a population Kim et al.'s task does not contain. Absence of structural features in their model is
evidence that structure was **not necessary for their task**, not that it carries **no marginal
value** for ours. Establishing the latter requires an ablation on our data, which §7 itself concedes
has never been run.

The second "data point" — this study's own text-only 12/12 — is not independent evidence either, since
`probe_classifier.py`'s structural-only rule also scores 12/12 (see C4).

**Impact.** §7's "Two data points cut against needing them at all" does not hold. §3 Family D's
two-readings framing is fine and should be the model.

**Action — wording correction.** Replace the §7 sentence with: *Kim et al. establish that content
embeddings suffice for their bill-similarity task; they do not measure structure's marginal value for
cross-version identity, and neither do we. Our labeled set cannot separate the two, since a
structural-only rule also scores 12/12 on it.*

---

### 11. Reproducibility and research-state cleanup

**Verdict: CONFIRMED, worse than described. Repaired in this branch.**

**Evidence — the probes did not run at all.** Two independent breakages:

1. **Renamed imports (#492).** All 15 probe files hardcoded
   `Path("/Users/williamhea/Documents/Code/civictech/appropriations_bills")`, and 13 imported
   `_text_similarity` / `_MOVE_THRESHOLD` / `_SIMILARITY_THRESHOLD` from `deltatrack.diff_bill`. Those
   moved to `deltatrack.similarity` and lost their underscores. Verified as a **pure rename** (`git
   show 1d5836a`), so numbers reproduce once fixed.
2. **Corpus relocation (#308).** The probes read `bills/`; the curated fixtures moved to
   `tests/corpus/`. See the environment note at the top.

So `paper.md`'s *"Every number in Part 2 can be reproduced from the scripts named in Appendix A"* was
**false at review time** — none of them executed.

**Evidence — the breakage reaches outside the probes directory.**
`scripts/build_similarity_labels.py`, the answer key's regeneration path, is broken by the same
rename. That file is **not** ruff-excluded and is referenced by `tests/test_similarity_labels.py`'s
docstring as the way to re-freeze the fixture, and it still went unnoticed, because nothing runs it.
Fixed here; it now reaches its real failure (see the drift section above).

**Evidence — promised artifact missing.** `probes/eval_pass2.py`, promised by `pass2-protocol.md` §2.4
and load-bearing for §7, **does not exist**.

**Evidence — stale numbers.** Beyond the corpus table above: §6.4's consolidation figures (493/265/74/
41/88 vs current 516/271/66/42/60); `pass2-protocol.md` §0's "~1,330 pairs" (a targeted-search count
presented adjacent to rate language); §5's "64,276 provision bodies" (the union now yields 65,502, and
`mine_idf.py`'s own cache is built over a different, much larger pool — 232,924 bodies over 2,983
bills — so two rarity models coexist in one research program without the difference being stated).

**Repairs made in this branch** (mechanical only; no result rewritten):
- All 15 probes: absolute path → `Path(__file__).resolve().parents[4]`.
- 13 probes: renamed imports fixed.
- New `probes/corpus_roots.py` — union-corpus resolver + `merged_root()` symlink view, so probes read
  the whole corpus by changing one line.
- Verified no new lint: the 23 remaining ruff findings are pre-existing style in these
  deliberately-frozen scripts (12 E501, 5 E701, 3 E702, 2 F541, 1 I001); zero F401/F821.

**Action — remaining.** Write `eval_pass2.py` or delete the promise. Add a CI smoke test that
imports every probe, so the next rename fails loudly instead of silently. Mark superseded documents
explicitly rather than editing their conclusions.

---

## A. Revised statement of what Study 1 actually established

The strongest wording the evidence supports:

> On a 12-pair hand-labeled set drawn from four bills — six of them selected because the word-overlap
> baseline misclassifies them — a rare-token **weighted overlap coefficient** separates SAME from
> DIFFERENT with a margin of ~0.40, where word-overlap does not separate them at all and TF-IDF cosine
> misranks the stub→expansion cases. The separation is **robust to how rarity is defined**: five
> different document-frequency constructions, including one that collapses the corpus to 34 documents,
> all preserve the ordering and the 0.70 bar. It is **not robust as a calibration**: absolute values
> move by up to 0.24 across those same definitions, and leave-one-bill-out shows the cutoffs do not
> transfer.
>
> The measure is **symmetric** — a tf-idf-weighted overlap coefficient, exactly the maximum of the two
> directional containments — not the asymmetric Tversky index Study 1 describes. The property that
> produces the gain is normalising by the lighter side's rare-token mass; directionality is not
> required, and a genuinely directional variant reproduces every published result identically.
>
> Two claims Study 1 records as settled are **not established**. That "the text measure alone carries
> the accuracy gain" was never measured against a structural alternative, and cannot be: a
> structural-only rule also scores 12/12 on the same set. That the measure "generalizes across the
> appropriations→reconciliation boundary" rests on a single selected exemplar.
>
> **The labeled set has partly decayed.** Three of twelve pairs no longer correspond to any node the
> current parser emits. For the flagship stub→expansion case, re-deriving the pair from today's parser
> moves containment from 1.000 to 0.428 — below the keep bar — so the study's central exemplar now
> argues against the rule it was cited to support, while its identical section headers argue for the
> structural signal the study set aside.
>
> Containment's own false-keep mode is real, is untestable on this set, and is **more prevalent inside
> the production neighbourhood than in the cross-bill adversarial construction** used to demonstrate
> it: 35.1% of short cited removed provisions have a ≥0.70 partner available within their own bill
> version pair, against 0/976 for random cross-bill cited pairs.

> **↪ Round 2 (§R2-2)** replaces that last paragraph. The wording the evidence supports is:
>
> > Containment's own false-keep mode is real and is untestable on the 12-pair set. Holding the
> > anchor set, the rarity model and the candidate-set size constant, a spurious ≥0.70 partner is
> > available about **7.6× more often inside a bill than across bills** (0.412% vs 0.054% per
> > comparison, disjoint 95% CIs). That aggregate rests almost entirely on one bill: with 119-hr-1
> > removed the intervals overlap, and 119-hr-1 is the known consolidation bill, where a
> > high-containment pair is most likely to be a genuine "absorbed into" relation rather than an
> > error. So this is an **unlabeled opportunity rate**, and the direction is suggestive rather
> > than established. Cross-bill mining demonstrates that the failure mode exists; it does not
> > estimate operational prevalence, and neither does this until the pairs are ruled.

Unchanged and still sound: the problem framing (entity resolution over an ordered tree with an
unstable key), the signal inventory, the header-coverage table, that word-overlap measures the wrong
quantity, and the honesty apparatus in §8 — which anticipated more of this review than the review's
author expected.

---

## B. Revised Study 2 experimental design

> **↪ Round 2 (§R2-1, §R2-C).** The anchor unit survives and is right. The **candidate-union**
> mechanism below does not: a union of retrievers is still a retriever, so an anchor whose true
> counterpart every retriever misses is recorded as NONE and candidate recall computed from that
> dataset is 100% by construction. Measured on the corpus, the union@8 fails to show a
> header-identical candidate for **18.1%** of the anchors that have one
> (`probe_r8_oracle_gap.py`). §R2-C replaces this section's ground-truth mechanism with a
> region-exhaustive oracle and keeps everything else.

Keep the protocol's architecture. Its challenge/estimation separation (§1), by-bill splitting (§6),
blindness machinery (§5), and correlated-error caveat (§8) all survived challenge and are the strongest
parts. Three changes, then five clearly-separated evaluation targets.

### The unit changes from *decision* to *anchor*

Sample **provisions in version A**, not pairs the matcher produced. For each sampled anchor the human
records its counterpart(s) in version B — **including NONE and including MANY**. This is the only unit
from which recall is computable, and it makes every stage below measurable from one label set.

Candidates shown to the human are retrieved by a **union** of retrievers (structural path,
word-overlap, containment), with the retriever recorded per candidate and hidden from the labeler. No
single measure may gate discovery anywhere in Study 2 — that is the generalisation of the C6 and C8
defects.

### Five targets, never conflated

| # | target | question | population | metric |
|---|---|---|---|---|
| 1 | **candidate recall** | did the true counterpart enter the candidate set? | anchor sample | recall @ candidate-set |
| 2 | **ranking / scoring** | was the true counterpart preferred to false ones? | anchors with a true counterpart | top-1 accuracy, MRR |
| 3 | **assignment** | did the global matching pick the right correspondence? | anchors in collision groups | assignment accuracy |
| 4 | **final diff correctness** | did the staffer see the right modified/added/removed/moved? | anchor sample | per-anchor confusion matrix |
| 5 | **failure-mode existence** | does mode X occur, and how badly? | challenge strata | worst-case rate, **never a precision** |

Targets 1–4 are population estimates from the anchor sample. Target 5 is the challenge set and its
base rate is rigged by construction — the protocol §7 already says this and it must stay said.

### MVP cost

Deliberately small, because the point is to make the ruler honest, not large.

- **Anchor sample: 80 anchors.** Stratified by leaf level (account / section / subsection) and drawn
  proportionally across dev bills, with a separate held-out draw. Each anchor is one screen: the old
  provision, and ~8 union-retrieved candidates to accept, reject, or mark none/many.
- **Bounded consolidation subtree: ~40 anchors** in one committee subtree of 119-hr-1 v3→v4,
  annotated exhaustively (C8). This is the only recall denominator consolidation will have.
- **Financial stratum: re-mined** without the 0.50 floor (C6), then ~40 anchors.
- **Challenge strata: keep the existing pools**, re-characterised per C7, plus the
  production-neighbourhood pairs from `probe_r4` as a new and more operationally relevant stratum.

Roughly 160 labeled anchors, against the protocol's current ~150 pairs — comparable effort, and it
answers recall, which the current design cannot answer at any size.

### What stays exactly as drafted

By-bill splitting; scores stripped at label time with the automated leak guard; structural context
shown; per-stratum Cohen's kappa with support counts; the LLM as disagreement-flagger and reliability
screen but never a vote; Will's adjudication recorded before reading the LLM rationale; no silent caps.

---

## C. Blocking vs non-blocking

> **↪ Round 2 (§R2-E).** Superseded by the round-2 table. Three items move: the oracle design
> becomes a blocker in its own right, the evaluator moves from non-blocking to blocking (item 8
> below was wrong), and the drift item is restated as re-derivation plus quarantine rather than
> re-labeling. Items already done in round 2 are marked there.

**Blocking — must happen before any human labeling resumes**

1. **Re-derive the 12 existing labels against the current parser** and quarantine every drifted pair
   for re-review (protocol §4's own policy, never yet run on them). 3 of 12 are affected; one inverts.
2. **Re-mine the financial stratum** without the measure-dependent floor, reading
   `amount_source_old/new`, with a minimum-token floor (C6). The current pool is not fit for purpose.
3. **Switch the ground-truth unit to anchors** and freeze the five evaluation targets (C2, §B). This
   changes what the labelers are asked to do, so it cannot follow labeling.
4. **Add `unrelated` / `uncertain` to the consolidation label space** (C9) — small, and cheap only
   before labels exist.
5. **Correct the wording that would otherwise be laundered into Study 2's premises** (C1, C3, C4, C10)
   — specifically the asymmetry description, the cross-type generalization claim, "census", and "text
   carries the gain".

**Non-blocking — can wait**

6. Rewriting the theory section around the overlap coefficient (C1) — beyond the one-line correction.
7. Benchmarking directional-B against A on the reverse-direction population (C1) — Study 4.
8. `eval_pass2.py` (C11) — needed before *metrics*, not before labeling.
9. The probe-import CI smoke test (C11).
10. Superseded-document marking (C11).
11. Any decision about adopting structural confirmers (C4, C10) — Study 4, and now better motivated.

---

## D. New and changed reproducibility probes

All committed, all run from a normal checkout, all outputs quoted above.

| probe | decides | headline output |
|---|---|---|
| `corpus_roots.py` | *(infrastructure)* union-corpus resolver + merged view | 34 bills / 106 versions / 71 adjacent pairs |
| `probe_r1_containment_direction.py` | C1 | symmetry exact to 0.0; A ≡ max(B,C); A ≡ B on stub cases; 12/12 under both |
| `probe_r2_label_drift.py` | the drift finding | 3/12 labels unresolvable; Alien SNAP 1.000 → 0.428 |
| `probe_r3_financial_miner.py` | C6 | 203/240 (84.6%) invisible to the miner; 0/67,983 text-source disagreements |
| `probe_r4_production_neighborhood.py` | C7 | 27/77 (35.1%) in-bill vs 0/976 cross-bill cited |
| `probe_r5_idf_ablation.py` | C5 | all 5 rarity definitions preserve separation and the 0.70 bar |

Repaired (mechanical, no results rewritten): 15 probes de-hardcoded; 13 import-fixed.

---

## E. Documentation changes

Proposed, **not yet applied** — the review comes first, per the brief. History is preserved: nothing
is rewritten to look as though it was always right.

1. **`paper.md`** — add a dated **"Corrections after adversarial review (2026-08-06)"** block
   immediately after the Status header, linking here, carrying: the measure is a symmetric weighted
   overlap coefficient; the cross-type claim is one exemplar; "census" means disagreement analysis;
   "text carries the gain" is not established; and the Alien SNAP drift. Correct the six asymmetry
   sites in place with a footnote pointing at the block. Leave §6–§8's numbers standing with a note
   that they were computed on the pre-#308 corpus.
2. **`pass2-protocol.md`** — add a **§0b (2026-08-06)** update block in the same style as its existing
   §0: the anchor-unit change, the five evaluation targets, the financial re-mine, the consolidation
   subtree, and the label-space addition. Annotate §3's estimation-population definition inline rather
   than deleting it.
3. **`README.md`** — add `review-2026-08-methodology.md` to the contents table; add `corpus_roots.py`
   and the five `probe_r*` scripts to the reproduce section; fix the run instructions, which currently
   name a `PYTHONPATH=.` prefix and a `bills/`-only corpus that no longer hold.
4. **`methodology.md` / `spike.md`** — add a one-line header marking each as retained for research
   history and superseded by `paper.md` plus this review. Do not edit their conclusions.
5. **Memory** — `project_issue_56_similarity_thresholds` should record that the labels drifted and
   that labeling stays gated, so a future session does not resume from the stale premise.

---
---

# §R2 — Second adversarial review (round 2)

**Target: this document.** A second independent review put twelve criticisms to the round-1 review
itself, on the standard round 1 was held to: try to falsify each one against the code and the
corpus first, and only then act on it. Four hold as stated, six hold in part, and two attempts to
falsify succeeded well enough to leave the criticism materially narrower than it was put.

Two round-1 conclusions are overturned rather than refined, and both were overconfident in the same
way — a number was reported as evidence for a causal or comparative claim it could not carry.

**Failed falsification attempts are reported below alongside successful ones**, because the ones
that failed are what makes the surviving criticisms load-bearing.

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | anchor truth still conditioned on retrieval | **CONFIRMED**, now measured | oracle redesigned; 18.1% gap demonstrated |
| 2 | 35.1% vs 0/976 has incompatible denominators | **CONFIRMED**, worse than stated | re-run; direction survives in aggregate only |
| 3 | financial 84.6% denominator | **PARTLY CONFIRMED** | restated literally; conclusion unchanged |
| 4 | consolidation 47.5% interpretation | **PARTLY CONFIRMED** (review text survives; PR text does not) | PR corrected |
| 5 | IDF robustness over-claimed | **PARTLY CONFIRMED**; bite falsified | scoped by probe; margins unchanged on the live 9 |
| 6 | "label decay" is the wrong model | **CONFIRMED**, and it inverts the diagnosis | parser drift, not decay; provenance schema |
| 7 | all-five-version claim had no reproducer | **CONFIRMED** | `probe_r2` §4, all twelve labels |
| 8 | evaluator must be blocking | **CONFIRMED** | schema + fixture + evaluator + tests built |
| 9 | `merged_root()` can go stale | **CONFIRMED** | content-addressed; tested both ways |
| 10 | corpus manifest missing | **CONFIRMED**, worse than stated | manifest + banner + committed snapshot |
| 11 | blocking list insufficient | **CONFIRMED** | §R2-E |
| 12 | do not adjudicate the drifted records | **ACCEPTED** | blind packet built, not adjudicated |

---

## §R2-1. Anchor ground truth is still conditioned on candidate generation

**Verdict: CONFIRMED. Attempted falsification failed, and the failure is quantified.**

**The criticism.** Round 1's §B shows the human ~8 candidates retrieved by a union of structural
path, word overlap and containment, and asks SAME / NONE / MANY. If all three retrievers miss the
true counterpart, the human answers NONE, the dataset records "no counterpart", and candidate
recall computed from that dataset is 100% by construction.

**Falsification attempted.** The criticism is unanswerable in principle — a union of retrievers is
a retriever — so the only way it could fail to matter is if the union were *effectively* exhaustive
in this corpus. `probe_r8_oracle_gap.py` tests that by holding out a fourth signal none of the
three uses: exact header-text equality between the anchor and a candidate. Over the union corpus:

```
removed provisions examined (anchors)                      : 1144
anchors with a header-identical `added` provision available:  243
of those, the union@8 does NOT show the header twin        :   44 (18.1%)
```

So for nearly one in five anchors that has an obviously relevant candidate, that candidate never
reaches the human. The examples are the expected shape — an anchor in a 747-provision neighbourhood
whose twin is ranked out by three retrievers that agree with each other. **This is a lower bound**:
a header twin need not be the true counterpart, and a true counterpart need not share a header, so
nothing here bounds the real hole from above.

**The distinction round 1 collapsed**, stated explicitly because the whole design turns on it:

| | candidate suggestions | the truth universe |
|---|---|---|
| purpose | make annotation fast | decide whether a counterpart exists |
| may be produced by | any retriever, including the measures under test | nothing under test |
| may be incomplete | yes, that is what candidate recall measures | no — incompleteness becomes false NONEs |
| recorded per | candidate (`retrievers`) | anchor (`truth.oracle`, and `region_id`) |

**The oracle, chosen for cost.** Full-document browsing is the obvious independent universe and is
too expensive to be the default. `probe_r8` §2 measures the cheaper one — reviewing every provision
in a bounded structural region of the new version — on the real corpus, so the choice is priced
rather than asserted:

| bound | n | median | mean | p90 | max |
|---|---:|---:|---:|---:|---:|
| anchor's parent path | 1124 | **0** | 13.9 | 44 | 855 |
| grandparent path | 952 | **0** | 24.6 | 95 | 285 |
| top-level division | 1138 | **37** | 56.1 | 104 | 855 |

The median of 0 at the two tighter bounds is itself a finding: renumbering means the anchor's old
parent path frequently does not exist in the new version at all, so a region defined by *the
anchor's old path* is empty for most anchors and would make "none" trivially true — the failure
mode in a new costume. **The region must be defined on the new version's own structure** (a
division/title/account that exists there), which is the row that resolves: median 37, p90 104.

**Design consequence — sample regions, not anchors.** Reviewing 37 provisions per anchor is
unaffordable at 80 anchors and unnecessary: a region read once serves every anchor inside it. So
draw a small number of regions, take all anchors within them, and read each region once. ~4 regions
at median size is a few hundred reads and yields exhaustive truth for every anchor they contain.
This is the same move round 1's C8 made for consolidation, generalised to the whole design.

**Enforcement, not intention.** `pass2_schema.py` requires `truth.oracle` per anchor and
`found_via` per counterpart; `region-exhaustive` additionally requires `region_id`, because "none"
is uninterpretable without the bound it is none within. `eval_pass2.py` then **refuses** to put an
anchor whose oracle is `suggested-list` into the candidate-recall denominator. A dataset labeled
entirely through the suggestion list therefore yields a denominator of zero and says so, instead of
yielding 100%. `tests/test_pass2_eval_contract.py` proves the refusal changes the answer by
removing it.

**Action — blocking, design changed.** Regions, not anchors, as the sampling unit; oracle and
`found_via` recorded; evaluator enforces the exclusion. A counterpart later found outside a stated
region is a recorded `region-escape`, not a labeling error.

---

## §R2-2. The 35.1% vs 0/976 comparison, re-run with everything held constant

**Verdict: CONFIRMED, and the incompatibility was larger than the criticism claimed. The
conclusion partly survives re-testing.**

**Falsification attempted, and it turned up a third defect.** The criticism named two differences
(per-anchor vs per-comparison; unmatched candidate-set size). There is a third, which neither round
had noticed: **the two numbers were computed under different rarity models.**
`probe_review_gameability.py` builds document frequencies inline over the 34-bill union (65,502
bodies); `probe_r4_production_neighborhood.py` imports `mine_common.vec`, which loads
`idf_cache.json`, built over `bills/` + `bills_corpus/` — **232,924 bodies over 2,983 bills**. The
containment values in the two rows of round 1's C7 table are not on the same scale.

**The apples-to-apples experiment.** `probe_r6_rate_parity.py` holds the anchor set, the measure,
the rarity model and the candidate-set size constant, and varies only where the long candidates
come from. Same 77 anchors; for each, k candidates where k is its own real neighbourhood size; 20
control draws per anchor from other bills' added provisions:

| arm | per-comparison | per-anchor |
|---|---|---|
| production (own bill) | **36 / 8,734 = 0.412%** [0.298, 0.570] | **27 / 77 = 35.1%** [25.3, 46.2] |
| control (other bills, k matched) | **94 / 174,680 = 0.054%** [0.044, 0.066] | **66 / 1,540 = 4.29%** [3.38, 5.42] |

The intervals are disjoint on both statistics, so **the direction round 1 claimed does survive** —
about 7.6× more available inside a bill than across bills, holding opportunity count constant.

**But it does not survive dropping one bill.** 119-hr-1 supplies 24 of the 27 production hits:

| arm, 119-hr-1 removed | per-comparison |
|---|---|
| production | 6 / 1,014 = 0.592% [0.271, 1.285] |
| control | 57 / 20,280 = 0.281% [0.217, 0.364] |

Overlapping intervals on n=11 anchors. And 119-hr-1 is the known consolidation bill, where a
high-containment same-bill pair is *most* likely to be a genuine "absorbed into" relation rather
than an error — so the bill carrying the aggregate effect is the bill whose hits are least likely
to be false keeps. **This remains an unlabeled opportunity rate.**

**And "0/976" was never evidence of anything.** At the control rate measured here, 976 draws expect
0.53 hits, so observing zero has probability ≈59% — the likeliest single outcome. Its Wilson upper
bound alone (0.392%) already overlapped the production per-comparison rate. Printing it as "0.0%"
beside "35.1%" read as a 350× gap that the data never contained.

**Action — claim narrowed** (wording in the §7 pointer above), `probe_r6` added to the standing
set, and `probe_r4`'s two headline numbers are no longer cited as a comparison.

---

## §R2-3. The financial miner's denominator

**Verdict: PARTLY CONFIRMED — right about the defect, slightly off about where it lives.**

**Falsification attempted.** The criticism says the review "describes 203/240 = 84.6% as
approximately the percentage of eligible cases hidden by the miner". Reading the artifacts:

- `probe_r3`'s own output line was already literal: *"removed financial nodes with >=1 added
  financial partner available : 240"*.
- Round 1's C6 says *"The floor removes 84.6% of the population from discovery"* — literal, but it
  never states which population, and never says the missed-correspondence count is unknown.
- **The PR description is not literal**: *"The financial miner hides 203 of 240 **eligible cases**
  (84.6%)"*. "Eligible cases" is exactly the promotion of a candidate count into a truth count.

So the criticism lands, on the PR body rather than on the probe.

**Restated literally, as required.** Of **240** removed financial provisions occurring in a version
pair that also contains at least one added financial provision, **203** have no added candidate
clearing the miner's 0.50 word-overlap floor. **40** of those 203 have a ≥0.70 containment
candidate. **The number that are genuine missed correspondences is unknown until they are labeled**
— and at least 3 of the 40 are the degenerate `"$0."` single-token artifact, so even 40 is not a
clean count of severe-false-split shapes.

Support, added in this round because a rate over an undeclared distribution invites the same error:

| bill | in population | below floor | + strong containment |
|---|---:|---:|---:|
| 119-hr-1 | 108 | 72 | 27 |
| 114-hr-2029 | 89 | 89 | 3 |
| 118-hr-4366 | 23 | 23 | 5 |
| 115-hr-5895 | 17 | 16 | 2 |
| 118-hr-8774 | 2 | 2 | 2 |
| 118-hr-8752 | 1 | 1 | 1 |

**The conclusion is not weakened.** The miner cannot be used to estimate severe false-split recall,
because its discovery mechanism suppresses low-word-overlap cases — and that follows from the
exclusion alone, with no assumption about how many of the excluded are real.

---

## §R2-4. The consolidation 47.5% interpretation

**Verdict: PARTLY CONFIRMED — the criticism is right about the claim, but the round-1 review text
already made it correctly.**

**Falsification attempted, and it succeeded for the review.** Round 1's C8 reads: *"The other 245
(47.5%) are unobservable to any label set built this way."* That is the exclusion framing the
criticism asks for, not a claim about relationships. There is no independent truth showing the 516
correspond anywhere, and round 1 never asserted one.

**The criticism lands on the PR description**, which says *"The consolidation miner makes 47.5% **of
relationships** unobservable"*. That is the error, and it is corrected in the PR body.

The wording now used in both places:

> 47.5% of leftover removed provisions are excluded from the containment-selected annotation
> population. A dataset produced by that miner therefore cannot supply a denominator for
> consolidation recall.

**No conclusion changes**, because the bounded-exhaustive-subtree proposal follows from the
exclusion, not from any belief about how many of the 245 have counterparts.

---

## §R2-5. Scope of the IDF robustness result

**Verdict: PARTLY CONFIRMED. The scope criticism is right; its practical bite was falsified.**

**Confirmed.** `probe_r5` scores `p["text_old"]` / `p["text_new"]` — the fixture's frozen strings.
Since three of twelve no longer correspond to anything the parser emits, a result over all twelve
is a result about historical observations, and round 1 stated it without that scope.

**Falsification succeeded, and it matters.** `probe_r5` §2b now repeats the entire analysis over
the nine pairs whose stored text still resolves on **both** sides in the current parse. For those
nine the frozen string is byte-identical to a body the parser emits today, so re-deriving them
returns the same string and therefore the same score — they are current observations, not merely
historical ones. Every margin is unchanged:

| variant | margin, all 12 (historical) | margin, resolving 9 (current) |
|---|---:|---:|
| V1 per-version | +0.404 | **+0.404** |
| V2 dedup bodies per bill | +0.400 | **+0.400** |
| V3 one doc per bill | +0.324 | **+0.324** |
| V4 numerics dropped | +0.313 | **+0.313** |
| V5 citations dropped | +0.427 | **+0.427** |

The 0.70 bar holds in all five, both ways. So the ablation **does not rest on the quarantined
records at all** — they are not load-bearing for the separation.

**Wording adopted.** *"Rarity is robust as identity evidence across five document-frequency
definitions, on the nine labeled pairs whose representation the current parser still emits, and on
all twelve as historically frozen. It is untested on the three quarantined observations."* The
narrower claim the criticism proposed would have understated what the probe can support.

**Frozen now, per the criticism.** The five variants, the 0.70 bar and the reported quantities are
fixed as of 2026-08-06 and recorded in the probe's docstring. Re-running the same five after
re-adjudication is a replication; changing them first is fitting to the answer.

---

## §R2-6. "Label decay" is the wrong model — and the right one inverts the diagnosis

**Verdict: CONFIRMED, and the experiment changed the finding rather than only the vocabulary.**

**The chain the round-1 word conflated:**

```
source legislation  ->  parser representation  ->  research observation  ->  human label
   (the XML bytes)        (the node bodies)         (text_old/text_new)      (SAME/DIFFERENT)
```

"3 of 12 labels no longer resolve" is a fact about the **third** arrow. It is silent on which of
the first two moved, and round 1 asserted the parser without testing it.

**The experiment.** `probe_r7_provenance.py`, two independent steps:

1. **The source is stable.** Every XML file the twelve labels reference is byte-identical (git blob
   identity, so a working-tree edit cannot fake it) to the copy that first entered git: 8 files
   unchanged, 0 changed.
2. **The parser is what moved.** The engine is materialized *as of the answer-key commit*
   (`402563e`, 2026-07-10) into a temp tree and run against **today's** XML. It reproduces **all
   three** stored texts that the current parser does not:

```
pair                       side     old parser   current parser
contested-2-corps-110      old             yes               NO
anchor-diff-sec252         old             yes               NO
extreme-alien-snap-10012   old             yes               NO

sides the OLD parser reproduces but the CURRENT one does not : 3
sides NEITHER parser reproduces from today's XML             : 0
```

**So nothing decayed.** The legislation is unchanged, and the human's judgment about it was never
invalidated. The engine now divides the same bytes into different provisions, so **the unit that
was ruled on is not a unit the pipeline produces**. The correct term is **representation drift**,
and the correct remedy is re-derivation plus a fresh ruling over the new unit — not treating the
old ruling as suspect.

That distinction is not cosmetic. "Decay" implies the labels are the damaged thing and invites
re-labeling; representation drift says the labels are intact and the *observation* has to be
rebuilt, which is a different, smaller, and better-defined job.

**Residual gap, stated because it is real.** Step 1 establishes stability only from each file's
first commit. The copy the builder actually read on 2026-07-10 lived in the then-gitignored
`bills/` and is unrecorded, so the window between labeling and first commit rests on no evidence.
That gap is precisely what a source hash in the fixture would have closed.

**The provenance invariant, so a future parser change fails loudly.** `pass2_schema.py` requires on
every node reference: `bill`, `version`, `source_sha256` (the XML bytes), `parser_commit`,
`schema_version`, `match_path` (which may legitimately drift) and `text_sha256` (which may not,
silently). A change to either hash re-quarantines the **observation** and leaves the **human label**
untouched — they are separate records, which is what `readjudication-sealed.json` already models
(`historical_observation` vs `current_observation`). `tests/test_pass2_eval_contract.py` fails any
record missing them.

**Not yet applied to the existing fixture.** `tests/data/similarity_labels.json` still carries no
`text_sha256` or `source_sha256`; adding them means rewriting the fixture, which is a change to a
committed answer key and is left for Will's call rather than done inside a review.

---

## §R2-7. The all-version assertion now has a reproducer

**Verdict: CONFIRMED. `probe_r2` did not demonstrate it; it does now.**

The round-1 claim — the 81-character stub exists in no version of 119-hr-1, "verified across all
five" — was true but rested on an ad-hoc check that was never committed. `probe_r2` §1 only ever
checked the single version each label names.

`probe_r2` §4 now prints, for **all twelve** labels, every version of the bill in which each stored
text appears, and separates two failure modes the single-version check conflated: a body that
**MOVED** to another version (stale locator) from one that is **ABSENT** everywhere (vanished
representation). All three drifted labels are ABSENT, not MOVED:

```
extreme-alien-snap-10012   (5 versions of 119-hr-1 in corpus)
    text_old  labelled 1_reported-in-house   -> ABSENT  found in: (none)
contested-2-corps-110      (5 versions of 115-hr-5895 in corpus)
    text_old  labelled 4_engrossed-amendment-senate -> ABSENT  found in: (none)
anchor-diff-sec252         (5 versions of 115-hr-5895 in corpus)
    text_old  labelled 4_engrossed-amendment-senate -> ABSENT  found in: (none)
```

Also visible, and worth recording: two other labels reference the *same* 115-hr-5895 version and
resolve fine, so this is provision-specific re-segmentation, not a whole-version parse failure.

---

## §R2-8. The evaluator belongs in the blocking set

**Verdict: CONFIRMED. Round 1's item 8 was wrong.**

Round 1 reasoned that metrics are needed after labeling. The risk is not lateness, it is that the
**schema cannot produce the metrics**, and the only way to find that out is to compute them —
after ~160 human rulings, that means collecting them again.

Built in this round, deliberately skeletal:

- **`probes/pass2_schema.py`** — the frozen schema (`pass2-anchor-v1`): relations
  (`one-to-one` / `one-to-many` / `many-to-one` / `none` / `uncertain`, no speculative
  `many-to-many`), oracles, per-candidate retrievers, per-counterpart `found_via`, and the
  provenance fields from §R2-6, with a validator that rejects a record which cannot support a
  metric it would be counted in.
- **`probes/fixtures/eval_contract_synthetic.json`** — ten hand-authored records, no legislation
  and no human judgments, covering every shape the design must handle: clean one-to-one, no
  counterpart, one-to-many with a retrieval gap, a candidate miss found only by browsing, a ranking
  miss, an assignment collision with one winner and one loser, a suggestion-list-only truth, an
  uncertain, and a challenge-stratum failure.
- **`probes/eval_pass2.py`** — computes all five targets and enforces each one's population.
- **`tests/test_pass2_eval_contract.py`** — pins each metric's value on the fixture and proves the
  guards fire.

Output on the synthetic fixture — every target non-degenerate, with both successes and failures so
no metric passes by being vacuously 1.0:

```
1 candidate recall     4/6 counterparts over 5 eligible anchors; misses: a3 (region-sweep), a4 (browse)
2 ranking              n=4, top-1 0.75, MRR 0.833
3 assignment           1 collision group, 2 anchors, accuracy 0.50
4 diff correctness     n=9, accuracy 0.556, full confusion matrix
5 failure modes        high-containment-different: 1/1, flagged NOT a precision
EXCLUDED from candidate recall: a8-suggested-only
```

**Answering the gate question directly.** *If we collect these labels exactly as designed, can we
later calculate candidate recall, ranking accuracy, assignment accuracy and final diff correctness
without discovering that our ground truth was conditioned on the matcher?* **Yes, demonstrably** —
and the demonstration is executable, not a claim: `test_the_anti_circularity_exclusion_can_fire`
shows candidate recall moving (6→7 counterparts, 4→5 found) when the exclusion is removed, so the
guard is doing work rather than decorating the code.

Two design decisions worth a reviewer's attention. Nodes are joined on `text_sha256`, not
`match_path` — the path is the unstable key this whole program exists because of, so joining on it
would break the evaluator exactly where matching is hardest. And collision groups are **derived**,
not annotated: a human ruling one anchor at a time cannot see that two anchors claim the same
target, so asking them to record it would be asking for something they are not positioned to know.

---

## §R2-9. `merged_root()` could go stale, and the precedence was backwards

**Verdict: CONFIRMED. Fixed, and the fix is tested in both directions.**

**Staleness.** The docstring said *"rebuilt on each call … so it cannot go stale"*. The
implementation reused one fixed temp directory and skipped any link that already existed, which
made that false in two ways: a link whose source had been deleted survived (`is_symlink()` is true
for a broken link), and a link pointing at the losing side of a precedence change survived, because
existing-at-all was the only test. Every later run then read a corpus no root described.

`merged_root()` is now **content-addressed**: the directory name is a hash of the exact
`{bill: {version: source path}}` mapping, built in a private staging directory and moved into place
with one `os.replace`. A changed corpus is a different name and therefore a fresh build; an
unchanged corpus reuses a tree correct by construction; a half-built tree is never visible.
Symlinks still mean a source whose *contents* change needs no rebuild — only the file **set** is
content-addressed, which is the part that could go stale.

**Proving the gate can fire.** `tests/test_research_probes.py` runs the replaced algorithm verbatim
against a synthetic corpus and asserts it *does* leave the stale link behind. A staleness test whose
counterpart has never gone red cannot distinguish "no staleness" from "no check".

**Precedence, flipped.** The docstring said `bills/` wins collisions, and it did. That was the wrong
way round: `bills/` is gitignored and disposable (#308, ADR 0015), `tests/corpus/` is committed and
byte-identical everywhere. `ROOTS` now puts `tests/corpus` first, so the largest possible share of
any result is reproducible from a clean checkout. `duplicate_versions()` makes the choice auditable
instead of assumed, and on the current corpus **all 23 collisions are byte-identical**, so the
precedence is immaterial to results and load-bearing only for provenance. A test asserts that, and
will fail if it stops being true.

**A gate where there was none.** These research scripts are excluded from lint and format
(`pyproject.toml`), and round 1 found what that cost: #492 renamed three names and broke thirteen
of them, #308 moved the corpus out from under all fifteen, and nothing noticed for months because
nothing ran them. `tests/test_research_probes.py` adds the two checks that would have caught both,
statically, with no corpus needed: every `from deltatrack… import` still resolves, and no probe
hardcodes an absolute home path. Excluding a directory from lint is a decision about *style*; it
should not also be a decision to stop checking that the code resolves.

---

## §R2-10. Corpus manifest

**Verdict: CONFIRMED, and the hole is larger than the criticism described.**

"34 bills / 106 versions" does mean "whatever XML happened to be on one disk". Measured:

```
versions by root : tests/corpus 58  |  bills 48
```

So **45% of the corpus every union number is computed over does not exist in a clean clone.** And
the bigger omission is not the XML at all: the containment values depend equally on the rarity
model, and `mine_idf.py` builds that over `bills/` + `bills_corpus/` — **232,924 provision bodies
across 2,983 bills**, both trees gitignored. Until this round, no probe's output said which of the
two rarity models it had used (see §R2-2, where that silence produced an invalid comparison).

**What was added.** `corpus_roots.manifest()` records `bill`, `version`, `root` and **SHA-256** for
every file, plus the repo commit, the per-root split, the collision report, and the IDF model's
corpus name, document count and cache hash. `manifest_digest()` reduces it to one short string that
two runs share iff they read the same bytes.

**Where it lives, and why that split.** Committing a full manifest and *maintaining* it would
conscript someone into upkeep for a tree that legitimately changes. So:

- **Printed by every probe**, as a one-line banner, so no output is anonymous about its inputs:
  `[corpus e3e05399eb6196d5] 34 bills / 106 versions / 71 adjacent pairs | idf=bills+bills_corpus n_docs=232924 sha=89d4508e5a4f | repo e3a98ae81bc1`
- **Committed once as a snapshot** of the run that produced the numbers reported here
  (`corpus-manifest.json`). A reader compares their banner digest against it and knows immediately
  whether they are looking at the same corpus, instead of inferring it from a bill count.

**Honest limit.** A manifest makes a result *auditable*; it does not make it *reproducible*. Half
this corpus and the entire rarity model cannot be reconstructed from the repository. The manifest's
value is that this is now visible in every output rather than in one caveat at the top of one
document.

---

## §R2-11 / 12. Adjudication of the drifted records

**Verdict: ACCEPTED without qualification. Packet prepared; nothing adjudicated.**

No ruling was inferred from word overlap, containment, header equality, or the current matcher, and
the historical label was not carried forward. `probes/make_readjudication_packet.py` writes two
deliberately separate files:

- **`readjudication/readjudication-packet.md`** — blind. Bill, versions, the current new-version
  provision, and the old-version candidates, with structural breadcrumbs and headers (shown on
  purpose: protocol §5 treats structural context as a signal the human legitimately uses). No
  scores, no matcher decision, no prior verdict, no indication of which approach an answer favours.
- **`readjudication/readjudication-sealed.json`** — the historical observation (stored text,
  hashes, original human label, historical scores, label commit) and the current observation
  (parser commit, source hashes, the current options) as **separate records**. The current one
  carries no label and must not inherit one.

**The subtle part is how the old side is chosen.** For two of the three the stored old text is gone,
so something must decide what the reviewer sees. Choosing by best text similarity — what `probe_r2`'s
diagnostic table does — would let a signal under evaluation pick the evidence its own re-validation
rests on. The packet therefore does not choose: it shows **every** node the current parser emits at
the label's structural path, in document order, and asks which (if any) is the counterpart. For
`extreme-alien-snap-10012` that surfaces both sides of the `sec. 10012` path collision, which is the
honest presentation of that case.

**Leak scan.** The packet is masked and scanned with the same `blindness.py` guard the live labeling
path uses, plus an explicit check that no stored score string appears. It fired once, on the word
"measures" in prose this round authored; the prose was reworded rather than the guard loosened.

**Two limits, stated rather than engineered away.** The seal is a convention — both files are
committed and readable. And Will ruled these pairs in July and may remember; no mechanism can
prevent that, so the packet asks the legislative question over the *current* unit, which is a
genuinely different question, rather than asking for the old verdict to be reconfirmed.

---

## §R2-C. Revised Study 2 labeling design

Everything in round 1's §B stands except the ground-truth mechanism. The invariant:

> **Candidate generators may help humans find counterparts. They may not define whether a
> counterpart exists.**

Operationally, in four rules:

1. **Sample regions, then anchors inside them.** A region is a bounded structural unit of the
   **new** version (division / title / account) that exists there — not the anchor's old path,
   which renumbering empties for most anchors (§R2-1). Median region: 37 provisions.
2. **Read the region once, exhaustively.** Every provision in it is reviewable, retrieved or not.
   That, not the suggestion list, is the truth universe. Cost amortises across every anchor in the
   region.
3. **Retrieval still drives the UI, and is recorded as such.** Candidates are ordered by the
   retriever union so the common case is one click; the ordering is a convenience and the human may
   accept a counterpart from anywhere in the region. `found_via` records which happened —
   `suggested`, `region-sweep`, or `browse`.
4. **The oracle is recorded per anchor and enforced downstream.** `region-exhaustive` requires
   `region_id`; `suggested-list` anchors are excluded from candidate recall by `eval_pass2.py`.
   `document-search` is the escalation when a region sweep returns none and the reviewer suspects a
   cross-region move; a counterpart later found outside a stated region is a recorded
   `region-escape`.

Label space: `one-to-one`, `one-to-many`, `many-to-one`, `none`, `uncertain` — plus round 1's C9
addition of `unrelated` / `uncertain` to the consolidation stratum. `uncertain` is never folded
into `none`; a test pins that.

Unchanged from round 1 §B: the five evaluation targets, by-bill splitting, scores stripped at label
time with the automated leak guard, structural context shown, per-stratum kappa with support, the
LLM as disagreement-flagger and never a vote, no silent caps.

**MVP cost, restated on the new unit.** ~4 sampled regions (median 37 provisions each, p90 104)
gives exhaustive truth for every anchor they contain — on the order of 150–400 provision reads for
roughly 40–80 anchors, against round 1's 80 anchors × 8 candidates with no recall denominator at
all. The bounded consolidation subtree (C8) is the same mechanism and merges into it.

---

## §R2-E. Revised blocking / non-blocking

**Blocking — before any human labeling resumes**

| # | item | state |
|---|---|---|
| 1 | **Re-derive the 12 observations** against the current parser and **quarantine** the drifted ones. The human labels are **not** rewritten (§R2-6). | probes done; fixture not yet carrying `text_sha256` / `source_sha256` — **Will's call** |
| 2 | **Re-mine the financial stratum** without signal-conditioned discovery: union retrieval, `amount_source_old/new`, minimum-token floor (C6, §R2-3). | not started |
| 3 | **Anchor-level ground truth with an oracle independent of retrieval** (§R2-1, §R2-C). | designed + enforced in schema/evaluator; sampling not run |
| 4 | **Freeze the correspondence/label schema**, including `none` / `uncertain` / multiple (C9, §R2-8). | **done** — `pass2_schema.py`, `pass2-anchor-v1` |
| 5 | **Skeletal evaluator proving the schema computes the promised metrics** (§R2-8). | **done** — `eval_pass2.py` + 14 tests |
| 6 | **Correct the Study 1 premises Study 2 would inherit** (C1, C3, C4, C10) — asymmetry, cross-type generalization, "census", "text carries the gain". | proposed in §E, **not applied** |

**Non-blocking — necessary to merge this review, not gates on annotation**

| # | item | state |
|---|---|---|
| 7 | Production-neighbourhood rate normalization (§R2-2) | **done** — `probe_r6` |
| 8 | Exact percentage wording, financial + consolidation (§R2-3, §R2-4) | **done** in this document; PR body corrected |
| 9 | `merged_root()` staleness + precedence (§R2-9) | **done**, tested both ways |
| 10 | Corpus manifest (§R2-10) | **done** — banner + committed snapshot |
| 11 | All-version provenance reproducer (§R2-7) | **done** — `probe_r2` §4 |
| 12 | Probe-import CI gate (round 1 item 9) | **done** — `tests/test_research_probes.py` |
| 13 | Theory rewrite around the overlap coefficient; directional-B benchmark; structural-confirmer decision | Study 4 |
| 14 | Re-run the frozen IDF ablation after re-adjudication (§R2-5) | blocked on item 1; **variants frozen, do not re-tune** |

**The distinction being drawn.** An item gates *annotation* if collecting labels without it would
produce a dataset that cannot answer its question — items 1–6 all fail that test. An item gates
*merging* if a reader would otherwise carry away a number the evidence does not support — items
7–11. Wording and infrastructure defects are real and are fixed, but a labeler's screen does not
change because a percentage was restated, so they do not hold up the labeling.

---

## §R2-D. Probes added and changed in round 2

| probe | decides | headline output |
|---|---|---|
| `probe_r6_rate_parity.py` | §R2-2 | production 0.412% vs matched control 0.054% per comparison; overlaps once 119-hr-1 is removed |
| `probe_r7_provenance.py` | §R2-6 | source byte-identical; the 2026-07-10 parser reproduces all 3 drifted texts from today's XML |
| `probe_r8_oracle_gap.py` | §R2-1 | union@8 misses a header-identical candidate for 18.1% of anchors that have one; region-size cost table |
| `pass2_schema.py` + `eval_pass2.py` + `fixtures/eval_contract_synthetic.json` | §R2-8 | all five targets computed; circularity exclusion proven to fire |
| `make_readjudication_packet.py` | §R2-12 | blind packet + sealed provenance, leak-scan clean |
| `corpus_roots.py` *(changed)* | §R2-9, §R2-10 | content-addressed merged view; committed-first precedence; manifest + banner |
| `probe_r2_label_drift.py` *(changed)* | §R2-7 | §4 all-version provenance for all 12 labels |
| `probe_r3_financial_miner.py` *(changed)* | §R2-3 | denominator stated literally; by-bill support |
| `probe_r5_idf_ablation.py` *(changed)* | §R2-5 | §2b margins over the 9 resolving pairs — identical |

New tests, which run in CI unlike the probes themselves: `tests/test_research_probes.py` (the
import gate, the corpus-view invariants, and the manifest) and `tests/test_pass2_eval_contract.py`
(the data contract). Both are parametrized over things that will grow, so their counts are not
quoted here — run them.

---

## §R2 — what still needs human judgment

1. **The three drifted observations.** Packet ready; not adjudicated, and deliberately not
   inferrable from any signal in this repository.
2. **Whether to add `text_sha256` / `source_sha256` to `tests/data/similarity_labels.json`.** It is
   the right invariant (§R2-6) and it means rewriting a committed answer key, which a review should
   not do to itself.
3. **Applying §E's documentation corrections to `paper.md` and `pass2-protocol.md`.** Still
   proposed, not applied, so the wording can be agreed first.
4. **Whether `tests/test_research_probes.py` should exist at all.** It couples the product suite to
   research artifacts, which is a real cost. The argument for it is that the alternative already
   failed: a lint exclusion silently became a "nothing checks this" exclusion for months.
5. **The region-sampling parameters** — how many regions, at which bound, across which bills. The
   cost table prices the options; the coverage/effort trade is a judgment call.
