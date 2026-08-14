"""What a PDF ``moved`` currently means, measured pair by pair (slice 6, phase A).

Runs the **current** production stages — ``pdf_round1_with_stage_outputs`` through
``settle_pdf_correspondences`` — and records, for every settled binary correspondence,
the facts that decide moved-vs-modified: the round that selected it, the retriever
invocations that admitted it, both anchors, both page ranges, whether the texts are
identical, and the exact ``word_overlap`` the evidence carries.

**The classification rule is transcribed here as literals, not imported**, and the
resulting sequence is asserted equal to ``diff_pdfs``' own hunk stream on every pair
before a single count is reported. Importing ``MOVE_THRESHOLD`` or calling
``_classified_pdf`` would make the census agree with production by construction, which is
the failure mode this thread has shipped twice (record §"never build a control's
expectation from the thing it checks"). The transcription is an independent statement of
the rule; the equality assertion is what makes it evidence.

Partitions, named as the slice-6 brief names them:

    A  round-2 assignment moves
    B  round-1 moves whose two texts are identical (anchor renamed, body untouched)
    C  round-1 moves whose texts differ and whose overlap clears the move cutoff
    D  round-1 *modified* rows whose anchors differ but whose overlap does not clear it
       -- the negative population, without which the current rule validates itself
    E  round-1 rows whose anchors are equal (moved is unreachable by anchor equality)
    F  round-1 rows where an anchor is absent on one or both sides (moved is unreachable
       because the rule requires both)

    uv run python docs/research/pdf-matching-convergence/probes/pdf_move_semantics_census.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import accepted_pdf_pairs, pages_for  # noqa: E402

from deltatrack.diff_pdf import (  # noqa: E402
    PdfObservationRegistry,
    _flatten,
    _group_into_blocks,
    _with_front_matter,
    assign_pdf_moves,
    diff_pdfs,
    extract_anchors,
    pdf_move_evidence,
    pdf_round1_with_stage_outputs,
    pdf_unmatched_population,
    retrieve_pdf_move_candidates,
    settle_pdf_correspondences,
)

# Transcribed from `similarity.py`, deliberately NOT imported. If the constants move, this
# probe must go red rather than follow them: it is the independent statement of the rule.
_MOVE_CUTOFF = 0.6
_SIMILARITY_CUTOFF = 0.4
_ROUND_1 = 1
_ROUND_2 = 2
_OVERLAP = "word_overlap"

_PREVIEW = 160


def _anchor_text(block) -> str | None:
    return block.anchor.text if block.anchor else None


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat[:_PREVIEW] + ("..." if len(flat) > _PREVIEW else "")


def _classify(row: dict) -> str | None:
    """The current rule, restated. Returns the change_type, or None where PDF emits nothing."""
    if row["old_ordinal"] is None:
        return "added"
    if row["new_ordinal"] is None:
        return "removed"
    if row["round"] == _ROUND_2:
        return "moved"
    anchors_differ = (
        row["old_anchor"] is not None and row["new_anchor"] is not None and row["old_anchor"] != row["new_anchor"]
    )
    if row["text_identical"] and not anchors_differ:
        return None
    if anchors_differ and row["word_overlap"] >= _MOVE_CUTOFF:
        return "moved"
    return "modified"


def _partition(row: dict) -> str:
    if row["change_type"] not in {"moved", "modified"}:
        return "-"
    if row["round"] == _ROUND_2:
        return "A"
    if row["old_anchor"] is None or row["new_anchor"] is None:
        return "F"
    if row["old_anchor"] == row["new_anchor"]:
        return "E"
    if row["change_type"] == "modified":
        return "D"
    return "B" if row["text_identical"] else "C"


def census(v1_pages, v2_pages) -> tuple[list[dict], list]:
    """Every settled correspondence as a row, plus the hunk sequence the rows imply."""
    v1_indexed, v2_indexed = _flatten(v1_pages), _flatten(v2_pages)
    v1_anchors, v2_anchors = extract_anchors(v1_pages), extract_anchors(v2_pages)
    v1_blocks = _group_into_blocks(v1_indexed, v1_anchors)
    v2_blocks = _group_into_blocks(v2_indexed, v2_anchors)
    _with_front_matter(v1_blocks, v1_anchors)
    _with_front_matter(v2_blocks, v2_anchors)

    registry = PdfObservationRegistry(v1_blocks, v2_blocks)
    round1 = pdf_round1_with_stage_outputs(
        v1_blocks, v2_blocks, registry, threshold=_SIMILARITY_CUTOFF, move_threshold=_MOVE_CUTOFF
    )
    pairings = list(round1.pairings)
    population = pdf_unmatched_population(pairings, registry)
    candidates = retrieve_pdf_move_candidates(population, bound=_MOVE_CUTOFF)
    evidence = pdf_move_evidence(candidates)
    moves = assign_pdf_moves(population, evidence, threshold=_MOVE_CUTOFF)
    settled = settle_pdf_correspondences(
        pairings,
        registry,
        moves,
        round1_evidence=round1.evidence,
        round1_move_bases=round1.move_bases,
    )

    rows: list[dict] = []
    for item in sorted(settled, key=lambda s: s.position):
        c = item.correspondence
        old_ref = c.old[0] if c.old else None
        new_ref = c.new[0] if c.new else None
        old_block = registry.block(old_ref) if old_ref else None
        new_block = registry.block(new_ref) if new_ref else None
        overlap = None
        invocations: list[str] = []
        if c.evidence:
            value = c.evidence[0].get(_OVERLAP)
            overlap = float(value) if isinstance(value, float) else None
        if old_ref is not None and new_ref is not None:
            source = candidates if item.round == _ROUND_2 else round1.candidates
            candidate = source.candidate_for(old_ref, new_ref)
            if candidate is not None:
                invocations = sorted(p.invocation.retriever for p in candidate.proposals)
        row = {
            "old_ordinal": old_ref.ordinal if old_ref else None,
            "new_ordinal": new_ref.ordinal if new_ref else None,
            "round": item.round,
            "position": item.position,
            "invocations": invocations,
            "old_anchor": _anchor_text(old_block) if old_block else None,
            "new_anchor": _anchor_text(new_block) if new_block else None,
            "old_range": list(old_block.page_range) if old_block and old_block.page_range else None,
            "new_range": list(new_block.page_range) if new_block and new_block.page_range else None,
            "text_identical": (old_block.text == new_block.text) if (old_block and new_block) else False,
            "word_overlap": overlap,
            "old_words": len(old_block.text.split()) if old_block else 0,
            "new_words": len(new_block.text.split()) if new_block else 0,
            "old_preview": _preview(old_block.text) if old_block else "",
            "new_preview": _preview(new_block.text) if new_block else "",
        }
        row["change_type"] = _classify(row)
        row["partition"] = _partition(row)
        rows.append(row)
    implied = [
        (r["change_type"], r["old_anchor"], r["new_anchor"], r["old_range"], r["new_range"])
        for r in rows
        if r["change_type"] is not None
    ]
    return rows, implied


def main() -> None:
    pairs = accepted_pdf_pairs()
    print(f"{len(pairs)} production-accepted adjacent PDF pairs", file=sys.stderr, flush=True)
    all_rows: list[dict] = []
    for n, (bill, old, new) in enumerate(pairs, 1):
        print(f"[{n}/{len(pairs)}] {bill} {old.stem} -> {new.stem}", file=sys.stderr, flush=True)
        v1_pages, v2_pages = pages_for(old), pages_for(new)
        reference = diff_pdfs(v1_pages, v2_pages)
        rows, implied = census(v1_pages, v2_pages)
        produced = [
            (
                h.change_type,
                h.v1_anchor.text if h.v1_anchor else None,
                h.v2_anchor.text if h.v2_anchor else None,
                list(h.v1_range) if h.v1_range else None,
                list(h.v2_range) if h.v2_range else None,
            )
            for h in reference.hunks
        ]
        assert implied == produced, (
            f"the transcribed classification diverged from diff_pdfs on {bill} {old.stem}->{new.stem}; "
            "every partition below would describe a rule that is not the one shipping"
        )
        for row in rows:
            row["bill"] = bill
            row["pair"] = f"{old.stem}->{new.stem}"
        all_rows.extend(rows)

    described = [r for r in all_rows if r["change_type"] in {"moved", "modified"}]
    counts = Counter(r["partition"] for r in described)
    shape = Counter(str(r["change_type"]) for r in all_rows)
    moved = [r for r in described if r["change_type"] == "moved"]
    print("\n=== the moved population, by why it is moved ===")
    print(f"  A  round-2 assignment moves                    {counts['A']}")
    print(f"  B  round-1 identical text, anchor renamed      {counts['B']}")
    print(f"  C  round-1 differing text, overlap >= 0.6      {counts['C']}")
    print(f"     total moved                                 {len(moved)}")
    print("\n=== the counterpopulation ===")
    print(f"  D  round-1 anchors differ, overlap < 0.6       {counts['D']}  (classified modified)")
    print(f"  E  round-1 anchors equal                       {counts['E']}  (moved unreachable)")
    print(f"  F  round-1 an anchor absent                    {counts['F']}  (moved unreachable)")
    print("\n=== the whole settled population, by emitted change_type ===")
    for change_type, count in sorted(shape.items()):
        print(f"  {change_type:10s} {count}")

    # Only the DESCRIBED rows are written. The added/removed/suppressed rows are 7,955 of the
    # 8,840 settled correspondences and carry two text previews each; keeping them would make a
    # multi-megabyte artifact out of rows no consumer of this file reads. Their counts are
    # recorded so the artifact still says what population it was cut from. Partition E (719
    # same-anchor rows) is reduced to what the report reads from it -- an overlap distribution
    # -- because moved is unreachable there by anchor equality and no row of it is adjudicated.
    # This probe is deterministic and committed, so full detail is one command away.
    trimmed = []
    for row in described:
        if row["partition"] == "E":
            trimmed.append({k: row[k] for k in ("bill", "pair", "partition", "change_type", "word_overlap")})
        else:
            trimmed.append(dict(row))
    out = Path(__file__).resolve().parent.parent / "results" / "move-semantics-census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"rows": trimmed, "partition_counts": dict(counts), "settled_population": dict(shape)},
            indent=1,
        )
        + "\n"
    )
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
