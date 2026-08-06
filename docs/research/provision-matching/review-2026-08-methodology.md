# Methodology review — adversarial challenge to Study 1 and the Study 2 protocol

**Status:** Review complete; **human labeling stays gated.** This document is the deliverable that
`pass2-protocol.md` §10.1 gates on, extended to cover an independent adversarial review of Study 1.
**Date:** 2026-08-06. **Reviews:** `paper.md` (Study 1), `pass2-protocol.md` (Study 2), `probes/`.
**Supersedes nothing.** It records what survived challenge, what did not, and what neither side saw.

Every claim below was tested against the code and the corpus rather than argued from the documents.
Where a criticism could be decided empirically, a probe decides it, and the probe is committed.
Failed falsification attempts are reported alongside successful ones.

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
all five). Today's parser rolls the amendment's sub-paragraphs into the section body, so the old side
is already 1,443 characters and the stub→expansion signature is gone. Containment 0.428 sits below
the 0.70 keep bar, so the measure the study recommends **would now false-split the case the study
cites as its proof.**

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

Unchanged and still sound: the problem framing (entity resolution over an ordered tree with an
unstable key), the signal inventory, the header-coverage table, that word-overlap measures the wrong
quantity, and the honesty apparatus in §8 — which anticipated more of this review than the review's
author expected.

---

## B. Revised Study 2 experimental design

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
