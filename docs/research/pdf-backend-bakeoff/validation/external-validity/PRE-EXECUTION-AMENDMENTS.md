# Pre-execution amendments

**Every amendment here was made while NO confirmatory architecture output existed.** No H
or X output has ever been produced on any confirmatory holdout document. `x04`'s F5 asserts
that mechanically, and it is the condition that makes amending a frozen protocol before
execution methodologically legitimate rather than a degree of freedom.

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
| `UNSCORABLE` | either side `UNALIGNABLE` |

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
{"id": "A6", "class": "TOOLING", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x03_select_holdout.py", "probes/x04_freeze_check.py",
                   "probes/m3_boundaries.py", "probes/m3_selftest.py",
                   "PRE-EXECUTION-AMENDMENTS.md",
                   "holdout/CRPT-118HRPT146/CRPT-118HRPT146.pdf"]}
```

**What changed.**

1. `x03_select_holdout.py` — every download-rejection path now deletes the file, and a
   download must begin with `%PDF-` to be accepted (`accept_download`).
2. `x04_freeze_check.py` — F7, F8 and F9 added, with self-tests.
3. `m3_boundaries.py` / `m3_selftest.py` — new, per A3/A4.

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
 "files_touched": ["probes/x01_contamination.py", "results/contamination.json"]}
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

## What was deliberately NOT amended

- **Membership.** Unchanged, 17 documents. The orphan `CRPT-118HRPT146.pdf` was never a
  member; deleting it corrects the *directory*, not the population.
- **The stale-prose findings did not trigger a re-selection.** Consuming a fresh population
  to fix prose contradictions found before scoring would waste a scarce resource for no
  methodological gain.
- **`PRE-REGISTRATION.md` itself.** Byte-frozen at `c399e9d`, so F4 keeps its plain
  meaning. Read it **as amended by this file**.
