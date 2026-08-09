"""Pure encodings of frozen methodology rules. NOT a harness component.

Each function here is a frozen rule written down executably so it can be tested before any
result-bearing component consumes it. Nothing here reads a PDF, an architecture output, an
oracle, or the holdout; nothing here makes a decision. `x15_methodology_contracts.py` is the
test.

    A28.1   adequacy occurrence counting -- the union of A27.1 source-position keys
    A28.2   the 4.5 adequacy state machine
    A28.3   canonical PRE-BLINDING stimulus identity, and the blind id derived from it
    A28.4   frozen renderer scale
    A27.7   domain-separated deterministic ranking
"""

from __future__ import annotations

import hashlib
import json

# ----------------------------------------------------------------- A27.7 determinism

SELECTION_SEED = 20260807


def canonical(obj) -> str:
    """One canonical serialization for every identity tuple. Tested, not assumed.

    `sort_keys` + no whitespace + explicit list/tuple coercion, so the same logical identity
    can never hash two ways because a caller passed a tuple where another passed a list.
    """

    def norm(o):
        if isinstance(o, (list, tuple)):
            return [norm(x) for x in o]
        if isinstance(o, dict):
            return {str(k): norm(v) for k, v in o.items()}
        return o

    return json.dumps(norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def rank_key(namespace: str, item_identity) -> str:
    """A27.7: deterministic rank of one item within one purpose. No RNG, no input order."""
    return hashlib.sha256(f"{namespace}|{SELECTION_SEED}|{canonical(item_identity)}".encode()).hexdigest()


def select(namespace: str, identities: list, k: int) -> list:
    """The first `k` identities by domain-separated rank. Order-independent and reproducible."""
    return [i for _r, i in sorted((rank_key(namespace, i), i) for i in identities)][:k]


def order(namespace: str, identities: list) -> list:
    """Full deterministic ordering, used for blind presentation order."""
    return [i for _r, i in sorted((rank_key(namespace, i), i) for i in identities)]


# ------------------------------------------------- A28.3 canonical stimulus identity


def base_stimulus_identity(document_sha256: str, page_number: int, region_ordinal: int):
    return ("region", document_sha256, page_number, region_ordinal)


def control_stimulus_identity(
    control_kind: str, source_fixture_sha256: str, page_number: int, region_ordinal: int, control_variant: str
):
    return ("control", control_kind, source_fixture_sha256, page_number, region_ordinal, control_variant)


def r1_repeat_identity(base_identity):
    return ("r1-repeat", list(base_identity))


def blind_id(final_stimulus_identity) -> str:
    """The adjudicator-facing ALIAS, derived AFTER all selection is settled.

    It exists only so the adjudicator cannot infer provenance. It must never determine
    membership, repeat selection, audit selection or presentation order -- those all rank
    canonical identities. `x15` proves that by re-deriving every selection under a different
    blind-id scheme and requiring identical results.
    """
    return hashlib.sha256(f"blind-id|{SELECTION_SEED}|{canonical(final_stimulus_identity)}".encode()).hexdigest()[:16]


class BlindIdCollision(Exception):
    """A30.5 -- two distinct realized stimuli were assigned the same adjudicator-facing id."""


class DuplicateStimulusIdentity(Exception):
    """A30.5 -- the realized stimulus set contains the same canonical identity twice."""


def assert_realized_blind_ids_unique(final_identities) -> dict:
    """A30.5 -- blind ids must be unique over the COMPLETE REALIZED stimulus set.

    Called before any oracle artifact is committed and before adjudication begins; returns
    `blind id -> canonical identity` when clean and RAISES otherwise.

    WHY A SYNTHETIC UNIQUENESS CHECK WAS NOT ENOUGH. x15 shows the scheme separates a
    handful of constructed identities. That is a property of those identities, not a proof
    about the set the study will actually build, which is not known until selection,
    controls and repeats have all been resolved. The invariant has to be asserted on the
    realized set or it is not asserted at all.

    WHY A COLLISION IS A BUILD FAILURE AND NOTHING ELSE. Overwriting loses a stimulus;
    merging fuses two adjudications; last-write-wins silently picks one. Salting or
    re-rolling the alias after seeing the stimulus set would let the set choose the scheme,
    which is exactly the influence A28.3 removed when it stopped blind ids from steering
    sampling. So this refuses deterministically and requires review.
    """
    mapping: dict[str, str] = {}
    seen: set[str] = set()
    for ident in final_identities:
        form = canonical(ident)
        if form in seen:
            raise DuplicateStimulusIdentity(f"identity appears twice in the realized set: {form}")
        seen.add(form)
        bid = blind_id(ident)
        if bid in mapping:
            raise BlindIdCollision(f"blind id {bid} claimed by both {mapping[bid]} and {form}")
        mapping[bid] = form
    return mapping


# ------------------------------------------------------------- A28.4 renderer scale

PRIMARY_DPI = 300
R1_REPEAT_DPI = 330  # 300 x 1.10, fixed pre-execution; higher so the repeat is not less legible


def required_dpi(is_r1_repeat: bool) -> int:
    return R1_REPEAT_DPI if is_r1_repeat else PRIMARY_DPI


# --------------------------------------------------- A28.1 / A28.2 section 4.5 adequacy

ADEQUACY_KINDS = frozenset({"account", "agency", "grouping"})
# A28.1 restricts adequacy to the P-head population. A30.4 makes that restriction
# EXECUTABLE here rather than an obligation on callers -- see `filter_keys`.
P_HEAD = "P-head"


def adequacy_occurrences(h_keys, x_keys) -> int:
    """|H_keys union X_keys| over A27.1 source-position occurrence keys.

    Symmetric: neither arm's failure can remove a key the other emitted. Counts one physical
    occurrence once even when both arms emit it, because the key is a source position rather
    than an arm's output. No text similarity and no oracle result enters this.

    Callers pass keys already restricted by `filter_keys`, which since A30.4 applies BOTH
    the P-head population restriction and the account / agency / grouping kind restriction
    itself rather than trusting the caller to have done it.

    Each key is an A30.1 occurrence identity, whose fourth component is the absolute
    `start_ngid` -- so two occurrences beginning on one physical line stay distinct, and a
    missing earlier occurrence cannot renumber a later one.
    """
    return len(set(h_keys) | set(x_keys))


def filter_keys(keyed) -> set:
    """Keep only P-head account/agency/grouping occurrences (A28.1, executable by A30.4).

    Input is `(key, kind, population)`.

    KIND. The design pilot's "heading occurrences emitted" quantity used exactly those three
    classes; the later oracle codebook is broader, and widening the adequacy denominator to
    title/division/section would silently make the holdout look more adequate than the
    frozen quantity it is compared against.

    POPULATION. A28.1 restricts adequacy to P-head, but until A30.4 this function filtered
    on kind alone and its docstring made the population restriction an obligation on the
    CALLER. A caller obligation is not a gate: it cannot fail, and nothing in the harness
    would have reported a P-robust document silently inflating the adequacy count -- the
    number would simply have been larger, and larger reads as *more* adequate. Applying both
    restrictions here makes the frozen clause falsifiable, and x15 proves it by adding
    arbitrarily many P-robust adequacy-kind keys and requiring the count not to move.
    """
    return {key for key, kind, population in keyed if population == P_HEAD and kind in ADEQUACY_KINDS}


# ------------------------------------------------------- A36.7 the M5 role coarsening

M5_LEAF = "LEAF"
M5_CONTAINER = "CONTAINER"
M5_UNSCORABLE = "UNSCORABLE"

# The adjudicator records the FINE section 5.3 role; M5 alone coarsens it. HARNESS-PLAN 3's
# "coarse leaf/container role" described this SCORING map, not what the adjudicator writes down
# -- asking only leaf-vs-container would discard information 5.3 requires and could not be
# recovered later.
ORACLE_ROLE_TO_M5 = {
    "account": M5_LEAF,
    "section": M5_LEAF,
    "agency": M5_CONTAINER,
    "grouping": M5_CONTAINER,
    "title": M5_CONTAINER,
    "division": M5_CONTAINER,
    "other": M5_UNSCORABLE,
}

# Production's emitted anchor kinds. COMPLETE against `AnchorKind`, which x21 asserts against
# the production Literal rather than trusting this comment -- a kind added to production later
# must FAIL a control instead of arriving silently as an unmapped role.
#
# `division` is an oracle role and an `Anchor` FIELD, never an emitted KIND, which is why it
# appears in the oracle map only.
EMITTED_KIND_TO_M5 = {
    "account": M5_LEAF,
    "section": M5_LEAF,
    "major": M5_CONTAINER,
    "agency": M5_CONTAINER,
    "grouping": M5_CONTAINER,
    "title": M5_CONTAINER,
    "subsection": M5_UNSCORABLE,
    "preamble": M5_UNSCORABLE,
}


class UnknownRole(Exception):
    """A36.7 -- a role outside the frozen map. Refuses; never silently UNSCORABLE.

    Mapping an unknown role to UNSCORABLE would quietly SHRINK the M5 denominator, and a
    smaller denominator reads as a cleaner result rather than as a defect.
    """


def m5_oracle_role(role: str) -> str:
    if role not in ORACLE_ROLE_TO_M5:
        raise UnknownRole(f"oracle role not in the frozen A36.7 map: {role!r}")
    return ORACLE_ROLE_TO_M5[role]


def m5_emitted_kind(kind: str) -> str:
    if kind not in EMITTED_KIND_TO_M5:
        raise UnknownRole(f"emitted kind not in the frozen A36.7 map: {kind!r}")
    return EMITTED_KIND_TO_M5[kind]


def m5_scorable(oracle_role: str, emitted_kind: str) -> bool:
    """A36.7 -- in the M5 denominator only when BOTH sides coarsen to LEAF or CONTAINER."""
    return M5_UNSCORABLE not in (m5_oracle_role(oracle_role), m5_emitted_kind(emitted_kind))


def m5_agreement(oracle_role: str, emitted_kind: str):
    """Do the two sides agree after coarsening? `None` when the pair is out of scope.

    `None` rather than False: an excluded pair is not a disagreement, and counting it as one
    would penalise the architecture for a role M5 was never licensed to score.
    """
    if not m5_scorable(oracle_role, emitted_kind):
        return None
    return m5_oracle_role(oracle_role) == m5_emitted_kind(emitted_kind)


def adequacy(strata_filled: int, occurrences: int) -> str:
    """A28.2 -- the 4.5 rows as an ORDERED, EXHAUSTIVE state machine. No threshold changed.

    The frozen table left `>= 7 strata` with 300-799 occurrences matching no row, and
    `5-6 strata` with `< 300` matching two rows with no precedence. Ordering the failure
    condition first resolves the overlap conservatively and makes the space total.
    """
    if strata_filled < 5 or occurrences < 300:
        return "INADEQUATE"
    if strata_filled >= 7 and occurrences >= 800:
        return "GENERALISABLE"
    return "LIMITED"
