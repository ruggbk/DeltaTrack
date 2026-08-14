# Issue draft — PDF anchors have no stable identity across line wrapping

**Not filed.** Filing on a public repo is outward-facing, so opening this is Will's call. Copy
the body below into a new issue when you want it tracked; the front matter here is notes for
that decision, not part of the issue.

- **Suggested type:** bug (it produces false statements in shipped reports), with a design
  component.
- **Suggested labels:** `pdf`, `parser`, `epic` if the four workstreams below are split into
  sub-issues.
- **Evidence:** `docs/research/pdf-matching-convergence/slice6-moved-semantics.md` §4, §9;
  reproduce with `probes/pdf_move_anchor_adjudication.py`.
- **Relationship to ADR 0020:** none. The convergence work is complete as of slice 6a. This is
  the semantic defect that work uncovered and deliberately did not fix.

---

## PDF report claims sections were renamed when only the line wrapping changed

### What happens

The PDF diff reports a heading as renamed when the bill prints exactly the same heading in both
versions. A staffer reading the report is told a provision was renumbered or renamed; nothing
was.

Real sentences the current engine produces on the committed corpus:

```
Renumbered: NAVY AND MARINE CORPS → AND MARINE CORPS
Renumbered: HOUSING IMPROVEMENT FUND → FUND
Renumbered: TRATION → MAINTENANCE, WESTERN AREA POWER ADMINISTRATION
Renumbered: GINIA.— → WEST VIRGINIA.—
Renumbered: OPERATION AND MAINTENANCE, SOUTHWESTERN → OPERATION AND MAINTENANCE, SOUTHWESTERN POWER
```

Taking the first: both versions print the account heading

```
FAMILY HOUSING OPERATION AND MAINTENANCE, NAVY AND MARINE CORPS
```

The 2018 print wraps it after `MAINTENANCE,` and the 2019 print wraps it after `NAVY`. The
heading is identical; only the column it broke in moved.

### Why

An "anchor" is captured from **one printed line**. A GPO account heading is set centred in caps
and wraps across as many lines as it needs, so the anchor is a *fragment* of the heading whose
content depends on where the typesetter broke the line. Two versions that re-typeset the same
bill therefore produce two different anchor strings for one unchanged heading.

`formatters/canonical._pdf_move` then decides `move.kind` by comparing anchor **text**:

```python
if hunk.v1_anchor is not None and hunk.v2_anchor is not None and hunk.v1_anchor.text != hunk.v2_anchor.text:
    return {"kind": "renumbered", "old_label": ..., "new_label": ...}
```

so a wrap difference is reported to the reader as a renaming.

### How often, on the committed corpus

Measured over the 17 production-accepted adjacent PDF pairs
(`probes/pdf_move_anchor_adjudication.py`, which prints the actual page lines for every row):

| | |
|---|---|
| moved cards rendered `Renumbered: X → Y` | 156 of 165 |
| round-1 changed-anchor moves whose **printed heading is identical** | 13 of 20 |
| round-2 moves whose anchors differ | 136 |
| …of those, whose **printed heading is identical** | at least 9 |

The 13 and the 9 are floors, not exact counts: the measuring predicate scores a
hyphenation-split heading as "genuinely differs", and reading its printed context shows the
same heading on both sides.

**Concentration caveat.** 16 of the 20 round-1 rows come from a single version pair
(115-hr-5895 `3_placed-on-calendar-senate → 4_engrossed-amendment-senate`), a
strike-all-and-insert Senate amendment that re-typeset the whole bill. That is the condition
which produces this defect, so the corpus frequency is a poor guide to how often a *user* hits
it — a re-typesetting amendment is exactly the comparison a staffer runs.

### Related, and probably the same root cause

One round-1 pair on this corpus pairs two **different appropriations accounts** because their
boilerplate is 78% identical, and reports `Renumbered: ELECTRICITY DELIVERY → NUCLEAR ENERGY`.
That is a correspondence defect rather than a labelling one, but it is reachable because the
anchor carries no identity strong enough to refuse the pairing.

Two of the nine `relocated` cards render `Moved: A → A` — identical breadcrumbs on both sides,
i.e. a move claim with no destination.

### What a fix needs to cover

1. **A stable heading identity** that survives line wrapping and hyphenation, so the same
   printed heading yields the same identity in both versions.
2. **The false `Renumbered:` labels**, which are decided independently of the matcher in
   `canonical._pdf_move` — fixing correspondence alone does not fix them.
3. **Semantic definitions for `moved` / `renumbered` / `relocated`.** ADR 0006 says canonical
   JSON carries pipeline-neutral semantic facts; the agreed target for `moved` is *the same
   legislative provision at a different legislative location*, which is not expressible until
   (1) exists. Today's value is provenance wearing a semantic name.
4. **External validity.** Any fix should be evaluated on re-typesetting amendments beyond the
   three corpus pairs that carry almost all the observed instances.

### What is deliberately not in scope here

The ADR 0020 stage separation is finished (slice 6a) and this issue does not reopen it.
Retiring the round-1 move basis — the change that would remove 13 of these false labels — is a
canonical behaviour change tracked separately as "6b" in the design memo, and is blocked on (1)
and (3) above rather than on the architecture.
