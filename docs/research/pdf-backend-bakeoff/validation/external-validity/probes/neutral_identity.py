"""Neutral identity contract: literal source-glyph membership, and the discordance rules.

SUPERSEDES the projection half of `neutral_geometry.py`. A19 claimed projection was "by
GLYPH MEMBERSHIP" and that membership "needs no tolerance". Neither was true of the code:
`project_by_glyphs` received only BASELINES and assigned each to the nearest neutral line
with NO maximum distance, so a glyph at y = -5000 was still forced onto a neutral line.
That is baseline inference, not membership. This module makes the word literal.

THE NEUTRAL GLYPH ID
--------------------
    gid = (document_sha256, page_number, source_char_index)

`source_char_index` is the index `i` in `FPDFText_CountChars(text_page)` order -- the
engine's own text-page character index, which both adapters already iterate
(`for i in range(max(n, 0))`) and which **neither currently stores**: both `continue` past
characters they reject, so a list position is not the index. Recording `i` is pure
provenance: it changes no extraction decision on either arm, and it is the only exact
identity both arms can name for the same mark on the page.

ELIGIBILITY IS GEOMETRIC, NOT LEXICAL
-------------------------------------
A source glyph is neutral-eligible iff it has a VALID INK BOX -- present, finite, and
positive area -- and is upright. Newlines, generated spaces and control entries carry no
ink and are excluded by that rule alone. `x08` demonstrates this on development documents
rather than assuming it.

IDENTITY NORMALISATION IS NOT ARCHITECTURE-OUTPUT NORMALISATION
---------------------------------------------------------------
This is the distinction A22 exists to freeze, and the one the first cut of this module
erased. Model G answers *which physical line each source glyph belongs to*. That question
has one right answer and both arms must be held to it. It must NOT be allowed to answer
the different question of *how many lines the architecture emitted, and which glyphs it
grouped together* -- because that grouping IS an architecture output, and it is one of the
two things the seam can change.

Concretely: H welding two physical lines into one emitted line, while X emits two, leaves
both arms' PROJECTED TEXT identical on both neutral lines -- partition hands each line back
exactly its own glyphs. Comparing only projected text therefore reports `SAME` for a
reconstruction disagreement that A17.4 existed to observe. The repair is not to weaken the
projection; it is to compare a second, independent quantity: the RECONSTRUCTION SIGNATURE.

    TEXT_DISCORDANCE          what characters the arm produced for this line's glyphs
    SEGMENTATION_DISCORDANCE  how the arm grouped this line's glyphs into emitted lines

The two are deliberately orthogonal. A word-space difference (`FAMILYHOUSING` vs
`FAMILY HOUSING`) moves the text and must NOT move the signature -- inserted characters
carry no gid and never enter it. A merge or split moves the signature and need not move
the text. Keeping them separate is what lets M3 score word boundaries without a
segmentation difference fabricating a boundary error.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

BASELINE_TOL_FACTOR = 0.5


@dataclass(frozen=True)
class SourceGlyph:
    """One below-seam ink mark, with the identity both arms can name."""

    gid: int  # source char index within the page
    baseline: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 0.0)


def eligible(gid: int | None, box: tuple | None, upright: bool) -> bool:
    """Neutral-eligible iff it is a real ink mark. NO codepoint is consulted.

    Generated spaces have `gid is None` (engine inventions), newlines and control entries
    have no box or a degenerate one. Nothing here can condition on H-vs-X text behaviour,
    because nothing here reads text.
    """
    if gid is None or box is None:
        return False
    x0, y0, x1, y1 = box
    if any(v is None for v in (x0, y0, x1, y1)):
        return False
    return upright and (x1 - x0) > 0 and (y1 - y0) > 0


@dataclass(frozen=True)
class NeutralLine:
    page: int
    ordinal: int
    baseline: float
    x0: float
    y0: float
    x1: float
    y1: float
    gids: frozenset[int]

    @property
    def key(self) -> tuple[int, int]:
        return (self.page, self.ordinal)


def cluster(glyphs: list[SourceGlyph], page: int) -> list[NeutralLine]:
    """Cluster eligible source glyphs into neutral lines, carrying their GIDS.

    Same geometric rule A19 froze -- tolerance 0.5 x median ink height, descending baseline,
    anchored on the cluster's first glyph -- but each line now OWNS an explicit gid set, so
    membership is a fact rather than something inferred later.
    """
    if not glyphs:
        return []
    tol = BASELINE_TOL_FACTOR * (statistics.median([g.height for g in glyphs]) or 1.0)
    rows: list[list[SourceGlyph]] = []
    anchor: float | None = None
    for g in sorted(glyphs, key=lambda g: (-g.baseline, g.x0, g.gid)):
        if anchor is None or abs(g.baseline - anchor) > tol:
            rows.append([g])
            anchor = g.baseline
        else:
            rows[-1].append(g)
    return [
        NeutralLine(
            page=page,
            ordinal=i,
            baseline=round(statistics.median([g.baseline for g in row]), 4),
            x0=round(min(g.x0 for g in row), 4),
            y0=round(min(g.y0 for g in row), 4),
            x1=round(max(g.x1 for g in row), 4),
            y1=round(max(g.y1 for g in row), 4),
            gids=frozenset(g.gid for g in row),
        )
        for i, row in enumerate(rows)
    ]


def build_owner(lines: list[NeutralLine]) -> dict[int, tuple[int, int]]:
    """gid -> owning neutral-line key, for every eligible glyph on the page.

    The signature needs to name the OTHER neutral lines an emitted line reaches into, and
    naming them by key rather than by index keeps the representation stable if the caller
    ever passes a subset of lines.
    """
    return {g: ln.key for ln in lines for g in ln.gids}


# --------------------------------------------------------------- architecture output


@dataclass
class EmittedLine:
    """ONE reconstructed printed line, as the architecture actually emits it.

    This is deliberately NOT a free-floating "fragment". In both arms the emitted printed
    line is one element of `Page.print_lines` -- a single non-chrome baseline cluster, with
    its GPO margin number already stripped. `Page.lines` (the `_merge_print_lines` output)
    is a LATER, deterministic soft-hyphen recombination shared by both arms, and is not the
    unit: it spans several physical lines by design, so scoring it would manufacture a
    cross-line merge on every hyphenated line in BOTH arms at once.

    `lid` is the architecture's own emitted-line identity, `(page_number, index within
    Page.print_lines)`. It exists so that "these two glyphs were emitted on the same line"
    is a recorded fact rather than something re-derived from geometry.

    Each cell is `(gid, char)`. A gid of None is a character the architecture INSERTED --
    a word space it decided on, or an engine-generated space it consumed. That is precisely
    the thing under test, so it is carried, never normalised away, and it never enters the
    reconstruction signature.
    """

    cells: list[tuple[int | None, str]] = field(default_factory=list)
    lid: tuple[int, int] | None = None

    @property
    def gids(self) -> set[int]:
        return {g for g, _ in self.cells if g is not None}

    def text(self) -> str:
        return "".join(c for _, c in self.cells)


def contribution(emitted: list[EmittedLine], line: NeutralLine) -> str:
    """MODEL G -- the architecture's text for exactly the glyphs this neutral line owns.

    Set membership on gids. No tolerance, no nearest-anything, no text similarity.

    Spacing is PRESERVED, which is the whole point: an inserted character (gid None) is kept
    when it sits BETWEEN two retained glyphs of this line. So the same gid set yields
    "FAMILYHOUSING" from an architecture that welded and "FAMILY HOUSING" from one that did
    not -- the neutral skeleton supplies identity and never supplies spacing.

    Emitted lines are concatenated in the order of their FIRST owned gid, so ordering is a
    function of source identity rather than of emission order: reversing the list cannot
    change the result.

    THEY ARE JOINED BY "\\n", NOT BY "". This corrects A21, which joined by "" and thereby
    manufactured a WELD out of a SPLIT. When an arm emits one neutral line as two printed
    lines, its output really does carry a line break between those characters -- production
    joins printed lines with "\\n" (`Page.text`) -- so "" asserts an adjacency the arm never
    produced. The consequence was not cosmetic: a heading split at a word boundary would
    have projected as `FAMILYHOUSING`, scored a fabricated M3 weld against an oracle reading
    `FAMILY HOUSING`, and counted as `X_REGRESSES` -- a veto term in Rule 1.

    "\\n" needs no new machinery downstream: `m3_boundaries.decompose` tests `ch.isspace()`,
    so a line break is already read as a word boundary, and M2's frozen normalisation
    already collapses whitespace runs. A split at a word boundary therefore costs nothing,
    while a split MID-word still registers as a real boundary defect, which is correct --
    the arm did break the word across two printed lines.
    """
    owned: list[tuple[list[tuple[int | None, str]], int]] = []
    for frag in emitted:
        kept: list[tuple[int | None, str]] = []
        pending: list[tuple[int | None, str]] = []
        seen_owned = False
        for gid, ch in frag.cells:
            if gid is None:
                (pending if seen_owned else []).append((gid, ch))
                continue
            if gid in line.gids:
                if seen_owned:
                    kept.extend(pending)
                pending = []
                kept.append((gid, ch))
                seen_owned = True
            else:
                pending = []  # an inserted char adjacent to a foreign glyph is not ours
        if kept:
            first = min(g for g, _ in kept if g is not None)
            owned.append((kept, first))
    owned.sort(key=lambda kv: kv[1])
    return "\n".join("".join(ch for _, ch in cells) for cells, _ in owned)


def reconstruction_signature(emitted: list[EmittedLine], line: NeutralLine, owner: dict[int, tuple[int, int]]) -> tuple:
    """How this architecture GROUPED this neutral line's glyphs into emitted printed lines.

    The smallest representation that captures the behaviour the D-frame must respond to.
    One element per emitted line that carries at least one of this neutral line's glyphs,
    ordered by its first owned gid:

        (this line's gids that the emitted line carries,  other neutral lines it reaches)

    That pair is exactly enough, and no more:

      * its LENGTH is the emitted-line cardinality for this neutral line, so a split shows;
      * its first member partitions the line's glyphs, so WHERE a split falls shows;
      * its second member names the cross-neutral-line grouping, so a merge shows, and
        merges with DIFFERENT spans are distinguishable from each other.

    Deliberately absent:

      * text and inserted characters -- a word-space difference must not register as a
        segmentation difference, or M3 would see a boundary error that does not exist;
      * emitted-line ids -- two arms numbering their lines differently is not a disagreement
        about grouping, and including lids would make every comparison trivially unequal;
      * glyphs off the neutral skeleton -- an arm may emit a mark the skeleton excludes
        (H keeps `size > 1.0`, the skeleton requires positive ink area), and that is a
        coverage fact, counted separately, not a grouping fact.

    Tuples rather than frozensets so the value is ordered, hashable, comparable and
    JSON-representable without a normalisation step that could differ between arms.
    """
    parts: list[tuple[tuple[int, ...], tuple[tuple[int, int], ...], int]] = []
    for frag in emitted:
        owned = sorted(g for g in frag.gids if g in line.gids)
        if not owned:
            continue
        others = sorted({owner[g] for g in frag.gids if g in owner and owner[g] != line.key})
        parts.append((tuple(owned), tuple(others), owned[0]))
    parts.sort(key=lambda t: t[2])
    return tuple((o, ot) for o, ot, _ in parts)


def line_state(
    h_emitted: list[EmittedLine],
    x_emitted: list[EmittedLine],
    line: NeutralLine,
    owner: dict[int, tuple[int, int]],
) -> dict:
    """The frozen per-neutral-line comparison object.

    Carries BOTH comparable quantities -- projected text and reconstruction signature --
    plus the coarse presence label and the diagnostics. The label is for reading; the two
    quantities are what the discordance predicates consume.
    """
    h_own = [f for f in h_emitted if f.gids & line.gids]
    x_own = [f for f in x_emitted if f.gids & line.gids]
    h_text, x_text = contribution(h_emitted, line), contribution(x_emitted, line)
    h_sig = reconstruction_signature(h_emitted, line, owner)
    x_sig = reconstruction_signature(x_emitted, line, owner)

    if not h_own and not x_own:
        state = "BOTH_ABSENT"
    elif not h_own:
        state = "H_ABSENT"
    elif not x_own:
        state = "X_ABSENT"
    else:
        state = "SAME" if h_text == x_text else "TEXT_DIFFERS"

    h_gids = {g for f in h_emitted for g in f.gids} & line.gids
    x_gids = {g for f in x_emitted for g in f.gids} & line.gids
    h_seq = [g for f in h_own for g, _ in f.cells if g in line.gids]
    x_seq = [g for f in x_own for g, _ in f.cells if g in line.gids]
    return {
        "line": line.key,
        "state": state,
        "h_text": h_text,
        "x_text": x_text,
        "h_signature": h_sig,
        "x_signature": x_sig,
        "diagnostics": {
            "H_EMITTED_LINE_COUNT": len(h_own),
            "X_EMITTED_LINE_COUNT": len(x_own),
            "H_SOURCE_GLYPH_LOSS": sorted(line.gids - h_gids),
            "X_SOURCE_GLYPH_LOSS": sorted(line.gids - x_gids),
            "H_SOURCE_GLYPH_DUPLICATION": len(h_seq) != len(set(h_seq)),
            "X_SOURCE_GLYPH_DUPLICATION": len(x_seq) != len(set(x_seq)),
            "H_CROSS_LINE_MERGE": any(f.gids - line.gids for f in h_own),
            "X_CROSS_LINE_MERGE": any(f.gids - line.gids for f in x_own),
        },
    }


# ------------------------------------------------------------------ discordance rules
#
# Every predicate below is an INEQUALITY BETWEEN THE TWO ARMS' OWN VALUES. That is what
# makes symmetry structural rather than tested-and-hoped-for: `a != b` is `b != a` for any
# a and b, so D(H,X) == D(X,H) holds by construction and the tests confirm the construction
# rather than establish the property. One-arm "badness" flags are deliberately NOT used:
# if both arms merge N0 and N1 the same way there is no H/X discordance to adjudicate, and
# a rule reading `H_CROSS_LINE_MERGE or X_CROSS_LINE_MERGE` would wrongly include it.


def text_discordance(state: dict) -> bool:
    """Did the arms produce different CHARACTERS for this neutral line's glyphs?

    Absence is a text difference, not a separate case: an arm that emits nothing for the
    line contributes "", so H_ABSENT and X_ABSENT fall out of the same comparison and keep
    their mirror symmetry for free.
    """
    return state["h_text"] != state["x_text"]


def segmentation_discordance(state: dict) -> bool:
    """Did the arms GROUP this neutral line's glyphs into emitted lines differently?"""
    return state["h_signature"] != state["x_signature"]


def line_discordance(state: dict) -> bool:
    """D-frame membership contributed by one neutral line: the union of the two.

    NOTE the case this deliberately excludes. When NEITHER arm emits the line -- a running
    head, a page number, a `VerDate` stamp, all correctly dropped as chrome by both -- both
    texts are "" and both signatures are (), so nothing fires. The previous rule
    (`state != "SAME"`) put every such line in the D-frame, scoring agreement as
    discordance and flooding a census frame with page furniture. PRE-REGISTRATION 5.8 is
    explicit that the D-frame "cannot see a failure both architectures share. That is
    exactly why the C-frame exists", so a shared drop belongs to RQ2, not here. It stays
    visible as the BOTH_ABSENT count.
    """
    return text_discordance(state) or segmentation_discordance(state)


def anchor_discordance(h_anchors, x_anchors) -> bool:
    """Do the arms emit different anchor sets for this region?

    Region-level, as PRE-REGISTRATION 5.8 fixes it ("every region where their emitted
    anchor sets differ"). An anchor is placed in a region by IDENTITY, not by position: the
    neutral line owning the first gid of the emitted line the anchor was read from decides
    its region. Sets, so ordering cannot create a spurious difference.
    """
    return set(h_anchors) != set(x_anchors)


def region_discordance(states: list[dict], h_anchors=(), x_anchors=()) -> bool:
    """A neutral region enters the D-frame iff any of the three discordances fires."""
    return any(line_discordance(s) for s in states) or anchor_discordance(h_anchors, x_anchors)


def m0(states: list[dict]) -> dict:
    """M0's components. Raw counts preserved; no weighted composite is invented.

    One denominator for the three line-rate components -- every neutral line in scope --
    so M0a, M0b and M0_any are directly comparable to each other. The anchor component has
    a different denominator (regions) and is therefore reported separately by the caller
    and never pooled with these.

    `M0b_only` is the number this repair exists to produce: neutral lines where the arms
    agree on every character but disagree on how they cut the page into lines. Under the
    superseded rule that count was structurally unreachable.
    """
    n = len(states)
    text = [s for s in states if text_discordance(s)]
    seg = [s for s in states if segmentation_discordance(s)]
    any_d = [s for s in states if line_discordance(s)]
    seg_only = [s for s in seg if not text_discordance(s)]
    text_only = [s for s in text if not segmentation_discordance(s)]
    return {
        "neutral_lines": n,
        "M0a_text": len(text),
        "M0b_segmentation": len(seg),
        "M0_any": len(any_d),
        "M0b_only_segmentation": len(seg_only),
        "M0a_only_text": len(text_only),
        "both_absent": sum(1 for s in states if s["state"] == "BOTH_ABSENT"),
        "M0a_text_rate": round(len(text) / n, 6) if n else None,
        "M0b_segmentation_rate": round(len(seg) / n, 6) if n else None,
        "M0_any_rate": round(len(any_d) / n, 6) if n else None,
    }
