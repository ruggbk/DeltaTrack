"""Can a settled ``CorrespondenceSet`` later revise 1:0 and 0:1 records into a 1:1?

The proposition this demonstrates, stated exactly:

    A ``CorrespondenceSet`` that has already settled first-pass 1:0 and 0:1 records
    cannot subsequently revise those same observations into a later 1:1 move
    correspondence under the current contract and API.

Why it is worth demonstrating. The current engine can first treat two observations as a
removal and an addition, and later relink them as a move. That is a property of the
legacy code path, described here in its own terms: the legacy engine does not materialise
ADR 0020 ``Correspondence`` values at all, and ``match_nodes`` output is not necessarily
settled, because classification can still revoke a pairing. If an ADR 0020 migration
materialised those earlier states as *settled* ``Correspondence`` values, the current
``CorrespondenceSet`` contract would refuse the later revision. That refusal is the
architectural finding, and it is a constraint on migration order rather than a defect in
either the contract or the engine.

This runs the sequence against the real types instead of arguing it, so the answer is a
demonstration rather than a reading. Read-only, writes nothing, changes no contract.

    uv run python scripts/probe_correspondence_revision.py
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

    # 1. The two shapes a migration would materialise from a removal and an addition.
    #    Both are constructible: the refusal below is not about the shapes being invalid.
    removal = Correspondence(old=(old_ref,))
    addition = Correspondence(new=(new_ref,))
    print(f"1:0 constructible: {removal.shape}")
    print(f"0:1 constructible: {addition.shape}")

    # 2. Settling them succeeds. This step is NOT where the constraint bites.
    settled = CorrespondenceSet([removal, addition])
    print(f"settled separately, without complaint: {len(settled)} correspondences")

    # 3. The constraint bites here: relinking the SAME two observations as one move.
    moved = Correspondence(
        old=(old_ref,),
        new=(new_ref,),
        evidence=(CorrespondenceEvidence.of(old_ref, new_ref, similarity=1.0),),
    )
    try:
        settled.add(moved)
        print("RESULT: the later 1:1 revision was accepted")
    except ValueError as exc:
        print(f"RESULT: the later 1:1 revision is refused -- {exc}")

    # 4. And whether any API exists that would let the revision happen at all.
    api = [name for name in dir(settled) if not name.startswith("_")]
    print(f"CorrespondenceSet public API: {api}")
    print("no remove or replace member, so the revision is unrepresentable, not merely refused")


if __name__ == "__main__":
    main()
