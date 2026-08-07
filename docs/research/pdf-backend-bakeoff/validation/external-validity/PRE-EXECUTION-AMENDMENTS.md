# Pre-execution amendments

**Every amendment here was made while no confirmatory architecture output existed.** That
is the condition making it legitimate to amend a frozen protocol before execution rather
than a degree of freedom. **Its evidence is of two different strengths, and A11 separates
them:** F5 establishes as a *repository fact* that no canonical score artifact exists; that
no H/X extraction was ever *run* is an **attestation**, because git cannot prove a command
was never executed. The provable ordering fact is enforced instead by the execution-start
marker (A11).

## Why this file exists, and the invariant it protects

The fact worth preserving is not "the pre-registration file was never edited". It is:

> The **sampling procedure** and the **decision rule** were fixed before the population was
> drawn, and every later change was made without any confirmatory result in existence, so
> no change can have been selected for the answer it produces.

`PRE-REGISTRATION.md`'s F4 proxies that with "unmodified since before the membership
commit". That proxy is *too strong in one direction and too weak in another*: it forbids
correcting prose that contradicts an already-frozen rule, and it says nothing about the
**code** that draws the sample or computes the score. So the protocol document is left
**byte-frozen at `c399e9d`**, every later change is recorded here, and `x04` gains three
invariants:

| invariant | what it enforces |
|---|---|
| **F7** | the set of files under `holdout/` equals **exactly** the set named by `holdout_membership.json` — no unmanifested artifact may sit inside the frozen population |
| **F8** | every manifested file begins with `%PDF-` |
| **F9** | **every file in this study directory whose last commit is after the membership commit must be declared below**, and no amendment may declare `affects_membership: true` |

F9 is the general form of the defect this pass found: *a manifest, a protocol or a gate
claiming a closed world while the filesystem or the code admits something outside it.*

## Scope

| class | may it change a rule that scores the population? | conditions |
|---|---|---|
| `CLERICAL` | **no** — corrects prose that contradicts an already-frozen rule, or removes a withdrawn population's numbers | none |
| `SUBSTANTIVE` | **yes** | only while no confirmatory output exists; must argue explicitly why the population stays valid |
| `TOOLING` | **no** — harness code that cannot change membership or a score | must state the evidence that it cannot |

**No amendment may change membership.** A change requiring that is not an amendment; it is
a re-selection.

---

## A1 — CLERICAL. The protocol carried the withdrawn design population's numbers

```json
{"id": "A1", "class": "CLERICAL", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**Stale text.** §7.1 "what happened on 19 named documents"; §7.2's pre-committed reporting
template "On the 19 frozen documents"; §8.3 "at N ≈ 14 the tightest achievable zero-event
bound is ≈ 19 %"; §8.3 "the honest strength of a 14-document holdout".

**Why it became stale.** Those numbers described the **design** population (19 documents,
14 P-head) that was withdrawn as non-pre-registered. The confirmatory population is
different, and the numbers were never rules — they were illustrations baked into prose.

**Correct current interpretation.** The protocol is **population-agnostic**. Read every
such figure as a symbol whose realized value comes from
`results/holdout_membership.json` and the findings document, never from this prose:

| symbol | meaning | realized value |
|---|---|---|
| **N** | frozen documents | `holdout_membership.json` → `n_documents` |
| **N_head** | P-head documents | members with `population == "P-head"` |
| **H** | heading occurrences | computed at extraction time |
| **r** | achieved exact 95 % zero-event upper bound on the per-document rate, `1 − 0.05^(1/N_head)` | reported in findings |

The §8.1 table (600 headings → 0.00498 against 14 documents → 0.1926) is **retained as the
worked example that demonstrated the estimand defect**, on the design population, and is
correct as history. It is not a claim about the confirmatory population.

**Can this affect membership or scoring?** No. No rule changes.

---

## A2 — CLERICAL. Red-team rows still referenced the withdrawn δ

```json
{"id": "A2", "class": "CLERICAL", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**Stale text.** Red-team row 10 ("X must clear δ **and** be one-directional"); row 12
("δ is fixed before results, derived from a measured 652-heading document, and is 4×
tighter than the prior protocol's"); row 13 ("§7.2 rule 3 voids the run outright if the
denominator cannot support a bound under δ").

**Why it became stale.** §7.1 withdrew δ entirely and §7.2 rule 3 no longer mentions a
denominator floor. The rows were written when δ was live and were not updated with it.

**Correct current interpretation.** **There is no δ.** Row 10's risk is now answered by
§7.2 rule 1 being count-based and one-directional. Row 12's risk is **moot** — a margin
that does not exist cannot be chosen to make a tie unfalsifiable; the replacement risk,
that a *descriptive* result is over-read, is answered by §7.2's mandated reporting
sentence. Row 13's mechanism is now §7.2 rule 3's control failures, not a denominator
floor. Row 21 already records the δ withdrawal correctly and stands.

**Can this affect membership or scoring?** No.

---

## A3 — SUBSTANTIVE. The decision unit for M3 is the heading occurrence

```json
{"id": "A3", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** §6.3 defined M3 at aligned **boundary positions** and said the decision
rule counts WELD/SPLIT outcomes there, while §7.2 rule 1 required X to repair
"≥ 5 printed account or agency **headings**". Those are different units, and one heading
can carry several boundary defects — so the same evidence could satisfy the rule on one
reading and not the other.

**Resolution, frozen.** The decision unit is the **unique heading occurrence**, because the
architecture question is about corrupted account and agency *labels*, which is the unit of
downstream harm. Boundary outcomes remain **diagnostic** and are always reported.

Mechanically, implemented and tested in `probes/m3_boundaries.py`:

> a heading is **CLEAN** for an architecture when it has zero WELD, zero SPLIT and zero
> TEXT_ERROR against the oracle.

| heading-level outcome | condition |
|---|---|
| `X_CORRECTS` | H not clean, X clean |
| `X_REGRESSES` | H clean, X not clean |
| `BOTH_CLEAN` | both clean |
| `BOTH_DIRTY` | neither clean, **whatever the defect counts** |
| `UNSCORABLE` | **superseded by A9**: only when the ORACLE has no text. `UNALIGNABLE` is withdrawn |

**The case the review raised is answered explicitly: if H has two WELDs and X repairs one,
that is `BOTH_DIRTY` and is NOT a correction.** A half-repaired account label is still a
wrong account label. `probes/m3_selftest.py` asserts exactly that case.

**Why the population stays valid.** The choice of unit is a statement about what counts as
product harm. It is independent of which documents were drawn, and it cannot be tuned
toward an answer, because **no H or X output exists on any confirmatory document**. The
pilot moreover found zero heading-level differences on development material, so there is no
observed direction to tune toward.

---

## A4 — SUBSTANTIVE. M3's alignment is operationalized; the edit budget is removed

```json
{"id": "A4", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** §6.3 said "cannot be aligned within the frozen edit budget" but froze no
algorithm, no costs, no budget, no tie-breaking, no Unicode rule and no repeated-character
rule. Scoring behaviour was therefore left to whoever wrote the scorer.

**Resolution, frozen and executable.**

- Alignment is over the **non-space** character sequences, so a spacing difference can
  never cause a misalignment.
- Normalisation is **NFKC + end-strip only**; case preserved; interior spaces preserved for
  the boundary vector, then excluded from the alignment sequence.
- **Needleman–Wunsch** global alignment, unit costs (match 0, substitution 1, indel 1).
- **Deterministic tie-break**: DIAGONAL, then UP (oracle-only), then LEFT (extractor-only),
  so `AB AB` → `ABAB` resolves identically on every run.
- A run of spaces is **one** boundary.
- **The edit budget is removed.** It was an arbitrary threshold on the exact quantity being
  measured. `UNALIGNABLE` now means what it says: the two sequences share **no** common
  subsequence. A long string with many substitutions still aligns.
- A boundary is comparable only when **both** endpoints aligned to oracle characters.

**Why the population stays valid.** Purely mechanical, chosen from properties of the
algorithm rather than from data, verified on synthetic and development material, and fixed
before any confirmatory output exists.

---

## A5 — SUBSTANTIVE. Rule 1's omnibus veto is replaced by per-metric directionality

```json
{"id": "A5", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** Rule 1 required that "no other metric moves against X by more than one
heading occurrence per affected document". M1 counts heading occurrences, M2 matched
headings, M4 **parent relations** and M6 **amount attributions** — so a veto denominated in
heading occurrences cannot literally apply to M6 at all.

**Resolution, frozen.** The omnibus veto is deleted. Each metric is vetoed in **its own
native unit**, and every veto is a **hard directionality check**, so no new threshold is
invented. This is deliberately *stricter* than what it replaces.

**Rule 1 — choose corrected extended glyph only if ALL four hold:**

| # | condition | unit |
|---|---|---|
| 1 | `X_CORRECTS ≥ 5` on the human-adjudicated D-frame census | heading occurrence |
| 2 | `X_REGRESSES == 0` | heading occurrence |
| 3 | no amount whose attributed account is correct under H and wrong under X | amount attribution (M6) |
| 4 | no heading whose immediate parent is correct under H and wrong under X | parent relation (M4) |

Condition 2 tightens the previous "regresses ≤ 1" to **zero**. With an expected denominator
near zero, "≤ 1" is not a tolerance — it is 20 % of the win threshold. M2 needs no separate
veto: a text difference already makes a heading not clean, so it is inside conditions 1–2.

**If condition 1 holds but any of 2–4 fails**, the outcome is **insufficient evidence /
review**, never an X win.

**Why the population stays valid.** Every change is a *tightening* in the incumbent's
favour, denominated in units fixed by the metrics themselves, made with no confirmatory
output in existence.

---

## A6 — TOOLING. Harness repairs after the population freeze

```json
{"id": "A6", "class": "TOOLING", "commits": ["3d3e3fc", "481731b"], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x03_select_holdout.py",
                   "PRE-EXECUTION-AMENDMENTS.md",
                   "holdout/CRPT-118HRPT146/CRPT-118HRPT146.pdf"],
 "note": "probes/x04_freeze_check.py moved to A11, which changes what the gate MEANS and is recorded SUBSTANTIVE."}
```

**What changed.**

1. `x03_select_holdout.py` — every download-rejection path now deletes the file, and a
   download must begin with `%PDF-` to be accepted (`accept_download`).
2. `x04_freeze_check.py` — F7, F8 and F9 added, with self-tests.
3. `m3_boundaries.py` / `m3_selftest.py` are declared under **A3/A4 only**. They
   carry scoring semantics, so listing them here as TOOLING as well would let a
   substantive change hide behind a tooling declaration — F9 now rejects exactly that,
   and it rejected this file until the duplicate was removed.

**Why it cannot change membership, with evidence rather than assertion.** The only
behavioural change in the selector is that a non-PDF download is now rejected by a header
check instead of by `page_count` raising. `CRPT-118HRPT146` was **already rejected** by the
old path — it was never a member; only its file was left behind. The header check could in
principle reject a PDF whose header is not at offset 0, so that was measured rather than
assumed: **all 17 manifested files begin with `%PDF-`**, asserted continuously by F8. So
the new rule would have accepted exactly the same 17 documents.

**Why the selector was not simply left alone.** Leaving it would preserve a bug that
writes unmanifested files into the frozen population directory on any future run.

---

## A7 — TOOLING. The contamination probe was reading its own output

```json
{"id": "A7", "class": "TOOLING", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "superseded_by": "A8",
 "note": "A8 now owns probes/x01_contamination.py and results/contamination.json as a SUBSTANTIVE change; declaring them here as well would let a substantive change hide behind a tooling declaration, which F9 rejects."}
```

**Found while sweeping for the same class of defect as A6: a closed world that is not
closed.** `x01` scans the research tree for `.json` to find bill ids "named in research".
Its own output, `results/contamination.json`, is a `.json` in that tree, and it **records**
the 2,963 xml-only bills it deliberately does **not** exclude. So a second run re-ingested
every one of them as `named_in_research`.

**Measured:** re-running against the frozen artifact took the exclusion set from **93 bills
to 3,080**, and flagged **all 17 confirmatory holdout members** as contaminated. F3 reads
the committed file, so the frozen gate was never wrong — but any re-derivation would have
condemned the population the probe exists to protect, and the failure would have looked
like a contamination finding rather than a bug.

**Repairs.**

1. Generated artifacts are no longer scanned (`"results" in f.parts`). An output that is
   also an input is a ratchet, not a derivation.
2. **This study's own frozen population is subtracted**, in its own recorded class
   `own_study_population_not_excluded`. Once a holdout is committed it is exposed by
   construction, so without this the probe condemns it forever. The class name states the
   scope: a **future** study must treat these 17 as contaminated.
3. An **idempotence gate**: after writing, the derivation is re-run with the new file in
   place and must reproduce the same answer, else exit 3.

**A first version of that gate was wrong and is worth recording.** It compared against the
*committed* artifact and failed on any change — but the exclusion set legitimately **grows**
as material is committed, so it fired on honest growth (+17 bills, +5 reports, all of them
the withdrawn design PDFs that are now in git history). A gate that forbids legitimate
change is not a gate, it is a permanent red light. It now tests the property that actually
matters: re-deriving with its own output present must be a no-op.

**Verified:** two consecutive runs produce byte-identical output
(`5866c7da…`), and the honest exclusion set is now **110 bills / 38 report packages**.

**Can this affect membership or scoring?** No. Membership is unchanged, and the 17 members
are exempted rather than re-selected.

---

## A8 — SUBSTANTIVE. Freshness is decided against a pre-selection snapshot, not by subtraction

```json
{"id": "A8", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x01_contamination.py", "results/contamination.json"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A7"}
```

**The defect.** A7 subtracted the study's own membership from every exposure class. That
cannot distinguish

- **(A)** exposure this study *caused*, by committing its own frozen holdout — harmless;
- **(B)** exposure that existed *before* selection, on a document picked anyway —
  disqualifying,

and it silently forgives **(B)**. "Current exposure minus current membership" is a proxy
for freshness, not freshness.

**Repair.** Freshness is now decided against the **pre-selection snapshot**: the
contamination and design-exposure artifacts as they stood at the commit immediately before
the population commit, read from git at `<population_commit>~1`. That state is immutable,
cannot be edited by any later run, and **by construction cannot contain exposure this
study later caused**. No exemption is therefore needed, and the own-study subtraction is
**withdrawn**: `contamination.json` now records the 17 members as exposed in their natural
classes, which is true and which a future study needs.

**The audit result, which is the reason no reselection follows.** At `c399e9d` — the
pre-selection state — the inventory carried **93 excluded bills, 33 report packages** and
**no own-study class at all**, and **all 17 confirmatory members were absent from every
disqualifying exposure class**. Reproduce with
`git show c399e9d:…/results/contamination.json`.

**Controls.** Two self-tests now encode the distinction: case **B** (contaminated before
selection, later a member) must fail; case **A** (clean before selection, exposed only by
its own frozen commit) must pass. A snapshot that already carries an own-study exemption is
refused as not-pre-selection.

**Class note.** Recorded SUBSTANTIVE rather than TOOLING because it changes what F3 *means*,
even though it changes no score. It does not touch membership, and the audit shows the
answer is unchanged.

---

## A9 — SUBSTANTIVE. `UNALIGNABLE` is withdrawn; severe corruption stays in the denominator

```json
{"id": "A9", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A4"}
```

**The defect, confirmed by the reviewer's own case.** A4 documented `UNALIGNABLE` as "the
two sequences share no common subsequence", but the code declared it when the *chosen
minimum-cost alignment* contained no exact match. **Measured:** `AB` against `BA` has
LCS = 1 — it plainly shares `A` and `B` — yet minimum cost is two substitutions, the
DIAGONAL tie-break selects them, and the implementation returned `UNALIGNABLE`. Prose and
code disagreed.

**The deeper problem, which decided the repair.** `UNALIGNABLE` made the heading
`UNSCORABLE`, which removed it from the comparison — so the mechanism **excluded precisely
the worst failures**. If X emitted garbage where H read the label correctly, X's
catastrophic failure vanished instead of counting as `X_REGRESSES`. That is an exclusion
that removes the distinguishing cases, the recurring defect of this study.

**Repair: the category is withdrawn rather than repaired.** Severe corruption is a severe
`TEXT_ERROR`; the heading is not clean and stays in the denominator. This needed neither of
the two offered options, because the semantic mismatch disappears with the category.

- `NO_REFERENCE` replaces it, and fires **only when the oracle has no text** for a heading
  (unreadable region). A missing *reference* is an oracle limit; a garbage *extraction* is
  an architecture result.
- `no_common_subsequence` survives as a **diagnostic flag** with no effect on scoring.
- An empty extraction now scores `TEXT_ERROR` on every printed character, not an exclusion.

**Direction of effect:** strictly *safer for the incumbent*. Catastrophic X output now
counts against X, where before it was discarded.

**Tests.** All six adversarial pairs (`AB/BA`, `ABA/BAA`, `ABC/BAC`, `AAB/ABA`,
`ABAB/BABA`, `AAAAAB/BAAAAA`) remain scorable and are not flagged as sharing nothing; a
garbage extraction is `X_REGRESSES` in both directions; only a missing oracle reference is
`UNSCORABLE`.

---

## A10 — SUBSTANTIVE. A count threshold may not be applied to a D-frame subsample

```json
{"id": "A10", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": [],
 "supersedes_text_in": "PRE-REGISTRATION.md 5.5.1 and PRE-EXECUTION-AMENDMENTS.md A5"}
```

**The defect.** §5.5.1 allows a seeded 60-item subsample when the D-frame census exceeds the
human adjudication budget, while A5's Rule 1 uses **raw counts** (`X_CORRECTS ≥ 5`,
`X_REGRESSES == 0`). A raw count is valid on a **census** and not on a **sample**: five
corrections among 60 sampled items says nothing definite about 150, and zero regressions
among 60 does not establish zero among 150.

**Repair, frozen.**

> If the D-frame contains more items than the pre-set human budget can adjudicate, **Rule 1
> cannot choose corrected extended glyph.** The outcome is `INSUFFICIENT_COMPARATIVE_EVIDENCE`.

A seeded 60-item sample may still be adjudicated **for descriptive diagnosis**, and is
reported as such, but the `≥5 / ==0` thresholds are **not** applied to it. No sampling
estimator is built for a contingency the pilot suggests is rare.

**Three outcomes, kept distinct, and never collapsed.**

| outcome | meaning |
|---|---|
| `HYBRID_BY_PRIOR` | the pre-stated architectural prior stands; comparative evidence did not overturn it |
| `EXTENDED_BY_RULE_1` | X met every condition of Rule 1 on a **full census** |
| `INSUFFICIENT_COMPARATIVE_EVIDENCE` | Rule 1 could not be evaluated — census too large for the human budget, or a control failed |

**"X failed to prove a win because we did not adjudicate enough items" must never be
written as "H empirically beat X."** Hybrid remains the default by prior, not by victory.

---

## A11 — SUBSTANTIVE. A one-way execution boundary, and F9 hardening

```json
{"id": "A11", "class": "SUBSTANTIVE", "commits": ["c111433"], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "A12 also changes this file; both are SUBSTANTIVE, so neither hides behind a TOOLING declaration."}
```

**The defect.** This file claimed F5 "mechanically establishes" that no confirmatory output
existed. F5 checks `not scores.json.exists()`. That is a claim about **one artifact**; it
cannot establish that nobody ran H or X locally, wrote output elsewhere, or deleted it.
**Git cannot prove a computation was never performed.**

**Repair — narrow the claim, then make the useful fact provable.**

| claim | evidence |
|---|---|
| *no canonical score artifact exists* | **repository fact**, F5 |
| *no confirmatory H/X extraction has been run* | **attestation** recorded in the marker; weaker, and labelled so |

The provable and useful fact becomes **ordering**: *this scoring rule existed before the
commit that authorized execution.* That is enforced by an **execution-start marker**,
`results/EXECUTION-START.json`, emitted only by `x04 --authorize-execution`, which
**refuses** while any freeze or readiness gate is open. After the marker:

- no further `SUBSTANTIVE` pre-execution amendment is permitted — F9 rejects one whose
  commit is not an ancestor of the marker;
- a scoring-rule change becomes a **deviation**, not an amendment;
- confirmatory output may exist, and F5 stops requiring its absence.

**F9 hardening**, because a declaration must not be acceptable merely because a path is
listed. F9 now also rejects: duplicate amendment ids; a `files_touched` path that neither
exists nor was deleted; a file declared under **both** a SUBSTANTIVE and a TOOLING
amendment; and a TOOLING amendment that claims to change a scoring rule.

**F9 caught this file.** `m3_boundaries.py` and `m3_selftest.py` were declared under A3/A4
(SUBSTANTIVE) *and* A6 (TOOLING) — the exact hiding pattern the check exists to prevent.
The duplicate declaration was removed.

---

## A12 — SUBSTANTIVE. Two more proxy/property mismatches, found by targeted sweep

```json
{"id": "A12", "class": "SUBSTANTIVE", "commits": ["0e877b4"], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": []}
```

The recurring pattern in this study is *the gate checks a proxy for the property we care
about*. A deliberate sweep for further instances found two.

**F6 repeated F4's exact defect, in the check that proves BLINDING.** It compared
`first_commit(oracle_key)` against `first_commit(oracle_adjudicated)`. The membership file
has already demonstrated that an artifact can be withdrawn and re-created at the same path,
after which `first_commit` returns a commit for a version that no longer exists — so F6
would have "proved" the ordering of a key nobody would score against. Both sides now use
the last-modifying commit, matching F4.

**G2 believed a self-reported label.** The evidence file declares
`"population": "DEVELOPMENT"`, and G2 accepted that string as proof the X2 assertions were
not run on the holdout. A file can say DEVELOPMENT while having been produced on holdout
members — the same class as trusting a `.pdf` filename over PDF bytes. G2 now requires the
evidence to *list its documents* and checks them against membership directly; the label
alone is no longer sufficient, and a non-empty document list is required so the check
cannot pass vacuously.

**Controls:** `--self-test` gains "G2 rejects evidence LABELLED development that names a
holdout member" alongside the existing self-labelled-HOLDOUT case, giving 22/22.

**Can this affect membership or scoring?** No. Both are gate strictness; neither computes
a score. Recorded SUBSTANTIVE rather than TOOLING because each changes what a gate
*means*, and A11 established that as the dividing line.

---

## A13 — SUBSTANTIVE. The gate validated the working tree against itself

```json
{"id": "A13", "class": "SUBSTANTIVE", "commits": ["641013c"], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "A11 and A12 also touch this file; all three are SUBSTANTIVE, so nothing hides behind a TOOLING declaration."}
```

**Found by a targeted sweep for the study's recurring pattern — the gate checks a proxy for
the property we care about. This is the most serious instance yet, because it defeats every
other freeze invariant at once.**

`committed()` was `git ls-files --error-unmatch`, which proves a path is **tracked**. The
property we need is that the artifact is **identical to what was committed**. Since every
invariant reads the working tree, they collectively validated the working tree *against
itself*.

**Demonstrated, not argued.** Deleting 7 members from `holdout_membership.json` and
removing their 7 PDFs — **no commit** — leaves an internally consistent tree, so:

| invariant | result on the tampered tree |
|---|---|
| F1 membership committed | **PASS** — "10 members, committed=True" |
| F2 hashes match | **PASS** — 10 files match |
| F3 freshness | **PASS** — 10 members clean |
| F7 set equality | **PASS** — 10 files == 10 manifested |
| F8 PDF headers | **PASS** |
| **FREEZE INTEGRITY** | **COMPLETE** — over a population that is not the committed one |

**Repairs.**

1. `committed()` now means **tracked AND unmodified against HEAD**.
2. **F10** asserts that the frozen artifacts — membership, contamination, design exposure,
   the pre-registration, this file, and the whole `holdout/` directory — carry **no
   uncommitted change of any kind**. Scoped to frozen artifacts: probe code is expected to
   change and is policed by F9 instead.

**A second, latent defect fixed in the same sweep.** `amendment_commits` selected an
amendment's latest commit with `max(commits, key=lambda c: git("rev-list","--count",c))`.
`rev-list --count` returns a **string**, so the comparison was lexicographic and `"9"`
beats `"1003"`. It is dormant today because no execution-start marker exists, but it would
have silently misjudged the one-way boundary the moment execution was authorized — the
check most likely to be trusted without re-derivation. Now compared as integers.

**Controls:** `--self-test` gains "F10 detects an uncommitted edit to the frozen manifest"
and "F1 no longer calls a MODIFIED manifest committed", giving **24/24**.

**Can this affect membership or scoring?** No. Membership is unchanged and re-verified at
17; this is gate strictness only. Recorded SUBSTANTIVE because it changes what *every*
freeze invariant means, on the dividing line A11 established.

---

## A14 — SUBSTANTIVE. Two post-freeze methodological commits were never declared

```json
{"id": "A14", "class": "SUBSTANTIVE", "commits": ["70ec76c", "985def9"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "Retroactive declaration. Found by binding F9 to commits instead of paths; the path-union rule had silently excused these."}
```

**Found by the F9 repair, in this study's own history.** The old F9 unioned every
`files_touched` and subtracted it from the changed-path set, so a path declared **once**
excused every later change to it. `probes/x04_freeze_check.py` has **nine** modifying
commits and was "declared", so all nine passed.

Binding declarations to commits instead exposed **two post-freeze commits that no amendment
ever described**:

| commit | change | why it is methodological |
|---|---|---|
| `70ec76c` | F4 compared against the withdrawn population — `first_commit(MEMBERSHIP)` returned the design-era commit after the file was re-created | changed what F4 *means* |
| `985def9` | F3 read the raw contamination classes rather than the exemption classes | changed what F3 *means* |

Both are gate-semantics changes made with no confirmatory output in existence, neither
touches membership, and neither computes a score — but neither was recorded, and under the
old rule neither ever would have been. They are declared here rather than excused.

**Why the population stays valid.** Both changes made gates *stricter* and neither can
select or deselect a document; membership is unchanged and re-verified at 17 by F11.

---

## A15 — SUBSTANTIVE. The freeze and the boundary were snapshots, not historical facts

```json
{"id": "A15", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "This pass's own commit is declared by the commit that lands it; F9 requires it."}
```

Five defects, each an instance of *the gate checks a proxy for the property*.

**1. A committed marker was never required for execution.** The final block of `main()`
consulted the marker **not at all**: with F/G green and no marker anywhere, x04 printed
`EXECUTION PERMITTED` and returned 0. Measured by stubbing both gate functions to pass —
authorization was optional. There is now a state machine: `ABSENT` → *READY TO AUTHORIZE*,
`UNCOMMITTED` → *AUTHORIZATION PENDING COMMIT*, `MUTATED` → *BOUNDARY VIOLATED*, all
`EXECUTION FORBIDDEN` with exit 1. Only a **valid committed write-once** marker permits
execution. Writing the file is not authorizing.

**2. The boundary was movable.** `marker_commit()` used `last_commit`, so editing the
marker at N would move the boundary to N and make a substantive change between M and N
appear to predate it. `first_commit` alone is not sufficient either — this study already
saw a path deleted and re-created. Immutability is now asserted directly: **exactly one
modifying commit, and the current blob equals the blob introduced by it.**

**3. The population freeze was movable.** F3, F4 and F9 derived it from
`last_commit(MEMBERSHIP)`, so a later committed edit to the manifest would have become the
new freeze, moved the pre-selection snapshot to that commit's parent, and shrunk the
post-freeze window. `POPULATION_FREEZE_COMMIT` is now **pinned to `4e2b520`**, and new
**F11** proves the current population is byte-identical to the frozen one (blob, id set,
paths, recorded SHA-256s). A later membership change now **fails** instead of re-anchoring.

**4. F9 bound declarations to paths, not changes** — see A14.

**5. The ledger was not sealed.** Nothing stopped `PRE-EXECUTION-AMENDMENTS.md` changing
after authorization. F9 now rejects any commit touching it after a valid boundary.

**Also:** the marker becomes a **manifest** of the exact frozen surface
(`population_freeze_commit`, `membership_blob`, `frozen_blobs` over every result-bearing
file), and normal x04 re-verifies those blobs afterwards, reporting **METHODOLOGY DRIFT**
as a deviation rather than silently moving to the new version.

---

## A16 — SUBSTANTIVE. Execution readiness did not cover the machinery that produces the answer

```json
{"id": "A16", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"]}
```

**The conceptual gap.** G1–G4 covered the adapter, its evidence, the adjudicator prompt and
the exposure list. None of the **runners, frame builders, oracle builder, scorers or
decision evaluator** had to exist. Authorizing on that basis would have permitted inspecting
confirmatory H/X output and *then* finishing the scorer — innocently or not, the scoring
rule would postdate the data.

**G5** now requires the whole result-bearing surface to exist and be committed:

| file | what answer it can move |
|---|---|
| `pdfium_extended_corrected.py` | X's character facts → every X metric |
| `reconstruct_extended_corrected.py` | X's word segmentation → every X metric |
| `run_hybrid.py` / `run_extended.py` | each architecture's extraction → every metric |
| `build_frames.py` | which records enter the C-frame and D-frame |
| `build_oracle.py` | what the adjudicator sees; which label binds to which region |
| `m3_boundaries.py` | WELD/SPLIT/TEXT_ERROR and the heading-level decision unit |
| `score_metrics.py` | M0–M9 outcomes |
| `decide_architecture.py` | the architecture decision itself |
| `x2_verify.py` | whether X's contract assertions actually hold |
| `adjudicator_prompt.md` | what the adjudicator is asked and shown |

**Deliberately NOT frozen:** report generation, table formatting, summary prose and
diagnostics that cannot affect inclusion, oracle data, metric classification or the
decision. Freezing them would be ceremony.

**G2 strengthened in the same pass.** A hand-written file naming `fake-doc-123`, labelled
DEVELOPMENT, made G2 green — proving only that a file asserts its own success. Evidence must
now bind provenance: every fixture path must **exist in the repo**, not be a holdout
document, and hash to its recorded SHA-256; and the adapter, reconstructor and verifier blob
SHAs must match the committed files, so evidence cannot outlive the code that produced it.

**Consequence, stated plainly:** most of this surface does not exist yet, so the study is
**not** ready to authorize. That is the honest state rather than a gate that reads green on
four files.

---

## What was deliberately NOT amended

- **Membership.** Unchanged, 17 documents. The orphan `CRPT-118HRPT146.pdf` was never a
  member; deleting it corrects the *directory*, not the population.
- **The stale-prose findings did not trigger a re-selection.** Consuming a fresh population
  to fix prose contradictions found before scoring would waste a scarce resource for no
  methodological gain.
- **`PRE-REGISTRATION.md` itself.** Byte-frozen at `c399e9d`, so F4 keeps its plain
  meaning. Read it **as amended by this file**.
