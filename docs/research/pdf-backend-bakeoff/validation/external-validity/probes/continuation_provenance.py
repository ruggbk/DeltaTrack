"""continuation_provenance -- A47. The single owner of the post-boundary continuation facts.

WHY THIS EXISTS. The inaugural execution crossed its one-way boundary at 89360b30 on a branch
that was archived and deleted. Nothing on `develop` records that, so every freeze invariant
reads green over a population that has already been measured end to end, and
`x04 --authorize-execution` would happily write a NEW immutable marker attesting that no
confirmatory H/X extraction had ever run on these 17 members. That statement is false.

THE INVARIANT THIS MODULE EXISTS TO PRESERVE:

    Once this frozen population has crossed its execution boundary, branch deletion,
    repository cleanup, external archival, rebasing, cherry-picking, or the absence of the
    original marker from the current branch must NEVER make the population appear pristine
    again.

Exposure leaves NO repository trace, which is the whole problem. The PDFs are byte-identical
afterwards (F2 passes BECAUSE Run 1 did not modify them), membership is untouched, and the
score artifact was never reached, so F5 passes too. There is no git fact to derive this from:
the boundary commit is not even a reachable object here. So the fact is recorded as an
ATTESTED HISTORICAL FACT in a committed artifact, corroborated by an external archive hash,
and this module is the only thing that reads it.

DELIBERATELY NOT A SECOND BOUNDARY. This module does not authorize anything and never writes
an execution marker. It reports that a boundary was ALREADY crossed, so a second pristine one
cannot be created for the same population.

SCOPED TO THE POPULATION, NOT THE BRANCH. The record names the population freeze commit and
the membership blob. If a genuinely new study freezes a new population, the record does not
match it and the continuation status does not leak into it.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
CONTINUATION = EV / "results" / "CONTINUATION.json"

SCHEMA = "continuation/1"

# The section 4.7 status carried by every result VALUE-DEPENDENT on the A45 post-boundary
# repair. Enabled-by is not value-dependent: without A45 the scorer cannot run at all, so
# treating availability as dependence would re-label every result and destroy the distinction
# the deviation register exists to record.
NON_CONFIRMATORY = "NON-CONFIRMATORY (PRE-REGISTRATION 4.7 -- A45 post-boundary deviation)"

CONTINUATION_RECORD_MISSING = "CONTINUATION_RECORD_MISSING"
CONTINUATION_RECORD_MALFORMED = "CONTINUATION_RECORD_MALFORMED"


class ContinuationError(RuntimeError):
    def __init__(self, code: str, detail: dict | None = None):
        super().__init__(f"{code}: {detail or {}}")
        self.code, self.detail = code, detail or {}


def load(path: Path | None = None) -> dict:
    """The continuation record, or raise. Never silently defaults to 'pristine'.

    A missing record must be an ERROR rather than an empty dict. Defaulting to "no prior
    execution" is precisely the failure this module exists to prevent: it would restore the
    pristine reading by accident the moment the file went missing.
    """
    p = Path(path) if path else CONTINUATION
    if not p.exists():
        raise ContinuationError(CONTINUATION_RECORD_MISSING, {"path": str(p)})
    try:
        rec = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ContinuationError(CONTINUATION_RECORD_MALFORMED, {"error": str(exc)}) from exc
    if rec.get("schema") != SCHEMA:
        raise ContinuationError(CONTINUATION_RECORD_MALFORMED, {"schema": rec.get("schema")})
    for key in ("population", "population_status", "prior_execution", "a45", "toolchain"):
        if key not in rec:
            raise ContinuationError(CONTINUATION_RECORD_MALFORMED, {"missing": key})
    return rec


def describes_population(rec: dict, population_freeze_commit: str, membership_blob: str) -> bool:
    """Is this record about THE population currently frozen?

    Both are required. The freeze commit alone would let a re-selected membership at the same
    commit inherit an exposure it never had; the blob alone would not survive a legitimate
    re-freeze of the identical bytes.
    """
    pop = rec.get("population", {})
    return (
        pop.get("population_freeze_commit") == population_freeze_commit
        and pop.get("membership_blob") == membership_blob
    )


def is_exposed(rec: dict) -> bool:
    """Has this population already crossed an execution boundary?"""
    return rec.get("population_status") == "EXPOSED"


def prior_boundary(rec: dict) -> str:
    return rec.get("prior_execution", {}).get("boundary_commit", "")


def exposure_summary(rec: dict) -> str:
    prior = rec.get("prior_execution", {})
    vis = prior.get("visible_results", {})
    return (
        f"Run {prior.get('run')} boundary {prior_boundary(rec)[:8]}; "
        f"H/X extraction on {prior.get('members_extracted')} members / {prior.get('pages_extracted')} pages; "
        f"visible: D census {vis.get('d_frame_census_regions')}, "
        f"S1 {vis.get('s1_documents_firing')}/{vis.get('s1_documents_total')}, "
        f"P-head {vis.get('p_head_documents')} docs / {vis.get('p_head_pages')} pages"
    )


def a45_status(rec: dict) -> str:
    """The 4.7 status for results VALUE-DEPENDENT on A45."""
    return rec.get("a45", {}).get("confirmatory_status", NON_CONFIRMATORY)


def continuation_claim(rec: dict) -> dict:
    """What a continuation may and may not be called."""
    return {
        "population_status": rec.get("population_status"),
        "claim": rec.get("continuation_claim"),
        "prohibited_claim": rec.get("prohibited_claim"),
        "prior_boundary": prior_boundary(rec),
        "ruling": rec.get("ruling"),
        "ruling_document": rec.get("ruling_document"),
    }


# ------------------------------------------------------------------ toolchain (A47.9)


def expected_toolchain(rec: dict) -> dict:
    return rec.get("toolchain", {})


def observed_toolchain() -> dict:
    """Live versions of the result-bearing dependencies.

    Reported rather than imported eagerly: a missing package is a DRIFT observation, not an
    import crash inside a gate.
    """
    import importlib.metadata as md
    import sys

    # DISTRIBUTION METADATA, not a module attribute. Attribute names differ per package and
    # drift between releases: `pypdfium2` exposes neither `__version__` nor `V_PYPDFIUM2` at
    # top level, so an attribute probe silently returns "" and the gate then reports drift
    # FOREVER, against every version including the correct one. A check that can never pass
    # is as useless as one that can never fail.
    out = {"python": ".".join(str(p) for p in sys.version_info[:3])}
    for dist in ("pypdfium2", "pymupdf"):
        try:
            out[dist] = md.version(dist)
        except Exception as exc:  # noqa: BLE001 -- absence is an observation, not a crash
            out[dist] = f"ABSENT ({type(exc).__name__})"
    return out


def toolchain_drift(rec: dict, observed: dict | None = None) -> list[str]:
    """Names of result-bearing dependencies whose live version differs from Run 1's.

    Only the three the reproducibility claim is scoped to. This is drift DETECTION for a
    continuation of a specific frozen run, not general environment reproducibility work.
    """
    want, have = expected_toolchain(rec), observed if observed is not None else observed_toolchain()
    drift = []
    for name in ("python", "pypdfium2", "pymupdf"):
        expected = want.get(name)
        if expected and have.get(name) != expected:
            drift.append(f"{name}: expected {expected}, observed {have.get(name) or 'UNKNOWN'}")
    return drift
