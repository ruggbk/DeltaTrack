"""score_metrics -- HARNESS-PLAN section 5. The frozen metric scorer, and NOTHING else.

    owns      PRE-REGISTRATION section 6 (M0-M9 minus M6) and section 8 (via A27.5/A37)
    consumes  committed artifacts ONLY -- frames, oracle key, oracle adjudicated,
              `cross_engine_control.json`, `s1_control.json`, and the committed membership's
              stratum labels
    tests     `x27_score_metrics.py` (SYNTHETIC + DEVELOPMENT only)

WHAT THIS MODULE MAY NOT DO, stated first because the boundary is the point.

It does not run H, run X, open a PDF, select a frame, rebuild a population, reconstruct XML or
PDF source truth, adjudicate anything, run historical repo discovery, or take the architecture
decision. Every fact it needs was made reachable from committed artifacts by A38, and A38.1's
ownership table is the map. `decide_architecture` owns section 7; the Rule 0 / Rule 1 / Rule 3
outcomes are ABSENT here on purpose -- this module emits the facts those rules read, and a
reader can check that no outcome enum appears in what it writes.

NOTHING HERE IS A NEW METHODOLOGICAL RULE. Where a frozen rule already has an executable owner
this module CALLS it rather than restating it, because two copies of a rule are two rules:

    M0 block                `neutral_identity.m0`               (A22/A23)
    M3 boundaries/outcome   `m3_boundaries.heading_outcome`     (A3/A4/section 6.3)
    M2 normalisation        `xml_sources.normalize`             (section 6.2)
    M5 role coarsening      `methodology_contracts.m5_*`        (A36.7)
    section 4.5 adequacy    `methodology_contracts.adequacy`    (A28.1/A28.2/A30.4)
    section 8 zero event    `methodology_contracts.zero_event_upper_bound`
    section 8 bootstrap     `methodology_contracts.section8_document_bootstrap` (A37, A38.10)
    Rule 0 margin clause    `methodology_contracts.margin_line_loss`            (A39.1)
    occurrence join         `build_oracle.resolve_adjudicated_occurrence`       (A38.7)
    adjudication encoding   `build_oracle.validate_adjudicated`                 (A38.7)
    answer routing          `build_oracle.PURPOSE_ROUTE`                        (A36.4)
    cross-engine gate       `cross_engine_control.json`, produced by `X09.gate` (A39.2)

The only quantity this module implements from scratch is the general one-sided
Clopper-Pearson upper bound, which A27.5 assigns to it explicitly and which
`methodology_contracts` deliberately does not carry.

MALFORMED INPUT REFUSES. Every refusal below exists because the alternative -- skipping a
record -- moves a denominator with nothing to show for it, and a smaller denominator reads as a
cleaner result. The refusals are deterministic and carry the offending record.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import build_frames as BF  # noqa: E402
import build_oracle as BO  # noqa: E402
import m3_boundaries as M3  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import neutral_identity as NI  # noqa: E402
from xml_sources import normalize as m2_normalize  # noqa: E402

SCHEMA = "metrics/1"
ARMS = ("H", "X")

# ---------------------------------------------------------------------- refusal reasons

FRAMES_NOT_A_SEQUENCE = "FRAMES_NOT_A_SEQUENCE"
MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
DUPLICATE_DOCUMENT_IDENTITY = "DUPLICATE_DOCUMENT_IDENTITY"
UNKNOWN_POPULATION = "UNKNOWN_POPULATION"
UNKNOWN_LINE_STATE = "UNKNOWN_LINE_STATE"
LINE_STATE_PREDICATE_DRIFT = "LINE_STATE_PREDICATE_DRIFT"
ANCHOR_EVIDENCE_DRIFT = "ANCHOR_EVIDENCE_DRIFT"
D_FRAME_ELIGIBILITY_DRIFT = "D_FRAME_ELIGIBILITY_DRIFT"
COVERAGE_FLOOR_DRIFT = "COVERAGE_FLOOR_DRIFT"
OCCURRENCE_RECORD_INCOMPLETE = "OCCURRENCE_RECORD_INCOMPLETE"
DUPLICATE_OCCURRENCE_KEY = "DUPLICATE_OCCURRENCE_KEY"
STIMULUS_DOCUMENT_NOT_IN_FRAMES = "STIMULUS_DOCUMENT_NOT_IN_FRAMES"
ADJUDICATION_ROUTE_MISSING = "ADJUDICATION_ROUTE_MISSING"
CONTROL_STIMULUS_IN_ESTIMAND = "CONTROL_STIMULUS_IN_ESTIMAND"
CROSS_ENGINE_DOCUMENT_MISSING = "CROSS_ENGINE_DOCUMENT_MISSING"
S1_ARTIFACT_MISSING = "S1_ARTIFACT_MISSING"
STRATUM_MISSING = "STRATUM_MISSING"
#: A null `role` is not the oracle's UNREADABLE. The codebook is a CLOSED vocabulary with
#: `other` for an unclassifiable heading and `UNREADABLE` for an illegible one, so a null is a
#: missing answer rather than a representable one, and mapping it to UNSCORABLE would shrink the
#: M5 denominator -- which reads as a cleaner result.
ROLE_MISSING = "ROLE_MISSING"

#: Statuses a metric entry can carry instead of a rate. I11 -- a zero content-bearing
#: denominator is VACUOUS and is never printed as agreement.
VACUOUS = "VACUOUS"
NOT_REPORTABLE_S1_DEAD = "NOT_REPORTABLE_S1_DEAD"

#: I13's reporting qualification. Never blocks -- A27.6 keeps x09 out of the gate vector.
PDFIUM_CONDITIONED_FRAME = "PDFIUM-CONDITIONED FRAME"

#: A24.2 / section 6 line states `build_frames` can commit. An unknown state REFUSES rather
#: than falling through to "not BOTH_ABSENT", which would silently enlarge the M0 risk set.
KNOWN_LINE_STATES = frozenset({"SAME", "TEXT_DIFFERS", "H_ABSENT", "X_ABSENT", "BOTH_ABSENT"})

#: section 6 M7: "emitted headings matching the letter-spaced signature (>= 3 single-character
#: tokens), per architecture". The threshold is the frozen protocol's, not phase 2's exploratory
#: `v08_display_split.py` regex (which required a RUN of >= 4 uppercase single-character tokens
#: on a physical line of ENGINE text). Those differ, and this module follows section 6 because
#: section 6 is the frozen source and A38.1 fixes M7's input as the emitted anchor TEXT. The run
#: length is recorded beside the count as a diagnostic so the stricter reading stays recoverable
#: from the artifact without a second metric existing.
M7_MIN_SINGLE_CHAR_TOKENS = 3

#: A27.5 / section 8.3. One-sided, 95 %.
SECTION8_ALPHA = 0.05
#: Halvings in the Clopper-Pearson bisection. Fixed, so the bound is bit-reproducible; 200 is
#: far past double precision, which is what makes "deterministic" true rather than approximate.
_CP_ITERATIONS = 200


class ScoreInputError(Exception):
    """A result-bearing input is malformed, incomplete or internally inconsistent.

    Deterministic and never a value: a scorer that repaired its input would be deciding what
    the study measured, and the repair would be invisible in the artifact.
    """

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


@dataclass(frozen=True)
class ScoreInputs:
    """Everything the scorer reads, supplied explicitly. No path is discovered here.

    `frames` is the sequence of committed document frames (`build_frames.build_document_frame`
    output). The `frames.json` wrapper belongs to whatever writes it; this module takes the
    document frames themselves so a wrapper change cannot silently reinterpret the population.

    `document_strata` maps document id -> stratum label, read from the committed membership by
    the caller. It feeds section 4.5's "strata filled" count and nothing else.

    `r1_role_agreement` is the section 5.6 R1 role reliability, when it has been established.
    `None` means NOT SUPPLIED, and M5 then carries that status explicitly rather than being
    reported as though its section 6 gate had been checked.
    """

    frames: tuple[dict, ...]
    oracle_key: dict
    oracle_adjudicated: dict
    cross_engine: dict
    s1: dict
    document_strata: dict = field(default_factory=dict)
    r1_role_agreement: float | None = None


# ------------------------------------------------------------------------- small helpers


def _require(record: dict, fields, where: str) -> None:
    missing = [f for f in fields if f not in record]
    if missing:
        raise ScoreInputError(MISSING_REQUIRED_FIELD, {"where": where, "missing": missing})


def rate(numerator: int, denominator: int, *, label: str = "") -> dict:
    """A metric entry: the number, and the denominator it is a fraction of.

    I11 -- a zero CONTENT-BEARING denominator yields VACUOUS, never 0.0 and never 1.0. Both of
    those read as a result; the protocol requires the absence of a population to be visible.
    """
    entry = {"numerator": numerator, "denominator": denominator}
    if label:
        entry["metric"] = label
    if denominator == 0:
        entry["value"] = None
        entry["status"] = VACUOUS
        return entry
    entry["value"] = numerator / denominator
    entry["status"] = "REPORTED"
    return entry


def _key_form(key):
    """One serialized form for an occurrence key. Tuples and lists are the same key.

    A38's own incidental finding: the two sides of the join were compared tuple-vs-list, unequal
    while being the same key, which would have made every matched-heading denominator zero.
    """
    if isinstance(key, (list, tuple)):
        return tuple(_key_form(k) for k in key)
    return key


def _readable(value) -> bool:
    """Is this adjudicated field an answer, or the oracle's own UNREADABLE?"""
    return value is not None and value != BO.UNREADABLE


# ------------------------------------------------------------- input validation (refusals)


def validate_inputs(inputs: ScoreInputs) -> dict:
    """Refuse malformed, incomplete or self-inconsistent input. Returns what it checked.

    Every check here is a fact about the COMMITTED artifacts, so a failure means the artifact
    chain is wrong rather than that a document scored badly. None of them is a threshold.
    """
    if not isinstance(inputs.frames, (list, tuple)):
        raise ScoreInputError(FRAMES_NOT_A_SEQUENCE, {"type": type(inputs.frames).__name__})

    seen: dict[str, int] = {}
    for frame in inputs.frames:
        _require(
            frame,
            ("document", "document_sha256", "population", "pages", "counts", "architecture_occurrences", "m9"),
            "document frame",
        )
        doc = frame["document"]
        if doc in seen:
            raise ScoreInputError(DUPLICATE_DOCUMENT_IDENTITY, {"document": doc})
        seen[doc] = 1
        if frame["population"] not in BF.KNOWN_POPULATIONS:
            raise ScoreInputError(UNKNOWN_POPULATION, {"document": doc, "population": frame["population"]})
        _validate_frame_internals(frame)
        _validate_occurrences(frame)
        _validate_m9(frame)

    _require(inputs.oracle_key, ("stimuli",), "oracle key")
    # The adjudicated encoding has ONE owner (A38.7). Calling it rather than re-checking the
    # namespaces here means the scorer cannot accept an artifact `build_oracle` would refuse.
    BO.validate_adjudicated(inputs.oracle_adjudicated, inputs.oracle_key)

    known_docs = set(seen)
    for bid, record in inputs.oracle_key["stimuli"].items():
        if record.get("control_kind") is not None:
            # A40 F5 -- a control has no document frame, and `frames == ()` is what keeps it out
            # of both estimands. If one ever acquired frame membership, skipping it by
            # `control_kind` would silently drop a region that CLAIMS to be in an estimand, so
            # the contradiction refuses here instead of being absorbed.
            if record.get("frames"):
                raise ScoreInputError(
                    CONTROL_STIMULUS_IN_ESTIMAND,
                    {"blind_id": bid, "control_kind": record["control_kind"], "frames": record["frames"]},
                )
            continue
        if record["document"] not in known_docs:
            raise ScoreInputError(STIMULUS_DOCUMENT_NOT_IN_FRAMES, {"blind_id": bid, "document": record["document"]})

    if not isinstance(inputs.s1, dict) or "fires" not in inputs.s1:
        raise ScoreInputError(S1_ARTIFACT_MISSING, {"got": sorted(inputs.s1) if isinstance(inputs.s1, dict) else None})
    _require(inputs.cross_engine, ("per_document",), "cross-engine control")
    qualified = {row["document"] for row in inputs.cross_engine["per_document"]}
    for doc in sorted(known_docs):
        if doc not in qualified:
            raise ScoreInputError(CROSS_ENGINE_DOCUMENT_MISSING, {"document": doc})
        if inputs.document_strata and doc not in inputs.document_strata:
            raise ScoreInputError(STRATUM_MISSING, {"document": doc})
    return {"n_documents": len(known_docs), "documents": sorted(known_docs)}


def _validate_frame_internals(frame: dict) -> None:
    """The committed line/region predicates must agree with the frozen rules that made them.

    This is the one place the scorer recomputes something: `build_frames` commits BOTH the
    comparable quantities (texts, signatures) and the booleans derived from them, and I9
    requires M0's eligibility and the D-frame's to be ONE set. A frame whose committed boolean
    disagrees with `neutral_identity`'s own predicate is not a frame this module can score.
    """
    doc = frame["document"]
    for page in frame["pages"]:
        _require(page, ("page_number", "neutral_lines", "regions"), f"page frame in {doc}")
        state_by_key = {}
        for line in page["neutral_lines"]:
            _require(line, ("key", "line_state", "in_m0_risk_set"), f"neutral line in {doc}")
            st = line["line_state"]
            _require(
                st,
                ("state", "h_text", "x_text", "h_signature", "x_signature", "diagnostics"),
                f"line_state in {doc}",
            )
            if st["state"] not in KNOWN_LINE_STATES:
                raise ScoreInputError(UNKNOWN_LINE_STATE, {"document": doc, "line": line["key"], "state": st["state"]})
            recomputed = {
                "text_discordance": NI.text_discordance(st),
                "segmentation_discordance": NI.segmentation_discordance(st),
                "in_m0_risk_set": NI.in_risk_set(st),
            }
            committed = {
                "text_discordance": st.get("text_discordance"),
                "segmentation_discordance": st.get("segmentation_discordance"),
                "in_m0_risk_set": line["in_m0_risk_set"],
            }
            if committed != recomputed:
                raise ScoreInputError(
                    LINE_STATE_PREDICATE_DRIFT,
                    {"document": doc, "line": line["key"], "committed": committed, "recomputed": recomputed},
                )
            state_by_key[tuple(line["key"])] = st

        for region in page["regions"]:
            _require(
                region,
                ("region_ordinal", "neutral_line_keys", "d_frame", "d_reasons", "anchor_evidence"),
                f"region in {doc}",
            )
            evidence = region["anchor_evidence"]
            differs = set(map(tuple, evidence["H"])) != set(map(tuple, evidence["X"]))
            if bool(evidence["differ"]) != differs or (BF.ANCHOR_DISCORDANCE in region["d_reasons"]) != differs:
                raise ScoreInputError(
                    ANCHOR_EVIDENCE_DRIFT,
                    {"document": doc, "region": region["region_ordinal"], "differ": evidence["differ"]},
                )
            states = [state_by_key[tuple(k)] for k in region["neutral_line_keys"] if tuple(k) in state_by_key]
            if len(states) != len(region["neutral_line_keys"]):
                raise ScoreInputError(
                    MISSING_REQUIRED_FIELD,
                    {"where": f"region {region['region_ordinal']} of {doc}", "missing": ["neutral line"]},
                )
            # I9 -- the same predicates decide M0 and D-frame membership. A discordant line in a
            # region the frame calls concordant would mean two eligibility sets, and the D-frame
            # census (Rule 1's population) and M0 would be measuring different things.
            line_level = any(NI.line_discordance(s) for s in states)
            if line_level and not region["d_frame"]:
                raise ScoreInputError(
                    D_FRAME_ELIGIBILITY_DRIFT,
                    {"document": doc, "region": region["region_ordinal"], "reason": "discordant line outside D-frame"},
                )
            if region["d_frame"] and not (line_level or differs):
                raise ScoreInputError(
                    D_FRAME_ELIGIBILITY_DRIFT,
                    {"document": doc, "region": region["region_ordinal"], "reason": "D-frame with no predicate"},
                )


def _validate_occurrences(frame: dict) -> None:
    """Every emitted occurrence is MATCHABLE or UNMATCHED, and keys are unique per arm."""
    doc = frame["document"]
    for arm in ARMS:
        rows = frame["architecture_occurrences"].get(arm)
        if rows is None:
            raise ScoreInputError(MISSING_REQUIRED_FIELD, {"where": f"architecture_occurrences of {doc}", "arm": arm})
        keys = []
        for row in rows:
            _require(
                row,
                ("anchor", "page_number", "region_ordinal", "occurrence_key", "match_status", "immediate_parent"),
                f"occurrence in {doc}/{arm}",
            )
            _require(row["anchor"], ("page_number", "line_number", "kind", "text"), f"anchor in {doc}/{arm}")
            status, key = row["match_status"], row["occurrence_key"]
            if status not in ("MATCHABLE", "UNMATCHED") or (status == "MATCHABLE") != (key is not None):
                raise ScoreInputError(
                    OCCURRENCE_RECORD_INCOMPLETE,
                    {"document": doc, "arm": arm, "match_status": status, "has_key": key is not None},
                )
            if key is not None:
                keys.append(_key_form(key))
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ScoreInputError(DUPLICATE_OCCURRENCE_KEY, {"document": doc, "arm": arm, "keys": duplicates[:4]})


def _validate_m9(frame: dict) -> None:
    """The M9 basis must be complete, and the coverage floor must still be production's 0.85.

    A committed floor other than 0.85 is not a document that scored badly; it is a threshold
    that moved, and section 4.7 makes that a deviation rather than a result.
    """
    for arm in ARMS:
        facts = frame["m9"].get(arm)
        if facts is None:
            raise ScoreInputError(MISSING_REQUIRED_FIELD, {"where": f"m9 of {frame['document']}", "arm": arm})
        _require(
            facts,
            (
                "derive_size_bands_returns_a_band",
                "coverage",
                "coverage_floor",
                "coverage_meets_floor",
                "n_lines_total",
                "n_margin_numbered_lines",
            ),
            f"m9 {arm} of {frame['document']}",
        )
        if facts["coverage_floor"] != 0.85:
            raise ScoreInputError(
                COVERAGE_FLOOR_DRIFT,
                {"document": frame["document"], "arm": arm, "coverage_floor": facts["coverage_floor"]},
            )
        if facts["coverage_meets_floor"] != (facts["coverage"] >= facts["coverage_floor"]):
            raise ScoreInputError(
                COVERAGE_FLOOR_DRIFT,
                {"document": frame["document"], "arm": arm, "reason": "committed verdict disagrees with the floor"},
            )


# ------------------------------------------------------------------------------ the M0 block


def m0_block(frame: dict) -> dict:
    """M0a / M0b / M0-any / M0b_defined / both_absent, and M0c beside them but never pooled.

    The line rates come from `neutral_identity.m0`, which owns A23's risk set: neutral lines
    emitted by AT LEAST ONE arm. A `BOTH_ABSENT` line is reported as a raw count and appears in
    no denominator -- counting it as agreement would make the rate a function of how much page
    furniture GPO set, which is a property of the layout and not of the seam.

    M0c is REGION-level (anchor sets differ) and is emitted alongside, never summed or averaged
    into the line rates: section 5's "never pooled with the above" is explicit.
    """
    states = [line["line_state"] for page in frame["pages"] for line in page["neutral_lines"]]
    block = dict(NI.m0(states))
    regions = [r for page in frame["pages"] for r in page["regions"]]
    anchor_discordant = [r for r in regions if BF.ANCHOR_DISCORDANCE in r["d_reasons"]]

    block["M0a_text_rate"] = rate(block["M0a_text"], block["risk_set"], label="M0a")
    block["M0b_segmentation_rate"] = rate(block["M0b_segmentation"], block["risk_set"], label="M0b_on_risk_set")
    block["M0_any_rate"] = rate(block["M0_any"], block["risk_set"], label="M0-any")
    # A23's reporting rule: only the rate on the DEFINED population may be described as "the
    # fraction of comparable groupings that disagree", and both must be emitted.
    block["M0b_rate_on_defined"] = rate(block["M0b_segmentation"], block["M0b_defined"], label="M0b_on_defined")
    block["M0c_anchor_regions"] = len(anchor_discordant)
    block["M0c_rate"] = rate(len(anchor_discordant), len(regions), label="M0c")
    block["M0c_pooling"] = "REGION-level; never pooled with the line rates (section 5)"
    block["both_absent_in_any_denominator"] = False
    block["risk_set_definition"] = "neutral lines with state != BOTH_ABSENT (A23, I3)"
    return block


# -------------------------------------------------------------------------------- M7


def m7_signature(text: str) -> dict:
    """The letter-spaced display-split signature for ONE emitted heading text.

    A self-signature over each architecture's OWN output (red-team #3): no oracle, and
    explicitly not a correctness measure. Tokenised on the section 6.2 normalisation so an
    NFKC-equivalent separator cannot hide a split.
    """
    normalized = m2_normalize(text or "")
    tokens = normalized.split(" ") if normalized else []
    singles = [t for t in tokens if len(t) == 1]
    run, longest = 0, 0
    for token in tokens:
        run = run + 1 if len(token) == 1 else 0
        longest = max(longest, run)
    return {
        "normalized": normalized,
        "n_tokens": len(tokens),
        "n_single_char_tokens": len(singles),
        "longest_single_char_run": longest,  # DIAGNOSTIC ONLY -- see M7_MIN_SINGLE_CHAR_TOKENS
        "matches": len(singles) >= M7_MIN_SINGLE_CHAR_TOKENS,
    }


def m7_block(frame: dict) -> dict:
    """M7 per architecture over the document's COMPLETE emitted occurrence census.

    Fires on 100 % of the holdout (section 6), so the population is every emitted occurrence --
    not the adjudicated subset, and not a frame. The matching texts are printed, not only
    counted: a count cannot distinguish a real signature from a coincidence.
    """
    out = {"threshold_single_char_tokens": M7_MIN_SINGLE_CHAR_TOKENS}
    for arm in ARMS:
        rows = frame["architecture_occurrences"][arm]
        hits = [(r, m7_signature(r["anchor"]["text"])) for r in rows]
        matched = [(r, s) for r, s in hits if s["matches"]]
        out[arm] = {
            "n_emitted": len(rows),
            "n_display_split": len(matched),
            "rate": rate(len(matched), len(rows), label="M7"),
            "instances": [
                {
                    "page_number": r["anchor"]["page_number"],
                    "line_number": r["anchor"]["line_number"],
                    "text": r["anchor"]["text"],
                    "n_single_char_tokens": s["n_single_char_tokens"],
                    "longest_single_char_run": s["longest_single_char_run"],
                }
                for r, s in matched
            ],
        }
    return out


# ------------------------------------------------------------------- M9 / Rule 0 raw facts


def _clause_loss(h_ok: bool, x_ok: bool) -> dict:
    """Which arm, if either, LOSES a boolean Rule 0 clause the other keeps.

    Shaped exactly like `methodology_contracts.margin_line_loss` so the three clauses read the
    same way. BOTH losing is not a loss here: section 7.2 rule 0 fires only when EXACTLY one
    architecture loses, and a shared failure is neutral for RQ1 and a FAILURE retained in RQ2.
    """
    if h_ok and not x_ok:
        return {"loser": "X", "fires": True, "h": h_ok, "x": x_ok}
    if x_ok and not h_ok:
        return {"loser": "H", "fires": True, "h": h_ok, "x": x_ok}
    return {"loser": None, "fires": False, "h": h_ok, "x": x_ok}


def rule0_facts(frame: dict) -> dict:
    """M9's raw facts per arm, and the three per-clause asymmetries. NO outcome is decided.

    I12 says M9 can reject an arm outright before any other metric is consulted. The REJECTION
    is section 7.2's; this reports which arm lost which clause, with no tolerance anywhere: the
    margin-line clause is `margin_line_loss` verbatim (A39.1 -- any strictly positive deficit
    fires), and the coverage clause is the committed 0.85 floor, already asserted unmoved.
    """
    h, x = frame["m9"]["H"], frame["m9"]["X"]
    return {
        "document": frame["document"],
        "population": frame["population"],
        "H": {k: v for k, v in h.items() if k != "margin_numbered_line_keys"},
        "X": {k: v for k, v in x.items() if k != "margin_numbered_line_keys"},
        "coverage_floor": h["coverage_floor"],
        "band_loss": _clause_loss(h["derive_size_bands_returns_a_band"], x["derive_size_bands_returns_a_band"]),
        "coverage_loss": _clause_loss(h["coverage_meets_floor"], x["coverage_meets_floor"]),
        "margin_line_loss": MC.margin_line_loss(h["n_margin_numbered_lines"], x["n_margin_numbered_lines"]),
        "margin_line_quantity": "count of Page.lines where line_number is not None (A39.1); no tolerance",
        "rule0_outcome": None,
        "rule0_owner": "decide_architecture -- A27.4's outcome enum is deliberately absent here",
    }


# ----------------------------------------------------------------- the M1-M5 heading join


def _adjudicated_occurrences(record: dict, answer: dict) -> list[dict]:
    """Every adjudicated heading of one stimulus, resolved to an A30 occurrence key.

    The resolution is `build_oracle.resolve_adjudicated_occurrence` (A38.7): committed facts
    only, no tolerance, no text/kind/order fallback, a tie or an absent candidate -> UNMATCHED.
    A refusal is CARRIED, never dropped and never converted into a match.
    """
    out = []
    for ordinal, heading in enumerate(answer.get("headings", [])):
        resolved = BO.resolve_adjudicated_occurrence(record, heading)
        out.append(
            {
                "ordinal": ordinal,
                "heading": heading,
                "resolved": resolved["matched"],
                "occurrence_key": _key_form(resolved["occurrence_key"]) if resolved["matched"] else None,
                "refusal": None if resolved["matched"] else resolved.get("reason"),
            }
        )
    return out


def _blank_heading_counts() -> dict:
    return {
        "n_adjudicated": 0,
        "n_adjudicated_unresolvable": 0,
        "n_emitted": {arm: 0 for arm in ARMS},
        "n_matched": {arm: 0 for arm in ARMS},
        "m2_exact": {arm: 0 for arm in ARMS},
        "m2_scored": {arm: 0 for arm in ARMS},
        "m2_excluded_unreadable": 0,
        "m3_clean": {arm: 0 for arm in ARMS},
        "m3_scored": {arm: 0 for arm in ARMS},
        "m3_boundary": {arm: {"WELD": 0, "SPLIT": 0, "OK": 0, "TEXT_ERROR": 0} for arm in ARMS},
        "m3_outcomes": {outcome.value: 0 for outcome in M3.HeadingOutcome},
        "m3_excluded_no_reference": 0,
        "m4_correct": {arm: 0 for arm in ARMS},
        "m4_scored": {arm: 0 for arm in ARMS},
        "m4_excluded_unreadable": 0,
        "m5_agree": {arm: 0 for arm in ARMS},
        "m5_scored": {arm: 0 for arm in ARMS},
        "m5_excluded_unscorable": {arm: 0 for arm in ARMS},
        "m5_excluded_unreadable": 0,
        "n_stimuli": 0,
    }


def _score_stimulus(counts: dict, record: dict, answer: dict) -> None:
    """Fold one (stimulus, route) into the running heading counts for its frame.

    THE POPULATIONS, each as section 6 fixes it:
        M1 recall     denominator = the ADJUDICATED enumeration (I10), never the emitted one
        M1 precision  denominator = the arm's EMITTED occurrences for this region
        M2/M4/M5      matched headings, minus the oracle's own UNREADABLE fields
        M3            adjudicated headings with a readable reference; an arm that emitted
                      nothing scores as a maximal TEXT_ERROR and STAYS in the denominator,
                      because `m3_boundaries` says a severe failure may never become an
                      exclusion (A9)
    """
    counts["n_stimuli"] += 1
    adjudicated = _adjudicated_occurrences(record, answer)
    counts["n_adjudicated"] += len(adjudicated)
    counts["n_adjudicated_unresolvable"] += sum(1 for a in adjudicated if not a["resolved"])

    emitted_by_key = {}
    for arm in ARMS:
        rows = record["architecture_occurrences"][arm]
        counts["n_emitted"][arm] += len(rows)
        emitted_by_key[arm] = {_key_form(r["occurrence_key"]): r for r in rows if r["occurrence_key"] is not None}

    for item in adjudicated:
        heading = item["heading"]
        oracle_text = heading.get("text")
        matched = {arm: emitted_by_key[arm].get(item["occurrence_key"]) if item["resolved"] else None for arm in ARMS}
        for arm in ARMS:
            if matched[arm] is not None:
                counts["n_matched"][arm] += 1

        # ---- M3, on projected TEXT plus the oracle. A segmentation label may never reach it.
        if not item["resolved"]:
            pass  # identity unknown: scoring it would fabricate a defect for both arms
        elif not _readable(oracle_text):
            counts["m3_excluded_no_reference"] += 1
        else:
            h_text = matched["H"]["anchor"]["text"] if matched["H"] else ""
            x_text = matched["X"]["anchor"]["text"] if matched["X"] else ""
            outcome, h_score, x_score = M3.heading_outcome(oracle_text, h_text, x_text)
            counts["m3_outcomes"][outcome.value] += 1
            for arm, score in (("H", h_score), ("X", x_score)):
                counts["m3_scored"][arm] += 1
                counts["m3_clean"][arm] += int(score.clean)
                counts["m3_boundary"][arm]["WELD"] += score.weld
                counts["m3_boundary"][arm]["SPLIT"] += score.split
                counts["m3_boundary"][arm]["OK"] += score.ok
                counts["m3_boundary"][arm]["TEXT_ERROR"] += score.text_error

        # ---- M2 / M4 / M5, on matched headings only
        if not _readable(oracle_text):
            counts["m2_excluded_unreadable"] += 1
        if not _readable(heading.get("parent")) and heading.get("parent") is not None:
            counts["m4_excluded_unreadable"] += 1
        if heading.get("role") == BO.UNREADABLE:
            counts["m5_excluded_unreadable"] += 1

        for arm in ARMS:
            occurrence = matched[arm]
            if occurrence is None:
                continue
            if _readable(oracle_text):
                counts["m2_scored"][arm] += 1
                counts["m2_exact"][arm] += int(m2_normalize(oracle_text) == m2_normalize(occurrence["anchor"]["text"]))

            # M4 -- the IMMEDIATE parent only. Full ancestry would score a different quantity
            # and would hide a one-level hierarchy error inside a correct grandparent.
            parent = heading.get("parent")
            if parent != BO.UNREADABLE:
                emitted_parent = occurrence["immediate_parent"]
                counts["m4_scored"][arm] += 1
                if parent is None or emitted_parent is None:
                    counts["m4_correct"][arm] += int(parent is None and emitted_parent is None)
                else:
                    counts["m4_correct"][arm] += int(m2_normalize(parent) == m2_normalize(emitted_parent))

            role = heading.get("role")
            if role == BO.UNREADABLE:
                continue
            if role is None:
                raise ScoreInputError(ROLE_MISSING, {"blind_id": answer.get("id"), "ordinal": item["ordinal"]})
            agreement = MC.m5_agreement(role, occurrence["anchor"]["kind"])
            if agreement is None:
                counts["m5_excluded_unscorable"][arm] += 1  # A36.7 -- out of the DENOMINATOR
            else:
                counts["m5_scored"][arm] += 1
                counts["m5_agree"][arm] += int(agreement)


def _heading_metrics_from_counts(counts: dict, r1_role_agreement: float | None) -> dict:
    """Turn the raw heading counts into the reported metric entries."""
    resolvable = counts["n_adjudicated"] - counts["n_adjudicated_unresolvable"]
    metrics = {
        "counts": counts,
        "M1": {
            arm: {
                # I10 -- the ADJUDICATED enumeration, including headings whose geometric
                # identity refused: they were printed, and removing them would shrink the
                # denominator invisibly. The sensitivity figure below is explicitly secondary.
                "recall": rate(counts["n_matched"][arm], counts["n_adjudicated"], label="M1 recall"),
                "precision": rate(counts["n_matched"][arm], counts["n_emitted"][arm], label="M1 precision"),
                "recall_sensitivity_excluding_unresolvable": rate(
                    counts["n_matched"][arm], resolvable, label="M1 recall (SECONDARY)"
                ),
            }
            for arm in ARMS
        },
        "M2": {arm: rate(counts["m2_exact"][arm], counts["m2_scored"][arm], label="M2") for arm in ARMS},
        "M3": {
            "clean_rate": {arm: rate(counts["m3_clean"][arm], counts["m3_scored"][arm], label="M3") for arm in ARMS},
            "boundary_outcomes": counts["m3_boundary"],
            "heading_outcomes": counts["m3_outcomes"],
            "decision_unit": "heading occurrence (A3); WELD/SPLIT tallies never substitute for it",
            "consumes": "projected text + oracle only -- never a segmentation label (section 5)",
        },
        "M4": {arm: rate(counts["m4_correct"][arm], counts["m4_scored"][arm], label="M4") for arm in ARMS},
        "M5": {
            arm: {
                "agreement": rate(counts["m5_agree"][arm], counts["m5_scored"][arm], label="M5"),
                "excluded_unscorable": counts["m5_excluded_unscorable"][arm],
            }
            for arm in ARMS
        },
    }
    metrics["M4"]["scope"] = "immediate parent only (A38.4 penultimate breadcrumb element)"
    metrics["M5"]["r1_role_gate"] = _r1_role_gate(r1_role_agreement)
    metrics["M5"]["licenses"] = "corroboration only -- section 6 forbids M5 deciding anything"
    return metrics


def _r1_role_gate(r1_role_agreement: float | None) -> dict:
    """Section 5.6's R1 role gate, represented rather than assumed.

    NOT SUPPLIED is a state, not a pass. Reporting M5 as though its gate had been checked when
    no R1 role agreement exists is precisely the "green because nothing measured it" failure.
    """
    if r1_role_agreement is None:
        return {"status": "NOT_SUPPLIED", "threshold": 0.80, "m5_void": False, "owner": "Rule 3 gate vector (A27.6)"}
    passes = r1_role_agreement >= 0.80
    return {
        "status": "PASS" if passes else "FAIL",
        "observed": r1_role_agreement,
        "threshold": 0.80,
        "m5_void": not passes,
        "owner": "Rule 3 gate vector (A27.6)",
    }


def heading_metrics(inputs: ScoreInputs) -> dict:
    """M1-M5 per document per FRAME, plus the pooled rows. C and D are never pooled together.

    A36.3 -- "never pooled" means separate ESTIMANDS, not disjoint sets: one physical region may
    be in both frames and is then counted once in each. A36.4 fixes which answer each estimand
    reads, and this walks `PURPOSE_ROUTE` rather than choosing: C metrics read the AI answer even
    where a human answer exists, because D membership is conditional on the architectures
    disagreeing and taking human truth there would let them pick their own oracle.

    Controls and R1 repeats are EXCLUDED and counted. A control belongs to no estimand
    (`ESTIMAND_PURPOSES` names the purposes that read one, and no control purpose is in it); an
    R1 repeat re-presents its primary's region, so counting it would put one physical occurrence
    in a denominator twice.
    """
    per_document: dict[str, dict] = {}
    excluded = {"control": 0, "r1_repeat": 0}
    frame_purposes = ((BO.C_FRAME, BO.PURPOSE_C_METRICS), (BO.D_FRAME, BO.PURPOSE_D_DECISION))

    for bid, record in inputs.oracle_key["stimuli"].items():
        if record.get("control_kind") is not None:
            excluded["control"] += 1
            continue
        if record.get("is_r1_repeat"):
            excluded["r1_repeat"] += 1
            continue
        for frame_name, purpose in frame_purposes:
            if frame_name not in record["frames"]:
                continue
            route = BO.PURPOSE_ROUTE[purpose]
            answer = inputs.oracle_adjudicated.get(route, {}).get(bid)
            if answer is None:
                raise ScoreInputError(ADJUDICATION_ROUTE_MISSING, {"blind_id": bid, "route": route})
            bucket = per_document.setdefault(record["document"], {})
            counts = bucket.setdefault(frame_name, _blank_heading_counts())
            _score_stimulus(counts, record, answer)

    documents = {}
    pooled = {frame_name: _blank_heading_counts() for frame_name, _p in frame_purposes}
    for document, by_frame in sorted(per_document.items()):
        documents[document] = {
            frame_name: _heading_metrics_from_counts(counts, inputs.r1_role_agreement)
            for frame_name, counts in sorted(by_frame.items())
        }
        for frame_name, counts in by_frame.items():
            _accumulate(pooled[frame_name], counts)
    return {
        "per_document": documents,
        "pooled": {
            frame_name: _heading_metrics_from_counts(counts, inputs.r1_role_agreement)
            for frame_name, counts in sorted(pooled.items())
            if counts["n_stimuli"]
        },
        "excluded_stimuli": excluded,
        "routing": {purpose: BO.PURPOSE_ROUTE[purpose] for _f, purpose in frame_purposes},
        "estimand_purposes": list(BO.ESTIMAND_PURPOSES),
        "pooling_rule": "C and D are separate estimands (A36.3); they are never summed together",
    }


def _accumulate(total: dict, part: dict) -> None:
    """Sum one document's raw counts into the pooled counts, recursively over the same shape."""
    for key, value in part.items():
        if isinstance(value, dict):
            _accumulate(total[key], value)
        else:
            total[key] = total[key] + value


# ------------------------------------------------------------------- section 8 statistics


def clopper_pearson_upper(events: int, n: int) -> float:
    """The exact one-sided 95 % Clopper-Pearson UPPER bound on pi. Unit = the DOCUMENT.

    A27.5 assigns this to `score_metrics`; `methodology_contracts` carries only the zero-event
    closed form, which is the frozen verbatim case and is delegated to it here rather than
    re-derived. For k > 0 the bound is the p solving `P(X <= k | n, p) = 0.05`, found by
    bisection with a FIXED iteration count so the value is reproducible bit for bit.

    No tolerance and no continuity correction: section 8.3 froze the exact procedure, and a
    "close enough" bound on a 14-document holdout is the one number the design cannot afford
    to soften.
    """
    if n < 1:
        raise ScoreInputError(MISSING_REQUIRED_FIELD, {"where": "clopper_pearson_upper", "n": n})
    if events < 0 or events > n:
        raise ScoreInputError(MISSING_REQUIRED_FIELD, {"where": "clopper_pearson_upper", "events": events, "n": n})
    if events == 0:
        return MC.zero_event_upper_bound(n)
    if events == n:
        return 1.0

    def cdf(p: float) -> float:
        return sum(math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(events + 1))

    lo, hi = 0.0, 1.0
    for _ in range(_CP_ITERATIONS):
        mid = (lo + hi) / 2
        if cdf(mid) > SECTION8_ALPHA:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def document_discordance_event(frame: dict) -> dict:
    """Section 8's per-DOCUMENT event: "has >= 1 heading-level H/X discordance".

    THE EVIDENCE, and why it is this one. `build_frames` commits, per region, whether the two
    arms' EMITTED ANCHOR SETS differ, and equality there is over the whole production `Anchor`
    value -- page, line, kind, text and division. So a heading either arm missed, placed
    differently, classed differently or read differently makes the sets differ, and that is
    exactly section 8.2's "produced identical heading output". It needs no oracle, and its
    predicate `H != X` is symmetric under swapping the arms.

    The line-level M0 predicates are deliberately NOT the event: a text or segmentation
    difference on an ordinary body line is not heading-level, and using it would answer a
    different question under section 8's name.
    """
    regions = [r for page in frame["pages"] for r in page["regions"]]
    discordant = [
        {"page_number": r["page_number"], "region_ordinal": r["region_ordinal"]}
        for r in regions
        if BF.ANCHOR_DISCORDANCE in r["d_reasons"]
    ]
    return {
        "document": frame["document"],
        "population": frame["population"],
        "event": bool(discordant),
        "n_anchor_discordant_regions": len(discordant),
        "evidence": discordant[:8],
        "definition": "any region whose emitted heading (Anchor) sets differ between H and X",
    }


def section8(frames, paired_metrics: dict) -> dict:
    """The section 8 block: the estimand, the exact bound, the bootstrap, and the pairing.

    P-HEAD ONLY. `SECTION8_DOCUMENT_DISCORDANCE` carries the population in the statistic's own
    identity because section 4.4.1 claims no heading metric on P-robust; a P-robust document
    entering here would both inflate N and silently reuse a draw sequence that is not its own.

    ZERO EVENTS: the closed form `1 - 0.05 ** (1/N)` and NO bootstrap. 8.1 measured that every
    resample of an all-zero cluster set is zero, so the percentile interval is [0.0, 0.0] and
    carries no information about a new document -- in precisely the case this design expects.
    The wording below therefore says what was OBSERVED and never that the true rate is zero.
    """
    # CANONICALLY ORDERED, for the reason `canonical_document_vector` sorts: the caller's listing
    # order must not reach the artifact. An input-ordered list means two runs over the same
    # population print different per-document detail, and a reader comparing them sees a
    # difference where there is none.
    events = sorted((document_discordance_event(f) for f in frames), key=lambda e: MC.canonical(e["document"]))
    p_head = [e for e in events if e["population"] == MC.P_HEAD]
    excluded = [e["document"] for e in events if e["population"] != MC.P_HEAD]
    n = len(p_head)
    k = sum(1 for e in p_head if e["event"])

    block = {
        "estimand": "pi = P(a document from the target population shows >= 1 heading-level H/X discordance)",
        "independent_unit": "document",
        "population": MC.P_HEAD,
        "excluded_documents_not_p_head": sorted(excluded),
        "n_documents": n,
        "events": k,
        "per_document": events,
        "forbidden": "no per-heading probability; no heading-as-iid-trial denominator (section 8.3)",
        "paired": paired_metrics,
    }
    if n == 0:
        block["clopper_pearson_upper_bound"] = None
        block["status"] = VACUOUS
        block["bootstrap"] = {"reported": False, "reason": MC.EMPTY_DOCUMENT_SET, "gating": False}
        block["statement"] = "no P-head document was scored, so no bound is licensed"
        return block

    block["clopper_pearson_upper_bound"] = clopper_pearson_upper(k, n)
    block["clopper_pearson_alpha"] = SECTION8_ALPHA
    block["status"] = "REPORTED"
    # The A37 helper is the ONLY bootstrap surface (A38.10), and it derives the event count from
    # the vector rather than taking one, so a supplied count cannot contradict what it summarises.
    block["bootstrap"] = MC.section8_document_bootstrap([(e["document"], e["event"]) for e in p_head])
    block["zero_event_closed_form_used"] = k == 0
    if k == 0:
        block["statement"] = (
            f"no heading-level discordance observed on {n} P-head document(s); exact one-sided "
            f"95 % upper bound on the per-document rate: {block['clopper_pearson_upper_bound']:.4f}. "
            "This is an OBSERVATION, not a claim that the true rate is zero."
        )
    else:
        block["statement"] = (
            f"{k} of {n} P-head document(s) showed at least one heading-level discordance; exact "
            f"one-sided 95 % upper bound on the per-document rate: "
            f"{block['clopper_pearson_upper_bound']:.4f}."
        )
    return block


#: Per-arm scalars the paired comparison is defined over. Each is (metric path, arm subkey), so
#: adding one cannot silently change how the mean is weighted.
PAIRED_METRICS = (
    ("M1_recall", ("M1", "{arm}", "recall")),
    ("M1_precision", ("M1", "{arm}", "precision")),
    ("M2", ("M2", "{arm}")),
    ("M3_clean", ("M3", "clean_rate", "{arm}")),
    ("M4", ("M4", "{arm}")),
    ("M5", ("M5", "{arm}", "agreement")),
)


def _dig(tree: dict, path, arm: str):
    node = tree
    for step in path:
        node = node.get(step.replace("{arm}", arm)) if isinstance(node, dict) else None
        if node is None:
            return None
    return node


def paired_differences(per_document_metrics: dict) -> dict:
    """Section 8.3 -- per-document paired differences, UNWEIGHTED mean over documents.

    Never weighted by heading count: a bill with 40 headings and one with 2 are one document
    each, and weighting would make the comparison a function of document length. Per-document
    detail is mandatory and is never collapsed to the mean alone.
    """
    out = {
        "weighting": "UNWEIGHTED mean over documents (section 8.3); never weighted by heading count",
        "difference": "X - H",
        "by_frame": {},
    }
    frames = sorted({frame for by_frame in per_document_metrics.values() for frame in by_frame})
    for frame_name in frames:
        rows = {}
        for name, path in PAIRED_METRICS:
            details, values = [], []
            for document, by_frame in sorted(per_document_metrics.items()):
                metrics = by_frame.get(frame_name)
                if metrics is None:
                    continue
                h, x = _dig(metrics, path, "H"), _dig(metrics, path, "X")
                if h is None or x is None or h.get("value") is None or x.get("value") is None:
                    details.append({"document": document, "difference": None, "status": VACUOUS})
                    continue
                difference = x["value"] - h["value"]
                details.append({"document": document, "H": h["value"], "X": x["value"], "difference": difference})
                values.append(difference)
            rows[name] = {
                "per_document": details,
                "n_documents_contributing": len(values),
                "unweighted_mean_difference": (sum(values) / len(values)) if values else None,
                "status": "REPORTED" if values else VACUOUS,
            }
        out["by_frame"][frame_name] = rows
    return out


# ------------------------------------------------------------------ section 4.5 adequacy


def adequacy_facts(frames, document_strata: dict) -> dict:
    """Section 4.5's inputs and the A28.2 state machine's verdict, as FACTS.

    A28.1 counts `|H_keys union X_keys|` over A27.1/A30.1 occurrence keys, restricted to P-head
    and to account/agency/grouping; A30.4 made both restrictions executable inside
    `filter_keys`, so they are applied by the owner rather than trusted to this caller.

    Rule 3's consumption of an INADEQUATE verdict belongs to `decide_architecture` (A27.6). The
    verdict is reported here because it is a property of the population, not of the decision.
    """
    keyed = []
    for frame in frames:
        for arm in ARMS:
            for row in frame["architecture_occurrences"][arm]:
                if row["occurrence_key"] is None:
                    continue
                keyed.append((_key_form(row["occurrence_key"]), row["anchor"]["kind"], frame["population"]))
    kept = MC.filter_keys(keyed)
    occurrences = MC.adequacy_occurrences(kept, set())
    strata = sorted({document_strata[f["document"]] for f in frames if f["document"] in document_strata})
    return {
        "kinds_counted": sorted(MC.ADEQUACY_KINDS),
        "population_counted": MC.P_HEAD,
        "n_occurrences": occurrences,
        "strata_filled": len(strata),
        "strata": strata,
        "verdict": MC.adequacy(len(strata), occurrences),
        "owner": "decide_architecture consumes this (Rule 3); the verdict itself is a population fact",
    }


# ----------------------------------------------------------------- cross-engine and S1


def qualification(cross_engine: dict) -> dict:
    """I13 -- the PDFIUM-CONDITIONED FRAME label, per document and for both headlines.

    The thresholds live in `x09_skeleton_cross_engine.gate` and reach here only through the
    committed artifact's `passed`; this module never re-derives 0.95 or 0.75. Failure on MORE
    than a third of sampled documents qualifies BOTH headlines. It never blocks (A27.6).
    """
    rows = cross_engine["per_document"]
    failed = [r["document"] for r in rows if not r["passed"]]
    return {
        "per_document": {r["document"]: (None if r["passed"] else PDFIUM_CONDITIONED_FRAME) for r in rows},
        "n_documents": len(rows),
        "n_failed": len(failed),
        "failed_documents": sorted(failed),
        # strictly MORE than one third, as x09's own consequence text states
        "both_headlines_qualified": len(failed) * 3 > len(rows),
        "decision_blocking": False,
        "threshold_owner": "x09_skeleton_cross_engine.gate (document 0.95 / page 0.75)",
    }


def s1_status(s1: dict) -> dict:
    """Section 5's first control: if S1 does not fire, M0 is NOT REPORTABLE.

    The consequence for the DECISION is A27.6's; the consequence for M0's reportability is
    section 5's own control row, so it is recorded here where M0 is produced.
    """
    fires = bool(s1.get("fires"))
    return {
        "fires": fires,
        "advance_scale": s1.get("advance_scale"),
        "m0_reportable": fires,
        "m0_status": "REPORTED" if fires else NOT_REPORTABLE_S1_DEAD,
        "gate_owner": "Rule 3 gate vector (A27.6)",
    }


# ------------------------------------------------------------------------------- the scorer


def score(inputs: ScoreInputs) -> dict:
    """The whole `metrics.json` payload. Facts only; no architecture outcome anywhere in it."""
    checked = validate_inputs(inputs)
    s1 = s1_status(inputs.s1)
    label = qualification(inputs.cross_engine)

    per_document = {}
    for frame in inputs.frames:
        document = frame["document"]
        block = m0_block(frame)
        if not s1["m0_reportable"]:
            # The comparator is not live, so the M0 rates are withheld rather than printed. The
            # raw counts stay: withholding evidence would be worse than withholding a rate.
            for name in ("M0a_text_rate", "M0b_segmentation_rate", "M0_any_rate", "M0b_rate_on_defined", "M0c_rate"):
                block[name] = {**block[name], "value": None, "status": NOT_REPORTABLE_S1_DEAD}
        per_document[document] = {
            "population": frame["population"],
            "stratum": inputs.document_strata.get(document),
            "qualification": label["per_document"].get(document),
            "M0": block,
            "M7": m7_block(frame),
            "M9": rule0_facts(frame),
        }

    headings = heading_metrics(inputs)
    for document, metrics in headings["per_document"].items():
        per_document[document]["headings_by_frame"] = metrics
    paired = paired_differences(headings["per_document"])

    return {
        "schema": SCHEMA,
        "owns": "PRE-REGISTRATION section 6 (M0-M9 minus M6) and section 8; HARNESS-PLAN section 5",
        "decision_taken_here": False,
        "decision_owner": "decide_architecture (section 7) -- no Rule 0/1/3 outcome appears here",
        "m6": "DEFERRED by A20; not computed, not reported, and not asked of the adjudicator",
        "documents_scored": checked["documents"],
        "s1": s1,
        "cross_engine_qualification": label,
        "per_document": per_document,
        "headings_pooled": headings["pooled"],
        "heading_population_notes": {
            "excluded_stimuli": headings["excluded_stimuli"],
            "routing": headings["routing"],
            "estimand_purposes": headings["estimand_purposes"],
            "pooling_rule": headings["pooling_rule"],
        },
        "section8": section8(inputs.frames, paired),
        "adequacy_4_5": adequacy_facts(inputs.frames, inputs.document_strata),
    }


def write_metrics(payload: dict, out_path: Path | None = None) -> Path:
    """Write the CANONICAL `metrics.json`. Refuses before a VALID execution boundary.

    Guarded by `build_oracle.assert_write_permitted`, the single authority the oracle, S1 and
    cross-engine writers already use, so no confirmatory artifact can be created under a weaker
    condition than the material it describes.
    """
    import json

    out_path = Path(out_path) if out_path else (EV / "results" / "metrics.json")
    BO.assert_write_permitted(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    return out_path
