"""Can ``CorrespondenceSet`` hold first-pass results, before the move pass revises them?

The engine settles correspondence in two passes: ``match_nodes`` pairs by path and
similarity, then ``reconcile_moves`` re-links a removal and an addition that are really
one section moved. An ADR 0020 staging that materialises first-pass output as
correspondence therefore has to revise it later.

This runs that sequence against the real contracts instead of reasoning about it, so the
answer is a demonstration rather than a reading. Read-only, writes nothing.

    uv run python scripts/probe_correspondence_completeness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltatrack.matching import (  # noqa: E402
    Correspondence,
    CorrespondenceEvidence,
    CorrespondenceSet,
    ObservationRef,
)


def main() -> None:
    old_ref = ObservationRef(side="old", ordinal=17)
    new_ref = ObservationRef(side="new", ordinal=204)

    # 1. First-pass shapes. match_nodes emits exactly these three.
    removal = Correspondence(old=(old_ref,))
    addition = Correspondence(new=(new_ref,))
    print(f"first-pass 1:0 constructible: {removal.shape}")
    print(f"first-pass 0:1 constructible: {addition.shape}")

    # 2. Settle them, as a stage running before the move pass would have to.
    settled = CorrespondenceSet([removal, addition])
    print(f"settled first-pass correspondences: {len(settled)}")

    # 3. The move pass now finds they are one section moved, and needs a 1:1 over the
    #    same two observations.
    moved = Correspondence(
        old=(old_ref,),
        new=(new_ref,),
        evidence=(CorrespondenceEvidence.of(old_ref, new_ref, similarity=1.0),),
    )
    try:
        settled.add(moved)
        print("RESULT: the move pass could revise settled first-pass correspondence")
    except ValueError as exc:
        print(f"RESULT: refused -- {exc}")

    # 4. And whether any API exists to make the revision possible at all.
    print(f"CorrespondenceSet public API: {[n for n in dir(settled) if not n.startswith('_')]}")


if __name__ == "__main__":
    main()
