"""The frozen Pass 2 annotation schema, and the invariant that makes candidate recall computable.

WHY A SCHEMA BEFORE ANY LABELS EXIST. The protocol promises five outputs from one dataset:
candidate recall, ranking accuracy, assignment accuracy, final diff correctness, and challenge-set
failure rates. Discovering after ~160 human annotations that a field needed for one of them was
never collected is the expensive failure, and it is invisible until you try to compute the metric.
So the schema is fixed first and an evaluator is written against it first (`eval_pass2.py`), on a
synthetic fixture, before a human rules anything.

THE INVARIANT, and how it is enforced rather than asserted:

    Candidate generators may help a human FIND a counterpart. They may not define whether one
    EXISTS.

That is not enforceable by good intentions, because the natural annotation flow -- show ~8
retrieved candidates, ask "which of these, or none?" -- makes "not retrieved" and "does not exist"
the same observation. An anchor whose true counterpart was missed by every retriever is recorded
as NONE, and candidate recall computed from that dataset is 100% by construction.

The schema separates the two by recording, per anchor, HOW the truth was established
(`truth.oracle`) and, per counterpart, HOW it was found (`found_via`). `eval_pass2.py` then
REFUSES to compute candidate recall over anchors whose oracle is `suggested-list`, because for
those anchors the candidate set defined the answer. The refusal is the enforcement: a dataset
labeled entirely through the suggestion list yields a candidate-recall denominator of zero and
says so, instead of yielding 100%.

THE ORACLES, cheapest first. Each is independent of retrieval in a different way; a study picks
per stratum, and the field records which was used so the population is never assumed.

  suggested-list      The human saw only the retrieved candidates. Sufficient for ranking,
                      assignment, and diff correctness. NOT ground truth for existence -- carries
                      no information about counterparts no retriever proposed.
  region-exhaustive   The human reviewed EVERY provision in a bounded structural region of the new
                      version (one account, one subcommittee title, one subtree), retrieved or
                      not. Truth is complete WITHIN that region, so "none" means none-in-region.
                      This is the cheap oracle, and the one the revised design uses by default:
                      the regions are small, and a counterpart outside its own account/title is
                      rare enough to be a separately recorded exception rather than the common
                      case the sampling has to cover.
  document-search     The human searched the whole new version by their own means (text search,
                      table of contents) with no region bound. Most expensive; reserved for
                      anchors where `region-exhaustive` returned none and the reviewer suspects a
                      cross-region move.

`region_id` is REQUIRED when the oracle is `region-exhaustive`, because "none" is only
interpretable against a stated region. An anchor labeled none-in-region and later found to
correspond outside it is not a labeling error; it is a `region-escape`, and it is recorded as one.

WHAT IS DELIBERATELY NOT HERE. No score fields on the human-facing record: measures stay in the
`system` block, which the labeling UI never renders (protocol §5's blindness guarantee, already
implemented and tested). No `many-to-many` relation -- it is not evidenced in this corpus and
adding it speculatively would invite its use as a dustbin.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "pass2-anchor-v1"

RELATIONS = ("one-to-one", "one-to-many", "many-to-one", "none", "uncertain")
ORACLES = ("suggested-list", "region-exhaustive", "document-search")
RETRIEVERS = ("structural-path", "word-overlap", "containment")
CHANGE_TYPES = ("modified", "moved", "removed", "unchanged")

#: Oracles under which "no counterpart" is a statement about the LEGISLATION rather than about
#: what a retriever happened to return. Only these anchors can enter a candidate-recall
#: denominator; `eval_pass2` enforces it.
INDEPENDENT_ORACLES = ("region-exhaustive", "document-search")

#: Provenance fields every observation carries, so a parser or corpus change re-quarantines the
#: OBSERVATION without touching the human judgment. The 2026-08 review found the existing answer
#: key carried none of these: three of its twelve pairs stopped resolving and nothing noticed,
#: and the cause (parser vs source vs judgment) could only be established by a separate
#: experiment. Each field pins one link in the chain
#: source legislation -> parser representation -> research observation -> human label.
PROVENANCE_FIELDS = (
    "bill",
    "version",
    "source_sha256",  # the XML bytes the observation was derived from
    "parser_commit",  # the engine commit that produced the representation
    "schema_version",  # this file's SCHEMA_VERSION
    "match_path",  # the structural locator, which may legitimately drift
    "text_sha256",  # the normalized body, which may not, silently
)


class SchemaError(ValueError):
    """A record that cannot support the metrics it would be counted in."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SchemaError(msg)


def validate_node_ref(ref: dict[str, Any], where: str) -> None:
    for f in ("bill", "version", "match_path", "text_sha256", "source_sha256", "parser_commit"):
        _require(f in ref, f"{where}: node ref missing provenance field {f!r}")
    _require(isinstance(ref["match_path"], list), f"{where}: match_path must be a list")
    _require(len(ref["text_sha256"]) == 64, f"{where}: text_sha256 must be a sha256 hex digest")


def validate_record(rec: dict[str, Any]) -> None:
    """Raise SchemaError unless this anchor record can support every metric it may enter."""
    aid = rec.get("anchor_id", "<no anchor_id>")
    _require(bool(rec.get("anchor_id")), "record has no anchor_id")
    _require(rec.get("schema_version") == SCHEMA_VERSION, f"{aid}: schema_version must be {SCHEMA_VERSION!r}")
    _require("anchor" in rec, f"{aid}: no anchor node")
    validate_node_ref(rec["anchor"], aid)

    truth = rec.get("truth")
    _require(isinstance(truth, dict), f"{aid}: no truth block")
    _require(truth.get("relation") in RELATIONS, f"{aid}: relation must be one of {RELATIONS}")
    _require(truth.get("oracle") in ORACLES, f"{aid}: oracle must be one of {ORACLES}")
    _require(bool(truth.get("adjudicator")), f"{aid}: truth has no adjudicator")

    if truth["oracle"] == "region-exhaustive":
        _require(
            bool(truth.get("region_id")),
            f"{aid}: region-exhaustive truth must name the region it is exhaustive over -- "
            "'none' is uninterpretable without it",
        )

    counterparts = truth.get("counterparts", [])
    _require(isinstance(counterparts, list), f"{aid}: counterparts must be a list")
    for cp in counterparts:
        validate_node_ref(cp, aid)
        _require(
            cp.get("found_via") in ("suggested", "browse", "region-sweep"),
            f"{aid}: every counterpart must record how it was FOUND; without it a counterpart the "
            "retrievers missed is indistinguishable from one they proposed, and candidate recall "
            "cannot be computed",
        )

    rel = truth["relation"]
    if rel == "none":
        _require(not counterparts, f"{aid}: relation 'none' with counterparts listed")
    elif rel == "one-to-one":
        _require(len(counterparts) == 1, f"{aid}: relation 'one-to-one' needs exactly 1 counterpart")
    elif rel in ("one-to-many", "many-to-one"):
        _require(len(counterparts) >= 1, f"{aid}: relation {rel!r} needs at least 1 counterpart")

    cands = rec.get("candidates", [])
    _require(isinstance(cands, list), f"{aid}: candidates must be a list")
    for i, c in enumerate(cands):
        validate_node_ref(c, aid)
        rs = c.get("retrievers", [])
        _require(
            isinstance(rs, list) and rs and all(r in RETRIEVERS for r in rs),
            f"{aid}: candidate {i} must record which retriever(s) surfaced it",
        )
        _require(isinstance(c.get("rank"), int), f"{aid}: candidate {i} has no integer rank")

    sysb = rec.get("system")
    _require(isinstance(sysb, dict), f"{aid}: no system block (what the matcher actually did)")
    _require(
        sysb.get("change_type") in CHANGE_TYPES,
        f"{aid}: system.change_type must be one of {CHANGE_TYPES}",
    )
    _require(isinstance(sysb.get("assigned"), list), f"{aid}: system.assigned must be a list")

    _require(
        truth.get("change_type") in CHANGE_TYPES,
        f"{aid}: truth.change_type must be one of {CHANGE_TYPES} -- final diff correctness is a "
        "comparison against what the staffer SHOULD have seen, so truth carries it too",
    )


def validate_dataset(records: list[dict[str, Any]]) -> None:
    seen = set()
    for rec in records:
        validate_record(rec)
        _require(rec["anchor_id"] not in seen, f"duplicate anchor_id {rec['anchor_id']!r}")
        seen.add(rec["anchor_id"])
