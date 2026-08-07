"""Neutral identity contract: literal source-glyph membership.

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

Four questions the review asked, answered from the adapters:

  1. Is the PDFium char index preserved today?  NO -- neither contract carries it.
  2. Can it be added to both arms without changing the comparison?  YES. Both loops already
     have `i`; appending it records provenance and alters no decision.
  3. Is another exact common identity available?  NO. Geometry is shared but is a
     MEASUREMENT, not an identity: two glyphs can share a box. List position is not stable
     because the arms skip different characters.
  4. Can generated spaces have no neutral identity?  YES, and they must: they are engine
     inventions with no ink, so they get `gid = None` and can never be a member of a
     neutral line.

ELIGIBILITY IS GEOMETRIC, NOT LEXICAL
-------------------------------------
A19 claimed the skeleton reads "no codepoint" while `x07` filtered `cp in (10, 13, 32)`.
That contradiction is removed: a source glyph is neutral-eligible iff it has a VALID INK
BOX -- present, finite, and positive area -- and is upright. Newlines, generated spaces and
control entries carry no ink and are excluded by that rule alone. `x08` demonstrates this on
development documents rather than assuming it.
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


# --------------------------------------------------------------- architecture output


@dataclass
class Fragment:
    """One reconstructed line from an architecture, as an ORDERED cell stream.

    Each cell is `(gid, char)`. A gid of None is a character the architecture INSERTED --
    a word space it decided on, or an engine-generated space it consumed. That is precisely
    the thing under test, so it is carried, never normalised away.
    """

    cells: list[tuple[int | None, str]] = field(default_factory=list)

    @property
    def gids(self) -> set[int]:
        return {g for g, _ in self.cells if g is not None}

    def text(self) -> str:
        return "".join(c for _, c in self.cells)


def contribution(fragments: list[Fragment], line: NeutralLine) -> str:
    """MODEL G -- the architecture's text for exactly the glyphs this neutral line owns.

    Set membership on gids. No tolerance, no nearest-anything, no text similarity.

    Spacing is PRESERVED, which is the whole point: an inserted character (gid None) is kept
    when it sits BETWEEN two retained glyphs of this line. So the same gid set yields
    "FAMILYHOUSING" from an architecture that welded and "FAMILY HOUSING" from one that did
    not -- the neutral skeleton supplies identity and never supplies spacing.

    Fragments are concatenated in the order of their FIRST owned gid, so fragment ordering
    is a function of source identity rather than of emission order: reversing the list
    cannot change the result.
    """
    owned: list[tuple[list[tuple[int | None, str]], int]] = []
    for frag in fragments:
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
    return "".join(ch for cells, _ in owned for _, ch in cells)


def line_state(h_frags: list[Fragment], x_frags: list[Fragment], line: NeutralLine) -> dict:
    """The frozen per-neutral-line comparison object.

    States: SAME / TEXT_DIFFERS / H_ABSENT / X_ABSENT / BOTH_ABSENT.
    Diagnostics travel alongside and do NOT enter the state, so no merge, split, drop or
    duplication can disappear silently while the state stays coarse enough to reason about.
    """
    h_own = [f for f in h_frags if f.gids & line.gids]
    x_own = [f for f in x_frags if f.gids & line.gids]
    h_text, x_text = contribution(h_frags, line), contribution(x_frags, line)

    if not h_own and not x_own:
        state = "BOTH_ABSENT"
    elif not h_own:
        state = "H_ABSENT"
    elif not x_own:
        state = "X_ABSENT"
    else:
        state = "SAME" if h_text == x_text else "TEXT_DIFFERS"

    h_gids = {g for f in h_frags for g in f.gids} & line.gids
    x_gids = {g for f in x_frags for g in f.gids} & line.gids
    h_seq = [g for f in h_own for g, _ in f.cells if g in line.gids]
    x_seq = [g for f in x_own for g, _ in f.cells if g in line.gids]
    return {
        "line": line.key,
        "state": state,
        "h_text": h_text,
        "x_text": x_text,
        "diagnostics": {
            "H_MULTIPART": len(h_own) > 1,
            "X_MULTIPART": len(x_own) > 1,
            "H_SOURCE_GLYPH_LOSS": sorted(line.gids - h_gids),
            "X_SOURCE_GLYPH_LOSS": sorted(line.gids - x_gids),
            "H_SOURCE_GLYPH_DUPLICATION": len(h_seq) != len(set(h_seq)),
            "X_SOURCE_GLYPH_DUPLICATION": len(x_seq) != len(set(x_seq)),
            "H_CROSS_LINE_MERGE": any(f.gids - line.gids for f in h_own),
            "X_CROSS_LINE_MERGE": any(f.gids - line.gids for f in x_own),
        },
    }


def differs(state: dict) -> bool:
    """D-frame membership for one neutral line. Symmetric under swapping H and X:
    every asymmetric state has an explicit mirror (H_ABSENT <-> X_ABSENT)."""
    return state["state"] != "SAME"
