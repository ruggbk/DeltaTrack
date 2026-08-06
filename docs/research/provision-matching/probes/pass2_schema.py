"""The frozen Pass 2 annotation schema (v3). ONE authoritative description of the semantics.

WHY A SCHEMA BEFORE ANY LABELS EXIST. The protocol promises five outputs from one dataset:
candidate recall, ranking accuracy, assignment accuracy, final diff correctness, and challenge-set
failure rates. Discovering after ~160 human annotations that a field needed for one of them was
never collected is the expensive failure, and it is invisible until you try to compute the metric.
So the schema is fixed first and an evaluator is written against it first (`eval_pass2.py`), on a
synthetic fixture, before a human rules anything.

THE INVARIANT:

    A method under evaluation may help a human FIND a counterpart. It may never define whether one
    EXISTS, directly or indirectly.

"Indirectly" is where three review rounds have found the failures, each one layer further out:
first the matcher chose the pairs; then the retrievers chose the candidate list; then a bounded
region chose the search area; then -- round 4 -- "the reviewer searched and found nothing" was
being read as "nothing is there". Each fix renamed the dependency rather than removing it. v3
removes it by making completeness a COUNT rather than a promise (see `document-exhaustive`).

NOTE ON THIS DOCSTRING. v2 shipped with prose that still described v1 semantics -- it said
`suggested-list` was "sufficient for ranking, assignment and diff correctness" while the executable
rules refused it for two of those, and described document search as discretionary while the rules
made escalation systematic. Stale explanatory prose preserving a superseded methodology is one of
this programme's own named findings, so: this docstring describes v3 and nothing else. Where an
earlier version differed, the history is in `review-2026-08-methodology.md`, not here.

--------------------------------------------------------------------------------------------------
THE FOUR PROPOSITIONS
--------------------------------------------------------------------------------------------------
Truth records support propositions, not "confidence levels". Four matter, and they are not nested
by cost -- which is why the requirement is per metric rather than one global strictness flag.

  affirmed-positive       "this specific node IS a counterpart of the anchor"
  affirmed-negative       "this specific node is NOT the same provision as the anchor"
                          Pairwise, like the positive. Added in v3: a high-containment false keep
                          can be ruled DIFFERENT without anyone establishing where the anchor's
                          true counterpart is, and that is legitimate, sufficient evidence for a
                          false-keep challenge. v2 forced such strata to pay for exhaustive
                          document review they did not need.
  complete-within-region  "no counterpart exists in region R" -- and nothing about outside R.
  complete-in-document    "the counterpart set is exactly this, across the whole target version."

Both pairwise propositions additionally require a PER-CANDIDATE BINARY question. A forced choice
among a candidate list yields "the best of what I was shown", which the candidate set manufactured.
`judgment_mode` records it and gates every proposition -- a forced-choice dataset supports nothing.

--------------------------------------------------------------------------------------------------
THE THREE ORACLES, and what each may claim
--------------------------------------------------------------------------------------------------
`truth.oracles` is a LIST of the steps actually performed, because escalation is a sequence and one
label cannot express it.

  suggested-list        The reviewer saw only retrieved candidates. Supports pairwise propositions
                        about the pairs shown. Supports NO completeness claim of any kind.

  region-exhaustive     The reviewer adjudicated every provision in one bounded structural region
                        of the target version, retrieved or not. `region_id` is REQUIRED: "none" is
                        uninterpretable without the bound it is none within. A counterpart later
                        found outside that region is a recorded `region-escape`, not a labeling
                        error.

  document-exhaustive   The reviewer adjudicated every provision of the target version that the
                        declared coverage rule admits. Not "searched" -- COVERED, and the record
                        proves it by carrying the SET:

                            truth.coverage = {
                                "rule": "all-nodes-with-body",
                                "target_source_sha256": ..., "target_parser_commit": ...,
                                "eligible_ordinals": [...],   # generated from the frozen parse
                                "reviewed_ordinals": [...],   # what was actually adjudicated
                            }

                        `complete-in-document` is granted only when the two are equal AS SETS.
                        Retrieval, search and structural navigation may order the queue; they may
                        not end it. A reviewer who stops early does not produce a defective record
                        -- they produce one that honestly claims less, and the evaluator refuses it
                        for the metrics that need more.

                        `rule` MUST come from `COVERAGE_RULES`, all measure-independent: a rule that
                        consulted word overlap or containment would let a method under evaluation
                        set its own denominator, one layer out. `all-nodes-with-body` excludes ~8.5%
                        of target nodes, and R9 §5 measures that every one of them is a structural
                        CONTAINER whose text lives in a descendant the rule does admit, with the
                        production matcher never pairing across that boundary. That is an empirical
                        regularity over this corpus, so a test asserts it; `all-nodes` is available
                        for a study that prefers the guarantee to the assumption.

--------------------------------------------------------------------------------------------------
WHAT IS DELIBERATELY NOT HERE
--------------------------------------------------------------------------------------------------
No score fields on the human-facing record: measures stay in the `system` block, which the labeling
UI never renders (protocol §5's blindness guarantee, already implemented and tested). No
`many-to-many` relation -- it is not evidenced in this corpus and adding it speculatively would
invite its use as a dustbin.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "pass2-anchor-v4"

RELATIONS = ("one-to-one", "one-to-many", "many-to-one", "none", "uncertain")
ORACLES = ("suggested-list", "region-exhaustive", "document-exhaustive")
RETRIEVERS = ("structural-path", "word-overlap", "containment")
CHANGE_TYPES = ("modified", "moved", "removed", "unchanged")
JUDGMENT_MODES = ("per-candidate-binary", "forced-choice")

#: Eligibility rules that may define the denominator of a coverage claim. Every one is
#: measure-independent by construction: none consults word overlap, containment, cosine, or any
#: ranking the systems under evaluation produce. Adding a measure-dependent rule here would
#: reintroduce the central defect one layer further out, so the allowlist is the enforcement.
COVERAGE_RULES = (
    "all-nodes",  # every node the parser emits for the target version
    "all-nodes-with-body",  # every node with non-empty body text
)

PAIRWISE = ("affirmed-positive", "affirmed-negative")

ORACLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "suggested-list": frozenset(PAIRWISE),
    "region-exhaustive": frozenset((*PAIRWISE, "complete-within-region")),
    # `complete-in-document` is NOT granted by the oracle's presence alone -- `establishes()`
    # additionally requires the reviewed SET to equal the eligible SET. That conditionality is the
    # substance of rounds 4 and 5 and cannot be expressed in this table.
    "document-exhaustive": frozenset((*PAIRWISE, "complete-within-region")),
}

# ---------------------------------------------------------------------------------------------
# v4: completeness is membership, not cardinality
# ---------------------------------------------------------------------------------------------
# v3 replaced "the reviewer searched" with a count: `coverage.reviewed >= coverage.eligible_total`.
# Round 5 pointed out that a count is still an assertion. A workflow that adjudicated node 42 twice
# and never reached node 117 records 161/161 and is certified complete, and v3's own contract test
# demonstrated the hole by *setting* `reviewed = eligible_total` to promote a record.
#
# v4 records SETS. `eligible_ordinals` is generated from the frozen target parse by a coverage rule
# (never typed by a reviewer or a client); `reviewed_ordinals` is what was actually adjudicated.
# Completeness is set equality, so duplicates collapse and an omission cannot be masked by one.
#
# `coverage.target_source_sha256` / `target_parser_commit` pin the parse the eligible set was
# derived from. Without them a coverage set from one document could certify completeness over a
# different one -- the same class of defect as a stale corpus, one field further in.
COVERAGE_FIELDS = (
    "rule",
    "target_source_sha256",
    "target_parser_commit",
    "eligible_ordinals",
    "reviewed_ordinals",
)

#: Source-side competition. Round 5's second criticism: a document-exhaustive sweep runs per OLD
#: anchor over the NEW document, which enumerates that anchor's counterparts. It says nothing about
#: which OTHER old provisions also claim the same new node, and a collision group cannot be scored
#: without that. Establishing it needs the sweep in the opposite direction -- for one target node,
#: review every old provision -- which is a separate cost and therefore a separate record.
COMPETITION_FIELDS = (
    "target_ordinal",
    "rule",
    "source_source_sha256",
    "source_parser_commit",
    "eligible_ordinals",
    "reviewed_ordinals",
    "claiming_ordinals",
)

#: What each metric's arithmetic ASSUMES about the truth record it consumes. Data, not prose, so
#: `eval_pass2` can enforce it and a test can prove the enforcement fires.
METRIC_TRUTH_REQUIREMENTS: dict[str, dict[str, str]] = {
    "candidate_recall": {
        "proposition": "the complete set of true counterparts is known across the target version",
        "requires": "complete-in-document",
        "why": (
            "The denominator is 'true counterparts that exist'. A counterpart the reviewer had no "
            "systematic opportunity to adjudicate is missing from it, and the anchors where that "
            "happens are exactly the anchors retrieval failed on -- so an incomplete oracle removes "
            "the hardest cases from the denominator and inflates recall. The bias is by SELECTION, "
            "not by a wrong label: a false NONE does not enter as a miss, it vanishes."
        ),
    },
    "ranking": {
        "proposition": "this specific node is a true counterpart of the anchor",
        "requires": "affirmed-positive",
        "why": (
            "Where the true counterpart sat in an ordering does not depend on whether a second one "
            "exists elsewhere. This is the one target the cheapest oracle genuinely supports."
        ),
    },
    # v4 splits what v3 called "assignment" into two questions that need truth in OPPOSITE
    # directions. v3 required `complete-in-document`, which is a sweep of the NEW document per OLD
    # anchor: it enumerates that anchor's counterparts and says nothing about which OTHER old
    # provisions claim the same new node. Deriving collision groups from "the records that happen to
    # be in the dataset" then scored a global question with one-directional truth.
    "assignment_per_anchor": {
        "proposition": "for THIS anchor, the system assigned exactly its true counterpart set",
        "requires": "complete-in-document",
        "why": (
            "A per-anchor question, answerable from a target-side sweep alone: the sweep enumerates "
            "every counterpart this anchor has, which is exactly what the system's assignment for "
            "this anchor is compared against. No claim is made about other anchors."
        ),
    },
    "collision_resolution": {
        "proposition": "for a contested target node, EVERY old provision that legitimately claims it is known",
        "requires": "complete-source-side",
        "why": (
            "The opposite direction from every other metric here. Whether a global assignment "
            "resolved a group correctly depends on who else was competing, and an unsampled "
            "competitor makes a wrong resolution look right. A target-side sweep cannot establish "
            "it at any level of thoroughness -- it is the wrong axis, not an insufficient amount of "
            "the right one. Establishing it needs a reverse sweep: for one target node, review "
            "every old provision."
        ),
    },
    "diff_correctness": {
        "proposition": "the true change type is known, which requires knowing whether ANY counterpart exists",
        "requires": "complete-in-document",
        "why": (
            "`removed` versus `moved` IS the question of whether a counterpart exists elsewhere. "
            "Truth built from a bounded search answers a different question, and answers it in the "
            "matcher's favour whenever the matcher also said `removed`."
        ),
    },
    "failure_modes": {
        "proposition": "depends on the challenge claim; the stratum declares it",
        "requires": "per-stratum",
        "why": (
            "'This high-containment pair is actually DIFFERENT' is pairwise and needs only an "
            "affirmed negative. 'The matcher missed a counterpart that exists' needs a positive. "
            "'There is no counterpart anywhere' needs document completeness. Charging all three the "
            "price of the most expensive one would make most challenge work unaffordable for no "
            "gain in validity."
        ),
    },
}

#: What a challenge stratum may declare it needs. `affirmed-negative` is v3's addition.
CHALLENGE_REQUIREMENTS = ("affirmed-positive", "affirmed-negative", "complete-in-document")


def _set_covers(block: dict[str, Any] | None) -> bool:
    """Does `reviewed_ordinals` cover `eligible_ordinals` as a SET?

    v3 asked `reviewed >= eligible_total`, which a workflow that adjudicated node 42 twice and never
    reached node 117 satisfies exactly. Set equality cannot be satisfied that way: duplicates
    collapse, and an omission has nothing to hide behind.

    Completeness is a statement about membership, not cardinality.
    """
    if not isinstance(block, dict):
        return False
    if block.get("rule") not in COVERAGE_RULES:
        return False
    eligible, reviewed = block.get("eligible_ordinals"), block.get("reviewed_ordinals")
    if not isinstance(eligible, list) or not isinstance(reviewed, list) or not eligible:
        return False
    return set(reviewed) == set(eligible)


def coverage_is_complete(truth: dict[str, Any]) -> bool:
    """Was every eligible node of the TARGET document actually adjudicated for this anchor?"""
    return _set_covers(truth.get("coverage"))


def competition_is_complete(truth: dict[str, Any]) -> bool:
    """Was every eligible provision of the SOURCE document adjudicated against the target node?

    The reverse sweep. Establishes `complete-source-side`: for one contested target node, which old
    provisions legitimately claim it. Nothing in a target-side sweep can substitute for this.
    """
    return _set_covers(truth.get("competition_coverage"))


def establishes(truth: dict[str, Any], proposition: str) -> bool:
    """Can this truth record support this proposition?

    Takes the whole record rather than (oracles, judgment_mode) because `complete-in-document` now
    depends on measured coverage, not only on which oracles ran.
    """
    if truth.get("judgment_mode") != "per-candidate-binary":
        return False
    oracles = truth.get("oracles") or []
    if proposition == "complete-in-document":
        return "document-exhaustive" in oracles and coverage_is_complete(truth)
    if proposition == "complete-source-side":
        # Deliberately NOT gated on an oracle name: the reverse sweep is a different axis, and
        # naming `document-exhaustive` says nothing about whether it was ever performed.
        return competition_is_complete(truth)
    caps: set[str] = set()
    for o in oracles:
        caps |= ORACLE_CAPABILITIES.get(o, frozenset())
    return proposition in caps


# --------------------------------------------------------------------------------------------
# observation identity
# --------------------------------------------------------------------------------------------
# v2 joined nodes on `(source_sha256, parser_commit, element_id)`, citing a measurement that had
# never been committed. R9 §4 now measures it: element_id is non-empty and unique across all 73,296
# nodes in all 106 documents. It holds -- and it is still the wrong key.
#
# element_id's uniqueness is an empirical regularity of GPO's markup plus the parser's synthesis for
# nodes that lack one. It is a property of 34 bills, and legislation the corpus has not seen is
# exactly what the study is for. The node ORDINAL -- the index into `BillTree.nodes` -- is unique BY
# CONSTRUCTION inside one parse. The standard objection is that an ordinal shifts when the parser
# changes; but the key already carries `parser_commit`, so cross-parser stability was never
# required, and a changed parser must re-quarantine the observation anyway (round 2's drift
# finding). A shifted ordinal forces exactly that.
#
# Three concepts, kept apart:
#   OBSERVATION IDENTITY   `(source_sha256, parser_commit, node_ordinal)` -- which parsed node.
#   CONTENT INTEGRITY      `text_sha256` -- drift detection. Two nodes may legitimately share it;
#                          33% of documents in this corpus contain such a pair (R9 §1).
#   CROSS-VERSION IDENTITY the human's SAME/DIFFERENT ruling. The study's OUTPUT, never an input key.
OBSERVATION_ID_FIELDS = ("source_sha256", "parser_commit", "node_ordinal")

PROVENANCE_FIELDS = (
    "bill",
    "version",
    "source_sha256",
    "parser_commit",
    "node_ordinal",
    "match_path",
    "text_sha256",
    "element_id",  # recorded for traceability; NOT part of the identity
)


def observation_id(ref: dict[str, Any]) -> tuple:
    """Identity of one parsed node. See OBSERVATION_ID_FIELDS for why it is not the text hash."""
    return tuple(ref[f] for f in OBSERVATION_ID_FIELDS)


class SchemaError(ValueError):
    """A record that cannot support the metrics it would be counted in."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SchemaError(msg)


def _validate_coverage_block(block: Any, aid: str, name: str, fields: tuple[str, ...]) -> None:
    """Structural validation for a coverage set. Membership, identity, and no smuggled nodes.

    Three failure classes this catches that a count could not:
      * an ordinal reviewed that is not in the eligible universe -- named explicitly rather than
        silently changing the totals;
      * duplicates masking omissions -- caught by `_set_covers`, not here, but the explicit lists
        are what make that possible at all;
      * a coverage set derived from a DIFFERENT parse than the nodes it certifies, which would let
        one document's sweep certify completeness over another.
    """
    _require(
        isinstance(block, dict),
        f"{aid}: truth.{name} is required and must be a mapping -- completeness is granted on a "
        "reviewed SET, never on a reviewer-supplied count",
    )
    for f in fields:
        _require(f in block, f"{aid}: truth.{name} missing {f!r}")
    _require(
        block["rule"] in COVERAGE_RULES,
        f"{aid}: {name}.rule must be one of {COVERAGE_RULES} -- all measure-independent, so a "
        "system under evaluation cannot define the universe of its own completeness claim",
    )
    for f in ("eligible_ordinals", "reviewed_ordinals"):
        _require(
            isinstance(block[f], list) and all(isinstance(x, int) and x >= 0 for x in block[f]),
            f"{aid}: {name}.{f} must be a list of non-negative node ordinals",
        )
    _require(bool(block["eligible_ordinals"]), f"{aid}: {name}.eligible_ordinals is empty")
    stray = sorted(set(block["reviewed_ordinals"]) - set(block["eligible_ordinals"]))
    _require(
        not stray,
        f"{aid}: {name}.reviewed_ordinals contains {len(stray)} ordinal(s) outside the eligible "
        f"universe: {stray[:5]} -- a review of something the rule does not admit cannot count "
        "toward covering what it does",
    )


def validate_node_ref(ref: dict[str, Any], where: str) -> None:
    for f in PROVENANCE_FIELDS:
        _require(f in ref, f"{where}: node ref missing provenance field {f!r}")
    _require(isinstance(ref["match_path"], list), f"{where}: match_path must be a list")
    _require(len(ref["text_sha256"]) == 64, f"{where}: text_sha256 must be a sha256 hex digest")
    _require(
        isinstance(ref["node_ordinal"], int) and ref["node_ordinal"] >= 0,
        f"{where}: node_ordinal must be a non-negative integer -- it is the identity of the parsed "
        "node, and without it two provisions sharing boilerplate body text collapse into one (33% "
        "of documents in this corpus contain such a pair)",
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

    oracles = truth.get("oracles")
    _require(
        isinstance(oracles, list) and oracles and all(o in ORACLES for o in oracles),
        f"{aid}: truth.oracles must be a non-empty list drawn from {ORACLES}",
    )
    _require(
        truth.get("judgment_mode") in JUDGMENT_MODES,
        f"{aid}: truth.judgment_mode must be one of {JUDGMENT_MODES} -- a forced choice among a "
        "candidate list cannot establish that a node IS (or is not) the counterpart, only that it "
        "was the best of what was shown",
    )

    if "region-exhaustive" in oracles:
        _require(
            bool(truth.get("region_id")),
            f"{aid}: a region-exhaustive sweep must name the region it is exhaustive over -- "
            "'none' is uninterpretable without it",
        )

    if "document-exhaustive" in oracles:
        _validate_coverage_block(truth.get("coverage"), aid, "coverage", COVERAGE_FIELDS)
    if "competition_coverage" in truth:
        _validate_coverage_block(truth["competition_coverage"], aid, "competition_coverage", COMPETITION_FIELDS)
        comp = truth["competition_coverage"]
        _require(
            comp["source_source_sha256"] == rec["anchor"]["source_sha256"]
            and comp["source_parser_commit"] == rec["anchor"]["parser_commit"],
            f"{aid}: competition_coverage was derived from a different parse than the anchor's -- "
            "a reverse sweep over one source document cannot enumerate competitors in another",
        )
        _require(
            isinstance(comp.get("claiming_ordinals"), list)
            and set(comp["claiming_ordinals"]) <= set(comp["eligible_ordinals"]),
            f"{aid}: competition_coverage.claiming_ordinals must be a subset of the eligible "
            "source universe -- a claimant outside it was never in scope for the sweep",
        )
        _require(
            isinstance(rec.get("system", {}).get("competition_claimants"), list),
            f"{aid}: a record carrying competition_coverage must also record "
            "system.competition_claimants -- which OLD provisions the matcher assigned to that "
            "target. Both sides of the comparison are source-side ordinals; deriving the system's "
            "side from whichever anchors happen to be sampled is the defect this replaces",
        )

    counterparts = truth.get("counterparts", [])
    _require(isinstance(counterparts, list), f"{aid}: counterparts must be a list")
    rejected = truth.get("rejected", [])
    _require(isinstance(rejected, list), f"{aid}: truth.rejected must be a list")
    for group, name in ((counterparts, "counterparts"), (rejected, "rejected")):
        for cp in group:
            validate_node_ref(cp, f"{aid} {name}")
            _require(
                cp.get("found_via") in ("suggested", "browse", "region-sweep", "document-sweep"),
                f"{aid}: every {name} entry must record how it was FOUND; without it a counterpart "
                "the retrievers missed is indistinguishable from one they proposed, and candidate "
                "recall cannot be computed",
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
    _require(sysb.get("change_type") in CHANGE_TYPES, f"{aid}: system.change_type must be one of {CHANGE_TYPES}")
    _require(isinstance(sysb.get("assigned"), list), f"{aid}: system.assigned must be a list")
    for a in sysb["assigned"]:
        validate_node_ref(a, f"{aid} system.assigned")

    if rec.get("is_challenge"):
        _require(bool(rec.get("stratum")), f"{aid}: a challenge record must name its stratum")
        _require(
            rec.get("challenge_requires") in CHALLENGE_REQUIREMENTS,
            f"{aid}: a challenge record must declare `challenge_requires` from "
            f"{CHALLENGE_REQUIREMENTS} -- a pairwise false-keep claim needs only an affirmed "
            "negative, and charging it for exhaustive document review buys no validity",
        )
        if rec["challenge_requires"] == "affirmed-negative":
            _require(
                bool(rejected),
                f"{aid}: a stratum claiming a pair is DIFFERENT must record the rejected node in "
                "truth.rejected -- otherwise there is nothing the metric can test against",
            )

    _require(
        truth.get("change_type") in CHANGE_TYPES,
        f"{aid}: truth.change_type must be one of {CHANGE_TYPES}",
    )


def validate_dataset(records: list[dict[str, Any]]) -> None:
    seen = set()
    for rec in records:
        validate_record(rec)
        _require(rec["anchor_id"] not in seen, f"duplicate anchor_id {rec['anchor_id']!r}")
        seen.add(rec["anchor_id"])
    _require_observation_ids_identify_one_node(records)
    _require_one_claim_per_stratum(records)


def _require_one_claim_per_stratum(records: list[dict[str, Any]]) -> None:
    """A stratum makes ONE claim, so it has ONE truth requirement.

    Two records in one stratum declaring different `challenge_requires` would produce a single
    reported rate whose denominator mixed two different propositions -- and the evaluator, taking
    whichever record it saw first, would name only one of them. Found while building the v3
    fixture, which is what the fixture is for.
    """
    by_stratum: dict[str, set[str]] = {}
    for rec in records:
        if rec.get("is_challenge"):
            by_stratum.setdefault(rec["stratum"], set()).add(rec["challenge_requires"])
    mixed = {s: sorted(v) for s, v in by_stratum.items() if len(v) > 1}
    _require(not mixed, f"a challenge stratum must make one claim, but these mix requirements: {mixed}")


def _require_observation_ids_identify_one_node(records: list[dict[str, Any]]) -> None:
    """One observation id must describe exactly one node, on every recorded attribute.

    v2 compared only `text_sha256`, which round 4 showed was the weaker half of the check: two
    genuinely distinct provisions that share a body -- the boilerplate case, present in 33% of
    documents -- would carry the same identity AND the same text hash, and the validator saw no
    conflict. It compares every non-identity attribute now, so a generator that assigns one ordinal
    to two nodes is caught whenever those nodes differ in any recorded way.

    Two references to the SAME node legitimately repeat: an anchor's counterpart is usually also one
    of its candidates. The violation is one identity carrying two different descriptions.
    """
    by_id: dict[tuple, dict[str, set]] = {}
    for rec in records:
        refs = [rec["anchor"], *rec["truth"].get("counterparts", []), *rec["truth"].get("rejected", [])]
        refs += rec.get("candidates", []) + rec.get("system", {}).get("assigned", [])
        for ref in refs:
            slot = by_id.setdefault(
                observation_id(ref), {"text_sha256": set(), "match_path": set(), "element_id": set()}
            )
            slot["text_sha256"].add(ref["text_sha256"])
            slot["match_path"].add(tuple(ref["match_path"]))
            slot["element_id"].add(ref["element_id"])
    bad = {k: {f: v for f, v in attrs.items() if len(v) > 1} for k, attrs in by_id.items()}
    bad = {k: v for k, v in bad.items() if v}
    _require(
        not bad,
        f"observation id collision: {sorted(str(k) for k in bad)[:3]} -- one "
        "(source_sha256, parser_commit, node_ordinal) maps to more than one description, so it is "
        "not identifying a single parsed node and every join in the evaluator is unsound",
    )
