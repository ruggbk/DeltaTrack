# Slice 6 design memo — what a PDF `moved` should mean

**Status: RESEARCH APPROVED (2026-08-14). Slice 6a authorized and implemented; 6b explicitly
NOT authorized — see §10 for the reviewer's policy correction, which supersedes this memo's
original recommendation.**

The memo as written recommended H1 as the semantic definition of canonical `moved`. That was
**not accepted**. §10 now records the ruling: H2 is the semantic target, H1 is internal
provenance only, and 6b leaves ADR 0020 convergence entirely. The measurements in §1–§9 stand
as approved and are not to be re-run as a broad semantic study.

**No production code was changed to produce this research**, no threshold moved, no fixture or
baseline regenerated. **Five** probes were added under `probes/` and three result artifacts
under `results/`.

Everything below is measured on the current rebased branch (`worktree-pdf-adr0020-research`,
`028a0aa` at the time of measurement) over the **17 production-accepted adjacent PDF pairs**.
The historical 145/19/1/165 split was re-measured rather than inherited, and it still holds.

## How the numbers were produced, and why they are trustworthy

**One probe owns the independent transcription; the others do not, and should not be read as
if they did.**

`probes/pdf_move_semantics_census.py` runs the **current** production stages
(`pdf_round1_with_stage_outputs` → `settle_pdf_correspondences`) and then applies an
**independently transcribed** copy of the classification rule, with `0.6` and `0.4` written
as literals rather than imported. The hunk sequence that transcription implies is asserted
element-for-element equal to `diff_pdfs`' own output on every pair before any count is
reported. That assertion is the control: importing `MOVE_THRESHOLD` or calling
`_classified_pdf` would have made the census agree with production by construction, which is
the false-green shape this thread has shipped twice.

The other four are not independent reconstructions and do not need to be:

| probe | what it actually does |
|---|---|
| `pdf_move_boundary_report.py` | read-only over the census artifact; decides nothing |
| `pdf_move_anchor_adjudication.py` | reads the census artifact, then reads the real extracted pages |
| `pdf_move_user_facing.py` | runs the **real** downstream production path (canonical + view model) |
| `pdf_xml_move_comparison.py` | runs the **real** `diff_pdfs` and `diff_bills` and compares them |

Phase E is measured at the consumed output — the real canonical conversion and the real view
model — not inferred from the classifier.

**The census transcription has since become a slice 6a preservation oracle.** It spells the
*pre-6a* rule (anchor inequality + overlap ≥ 0.6, read from the settled round), and it still
reproduces `diff_pdfs` element-for-element after 6a moved that rule into assignment. Re-running
it is one of the cheapest checks that 6a preserved behaviour.

**Population caveat, stated next to the results because it bounds every conclusion below:**
16 of the 20 round-1 moves come from a single version pair (115-hr-5895
`3_placed-on-calendar-senate → 4_engrossed-amendment-senate`), and the other 4 from two
118-hr-4366 pairs. Three pairs of seventeen. That pair is a strike-all-and-insert Senate
amendment, so the whole bill was re-typeset and every line wrap moved — which is the
mechanism the findings turn on. External validity of the round-1 findings is thin, and the
recommendation names that as its own falsifier (§11).

---

## 1. Current moved population and partition

165 moved rows over the accepted corpus. Unchanged from the earlier study.

| | | n |
|---|---|---|
| **A** | round-2 assignment moves | **145** |
| **B** | round-1, texts identical, anchors differ | **1** |
| **C** | round-1, texts differ, anchors differ, overlap ≥ 0.6 | **19** |
| | **total moved** | **165** |

For context, the whole described population is 885 hunks over 8,840 settled correspondences
(2,437 suppressed as unchanged, 5,314 added, 204 removed).

## 2. Changed-anchor `modified` counterpopulation

This is the population the brief insisted on, and it is the first surprise.

| | | n |
|---|---|---|
| **D** | round-1, anchors differ, overlap **< 0.6** → `modified` | **1** |
| **E** | round-1, anchors equal → `modified` (moved unreachable) | 719 |
| **F** | round-1, an anchor absent on either side | **0** |

**The negative population is one row.** The whole round-1 changed-anchor population is 21
rows: 20 above the cutoff, 1 below it.

The single D row:

```
overlap 0.4848   'SECTION 1' -> 'SEC. 1'   115-hr-5895 3->4
  v1: SECTION 1. SHORT TITLE. / This Act may be cited as the "Energy and Water, ...
  v2: SEC. 1. SHORT TITLE. / This Act may be cited as the "Energy and Water, ...
```

A real heading change, in place, correctly called `modified`. It fails the cutoff because the
two blocks broke differently (74 words vs 25), not because of anything about location.

Overlap distributions, for completeness:

```
A round-2 moves            n=145  min=0.6054 max=1.0000   0.6:9 0.7:9 0.8:13 0.9:111 1.0:3
B round-1 identical-text   n=  1  min=1.0000 max=1.0000
C round-1 changed-anchor   n= 19  min=0.6667 max=1.0000   0.6:1 0.7:2 0.8:4 0.9:10 1.0:2
D round-1 changed-anchor   n=  1  min=0.4848 max=0.4848
E round-1 same-anchor      n=719  min=0.4146 max=1.0000
```

## 3. Round-2 same-anchor / different-anchor census

| | n |
|---|---|
| round-2 moves | 145 |
| …with the **same** anchor text on both sides | **9** |
| …with an anchor absent on either side | 0 |
| …whose two texts are identical | 1 |
| …starting on the same printed page number | 23 |
| …whose anchors differ only in punctuation/case/space | 0 |

**Not every round-2 move changes its anchor.** Nine do not, and several of those are the most
obviously real relocations in the corpus — e.g. `'STATE OF MISSISSIPPI.—'` moving from page
285 to page 870 of 118-hr-4366 with byte-identical text. So anchor inequality is not
*necessary* for relocation.

## 4. Near-0.6 adjudication

Sorted by exact overlap, the entire round-1 changed-anchor population sits in two clumps with
**nothing between 0.4849 and 0.6666**:

| overlap | part | anchor change | verdict |
|---|---|---|---|
| 0.4848 | D | `SECTION 1` → `SEC. 1` | closest below — real heading edit, in place |
| 0.6667 | C | `ADMINISTRATIVE PROVISION—MARITIME ADMIN…` → `…PROVISIONS—…` | closest above — real heading edit **and** a real relocation (p322 → p728) |
| 0.7500 | C | `DEPARTMENT OF DEFENSE FAMILY HOUSING` → `DEPARTMENT OF DEFENSE` | line-wrap artifact |
| 0.7822 | C | `ELECTRICITY DELIVERY` → `NUCLEAR ENERGY` | **two different appropriations accounts** |
| 0.8000 | C | `CYBERSECURITY, ENERGY SECURITY, …` → `…ENERGY SECRUITY, …` | real edit (a typo in the bill), in place |
| 0.8333 | C | `DOD MILITARY UNACCOMPANIED` → `…HOUSING IMPROVEMENT` | line-wrap artifact |
| 0.8571 | C | `RELATED AGENCY AND FDA` → `RELATED AGENCIES AND FDA` | real edit, in place |
| 0.8889 | C | `O&M, SOUTHWESTERN` → `O&M, SOUTHWESTERN POWER` | line-wrap artifact |
| 0.9091 ×2 | C | `FAMILY HOUSING O&M,` → `FAMILY HOUSING O&M, NAVY` | line-wrap artifact |
| 0.9247 | C | `HOUSING IMPROVEMENT FUND` → `FUND` | line-wrap artifact |
| 0.9412 | C | `MEMBERS' REP. ALLOWANCES … OFFICIAL` → `… OFFICIAL EXPENSES` | line-wrap artifact |
| 0.9688 | C | `SEC. 105` → `SEC. 104` | **genuine renumbering** |
| 0.9697 | C | `NAVY AND MARINE CORPS` → `AND MARINE CORPS` | line-wrap artifact |
| 0.9748 | C | `SEC. 104` → `SEC. 103` | **genuine renumbering** |
| 0.9804 | C | `SEC. 103` → `SEC. 102` | **genuine renumbering** |
| 0.9849 | C | `POWER ADMINISTRATION` → `ADMINISTRATION` | line-wrap artifact |
| 0.9924 | C | `EXPENSES—MEMBERS' … ALLOW-` → `PENSES—… ALLOWANCES''` | hyphen-split artifact |
| 1.0000 | B | `EXPENSES OF MEMBERS, AND OFFICIAL MAIL` → `OF MEMBERS, …` | line-wrap artifact |
| 1.0000 | C | `NAVY AND MARINE CORPS` → `AND MARINE CORPS` | line-wrap artifact |
| 1.0000 | C | `IMPROVEMENT FUND` → `FAMILY HOUSING IMPROVEMENT FUND` | line-wrap artifact |

The "verdict" column is not a reading of the anchor strings. `probes/pdf_move_anchor_adjudication.py`
prints, for every one of these 21 rows, the lines **actually printed on the page** around the
anchor on both sides, and computes the whole printed heading by walking the consecutive
heading-shaped lines. Measured over the 20 round-1 moves:

```
12  PRINTED HEADING UNCHANGED — the anchor differs only in where it wrapped
 5  printed heading genuinely differs
 3  not measurable (run-in `SEC. n.` anchor)   <- the three genuine renumberings
```

The 12 is a **floor**, not an exact count: the hyphen-split row (0.9924) is scored
"genuinely differs" because the hyphenation moved, and reading its printed context shows the
same quoted heading on both sides. Manual reading of all 21 printed contexts gives:

- **13 line-wrap / hyphenation artifacts** — the heading printed in the bill is identical on
  both sides; only the column it wrapped in moved.
- **3 genuine section renumberings** (`SEC. 105 → 104`, `104 → 103`, `103 → 102`).
- **2 genuine heading edits with the provision in place** (`SECRUITY` typo; `RELATED AGENCY`
  → `RELATED AGENCIES`, still at TITLE VI line 2).
- **1 genuine heading edit that also relocated** (`ADMINISTRATIVE PROVISION(S)`, p322 → p728).
- **1 apparent mispairing of two distinct accounts** (`ELECTRICITY DELIVERY` vs `NUCLEAR
  ENERGY`, paired because their boilerplate is 78% identical).
- plus the 1 D row, correctly `modified`.

**Answering the brief's question directly — what concrete example would prove 0.6 is not a
valid semantic boundary for moved-vs-modified?** Examples cross it in both directions, so the
threshold is not separating the two meanings:

- **Above the line, not moved:** `CYBERSECURITY, ENERGY SECURITY…` → `…SECRUITY…` at 0.80.
  The heading was misspelled in the new version. The provision did not move. Called `moved`.
- **Above the line, not even the same provision:** `ELECTRICITY DELIVERY` → `NUCLEAR ENERGY`
  at 0.78. Two different Department of Energy accounts. Called `moved`.
- **Below the line, and it did move:** none in this corpus — but only because the moved
  population that *is* below 0.6 was already removed upstream by the 0.4 revocation and the
  round-2 retrieval bound, both of which are also 0.6/0.4. The one row below (0.4848) is
  correctly `modified`, so the cutoff is not *wrong* there; it simply is not what decided it.

The 0.6 cutoff is a historical classifier value with no measured semantic support on this
population. It separates 20 rows from 1, and 13 of the 20 are layout artifacts.

## 5. H1 — provenance definition

> `moved` iff the correspondence was selected by round 2.

**Exact output impact: 20 rows flip `moved` → `modified`. 0 flip the other way.** (16 in
115-hr-5895 3→4, 2 in 118-hr-4366 3→4, 2 in 118-hr-4366 4→5.)

**Benefits.** It is the only candidate with cross-source corroboration (§8). It matches XML,
so one canonical field would carry one meaning across both sources. It removes, in one
change, 16 of the 20 rows that a reader would not call moved (13 artifacts + 2 in-place
heading edits + 1 mispairing). It requires no new signal — the round is already recorded on
`PdfSettledCorrespondence`.

**Failures.**

- It is a fact about the *matcher*, not about the *bill*: "the structural walk lost this and
  the relocation retriever found it again". It correlates with relocation but does not assert
  it. Two of the nine `relocated` cards it would keep already render **"Moved: X → X"** —
  identical breadcrumb on both sides — which is a move claim with no observable movement.
- It costs **4 rows a reader would call moved**: the 3 `SEC. 105→104`-style renumberings and
  the `ADMINISTRATIVE PROVISION(S)` relocation. For the 3 renumberings the loss is mostly
  cosmetic — those anchors are run-in, so the block body *starts* `SEC. 105. None of the
  funds…`, and a `modified` card's inline word-diff still shows `105 → 104`. The
  `ADMINISTRATIVE PROVISIONS` row's page jump (322 → 728) would no longer be announced.
- **It needs a decision about partition B that is easy to miss.** The one identical-text row
  currently escapes unchanged-suppression *because* it is going to become a move. Under H1 it
  falls through to `modified` with `old_text == new_text` — a card showing no change at all.
  Its printed heading is identical too, so suppression is the right answer, but that is a
  third output flip (one fewer card) and must be decided in the same change, not discovered
  afterwards.
- Paired discordance, stated as counts in each direction rather than as a net: **+16 / −4** on
  the changed-anchor population, on 3 of 17 pairs.

## 6. H2 — location-change definition

> `moved` iff the settled correspondence is the same provision at a different legislative
> location.

**The candidate factual predicate — `old.anchor.text != new.anchor.text` — is measurably
invalid, in both directions.**

- **Not sufficient.** 13 of the 20 round-1 moves have an unchanged printed heading; the
  anchor differs only in where the line wrapped. `probes/pdf_move_anchor_adjudication.py`
  prints the page lines for each.
- **Not necessary.** 9 of the 145 round-2 moves have equal anchors, including the clearest
  relocations in the corpus.

**Exact output impact if the proxy were adopted anyway: +1 (`SECTION 1 → SEC. 1` becomes
moved, which is wrong — it did not move) and −9 (the same-anchor round-2 relocations become
modified, which is also wrong).** It is worse than H3 in both directions.

**Is there a *better* location predicate available?** Not at assignment time, today.

- The **anchor is a line fragment, not an address.** That is the root of the problem, and it
  is not confined to slice 6 (§9).
- **Page/ordinal displacement is confounded by document growth.** 23 of 145 round-2 moves
  start on the same page number; the rest mostly reflect the whole bill shifting.
- A **hierarchical breadcrumb path does exist**, but only downstream: `canonical._path_for_anchor`
  builds it at export time from the anchor lists. It is derived from the same fragmented
  anchors, and it is not available to assignment.

So H2 is not merely unproven — the pipeline does not currently carry a location identity
capable of expressing it. Making H2 viable is a *parser* change (a stable anchor identity),
not a matching change, and it should not be smuggled into slice 6.

## 7. H3 — legacy-preserving assignment-reason definition

> Assignment records a named reason sufficient for classification: round-2 recovered move, or
> round-1 changed-anchor + the current similarity rule. Classification reads the reason and
> applies no threshold.

**Exact output impact: 0 flips. Byte-for-byte preserving.**

**Independent semantic support: none found.** The measurements above are exactly the search
for it. The `0.6` boundary separates 20 rows from 1 and does no semantic work; the predicate
actually carrying the meaning is anchor inequality, which §6 shows to be a line-wrap detector
on this population. Preserving H3 as *policy* would freeze a rule whose two components have
both been falsified.

H3 is nevertheless the right **mechanism**, and that distinction is the recommendation.

## 8. Unambiguous XML/PDF comparison evidence

15 of 17 accepted pairs have both formats committed. `probes/pdf_xml_move_comparison.py`
compares only where a provision is addressable without inventing a matcher: the PDF anchor is
a bare `SEC. n` label (case-folded, which is the sole spelling difference between the two
pipelines) and that label ends exactly one XML change's old-side path. Everything else is
skipped and counted.

**73 unambiguous rows.**

| | |
|---|---|
| XML also calls it `moved` | **62 / 73** |
| XML reports the same new label | **61 / 73** |
| disagreements | 9 XML `removed`, 2 XML `unchanged` |

**All 73 are partition A.** Verified, not assumed: none of the round-1 changed-anchor rows is
reachable this way (115-hr-5895 has no XML for version 3, and 4366's C-rows are account
headings rather than `SEC. n`). So this evidence supports **round-2 provenance** as a sound
basis for `moved`, and says **nothing** about the round-1 population that slice 6 is about.
Reported as the small number it is, per the brief.

## 9. Renderer / canonical semantics

Kept in the three categories the brief asked for.

**MEASURED** — `probes/pdf_move_user_facing.py`, real canonical + real view model, 165 cards:

| payload | n |
|---|---|
| `kind="renumbered"` | **156** (155 + 1 `body_unchanged`) |
| `kind="relocated"` | **9** (8 + 1 `body_unchanged`) |

`canonical._pdf_move` chooses `renumbered` by **the same anchor-inequality test** classification
uses. The report then shows:

- renumbered → `Renumbered: OLD → NEW`, plus `· body text unchanged` when the texts match.
- relocated → `Moved: <v1 breadcrumb> → <v2 breadcrumb>`.

Sentences the corpus actually produces today include:

```
Renumbered: NAVY AND MARINE CORPS → AND MARINE CORPS
Renumbered: HOUSING IMPROVEMENT FUND → FUND
Renumbered: TRATION → MAINTENANCE, WESTERN AREA POWER ADMINISTRATION
Renumbered: GINIA.— → WEST VIRGINIA.—
Renumbered: ELECTRICITY DELIVERY → NUCLEAR ENERGY
Renumbered: EXPENSES OF MEMBERS, AND OFFICIAL MAIL → OF MEMBERS, AND OFFICIAL MAIL · body text unchanged
Moved: … > ADVANCED TECHNOLOGY VEHICLES MANUFACTURING > DEPARTMENTAL ADMINISTRATION
    → … > ADVANCED TECHNOLOGY VEHICLES MANUFACTURING > DEPARTMENTAL ADMINISTRATION
```

2 of the 9 `relocated` cards render a `Moved:` sentence whose two breadcrumbs are identical.

**INFERENCE.** A staffer reading `Renumbered: NAVY AND MARINE CORPS → AND MARINE CORPS`
understands that the bill renamed a heading. Nothing was renamed; the heading wrapped one word
later. `Renumbered: ELECTRICITY DELIVERY → NUCLEAR ENERGY` reads as one account renamed into
another, across two distinct DoE appropriations. `Moved: A → A` reads as movement with the
destination missing.

**A defect wider than slice 6, and it is the one to file separately.** Because
`canonical._pdf_move` applies anchor inequality independently of classification, fixing the
moved-vs-modified call does **not** fix this. Of the 136 round-2 moves whose anchors differ —
each rendering `Renumbered: X → Y` — **9 print the same heading on both sides** by the same
measured predicate. Retiring the round-1 route removes 13 false renumbering claims; at least 9
more survive it, in a population slice 6 does not touch.

**POLICY (proposed).** Canonical `moved` should mean: *assignment settled this correspondence
by relocation recovery — the same provision, found where the structural walk did not expect
it.* `move.kind` should be decided by a **stable heading identity**, not by raw anchor-string
inequality; until that identity exists, `renumbered` is not a claim the data supports.

## 10. Recommendation for Q2 — SUPERSEDED BY THE REVIEWER RULING

### 10.1 What was originally recommended

Adopt H1 as the meaning, landed as 6a (mechanism, behaviour-preserving) then 6b (policy,
retire the round-1 changed-anchor route).

### 10.2 The ruling, 2026-08-14 — H1 REJECTED as the semantic definition

**H1 is not accepted as the final semantics of canonical `moved`.** ADR 0006 holds that
canonical JSON carries pipeline-neutral semantic facts, and round-2 provenance is an internal
matcher fact. This memo's own measurements make the distinction, and they cut against its
recommendation:

- H1 demotes four adjudicated genuine moves/renumberings to `modified` (§5);
- some round-2 moves have no observable changed anchor or location (§3, §9 — two render
  `Moved: X → X`);
- the XML corroboration is secondary and incomplete (62/73, 11 disagreements) and covers only
  the PDF **round-2** population (§8).

The settled positions:

| | |
|---|---|
| **H2** — *the same legislative provision changed legislative location* | the **semantic target** |
| **H1** — round-2 provenance | useful **internal provenance**, not a canonical meaning |
| **H3** — legacy rule as an assignment-recorded reason | **temporary mechanism**, shipped as 6a |

H2's *concept* is accepted and its current *proxy* stays falsified: raw anchor-text inequality
is not a stable location identity, and the parser carries no identity that could implement H2
today (§6).

**6b therefore leaves ADR 0020 convergence work entirely.** It is a separate
product/matching-semantics decision, to be taken after the location-identity defect has an
adequate solution, or after an explicit decision to ship a conservative interim reporting
policy. It is **not** authorized, and this memo's §11 falsifiers are retained as inputs to that
later decision rather than as a pending trigger.

### 10.3 What was authorized and shipped: slice 6a only

Assignment records a named basis; classification reads it and applies no threshold. The legacy
policy is preserved exactly, and output is byte-identical. Implemented — see §14.

### 10.4 Corrected 6b accounting, for whenever that decision is taken

The original §5 figure of "20 moved → modified plus one suppression decision" double-counts the
partition-B row. If that row is ultimately suppressed, the impact is:

    19 moved -> modified
     1 moved -> suppressed

not 20 plus a suppression. **Not implemented, and unchanged suppression policy is explicitly
out of scope for 6a**: there is no general production predicate that would suppress the
partition-B row without also risking suppression of a future genuine exact-text renumbering.
That belongs with the location-identity work.

### 10.5 Separately, and not as part of slice 6

File the anchor-fragmentation / stable-location-identity defect. It is the root cause of 13 of
the 20 round-1 moves, of at least 9 further false `Renumbered:` sentences on round-2 moves, and
it is what blocks H2 from being expressible at all. It should eventually cover stable heading
identity across wrapping and hyphenation, the false canonical `Renumbered:` labels, the
semantic `moved`/`renumbered`/`relocated` definitions, and the concentrated external-validity
population this study identified. Filing is outward-facing on a public repo, so it is Will's to
open — a ready draft is at
[`issue-draft-anchor-identity.md`](issue-draft-anchor-identity.md).

## 11. Concrete falsification of this recommendation

> **We would change this decision if any of the following were observed.**

1. **A round-1 changed-anchor move on a version pair outside 115-hr-5895 3→4 and the two
   118-hr-4366 pairs that is a genuine relocation or renumbering.** 16 of 20 come from one
   pair; if a wider corpus shows this population is routinely real rather than routinely a
   re-typesetting artifact, H1 discards real information and 6b should not ship.
2. **A `SEC. n → SEC. m` renumbering whose anchor is *not* run-in**, so the number does not
   appear in the block body. The "the word-diff still shows it" mitigation in §5 rests on the
   3 observed renumberings all being run-in; a standalone-heading renumbering would lose the
   fact entirely under H1.
3. **A stable heading identity landing in the parser** (the §9 defect being fixed). That makes
   H2 expressible, and a location-change definition would then be a better answer than a
   provenance one — it would state a fact about the bill rather than about the matcher.
4. **XML's own `moved` being re-specified.** H1's strongest argument is that one canonical
   field should carry one meaning; if the XML track redefines `moved`, PDF should follow that
   rather than the round number.

## 12. Architecture consequence — what assignment must record

Before 6a, `classify_pdf` → `_classified_pdf` read `_pdf_word_overlap(correspondence.evidence[0])`
and handed it to `_hunk_for_paired_blocks`, which compared it against `MOVE_THRESHOLD`. Both are
gone as of §14.

**Assignment emits a named basis per settled correspondence**, sufficient on its own. The
vocabulary is deliberately two names, not three — a settled correspondence with no basis is the
ordinary non-move case and needs no name of its own:

```
None                          assignment reported no move
"round1_anchor_similarity"    round-1 survivor, anchors differ, overlap >= cutoff
"round2_unmatched_recovery"   round-2 assignment claimed two unmatched observations for each other
```

**The names this memo originally proposed were rejected, and correctly.** `structural_path` is
wrong because PDF round 1 is `_block_key` alignment and a positional `replace` zip, not a path —
that is XML's vocabulary, and importing it here would name a mechanism PDF does not have.
`relocation_recovery` is wrong because this study did not establish that a round-2
correspondence is a legislative relocation; §3 measured nine that relocate nothing observable.
Both replacements are algorithmic and describe how the correspondence was settled, which leaves
the question of what `moved` should *mean* open instead of quietly answering it in a constant.

Constraints this must respect, each of which has already cost a review round on this thread:

- **The reason is not the round number.** `PdfSettledCorrespondence.round` exists for record
  *ordering* (a round-2 move takes its removal's slot). Overloading it as the classification
  input re-fuses two things the slice sequence separated, and it cannot express a fourth
  reason later.
- **Classification must stop reading `word_overlap` entirely.** After 6a, `_pdf_word_overlap`
  should have no caller inside `classify_pdf`. That is the testable property of the slice —
  and it is exactly the kind of property no output gate can see (a rule reading the right
  number for the wrong reason produces identical output), so it needs a control that moves the
  reason and watches classification follow, not another output comparison.
- **`_hunk_for_paired_blocks` stops deciding and becomes an emitter**, taking the decided type
  — the shape `_hunk_for_move` already has. Its current docstring ("Classifies as `moved`
  when…") is the fused act being removed.
- **Unchanged-suppression stays in classification, and stays UNCHANGED in 6a.** `old.text ==
  new.text and not anchors_differ` is a statement about what changed, not about what
  corresponds, so it is legitimately classification's. Its anchor clause is entangled with the
  move rule (§5), and revisiting it belongs with the location-identity work, not here.
- **The anchor relationship must arrive as evidence.** Assignment must not reread raw
  `_Block.anchor` while claiming the decision came through the staged architecture. All three
  states are represented — `equal` / `different` / `missing` — because the legacy boolean
  collapsed "no anchor" into "different anchor" and nothing downstream could tell them apart.
- **`_reconcile_moves` is still the round-2 oracle and must not be rewired** to consume the new
  basis.

## 13. Is the recommendation behaviour-preserving?

| | |
|---|---|
| **Slice 6a** (assignment records a basis; classification stops thresholding) | **behaviour-preserving** — 0 output flips, baseline byte-identical. **Shipped**, §14 |
| **Slice 6b** (retire the round-1 changed-anchor basis) | **intentional canonical behaviour change** — 19 `moved`→`modified` + 1 `moved`→suppressed (§10.4); moves the pinned PDF canonical baseline. **Not authorized**, and no longer ADR 0020 work |
| **The `move.kind` / anchor-fragmentation defect** (§9) | **unresolved, out of scope** — a parser-identity problem, wider than the moved question. Draft issue at [`issue-draft-anchor-identity.md`](issue-draft-anchor-identity.md) |

## 14. Slice 6a as shipped

Authorized 2026-08-14 and implemented on this branch.

**The seam.** `_pdf_round1_signals` now describes `anchor_relation` alongside `text_identical`
and `word_overlap`; `pdf_round1_move_basis` applies the legacy rule to that evidence and owns
its own threshold parameter; `assign_pdf_round1_move_bases` runs it over the post-revocation
pairings; `assign_pdf_moves` records `round2_unmatched_recovery` itself;
`settle_pdf_correspondences` attaches both and decides nothing; `_classified_pdf` reads
`move_basis` and consults neither the overlap nor `round`. `_hunk_for_paired_blocks` lost its
`similarity` parameter and is now the `modified` emitter.

**Why the existing gates could not be the control.** The policy is unchanged, so production is
byte-identical whether the rule runs in assignment or in classification. Measured, not assumed:
with the pre-6a threshold restored *in parallel* inside `_classified_pdf` (fault B below), the
canonical PDF baseline stayed **fully green, 27 passed**. Only the new controls caught it.

**Fault injection — every control shown able to fail** (`tests/test_pdf_move_basis.py`, 23
tests, all green unfaulted; production restored and `git status` clean after each):

| fault injected | controls red | canonical baseline |
|---|---|---|
| A — classification keys on `item.round` again | 5 | 3 pairs red |
| B — the move threshold restored *beside* the basis in classification | 5, incl. the static guard | **green — 27 passed** |
| C — the basis rule ignores its `anchor_relation` evidence | 2 | 16 pairs red |
| D — `move_bases` computed, then discarded | — | 3 pairs red, + 3 legacy-oracle pairs |
| E — `_reconcile_moves` wired back onto the production path | 1 | — |
| F — `move_basis` vocabulary validation disabled | 4 | — |

Fault D is the slice-7 lesson applied: a materialised intermediate that nothing reads is
indistinguishable from a correct one. It reddens **exactly** the three pairs this study
identified as carrying the 20 round-1 moves — 115-hr-5895 3→4, 118-hr-4366 3→4, 118-hr-4366
4→5 — which is independent confirmation that the census population and the shipped stage
describe the same rows.

The static guard (`test_no_classification_function_mentions_the_move_cutoff_or_the_overlap_reader`)
asserts an **absence**, so it carries its own positive control: it must also *find* the
forbidden names in `_greedy_pdf_move_links` and `_pdf_round1_signals`, which legitimately use
them. Without that, an empty result could not be told apart from a broken detector.

---

### Probes and artifacts

| probe | what it produces |
|---|---|
| `probes/pdf_move_semantics_census.py` | `results/move-semantics-census.json` — every settled row, partitioned; asserts the transcribed rule reproduces `diff_pdfs` |
| `probes/pdf_move_boundary_report.py` | §1–§6 tables, read-only over the census |
| `probes/pdf_move_anchor_adjudication.py` | the printed page context of all 21 round-1 changed-anchor rows + the wrap-artifact tally over all 165 moves |
| `probes/pdf_move_user_facing.py` | `results/move-user-facing.json` — the canonical `move` payload and rendered sentence for all 165 moved cards |
| `probes/pdf_xml_move_comparison.py` | `results/move-xml-comparison.json` — the 73 unambiguous cross-source rows |
