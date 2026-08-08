"""build_frames -- the two frames, never pooled. A19 / A22 / A23 / §5.8, made executable.

RESULT-BEARING. This is the first component whose output every later stage reads, so it can
move a realized result if it is wrong. It introduces NO new methodological rule: every rule
below is already frozen, and the fidelity comes from the frozen contracts plus the positive
and negative controls in `x17_build_frames.py`.

    A19    neutral skeleton; 8-line page-bounded regions; enrichment withdrawn
    A22/23 text vs segmentation discordance; the M0 comparative risk set
    A27.2  no amount-bearing reservation -- plain uniform C-frame, <= 8 regions/document
    A27.3  the adjudication ITEM is a region; the budget belongs to `decide_architecture`
    A27.7  domain-separated deterministic selection
    A28.5  the bilateral anchor->neutral bridge

WHAT THIS COMPONENT MAY NOT DECIDE. Which lines are neutral (`eligible` + `cluster`, frozen);
region size or alignment; any use of text to form a region; any enrichment predicate; any
amount-bearing reservation; whether a jointly-absent line enters the D-frame (it does not);
the selection seed or ranking rule. The only permitted freedom is JSON layout.

THE D-FRAME IS A COMPLETE CENSUS. No sampling, no truncation, and the 60-region budget is NOT
applied here. If the census is 61 or 2,000 regions this emits all of them; A27.3 gives the
budget to `decide_architecture`, and applying it early would silently destroy the very count
that decides whether Rule 1 may run at all.

M0 RATES ARE NOT SCORED HERE. The per-line comparative quantities are preserved verbatim from
`neutral_identity`; turning them into rates is `score_metrics`' job.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import methodology_contracts as MC
from neutral_identity import (
    NeutralLine,
    build_owner,
    emitted_gids,
    line_state,
    segmentation_discordance,
    text_discordance,
)

from deltatrack.parsers.pdf_anchors import extract_anchors

REGION_SIZE = 8  # A19, frozen
C_FRAME_MAX_PER_DOCUMENT = 8  # A27.2, frozen
P_HEAD = MC.P_HEAD

# anchor placement refusals -- the x14 rule, which refuses rather than guessing
AMBIGUOUS_MARGIN_NUMBER_ON_PAGE = "AMBIGUOUS_MARGIN_NUMBER_ON_PAGE"
NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER = "NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER"
EMITTED_INDEX_OUT_OF_RANGE = "EMITTED_INDEX_OUT_OF_RANGE"
EMITTED_LINE_CARRIES_NO_NEUTRAL_INK = "EMITTED_LINE_CARRIES_NO_NEUTRAL_INK"
FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE = "FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE"

TEXT_DISCORDANCE = "TEXT_DISCORDANCE"
SEGMENTATION_DISCORDANCE = "SEGMENTATION_DISCORDANCE"
ANCHOR_DISCORDANCE = "ANCHOR_DISCORDANCE"


# --------------------------------------------------------------------------- regions


@dataclass(frozen=True)
class Region:
    page_number: int
    ordinal: int
    line_keys: tuple
    short_trailing: bool


def enumerate_regions(neutral: list[NeutralLine], region_size: int = REGION_SIZE) -> list[Region]:
    """A19 literally: non-overlapping windows of `region_size` consecutive neutral lines,
    aligned to the PAGE START, page-bounded, and the short trailing window KEPT.

    I1 -- enumerated from the NEUTRAL SKELETON only. Enumerating from emitted lines would
    make a line both arms dropped unsamplable, and a shared failure invisible; that is
    exactly the failure the C-frame exists to see.

    I5 -- regions never cross pages, because this is called per page and the ordinal restarts.

    The short trailing window is A19's frozen rule, not a convenience: dropping a 1-7 line
    page tail would make the last lines of every page unsamplable, which is a systematic
    coverage hole aligned with page structure rather than a rounding detail.
    """
    if not neutral:
        return []
    page = neutral[0].page
    regions = []
    for start in range(0, len(neutral), region_size):
        window = neutral[start : start + region_size]
        regions.append(
            Region(
                page_number=page,
                ordinal=start // region_size,
                line_keys=tuple(ln.key for ln in window),
                short_trailing=len(window) < region_size,
            )
        )
    return regions


# ------------------------------------------------------------------- anchor placement


def place_anchor(anchor, print_lines, emitted, owner, ordinal_by_key, region_size: int = REGION_SIZE):
    """(region_ordinal, neutral_line_key) for one anchor, or (None, reason).

    THE A28.5 BRIDGE, unchanged: margin number -> unique print-line index -> same emitted
    index -> first neutral ngid -> owning NeutralLine -> region. No heading text is consulted
    at any step; matching an anchor to a line by its text would make anchor discordance
    circular, because text is one of the things being measured.

    `x17` asserts this reproduces `x14.place_anchor` for every anchor on every development
    page, so the rule lives in one place behaviourally even though it is spelled twice.
    """
    hits = [i for i, ln in enumerate(print_lines) if ln.line_number == anchor.line_number]
    if not hits:
        return None, NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER
    if len(hits) > 1:
        return None, AMBIGUOUS_MARGIN_NUMBER_ON_PAGE
    i = hits[0]
    if i >= len(emitted):
        return None, EMITTED_INDEX_OUT_OF_RANGE
    gids = sorted(emitted[i].gids)
    if not gids:
        return None, EMITTED_LINE_CARRIES_NO_NEUTRAL_INK
    key = owner.get(gids[0])
    if key is None:
        return None, FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE
    return (ordinal_by_key[key] // region_size, key), None


def place_arm_anchors(anchors, print_lines, emitted, neutral, region_size: int = REGION_SIZE):
    """region ordinal -> the set of emitted production Anchor VALUES resolved into it.

    The whole `Anchor` value is kept. No reduced signature is invented for frames: `Anchor`
    is a frozen dataclass, so set membership already compares page, line, kind, text and
    division, and choosing a subset would be this component inventing a matching rule the
    protocol never froze.
    """
    owner = build_owner(neutral)
    ordinal_by_key = {ln.key: ln.ordinal for ln in neutral}
    by_region: dict[int, set] = {}
    refusals = Counter()
    for anchor in anchors:
        placed, reason = place_anchor(anchor, print_lines, emitted, owner, ordinal_by_key, region_size)
        if reason:
            refusals[reason] += 1
            continue
        by_region.setdefault(placed[0], set()).add(anchor)
    return by_region, refusals


# ------------------------------------------------------------------------ page frames


@dataclass
class PageInput:
    """One page's frozen inputs. `h_anchors_by_region` / `x_anchors_by_region` are already
    placed, so synthetic controls can supply them directly without constructing a PDF."""

    page_number: int
    neutral: list[NeutralLine]
    h_emitted: list
    x_emitted: list
    h_anchors_by_region: dict = field(default_factory=dict)
    x_anchors_by_region: dict = field(default_factory=dict)
    anchor_refusals: Counter = field(default_factory=Counter)


def build_page_frame(page: PageInput, region_size: int = REGION_SIZE) -> dict:
    """Neutral lines with their comparative state, and the region grid with C/D evidence."""
    owner = build_owner(page.neutral)
    common = emitted_gids(page.h_emitted) & emitted_gids(page.x_emitted)

    states = {}
    for line in page.neutral:
        states[line.key] = line_state(page.h_emitted, page.x_emitted, line, owner, common)

    regions = enumerate_regions(page.neutral, region_size)
    region_rows = []
    for region in regions:
        h_anchors = page.h_anchors_by_region.get(region.ordinal, set())
        x_anchors = page.x_anchors_by_region.get(region.ordinal, set())

        # I4 -- the REGION is the membership unit; the LINE is the evidence. The two are
        # recorded separately so a concordant line inside a D region is never readable as
        # individually qualifying.
        text_lines = [k for k in region.line_keys if text_discordance(states[k])]
        seg_lines = [k for k in region.line_keys if segmentation_discordance(states[k])]
        anchors_differ = set(h_anchors) != set(x_anchors)

        reasons = []
        if text_lines:
            reasons.append(TEXT_DISCORDANCE)
        if seg_lines:
            reasons.append(SEGMENTATION_DISCORDANCE)
        if anchors_differ:
            reasons.append(ANCHOR_DISCORDANCE)

        region_rows.append(
            {
                "page_number": region.page_number,
                "region_ordinal": region.ordinal,
                "neutral_line_keys": [list(k) for k in region.line_keys],
                "short_trailing": region.short_trailing,
                "line_count": len(region.line_keys),
                "d_frame": bool(reasons),
                "d_reasons": reasons,
                # I4: the specific lines carrying each line-level predicate, never the whole region
                "discordant_lines": {
                    TEXT_DISCORDANCE: [list(k) for k in text_lines],
                    SEGMENTATION_DISCORDANCE: [list(k) for k in seg_lines],
                },
                "anchor_evidence": {
                    "differ": anchors_differ,
                    "H": sorted(anchor_repr(a) for a in h_anchors),
                    "X": sorted(anchor_repr(a) for a in x_anchors),
                },
                # C membership is filled by the document-level selector, which must see the
                # COMPLETE region enumeration before it may draw.
                "c_frame": False,
            }
        )

    line_rows = []
    for line in page.neutral:
        st = states[line.key]
        line_rows.append(
            {
                "key": list(line.key),
                "baseline": line.baseline,
                "bbox": [line.x0, line.y0, line.x1, line.y1],
                "gids": sorted(line.gids),
                "region_ordinal": line.ordinal // region_size,
                # I3 -- BOTH_ABSENT stays in the grid and in the artifact. It is excluded
                # from the comparative risk set and can never alone qualify a D region.
                "in_m0_risk_set": st["state"] != "BOTH_ABSENT",
                "line_state": {
                    "state": st["state"],
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "h_signature": _jsonable(st["h_signature"]),
                    "x_signature": _jsonable(st["x_signature"]),
                    "text_discordance": text_discordance(st),
                    "segmentation_discordance": segmentation_discordance(st),
                    "common_gids": st["common_gids"],
                    "diagnostics": st["diagnostics"],
                },
            }
        )

    return {
        "page_number": page.page_number,
        "neutral_lines": line_rows,
        "regions": region_rows,
        "anchor_refusals": dict(page.anchor_refusals),
    }


def anchor_repr(anchor) -> tuple:
    """The emitted production Anchor value, verbatim, for the artifact.

    This is a SERIALIZATION of the whole value, not a matching projection: equality is always
    decided on the `Anchor` objects themselves in `build_page_frame`.
    """
    return (anchor.page_number, anchor.line_number, anchor.kind, anchor.text, anchor.division)


def _jsonable(obj):
    if isinstance(obj, (list, tuple)):
        return [_jsonable(o) for o in obj]
    return obj


# -------------------------------------------------------------------- document frames


def select_c_frame(
    document_sha256: str, population: str, page_frames: list[dict], max_per_document: int = C_FRAME_MAX_PER_DOCUMENT
) -> list:
    """A27.2/A27.7 -- the plain uniform C-frame draw, after the COMPLETE enumeration.

    P-head documents only. The draw ranks canonical region identities with the frozen
    domain-separated seed, so it is reproducible and independent of listing order.

    NO reroll and NO replacement after inspecting region contents: a selected region stays
    selected even if both architectures drop all of its content. Replacing it would delete
    precisely the shared-failure evidence RQ2 exists to collect, and would make the sample
    a function of the thing being measured.
    """
    if population != P_HEAD:
        return []
    identities = [
        MC.base_stimulus_identity(document_sha256, pf["page_number"], r["region_ordinal"])
        for pf in page_frames
        for r in pf["regions"]
    ]
    return MC.select("cframe-select", identities, max_per_document)


def build_document_frame(
    document_sha256: str, document_id: str, population: str, pages: list[PageInput], region_size: int = REGION_SIZE
) -> dict:
    """The per-document frame object. Frame building only -- no artifact is written here."""
    page_frames = [build_page_frame(p, region_size) for p in pages]

    selected = select_c_frame(document_sha256, population, page_frames)
    chosen = {(ident[2], ident[3]) for ident in selected}  # (page_number, region_ordinal)
    for pf in page_frames:
        for r in pf["regions"]:
            if (pf["page_number"], r["region_ordinal"]) in chosen:
                r["c_frame"] = True

    d_census = [
        {"page_number": pf["page_number"], "region_ordinal": r["region_ordinal"], "d_reasons": r["d_reasons"]}
        for pf in page_frames
        for r in pf["regions"]
        if r["d_frame"]
    ]
    all_regions = [r for pf in page_frames for r in pf["regions"]]
    all_lines = [ln for pf in page_frames for ln in pf["neutral_lines"]]
    refusals = Counter()
    for pf in page_frames:
        refusals.update(pf["anchor_refusals"])

    return {
        "document": document_id,
        "document_sha256": document_sha256,
        "population": population,
        "region_size": region_size,
        "pages": page_frames,
        "counts": {
            "pages": len(page_frames),
            "neutral_lines": len(all_lines),
            "regions": len(all_regions),
            "short_trailing_regions": sum(1 for r in all_regions if r["short_trailing"]),
            "c_frame_selected": sum(1 for r in all_regions if r["c_frame"]),
            "d_frame_census": len(d_census),
            "d_text": sum(1 for r in all_regions if TEXT_DISCORDANCE in r["d_reasons"]),
            "d_segmentation": sum(1 for r in all_regions if SEGMENTATION_DISCORDANCE in r["d_reasons"]),
            "d_anchor": sum(1 for r in all_regions if ANCHOR_DISCORDANCE in r["d_reasons"]),
            "both_absent_lines": sum(1 for ln in all_lines if not ln["in_m0_risk_set"]),
            "m0_risk_set_lines": sum(1 for ln in all_lines if ln["in_m0_risk_set"]),
        },
        # the COMPLETE census, never sampled and never truncated to the A10 budget
        "d_frame_census": d_census,
        "d_frame_truncated": False,
        "anchor_refusals": dict(refusals),
    }


# ------------------------------------------------------- extraction from a real document


def page_inputs_from_arms(h_pages: list[dict], x_pages: list[dict], region_size: int = REGION_SIZE):
    """Build `PageInput`s from the two runners' returned per-page dicts.

    Each arm's production anchors are derived from ITS OWN returned production `Page`, exactly
    as `x14` does -- no runner needs an `anchors` key, and neither arm has a private path.

    Returns (page_inputs, skeleton_skew_pages). A19 requires ONE skeleton: if the arms
    disagreed the two frames would not be the same frame, so the caller must treat any skew
    as fatal rather than averaging over it.
    """
    x_by_page = {d["page_number"]: d for d in x_pages}
    inputs, skew = [], []
    for h in h_pages:
        pno = h["page_number"]
        x = x_by_page.get(pno)
        if x is None:
            continue
        if [(ln.key, sorted(ln.gids)) for ln in h["neutral"]] != [(ln.key, sorted(ln.gids)) for ln in x["neutral"]]:
            skew.append(pno)
            continue
        neutral = h["neutral"]
        h_by_region, h_ref = place_arm_anchors(
            extract_anchors([h["page"]]), h["page"].print_lines, h["emitted"], neutral, region_size
        )
        x_by_region, x_ref = place_arm_anchors(
            extract_anchors([x["page"]]), x["page"].print_lines, x["emitted"], neutral, region_size
        )
        refusals = Counter()
        refusals.update(h_ref)
        refusals.update(x_ref)
        inputs.append(
            PageInput(
                page_number=pno,
                neutral=neutral,
                h_emitted=h["emitted"],
                x_emitted=x["emitted"],
                h_anchors_by_region=h_by_region,
                x_anchors_by_region=x_by_region,
                anchor_refusals=refusals,
            )
        )
    return inputs, skew
