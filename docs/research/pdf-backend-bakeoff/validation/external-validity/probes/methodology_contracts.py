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


# ------------------------------------------------------------- A28.4 renderer scale

PRIMARY_DPI = 300
R1_REPEAT_DPI = 330  # 300 x 1.10, fixed pre-execution; higher so the repeat is not less legible


def required_dpi(is_r1_repeat: bool) -> int:
    return R1_REPEAT_DPI if is_r1_repeat else PRIMARY_DPI


# --------------------------------------------------- A28.1 / A28.2 section 4.5 adequacy

ADEQUACY_KINDS = frozenset({"account", "agency", "grouping"})


def adequacy_occurrences(h_keys, x_keys) -> int:
    """|H_keys union X_keys| over A27.1 source-position occurrence keys.

    Symmetric: neither arm's failure can remove a key the other emitted. Counts one physical
    occurrence once even when both arms emit it, because the key is a source position rather
    than an arm's output. No text similarity and no oracle result enters this.

    Callers must pass keys already restricted to P-head documents and to the account /
    agency / grouping kinds -- `filter_keys` does that and is tested.
    """
    return len(set(h_keys) | set(x_keys))


def filter_keys(keyed_kinds) -> set:
    """Keep only account/agency/grouping occurrences, per A28.1.

    The design pilot's "heading occurrences emitted" quantity used exactly those three
    classes; the later oracle codebook is broader, and widening the adequacy denominator to
    title/division/section would silently make the holdout look more adequate than the
    frozen quantity it is compared against.
    """
    return {key for key, kind in keyed_kinds if kind in ADEQUACY_KINDS}


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
