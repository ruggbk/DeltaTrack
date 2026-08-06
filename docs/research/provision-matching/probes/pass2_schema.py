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

SCHEMA_VERSION = "pass2-anchor-v2"

RELATIONS = ("one-to-one", "one-to-many", "many-to-one", "none", "uncertain")
ORACLES = ("suggested-list", "region-exhaustive", "document-search")
RETRIEVERS = ("structural-path", "word-overlap", "containment")
CHANGE_TYPES = ("modified", "moved", "removed", "unchanged")

# ---------------------------------------------------------------------------------------------
# v2: what an oracle can and cannot establish
# ---------------------------------------------------------------------------------------------
# v1 had a single flag, INDEPENDENT_ORACLES = (region-exhaustive, document-search), used only to
# keep suggestion-list anchors out of candidate recall. Round 3 showed that was two errors in one
# constant.
#
# First, it lumped `region-exhaustive` in with `document-search`, so a "none" established by
# sweeping ONE region was treated as a statement about the whole document. A counterpart that moved
# to another title is exactly the hard cross-region recall failure the study exists to measure, and
# under v1 it would have been recorded as truth that no counterpart exists.
#
# Second, it was applied to ONE metric. Ranking, assignment, diff correctness and the challenge
# rates all consumed suggestion-list records unfiltered, and diff correctness is the worst case:
# a reviewer who sees no counterpart in an incomplete list yields truth `removed`, which then
# scores the matcher's `removed` as correct. Matcher-conditioned truth, one step downstream.
#
# The fix is to stop reasoning about oracles as a rank ordering and state what each one PROVES.
# Three distinct propositions matter, and they are not nested by cost:
#
#   affirmed-positive        "this specific node IS a counterpart of the anchor"
#                            A positive claim about a pair the human actually looked at. Any oracle
#                            can support it, PROVIDED the human was asked a per-candidate binary
#                            question rather than "which of these 8 is it" -- a forced choice over
#                            an incomplete list manufactures a positive by construction. The
#                            protocol's card UI is already per-candidate binary; `judgment_mode`
#                            records it so the guarantee is data rather than a convention.
#   complete-within-region   "no counterpart exists in region R" -- and nothing outside R.
#   complete-in-document     "the counterpart set is exactly this, document-wide."
#
# Note there is no path from `complete-within-region` to `complete-in-document` by adding regions,
# because the sweep bound is per anchor. Escalation is the only route, which is why `oracles` is a
# LIST of the steps actually performed rather than a single label.
ORACLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "suggested-list": frozenset({"affirmed-positive"}),
    "region-exhaustive": frozenset({"affirmed-positive", "complete-within-region"}),
    "document-search": frozenset({"affirmed-positive", "complete-within-region", "complete-in-document"}),
}

#: How the human was asked. A forced choice among a candidate list cannot support
#: `affirmed-positive`, because "the best of these eight" is not "the same provision".
JUDGMENT_MODES = ("per-candidate-binary", "forced-choice")

#: What each metric's arithmetic ASSUMES about the truth record it consumes. Data, not prose, so
#: `eval_pass2` can enforce it and a test can prove the enforcement fires. Deriving these is the
#: whole of round 3's §2: for each metric, name the proposition its denominator or its correctness
#: test silently relies on, then admit only oracles that can establish it.
METRIC_TRUTH_REQUIREMENTS: dict[str, dict[str, str]] = {
    "candidate_recall": {
        "proposition": "the complete set of true counterparts is known, document-wide",
        "requires": "complete-in-document",
        "why": (
            "The denominator is 'true counterparts that exist'. A counterpart the human never had "
            "the opportunity to find is missing from it, and the anchors where that happens are "
            "exactly the anchors retrieval failed on -- so an incomplete oracle removes the hardest "
            "cases from the denominator and inflates recall. Note the bias is by SELECTION, not by "
            "a wrong label: a false NONE does not enter as a miss, it vanishes from the population."
        ),
    },
    "ranking": {
        "proposition": "this specific node is a true counterpart of the anchor",
        "requires": "affirmed-positive",
        "why": (
            "Ranking asks where the true counterpart sat in the ordering. That needs the identity "
            "of one affirmed counterpart, not the completeness of the set -- a second counterpart "
            "elsewhere in the document does not change where THIS one ranked. So region-local and "
            "even suggestion-list positives are admissible here, and this is the one metric where "
            "the cheap oracle is genuinely sufficient."
        ),
    },
    "assignment": {
        "proposition": "the complete set of correspondences competing for a node is known",
        "requires": "complete-in-document",
        "why": (
            "A collision group is only correct if every anchor claiming the contested node has been "
            "found. An unfound competitor makes a wrong assignment look right, and competitors are "
            "not confined to one region."
        ),
    },
    "diff_correctness": {
        "proposition": "the true change type is known, which requires knowing whether ANY counterpart exists",
        "requires": "complete-in-document",
        "why": (
            "`removed` versus `moved` is precisely the question of whether a counterpart exists "
            "somewhere else in the document. Truth built from a bounded search answers a different "
            "question, and answers it in the matcher's favour whenever the matcher also said "
            "`removed`."
        ),
    },
    "failure_modes": {
        "proposition": "depends on the challenge claim: existence claims need a positive, "
        "absence claims need document-wide completeness",
        "requires": "per-stratum",
        "why": (
            "A stratum claiming 'this false keep happens' needs only an affirmed negative pair. A "
            "stratum claiming 'the matcher missed a counterpart that exists' needs completeness. "
            "The stratum declares its own requirement in `challenge_requires`."
        ),
    },
}


def establishes(oracles: list[str], judgment_mode: str, proposition: str) -> bool:
    """Can a record labeled under these oracles, asked this way, support this proposition?

    The judgment mode gates EVERY proposition, not only `affirmed-positive`. The first cut of this
    function gated only positives, on the reasoning that completeness is about search coverage
    rather than about how the question was phrased. A contract test disagreed and it was right:
    every proposition here is built out of per-pair judgments. A counterpart SET is only as sound as
    each member's affirmation, so `complete-in-document` inherits the weakness; and a forced choice
    that offers "none of these" as one option among eight manufactures the false NONE directly,
    which is the failure this whole design exists to prevent.

    So a forced-choice dataset supports nothing. That is the intended severity: the protocol's card
    UI is already per-candidate binary, and this field exists to keep it that way rather than to
    make a weaker mode usable.
    """
    if judgment_mode != "per-candidate-binary":
        return False
    caps: set[str] = set()
    for o in oracles:
        caps |= ORACLE_CAPABILITIES.get(o, frozenset())
    return proposition in caps


#: Retained for readability at call sites; v1's constant, redefined against the capability table so
#: the two cannot drift apart.
INDEPENDENT_ORACLES = tuple(o for o, caps in ORACLE_CAPABILITIES.items() if "complete-in-document" in caps)

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
    "element_id",  # v2: WHICH node this is (see below)
)

# ---------------------------------------------------------------------------------------------
# v2: three different things v1 collapsed into one
# ---------------------------------------------------------------------------------------------
# v1's evaluator joined nodes on `(bill, version, text_sha256)`, reasoning that `match_path` is the
# unstable key this program exists because of. The first half of that was right; the conclusion was
# not, because it assumed body text identifies a node. R9 measured it: **33% of the documents in
# this corpus contain at least one body text shared by two or more provisions** -- 551 distinct
# texts, 1,544 node occurrences, up to 12 copies of one text in one version -- and it reaches every
# version of all four answer-key bills. Appropriations bills are built from repeated boilerplate;
# "No part of any appropriation contained in this Act shall remain available for obligation beyond
# the current fiscal year" is one provision per division.
#
# A content-hash join collapses those into one node, and it fails OPTIMISTICALLY: a candidate-recall
# miss against provision X scores as a hit whenever any boilerplate twin Y is in the candidate set.
#
# So three concepts, kept apart:
#
#   OBSERVATION IDENTITY   which parsed node this is, in one frozen document under one parser.
#                          `(source_sha256, parser_commit, element_id)`. `element_id` is emitted by
#                          the parser and is unique and non-empty on all 106 documents measured
#                          (R9 §4) -- preferred over a traversal ordinal because an ordinal shifts
#                          when anything earlier in the document changes, while an element id does
#                          not. It is REQUIRED to be unique; `validate_dataset` fails loudly rather
#                          than assuming, so a future parser that stops guaranteeing it cannot
#                          silently reintroduce the collapse.
#   CONTENT INTEGRITY      `text_sha256`. Detects representation drift (round 2, §R2-6). Never an
#                          identity: two nodes may legitimately share it.
#   CROSS-VERSION IDENTITY the thing the human is labeling -- "is this the same provision". It is
#                          the OUTPUT of the study and must never be used as an input key.
OBSERVATION_ID_FIELDS = ("source_sha256", "parser_commit", "element_id")


def observation_id(ref: dict[str, Any]) -> tuple:
    """Identity of one parsed node. See OBSERVATION_ID_FIELDS for why it is not the text hash."""
    return tuple(ref[f] for f in OBSERVATION_ID_FIELDS)


class SchemaError(ValueError):
    """A record that cannot support the metrics it would be counted in."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SchemaError(msg)


def validate_node_ref(ref: dict[str, Any], where: str) -> None:
    for f in PROVENANCE_FIELDS:
        if f == "schema_version":
            continue  # carried once per record, not per node
        _require(f in ref, f"{where}: node ref missing provenance field {f!r}")
    _require(isinstance(ref["match_path"], list), f"{where}: match_path must be a list")
    _require(len(ref["text_sha256"]) == 64, f"{where}: text_sha256 must be a sha256 hex digest")
    _require(
        bool(ref["element_id"]),
        f"{where}: node ref has an empty element_id -- without an observation identity, two "
        "provisions sharing boilerplate body text collapse into one node (33% of documents in "
        "this corpus contain such a pair)",
    )


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
    _require(bool(truth.get("adjudicator")), f"{aid}: truth has no adjudicator")

    # v2: `oracles` is a LIST of the search steps actually performed, not one label. A bounded
    # region sweep followed by a document-wide escalation is the intended workflow for negatives,
    # and it is a different epistemic position from either step alone -- one label cannot say so.
    oracles = truth.get("oracles")
    _require(
        isinstance(oracles, list) and oracles and all(o in ORACLES for o in oracles),
        f"{aid}: truth.oracles must be a non-empty list drawn from {ORACLES} (v2 replaced the "
        "single `oracle` field: escalation from a region sweep to a document search is two steps, "
        "and collapsing them loses exactly the distinction between none-in-region and none)",
    )
    _require(
        truth.get("judgment_mode") in JUDGMENT_MODES,
        f"{aid}: truth.judgment_mode must be one of {JUDGMENT_MODES} -- a forced choice among a "
        "candidate list cannot establish that a node IS the counterpart, only that it was the best "
        "of what was shown",
    )

    if "region-exhaustive" in oracles:
        _require(
            bool(truth.get("region_id")),
            f"{aid}: a region-exhaustive sweep must name the region it is exhaustive over -- "
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
    for a in sysb["assigned"]:
        # v2: the system's own output is joined on observation identity like everything else, so it
        # needs the same fields. v1 left these unvalidated, which meant the one side of the join
        # most likely to be machine-generated was the one side nothing checked.
        validate_node_ref(a, f"{aid} system.assigned")

    if rec.get("is_challenge"):
        _require(
            bool(rec.get("stratum")),
            f"{aid}: a challenge record must name its stratum -- a failure rate is meaningless "
            "without the rigged population it was measured in",
        )
        _require(
            rec.get("challenge_requires") in ("affirmed-positive", "complete-in-document"),
            f"{aid}: a challenge record must declare `challenge_requires` -- an existence claim "
            "('this false keep happens') needs only an affirmed positive, an absence claim ('the "
            "matcher missed a counterpart that exists') needs document-wide completeness, and the "
            "evaluator cannot infer which claim a stratum is making",
        )

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
    _require_observation_ids_are_unique(records)


def _require_observation_ids_are_unique(records: list[dict[str, Any]]) -> None:
    """No two DIFFERENT nodes may share an observation id, within one frozen document.

    The whole node-identity design rests on `element_id` being unique per parse. That holds on all
    106 documents measured (R9 §4), but "holds today" is not "is guaranteed", and the failure mode
    if it stops holding is silent: distinct provisions collapse and every metric moves in the
    optimistic direction. So the dataset asserts it rather than assuming it.

    Two references to the SAME node legitimately repeat -- an anchor's counterpart is usually also
    one of its candidates. The violation is one observation id carrying two different `text_sha256`
    values, which can only mean the id is not identifying a node.
    """
    by_id: dict[tuple, set[str]] = {}
    for rec in records:
        refs = [rec["anchor"], *rec["truth"].get("counterparts", []), *rec.get("candidates", [])]
        refs += rec.get("system", {}).get("assigned", [])
        for ref in refs:
            by_id.setdefault(observation_id(ref), set()).add(ref["text_sha256"])
    collisions = {k: v for k, v in by_id.items() if len(v) > 1}
    _require(
        not collisions,
        f"observation id collision: {sorted(str(k) for k in collisions)[:3]} -- one "
        "(source_sha256, parser_commit, element_id) maps to more than one body text, so it is not "
        "identifying a single parsed node and every join in the evaluator is unsound",
    )
