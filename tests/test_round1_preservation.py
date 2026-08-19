"""Round-1 matching, pinned against an oracle that cannot ask production what the rule is.

ADR 0020 Slice B0. No production behaviour changes here; this is the harness the round-1
separation will be measured against, built while ``match_nodes`` is still the legacy
implementation so the expectation is captured before anything moves.

## Why a transcription rather than a wrapper

The one failure a behaviour-preserving extraction can actually have is that the extraction
changed the rule. An oracle that called the extracted stage could not detect that, because
it would move with it. So ``legacy_*`` below is a **transcription of the composition** in
``diff_bill.match_nodes`` / ``_match_collision_group`` / ``_similarity_pair`` as they stood
at ``0ff0eb1e``, and it must never be replaced by a call to those functions or to whatever
round-1 retrieval, evidence and assignment stages later replace them.

It composes the same leaf primitives deliberately -- ``text_similarity`` and a transcribed
``_normalize_text``. Those have their own tests. What this guards is the *composition*: the
grouping, the division partition, the greedy competition, the tie direction, the
cross-division fallback and its population, the leftovers, and the order every one of them
is emitted in. An inverted comparison, a dropped gate, a reordered branch or a substituted
index space all surface here.

:func:`test_the_oracle_names_no_round_1_production_symbol` enforces the independence
structurally rather than by convention. Its refusal list was written ahead of the stages: it
already named what B1, B2 and B3 went on to introduce, so wiring the oracle to a stage that
did not exist yet was refused in advance rather than after the fact.

## Identity: ADR 0019, not ``element_id``

Every observation in the frozen trace is addressed by ``(side, node_ordinal)``, where the
ordinal is the node's index in the parser's COMPLETE emitted sequence for that side, and the
artifact records the ``source_sha256`` of each side plus the derived ``parser_revision`` that
together scope those ordinals -- the identity [ADR
0019](../docs/decisions/0019-observation-identity.md) requires of a stored artifact recording
a judgment about parsed observations.

An earlier version of this file keyed the trace on ``element_id``. That was a false green, not
a stylistic choice. ``bill_tree`` reads the attribute as ``attrib.get("id", "")``, so a
repeated or empty id is representable, and ADR 0019 keeps ``element_id`` as traceability
metadata precisely because its uniqueness is a sampled property of externally authored markup.
Two observations sharing an id make an element-id-keyed stream unable to distinguish a matcher
that exchanges their partners:
:func:`test_a_swap_between_same_id_observations_is_invisible_to_element_ids` builds that pair,
swaps them, and shows the old representation textually unchanged while the ordinal
representation moves.

Local ``(oi, ni)`` positions are a separate thing and stay separate: they are legacy assignment
ORDERING machinery, #590 measured that substituting parser ordinals for them changes the
selected correspondence, and they must not be replaced by ordinals.

## What is frozen, and what it gates

``tests/data/round1_legacy_trace.json`` holds, per committed version pair, the ADR 0019
provenance above plus a SHA-256 over the oracle's full ordered trace and the structural counts
behind it. It is generated from the ORACLE, never from production, so production is always
being compared against an independent expectation. Provenance is checked before any judgment is
compared, and a drift in either source bytes or parser revision fails closed rather than
rebinding the stored judgment to a different parse.

Three tests form the triangle:

- :func:`test_the_oracle_reproduces_the_frozen_trace` -- the oracle has not drifted. This is
  what stops someone "fixing" the oracle to agree with a changed production.
- :func:`test_production_reproduces_the_frozen_pairing_stream` -- the durable gate. Whatever
  round 1 becomes internally, ``match_nodes``' observable output must still be this.
- :func:`test_production_internals_reproduce_the_frozen_invocation_trace` -- today's
  corroboration at the stage boundary. It wraps the legacy internals, which exist now and
  may not after B1; B1 and B2 replace it with assertions on their own stage outputs,
  compared against the same frozen invocation trace.

## The two behaviours the corpus cannot see

Measured in the round-1 audit (§4 and §5, which retain the figures) and now bound by the two
synthetic fixtures below rather than by a probe -- the probe that first measured this was
retired at closure, and :func:`test_the_corpus_cannot_see_the_two_fixture_bound_mutations` is
what keeps the claim honest if the corpus ever grows a case that exercises either. Over all 27 committed
version pairs, **no** observation left over by within-division assignment ever reaches the
cross-division fallback (238 groups produce leftovers, 30 groups reach the fallback, the
sets are disjoint), and **every** list handed to the greedy is already in ascending parser
ordinal order. Both are accidents of this corpus, not properties of the code.

So two synthetic fixtures are load-bearing rather than illustrative. Without them, an
implementation that dropped the assignment-leftover path, or that substituted parser
ordinals for local positions, is byte-identical on all 27 canonical digests and passes every
other gate in this repository.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import textwrap
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pytest

from deltatrack.bill_tree import BillNode, normalize_bill
from deltatrack.diff_bill import (
    GroupAssignment,
    RetrievedPopulation,
    SelectedLink,
    assign_group,
    group_correspondence_evidence,
    match_nodes,
    match_nodes_with_retrieval,
    match_nodes_with_stage_outputs,
    observation_registry,
    retrieve_cross_division_population,
    retrieve_unique_path_population,
    retrieve_within_division_populations,
)
from deltatrack.matching import NEW, OLD, CandidateSet, CorrespondenceEvidence, RetrieverInvocation
from deltatrack.similarity import text_similarity
from tests.conftest import assert_manifest_committed, manifest_version_pairs, manifest_xml_ids
from tests.corpus_paths import DATA_DIR, PROJECT_ROOT

_FROZEN = DATA_DIR / "round1_legacy_trace.json"
_PROBES = PROJECT_ROOT / "docs" / "research" / "provision-matching" / "probes"


# --- The oracle: the legacy composition, transcribed -----------------------------------
#
# Nothing below may call diff_bill. See the module docstring and the independence guard.


def legacy_normalize(text: str) -> str:
    """``diff_bill._normalize_text``, transcribed."""
    return " ".join(text.split())


class Recorder:
    """Collects the ordered trace as the oracle runs, and counts similarity calls.

    **Every observation in the trace is addressed by its ADR 0019 node ordinal**, which is its
    zero-based index in the parser's COMPLETE emitted sequence for that side. The map is built
    once, in :func:`oracle_trace`, from the whole ``tree.nodes`` list; nothing here may derive
    an ordinal from a collision subgroup, a division sublist, an invocation-local population or
    a position in the pairing stream. ADR 0019 names indexing a filtered or re-sorted view as a
    genuine hazard precisely because the resulting address looks valid and points elsewhere.

    ``element_id`` is deliberately NOT the key. ADR 0019 records it as traceability metadata and
    refuses it as identity: ``bill_tree`` reads it as ``attrib.get("id", "")``, so an empty one
    is already representable, and its uniqueness is a sampled property of externally authored
    markup rather than a contract. A trace keyed on it cannot distinguish two observations that
    share an id, which is the false green
    :func:`test_a_swap_between_same_id_observations_is_invisible_to_element_ids` demonstrates.

    The similarity count is its own assertion rather than a by-product: the 1x1 shortcut's whole
    effect is that no ratio is computed, and that is a performance property the pairing stream
    cannot show.
    """

    def __init__(self, ordinals: dict[int, int] | None = None) -> None:
        self.invocations: list[dict] = []
        self.unique_selections: list[list[int]] = []
        self.similarity_calls = 0
        # `None` means SELECTION-ONLY: the oracle is being run for its pairing behaviour rather
        # than to produce a trace, which is what the production-injection controls need. It is a
        # distinct state from "an empty map", because an empty map would silently address every
        # node as unknown; here no address is ever requested.
        self.tracing = ordinals is not None
        self.ordinals = ordinals if ordinals is not None else {}

    @classmethod
    def selection_only(cls) -> Recorder:
        """A recorder for running the oracle as a drop-in for production's assigner, recording nothing."""
        return cls(None)

    def population(self, nodes: list[BillNode]) -> list[int]:
        """The addresses of an invocation population, or nothing when not tracing."""
        return [self.ordinal(n) for n in nodes] if self.tracing else []

    def ordinal(self, node: BillNode) -> int:
        """The node's address, refusing one the complete emitted sequence never carried.

        Raises rather than returning ``None``. A missing address means the oracle is holding a
        node from outside the parse it is describing, and a trace row silently carrying ``null``
        would compare equal to another such row -- reintroducing exactly the collapse that
        keying on ``element_id`` causes.
        """
        address = self.ordinals.get(id(node))
        if address is None:
            raise ValueError(
                f"node {node.element_id!r} is absent from the complete emitted sequence this trace "
                "addresses; its ADR 0019 ordinal cannot be derived"
            )
        return address

    def similarity(self, a: str, b: str) -> float:
        self.similarity_calls += 1
        return text_similarity(a, b)


def legacy_similarity_pair(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
    rec: Recorder,
    phase: str,
    variant: frozenset[str] = frozenset(),
) -> list[tuple[BillNode | None, BillNode | None]]:
    """``diff_bill._similarity_pair``, transcribed, with one hook per negative control."""
    # Populations are named by complete-sequence ordinal. `selected`, `left_old` and `left_new`
    # stay LOCAL positions into these lists: they are legacy assignment-order machinery, and #590
    # measured that substituting parser ordinals for them changes the selected correspondence.
    # The two coexist deliberately -- identity is the ordinal, ordering policy is the position.
    record: dict = {
        "phase": phase,
        "old": rec.population(old_nodes),
        "new": rec.population(new_nodes),
        "candidates": None,
        "selected": [],
        "left_old": [],
        "left_new": [],
    }

    if not old_nodes and not new_nodes:
        record["branch"] = "both_empty"
        rec.invocations.append(record)
        return []
    if not old_nodes:
        record["branch"] = "old_empty"
        record["left_new"] = list(range(len(new_nodes)))
        rec.invocations.append(record)
        return [(None, n) for n in new_nodes]
    if not new_nodes:
        record["branch"] = "new_empty"
        record["left_old"] = list(range(len(old_nodes)))
        rec.invocations.append(record)
        return [(o, None) for o in old_nodes]
    if len(old_nodes) == 1 and len(new_nodes) == 1 and "shortcut_computes_similarity" not in variant:
        record["branch"] = "shortcut_1x1"
        record["selected"] = [[0, 0]]
        rec.invocations.append(record)
        return [(old_nodes[0], new_nodes[0])]

    record["branch"] = "greedy"
    candidates: list[tuple[float, int, int]] = []
    for oi, o in enumerate(old_nodes):
        o_norm = legacy_normalize(o.body_text)
        for ni, n in enumerate(new_nodes):
            n_norm = legacy_normalize(n.body_text)
            candidates.append((rec.similarity(o_norm, n_norm), oi, ni))
    record["candidates"] = [[round(s, 12), oi, ni] for s, oi, ni in candidates]

    # --- ordering, and the mutations of it the controls exercise ---
    if "ordinal_tiebreak" in variant:
        o_ord = [rec.ordinal(n) for n in old_nodes]
        n_ord = [rec.ordinal(n) for n in new_nodes]
        candidates.sort(key=lambda c: (c[0], o_ord[c[1]], n_ord[c[2]]), reverse=True)
    elif "ascending_tie" in variant:
        candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    elif "candidate_set_order" in variant:
        o_ord = [rec.ordinal(n) for n in old_nodes]
        n_ord = [rec.ordinal(n) for n in new_nodes]
        candidates.sort(key=lambda c: (o_ord[c[1]], n_ord[c[2]]))
    else:
        candidates.sort(reverse=True)

    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    pairs: list[tuple[BillNode | None, BillNode | None]] = []
    selected: list[list[int]] = []

    for _sim, oi, ni in candidates:
        if oi in claimed_old or ni in claimed_new:
            continue
        claimed_old.add(oi)
        claimed_new.add(ni)
        selected.append([oi, ni])

    if "reorder_winners" in variant:
        selected = list(reversed(selected))
    if "swap_first_two_old_partners" in variant and len(selected) >= 2:
        # Exchange which OLD observation each of the first two winners corresponds to, leaving
        # the emitted row order and both NEW partners exactly where they were. Against a fixture
        # whose two old observations share an element_id, the element-id projection of the
        # stream is unchanged and the ordinal projection is not -- which is the whole point.
        (a_old, a_new), (b_old, b_new) = selected[0], selected[1]
        selected = [[b_old, a_new], [a_old, b_new], *selected[2:]]
    pairs.extend((old_nodes[oi], new_nodes[ni]) for oi, ni in selected)
    record["selected"] = selected

    left_old = [oi for oi in range(len(old_nodes)) if oi not in claimed_old]
    left_new = [ni for ni in range(len(new_nodes)) if ni not in claimed_new]
    if "reorder_leftovers" in variant:
        left_old = list(reversed(left_old))
        left_new = list(reversed(left_new))
    record["left_old"] = left_old
    record["left_new"] = left_new

    pairs.extend((old_nodes[oi], None) for oi in left_old)
    pairs.extend((None, new_nodes[ni]) for ni in left_new)

    rec.invocations.append(record)
    return pairs


def legacy_collision_group(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
    rec: Recorder,
    variant: frozenset[str] = frozenset(),
) -> list[tuple[BillNode | None, BillNode | None]]:
    """``diff_bill._match_collision_group``, transcribed."""
    if "flatten_divisions" in variant:
        # Drops the division partition entirely: one candidate population per match_path
        # group. Covers both "flatten division and cross-division retrieval" and "drop
        # division provenance" -- they are the same mechanism.
        return legacy_similarity_pair(old_nodes, new_nodes, rec, "flattened", variant)

    old_by_div: dict[str, list[BillNode]] = defaultdict(list)
    new_by_div: dict[str, list[BillNode]] = defaultdict(list)
    for node in old_nodes:
        old_by_div[node.division_key].append(node)
    for node in new_nodes:
        new_by_div[node.division_key].append(node)

    pairs: list[tuple[BillNode | None, BillNode | None]] = []
    unmatched_old: list[BillNode] = []
    unmatched_new: list[BillNode] = []
    # Observations a one-sided division contributed, as distinct from ones ASSIGNMENT left
    # over. Production does not draw this line; the oracle does, so a control can suppress
    # exactly one of the two populations.
    structural_old: list[BillNode] = []
    structural_new: list[BillNode] = []

    all_divs = dict.fromkeys(list(old_by_div.keys()) + list(new_by_div.keys()))

    for group_key in all_divs:
        div_old = old_by_div.get(group_key, [])
        div_new = new_by_div.get(group_key, [])

        if not div_old:
            unmatched_new.extend(div_new)
            structural_new.extend(div_new)
        elif not div_new:
            unmatched_old.extend(div_old)
            structural_old.extend(div_old)
        else:
            for o, n in legacy_similarity_pair(div_old, div_new, rec, "within", variant):
                if o is None:
                    unmatched_new.append(n)
                elif n is None:
                    unmatched_old.append(o)
                else:
                    pairs.append((o, n))

    # The population the fallback actually gets to consider. Identical to the unmatched lists
    # in production; a control narrows it WITHOUT removing anything from the unmatched lists,
    # because an observation the fallback never sees is still an unmatched observation and
    # still has to be emitted. Conflating the two deletes observations from the stream, which
    # is a different defect wearing this one's name.
    cross_old, cross_new = unmatched_old, unmatched_new
    if "no_assignment_leftovers" in variant:
        # The false-green this harness exists for: the fallback sees only observations no
        # division ever paired, never one that within-division ASSIGNMENT declined to claim.
        cross_old = [n for n in unmatched_old if any(n is s for s in structural_old)]
        cross_new = [n for n in unmatched_new if any(n is s for s in structural_new)]
    if "extra_cross_candidate" in variant:
        # Admits a pair the fallback never considers: an observation already paired inside a
        # division is offered to the cross round as well.
        cross_old = list(cross_old) + [o for o, _n in pairs][:1]

    if cross_old and cross_new:
        claimed: set[int] = set()
        for o, n in legacy_similarity_pair(cross_old, cross_new, rec, "cross", variant):
            if o is not None and n is not None:
                pairs.append((o, n))
                claimed.add(id(o))
                claimed.add(id(n))
        # Rebuild from the original lists rather than from the invocation's leftovers, so an
        # observation withheld from the pool keeps its place. Where the pool IS the unmatched
        # list -- production, and every unmutated run -- this is the same sequence the
        # invocation returned, in the same order.
        unmatched_old = [o for o in unmatched_old if id(o) not in claimed]
        unmatched_new = [n for n in unmatched_new if id(n) not in claimed]

    pairs.extend((o, None) for o in unmatched_old)
    pairs.extend((None, n) for n in unmatched_new)
    return pairs


def legacy_match_nodes(old_nodes, new_nodes, rec: Recorder, variant: frozenset[str] = frozenset()):
    """``diff_bill.match_nodes``, transcribed. Takes node lists, not trees."""
    old_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    new_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    for node in old_nodes:
        old_groups[node.match_path].append(node)
    for node in new_nodes:
        new_groups[node.match_path].append(node)

    all_paths = dict.fromkeys(list(old_groups.keys()) + list(new_groups.keys()))
    pairs: list[tuple[BillNode | None, BillNode | None]] = []

    for path in all_paths:
        group_old = old_groups.get(path, [])
        group_new = new_groups.get(path, [])

        if len(group_old) <= 1 and len(group_new) <= 1:
            if "unique_path_needs_same_division" in variant and group_old and group_new:
                # A plausible-looking "improvement": require the unique pairing to agree on
                # division. It changes 730 selections on the committed corpus.
                if group_old[0].division_key != group_new[0].division_key:
                    pairs.append((group_old[0], None))
                    pairs.append((None, group_new[0]))
                    continue
            if group_old and group_new:
                if rec.tracing:
                    rec.unique_selections.append([rec.ordinal(group_old[0]), rec.ordinal(group_new[0])])
            pairs.append((group_old[0] if group_old else None, group_new[0] if group_new else None))
        else:
            pairs.extend(legacy_collision_group(group_old, group_new, rec, variant))

    return pairs


# --- Trace shape and digest -------------------------------------------------------------


def complete_sequence_ordinals(old_nodes: list[BillNode], new_nodes: list[BillNode]) -> dict[int, int]:
    """The ADR 0019 address of every node, built from the COMPLETE emitted sequences.

    The only place an ordinal is minted. It is ``enumerate`` over the whole ``tree.nodes`` list
    for each side and nothing else -- never a collision subgroup, a division sublist, an
    invocation population or a stream position, all of which are filtered or re-sorted views and
    would yield an address that looks valid while naming a different node.

    Keyed on ``id(node)`` for the duration of one run, which is a run-local mechanism for
    recovering the ordinal and NOT ADR 0019 observation identity. Both trees hold every node
    alive for the whole comparison, and nothing here is persisted; the artifact stores the
    resulting integers alongside the source digest and parser revision that scope them.
    ``scripts/probe_node_identity.py`` sets the precedent.

    Two nodes of one side sharing an object would collapse two addresses onto one, so it is
    refused rather than assumed away.
    """
    ordinals: dict[int, int] = {}
    for side_nodes in (old_nodes, new_nodes):
        seen: dict[int, int] = {}
        for index, node in enumerate(side_nodes):
            if id(node) in seen:
                raise ValueError(
                    f"one node object appears at ordinals {seen[id(node)]} and {index} of a single "
                    "side; two observations would collapse onto one address"
                )
            seen[id(node)] = index
        ordinals.update(seen)
    return ordinals


def oracle_trace(old_nodes, new_nodes, variant: frozenset[str] = frozenset()) -> dict:
    """The oracle's full ordered trace for one comparison, addressed by ADR 0019 ordinal.

    ``old_nodes`` and ``new_nodes`` must be the complete emitted sequences for their side --
    ``tree.nodes``, not a filtered view. That is what makes every integer in the result a
    legitimate node ordinal.
    """
    rec = Recorder(complete_sequence_ordinals(old_nodes, new_nodes))
    pairs = legacy_match_nodes(old_nodes, new_nodes, rec, variant)
    return {
        "stream": [
            [rec.ordinal(o) if o is not None else None, rec.ordinal(n) if n is not None else None] for o, n in pairs
        ],
        "unique_selections": [list(p) for p in rec.unique_selections],
        "invocations": rec.invocations,
        "similarity_calls": rec.similarity_calls,
    }


def element_id_projection(old_nodes, new_nodes, variant: frozenset[str] = frozenset()) -> list[list[str | None]]:
    """The SUPERSEDED representation: the pairing stream keyed by ``element_id``.

    Retained for exactly one purpose -- to demonstrate, in
    :func:`test_a_swap_between_same_id_observations_is_invisible_to_element_ids`, that it cannot
    distinguish a mutation the ordinal representation does. Nothing else may assert on it and no
    frozen digest derives from it.
    """
    rec = Recorder(complete_sequence_ordinals(old_nodes, new_nodes))
    pairs = legacy_match_nodes(old_nodes, new_nodes, rec, variant)
    return [[o.element_id if o is not None else None, n.element_id if n is not None else None] for o, n in pairs]


def trace_digest(trace: dict) -> str:
    return hashlib.sha256(json.dumps(trace, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def trace_counts(trace: dict) -> dict:
    """Structural counts beside the digest, so a failure reads as a diagnosis.

    They assert nothing the digest does not. They exist so a red gate says "cross
    invocations 30 -> 29" rather than "two hex strings differ".
    """
    inv = trace["invocations"]
    return {
        "pairings": len(trace["stream"]),
        "unique_selections": len(trace["unique_selections"]),
        "invocations": len(inv),
        "within": sum(1 for i in inv if i["phase"] == "within"),
        "cross": sum(1 for i in inv if i["phase"] == "cross"),
        "shortcut_1x1": sum(1 for i in inv if i["branch"] == "shortcut_1x1"),
        "greedy": sum(1 for i in inv if i["branch"] == "greedy"),
        "selected_links": sum(len(i["selected"]) for i in inv),
        "similarity_calls": trace["similarity_calls"],
    }


def stream_digest(stream: list) -> str:
    """A digest over the ordered pairing stream alone, which is the durable production gate.

    The literal stream is 31,908 rows over the committed corpus and serializes to ~2.8 MB,
    which is not a reviewable committed artifact -- the same argument
    ``test_canonical_baseline`` makes for storing a digest. Diagnosis does not depend on the
    stored form: the oracle is right here, so a failing comparison recomputes the expected
    stream and names the first row that moved.
    """
    return hashlib.sha256(json.dumps(stream, separators=(",", ":")).encode()).hexdigest()


def source_sha256(path: Path) -> str:
    """SHA-256 of the source bytes, per ADR 0019.

    The file is committed under ``tests/corpus/``, so git already pins the bytes and this is
    *recorded* rather than relied on for storage -- ADR 0015's reservation, cashed in here.
    What it buys is that the stored judgment names the source it was made about, so a fixture
    swapped underneath it fails closed instead of silently rebinding.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def parser_revision() -> str:
    """The parser revision this trace's ordinals were derived under, DERIVED not declared.

    ADR 0019 requires a revision that "changes whenever code capable of changing the emitted
    observations changes", and accepts a content hash over the parser entry module and its
    transitive ``deltatrack`` imports. That mechanism already exists in this repository, in
    ``docs/research/provision-matching/probes/study2_frame.py``, and is reused rather than
    reimplemented -- a second copy of an identity rule is how two artifacts come to disagree
    about what parse they describe.

    Loaded the same way ``tests/test_pass2_eval_contract.py`` loads it. Its transitive set is
    ``bill_tree`` plus the two PDF parser modules ``bill_tree`` imports, and notably NOT
    ``diff_bill``: a matching change does not move the revision, so the two failure modes stay
    distinguishable. A matcher regression reddens the digests; a parser change reddens
    provenance and says the stored judgment is about a different emitted sequence.
    """
    spec = importlib.util.spec_from_file_location("_probe_study2_frame", _PROBES / "study2_frame.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parser_revision()


def frozen_record(old_path: Path, new_path: Path) -> dict:
    old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
    trace = oracle_trace(old_tree.nodes, new_tree.nodes)
    return {
        # ADR 0019 provenance: the two halves that scope every ordinal below.
        "old_source_sha256": source_sha256(old_path),
        "new_source_sha256": source_sha256(new_path),
        "parser_revision": parser_revision(),
        "sha256": trace_digest(trace),
        "stream_sha256": stream_digest(trace["stream"]),
        "counts": trace_counts(trace),
    }


def pair_key(old_path: Path, new_path: Path) -> str:
    return f"{old_path.parent.name}/{old_path.stem}->{new_path.stem}"


def load_frozen() -> dict:
    assert _FROZEN.exists(), (
        f"{_FROZEN} is missing. Generate it with:\n"
        "    UPDATE_ROUND1_TRACE=1 uv run pytest tests/test_round1_preservation.py"
    )
    return json.loads(_FROZEN.read_text())


def _regenerated() -> dict:
    pairs = manifest_version_pairs()
    assert pairs, "refusing to write a trace over zero version pairs"
    return {pair_key(o, n): frozen_record(o, n) for o, n in pairs}


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("UPDATE_ROUND1_TRACE"), reason="not in trace-update mode")
def test_regenerate_the_frozen_trace():
    """Opt-in regeneration, all-or-nothing, from the ORACLE and never from production."""
    _FROZEN.write_text(json.dumps(_regenerated(), indent=2, sort_keys=True) + "\n")


# --- Completeness floor ------------------------------------------------------------------


def test_manifest_fixtures_committed():
    assert_manifest_committed(manifest_version_pairs(), "round-1 preservation")


def test_the_frozen_trace_covers_every_manifested_pair():
    """A key naming no live fixture, or a live pair with no key, both fail closed."""
    frozen = load_frozen()
    live = {pair_key(o, n) for o, n in manifest_version_pairs()}
    assert set(frozen) == live, (
        f"frozen trace drifted from the manifest: only-frozen={sorted(set(frozen) - live)}, "
        f"only-live={sorted(live - set(frozen))}"
    )
    ids = manifest_xml_ids()
    for key in frozen:
        bill, stems = key.split("/", 1)
        for stem in stems.split("->"):
            assert f"{bill}/{stem}.xml" in ids, f"{key} names a fixture the manifest does not carry"


# --- The triangle -------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("old_path,new_path", manifest_version_pairs(), ids=lambda p: p.stem)
def test_the_oracle_reproduces_the_frozen_trace(old_path: Path, new_path: Path):
    """The oracle has not drifted from the expectation it produced.

    This is what stops the harness being repaired into agreement with a changed production:
    the frozen file is the fixed point, and both the oracle and production are measured
    against it.
    """
    frozen = load_frozen()[pair_key(old_path, new_path)]
    actual = frozen_record(old_path, new_path)
    assert actual["counts"] == frozen["counts"], f"{pair_key(old_path, new_path)}: counts moved"
    assert actual["sha256"] == frozen["sha256"], f"{pair_key(old_path, new_path)}: trace digest moved"


@pytest.mark.slow
@pytest.mark.parametrize("old_path,new_path", manifest_version_pairs(), ids=lambda p: p.stem)
def test_the_stored_judgment_names_the_parse_it_was_made_about(old_path: Path, new_path: Path):
    """ADR 0019 provenance, checked BEFORE any judgment is compared. Fails closed.

    A frozen ordinal means nothing on its own: it addresses a node inside one emitted sequence,
    produced from particular source bytes by a particular parser revision. If either moves, the
    stored digests describe a sequence that no longer exists, and comparing them would silently
    rebind a recorded judgment to a different subject -- the exact failure ADR 0019 was written
    for, where a parser change redefined what three stored observations meant.

    So this refuses rather than regenerates. A red here is not "update the fixture"; it is
    "the observation sequence moved, and the round-1 expectation has to be re-derived and
    re-reviewed against the new parse".
    """
    key = pair_key(old_path, new_path)
    frozen = load_frozen()[key]

    for label, path, field in (
        ("old", old_path, "old_source_sha256"),
        ("new", new_path, "new_source_sha256"),
    ):
        live = source_sha256(path)
        assert live == frozen[field], (
            f"{key}: the {label}-side source bytes changed ({frozen[field][:12]} -> {live[:12]}). "
            "Every ordinal in this record addresses the previous parse; re-derive the expectation "
            "rather than regenerating it to match."
        )

    live_revision = parser_revision()
    assert live_revision == frozen["parser_revision"], (
        f"{key}: the parser revision changed ({frozen['parser_revision'][:12]} -> {live_revision[:12]}), "
        "so the emitted observation sequence may differ and these ordinals may address different "
        "nodes. ADR 0019: a stored judgment is scoped to (source_sha256, parser_revision, ordinal). "
        "Re-derive and re-review; do not regenerate to make this green."
    )


@pytest.mark.slow
@pytest.mark.parametrize("field", ["old_source_sha256", "new_source_sha256", "parser_revision"])
def test_the_provenance_gate_can_fire(field: str, monkeypatch):
    """The negative control for the gate above, which has otherwise never rejected anything.

    Each provenance field is perturbed in the loaded artifact and the gate must refuse. Without
    this the check is an equality that has only ever been satisfied, and a typo in the field
    name would leave it comparing nothing while reading as protection.
    """
    old_path, new_path = manifest_version_pairs()[0]
    tampered = json.loads(_FROZEN.read_text())
    tampered[pair_key(old_path, new_path)][field] = "0" * 64
    monkeypatch.setitem(globals(), "load_frozen", lambda: tampered)

    with pytest.raises(AssertionError, match="source bytes changed|parser revision changed"):
        test_the_stored_judgment_names_the_parse_it_was_made_about(old_path, new_path)


@pytest.mark.slow
@pytest.mark.parametrize("old_path,new_path", manifest_version_pairs(), ids=lambda p: p.stem)
def test_production_reproduces_the_frozen_pairing_stream(old_path: Path, new_path: Path):
    """THE DURABLE GATE. Whatever round 1 becomes internally, this must still hold.

    Compares production's observable output -- the ordered pairing stream, each observation
    addressed by its ADR 0019 ordinal in the complete emitted sequence -- against the
    independently frozen expectation. It survives B1 and B2 because it names no internal
    function.

    **Addressed by ordinal, never by ``element_id``.** ADR 0019 keeps ``element_id`` as
    traceability metadata and refuses it as identity, and the refusal has teeth here: two
    observations sharing an id make an element-id-keyed stream unable to distinguish a matcher
    that exchanges their partners. See
    :func:`test_a_swap_between_same_id_observations_is_invisible_to_element_ids`.
    """
    key = pair_key(old_path, new_path)
    frozen = load_frozen()[key]
    old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
    ordinals = complete_sequence_ordinals(old_tree.nodes, new_tree.nodes)
    produced = [
        [ordinals[id(o)] if o is not None else None, ordinals[id(n)] if n is not None else None]
        for o, n in match_nodes(old_tree, new_tree)
    ]

    if stream_digest(produced) == frozen["stream_sha256"]:
        return

    # Only on failure: recompute the oracle's stream and name the first row that moved, so the
    # digest stays compact without costing the diagnosis.
    expected = oracle_trace(old_tree.nodes, new_tree.nodes)["stream"]
    where = next(
        (i for i, (a, b) in enumerate(zip(produced, expected)) if a != b),
        min(len(produced), len(expected)),
    )
    raise AssertionError(
        f"{key}: production's pairing stream differs from the frozen legacy expectation "
        f"({len(produced)} pairings vs {len(expected)}); first divergence at row {where}: "
        f"production={produced[where : where + 3]} expected={expected[where : where + 3]}"
    )


def observed_retrieval_populations(old_tree, new_tree) -> list[dict]:
    """The populations B1's RETRIEVAL STAGES emit, in order, addressed by ADR 0019 ordinal.

    Recorded at the new stage boundary rather than by wrapping ``_similarity_pair``. The
    pre-B1 version of this helper spied on the scorer and inferred each invocation's phase from
    a call counter; the phase is now a property of which retrieval function produced the
    population, so it is read rather than reconstructed.

    Only populations that actually form candidates are reported. A division present on one side
    only is a real retrieval output and is deliberately emitted by the stage, but it pairs
    nothing and runs no invocation, so it is not part of the invocation trace the oracle froze.
    """
    from deltatrack import diff_bill as db

    ordinals = complete_sequence_ordinals(old_tree.nodes, new_tree.nodes)
    seen: list[dict] = []
    real_within = db.retrieve_within_division_populations
    real_cross = db.retrieve_cross_division_population

    def record(population, phase):
        seen.append(
            {
                "phase": phase,
                "old": [ordinals[id(n)] for n in population.old],
                "new": [ordinals[id(n)] for n in population.new],
            }
        )

    def spy_within(old_nodes, new_nodes, registry):
        populations = real_within(old_nodes, new_nodes, registry)
        for population in populations:
            if population.forms_candidates:
                record(population, "within")
        return populations

    def spy_cross(unmatched_old, unmatched_new, registry):
        population = real_cross(unmatched_old, unmatched_new, registry)
        if population is not None:
            record(population, "cross")
        return population

    # Saved and restored here rather than through `monkeypatch`, which accumulates for the whole
    # test: across a corpus loop the second patch would wrap the FIRST iteration's spy, and that
    # spy holds the first pair's ordinal map. It fails loudly as a KeyError, but only because
    # the map is strict -- a looser bridge would have recorded the wrong addresses in silence.
    # Restoring per call also lets a mutation stay patched around this observer and compose.
    db.retrieve_within_division_populations = spy_within
    db.retrieve_cross_division_population = spy_cross
    try:
        match_nodes(old_tree, new_tree)
    finally:
        db.retrieve_within_division_populations = real_within
        db.retrieve_cross_division_population = real_cross
    return seen


@pytest.mark.slow
def test_the_retrieval_stages_emit_the_frozen_invocation_populations():
    """B1's stage boundary, against the SAME frozen expectation the pre-B1 internals met.

    The expectation is unchanged and was not regenerated for this slice: retrieval was named
    and extracted, so the populations it hands to assignment must be exactly the ones the fused
    implementation formed -- same membership, same order, same sequence of invocations.

    What moved is where the assertion is taken. It now reads the retrieval stages' own outputs,
    which is the boundary B2 consumes -- and it did survive the split of the fused scorer into
    :func:`group_correspondence_evidence` and :func:`assign_group`, unchanged and against this
    same frozen expectation.
    """
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        seen = observed_retrieval_populations(old_tree, new_tree)
        expected = [
            {"phase": i["phase"], "old": i["old"], "new": i["new"]}
            for i in oracle_trace(old_tree.nodes, new_tree.nodes)["invocations"]
        ]
        assert seen == expected, (
            f"{pair_key(old_path, new_path)}: the retrieval stages' populations differ from the frozen expectation"
        )
        checked += 1

    assert checked, "the invocation comparison ran over zero version pairs"


@pytest.mark.slow
@pytest.mark.parametrize("mutation", ["sorted_divisions", "sorted_fallback"])
def test_the_retrieval_stage_boundary_can_fail(mutation: str, monkeypatch):
    """The new stage-boundary test would otherwise only ever have been observed green.

    Two mutations a plausible B1 could have shipped, each tidying an order that turns out to be
    policy:

    ``sorted_divisions`` visits divisions in sorted key order instead of first-appearance order.
    ``sorted_fallback`` sorts the cross-division population instead of preserving the
    concatenation round 1a produced.

    Both leave every candidate PAIR intact and change only order, which is precisely the class
    of change a membership-only check would wave through.
    """
    from deltatrack import diff_bill as db

    real_within = db.retrieve_within_division_populations
    real_cross = db.retrieve_cross_division_population

    def sorted_divisions(old_nodes, new_nodes, registry):
        return tuple(sorted(real_within(old_nodes, new_nodes, registry), key=lambda p: p.division_key or ""))

    def sorted_fallback(unmatched_old, unmatched_new, registry):
        return real_cross(list(reversed(unmatched_old)), list(reversed(unmatched_new)), registry)

    if mutation == "sorted_divisions":
        monkeypatch.setattr(db, "retrieve_within_division_populations", sorted_divisions)
    else:
        monkeypatch.setattr(db, "retrieve_cross_division_population", sorted_fallback)

    moved = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        seen = observed_retrieval_populations(old_tree, new_tree)
        expected = [
            {"phase": i["phase"], "old": i["old"], "new": i["new"]}
            for i in oracle_trace(old_tree.nodes, new_tree.nodes)["invocations"]
        ]
        if seen != expected:
            moved.append(pair_key(old_path, new_path))

    assert moved, (
        f"the {mutation!r} mutation left every retrieved population identical, so the stage-boundary "
        "test cannot see a retrieval ordering regression"
    )


def test_assignment_never_receives_the_candidate_set():
    """Structural: ``CandidateSet`` order cannot become assignment order.

    ADR 0020's candidate set is canonically ordered by ordinal pair, and B0 measured that using
    that order as assignment order changes the selected links on 174 of 329 greedy invocations.
    The protection is the call signature: :func:`assign_group` is handed the ordered population
    and the evidence, holds no reference to the set, and so no ordering it carries can reach a
    selection.

    **The evidence stage now legitimately receives it, and that is the reviewed B2 correction.**
    The set is the admission authority -- nothing is described unless it holds the pair under the
    describing invocation -- so the guard cannot be "no stage sees the set". It is narrower and
    more exact: the set may gate *what* is described and may not order anything. Both halves are
    required here, so removing the parameter from the evidence stage reddens exactly as adding
    one to assignment does.

    Retargeted from ``_similarity_pair``, which B2 removed.
    """
    import inspect

    from deltatrack.diff_bill import _match_collision_group, _match_unique_path_group

    assert "candidates" not in inspect.signature(assign_group).parameters, (
        "assign_group takes the candidate set as a parameter; its canonical order is then one lookup "
        "away from the sequence it decides on"
    )
    assert "candidates" in inspect.signature(group_correspondence_evidence).parameters, (
        "the evidence stage no longer receives the candidate set, so retrieval's admission cannot "
        "constrain what reaches assignment"
    )

    # Both orchestrators, because B3 gave the unique path its own. A guard that inspected only the
    # collision one would have gone on passing while the new call site handed assignment the set.
    staged = ("group_correspondence_evidence", "assign_group")
    for orchestrator in (_match_collision_group, _match_unique_path_group):
        tree = ast.parse(textwrap.dedent(inspect.getsource(orchestrator)))
        reached = set()
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                continue
            if call.func.id not in staged:
                continue
            reached.add(call.func.id)
            if call.func.id != "assign_group":
                continue
            # The set may appear inside this call only as an argument of the nested evidence call.
            # A bare `candidates` among assign_group's own arguments is the regression.
            direct = {arg.id for arg in call.args if isinstance(arg, ast.Name)}
            assert "candidates" not in direct, (
                f"{orchestrator.__name__} calls assign_group with the candidate set as a direct "
                f"argument: {sorted(direct)}"
            )

        assert reached == set(staged), (
            f"{orchestrator.__name__} no longer calls {sorted(set(staged) - reached)}; this guard is "
            "inspecting a call site that has moved and would pass by finding nothing"
        )


def test_the_evidence_stage_reaches_the_candidate_set_by_lookup_and_never_iterates_it():
    """Structural: admission is a question asked of the set, not a walk over it.

    This is what lets the set be load-bearing without becoming an ordering.
    ``CandidateSet.candidates()`` is canonical by ordinal pair; a stage that iterated it to decide
    what to describe would hold that order at the moment it builds the sequence assignment reads,
    and the two genuinely differ -- on the interleaved fixture's fallback population the canonical
    order is ``[1, 2]`` and the invocation-local order is ``[2, 1]``.

    So the evidence path may name ``candidate_for`` and must not call ``candidates()`` or iterate
    the set. Checked over the evidence stage and the admission helper it delegates to, because the
    constraint belongs to the path rather than to either function alone.
    """
    import inspect

    from deltatrack.diff_bill import _refuse_a_candidate_retrieval_did_not_admit

    for stage in (group_correspondence_evidence, _refuse_a_candidate_retrieval_did_not_admit):
        tree = ast.parse(textwrap.dedent(inspect.getsource(stage)))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "candidates" not in called, (
            f"{stage.__name__} calls CandidateSet.candidates(); the canonical ordinal-pair order is then "
            "in scope where the described sequence is built"
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
                assert node.iter.id != "candidates", f"{stage.__name__} iterates the candidate set directly"

    assert "candidate_for" in inspect.getsource(_refuse_a_candidate_retrieval_did_not_admit), (
        "the admission helper no longer reaches the candidate set by lookup, so this guard is "
        "asserting the absence of an iteration over a set that is no longer consulted at all"
    )


#: Every symbol that would mean round-1 ASSIGNMENT had reached back for a measurement, an input
#: it must not read, or the threshold that belongs to a different rule. Spelled literally rather
#: than imported, for the reason ``EXPECTED_INVOCATION`` is: importing them would let a rename
#: move the guard and the code it guards together.
FORBIDDEN_IN_GROUP_ASSIGNMENT = frozenset(
    {
        "text_similarity",
        "_normalize_text",
        "diff_text",
        "body_text",
        "_similarity_signals",
        "similarity_correspondence_evidence",
        "SIMILARITY_THRESHOLD",
        "threshold",
        "score",
        "proposals",
    }
)


def test_group_assignment_names_no_measurement_and_no_threshold():
    """Structural: assignment cannot recompute what evidence already describes.

    ADR 0020's boundary is that evidence describes and assignment decides. An assignment stage
    that re-derives the similarity it was handed is not reading evidence at all -- it is the
    fused matcher with an extra parameter, and every test that supplies evidence would still
    pass because the recomputed answer usually agrees.

    Cheap and total where the behavioural control below is decisive but local: this reads the
    whole function body, so a recomputation on a branch no fixture reaches is still caught.
    ``threshold``, ``score`` and ``proposals`` are here for the two adjacent mistakes -- folding
    the later similarity rule's cutoff into the group competition, and reading
    ``Proposal.score`` as though a retrieval score were evidence.
    """
    import inspect

    tree = ast.parse(textwrap.dedent(inspect.getsource(assign_group)))
    named = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    named |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    offending = named & FORBIDDEN_IN_GROUP_ASSIGNMENT
    assert not offending, f"assign_group names {sorted(offending)}; assignment reads evidence and nothing else"


def test_the_measurement_guard_can_fire():
    """The negative control for the guard above, which has only ever been observed green."""
    tree = ast.parse("def fused(population, evidence):\n    return text_similarity(population.old[0].body_text, '')\n")
    named = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    named |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert named & FORBIDDEN_IN_GROUP_ASSIGNMENT >= {"text_similarity", "body_text"}, (
        "the guard failed to see an assignment stage plainly recomputing the measurement"
    )


# --- B1: the CandidateSet, bound independently of the code that builds it --------------------
#
# Assignment consumes `population.old` / `population.new` and the evidence describing them, and
# never the candidate set -- true of the fused scorer and still true of `assign_group`. So
# candidate materialisation can be wrong -- a dropped pair, a mis-attributed invocation -- while
# the frozen pairing stream, the retrieval-population tests and the canonical bytes all stay
# exact. Nothing above binds it. These do.

#: The two invocations B1's retrieval stages run under, rebuilt here from the literal names and
#: round rather than imported from production. Importing the constant would let a change to it
#: move expectation and actual together, which is the whole failure mode this file exists to
#: refuse. `1` is `PATH_ROUND`, spelled out for the same reason.
EXPECTED_INVOCATION = {
    "within": RetrieverInvocation.of("path_division_group", round=1),
    "cross": RetrieverInvocation.of("path_group_cross_division", round=1),
    # B3's unique-path retriever. Its population is a whole ``match_path`` group holding at most
    # one observation per side, so it is neither of the two above -- and it must not be spelled as
    # either, because a candidate's provenance is what makes a recall figure attributable to the
    # rule that surfaced it.
    "unique": RetrieverInvocation.of("path_unique_group", round=1),
}


def expected_candidate_provenance(old_tree, new_tree) -> dict[tuple[int, int], set]:
    """The candidate set B1 must have materialised, derived from the ORACLE's invocations.

    Independent by construction: it reads the transcribed invocation trace -- whose digest the
    frozen artifact pins -- and expands each invocation's population into its full cross
    product. It never calls ``RetrievedPopulation.propose_into``, which is the code under test;
    building the expected side with the production helper would assert only that the helper
    agrees with itself.

    Returns ``{(old_ordinal, new_ordinal): {invocation, ...}}``. Keying by observation pair and
    accumulating a SET of invocations is the checked-in ``CandidateSet`` semantics restated
    independently: one candidate per pair however many invocations proposed it, each retaining
    its own provenance.

    **B3 added the unique-path population, and it is expanded from the oracle's own
    ``unique_selections`` rather than from a re-walk of the groups.** That list is the ordered
    record of every non-colliding ``match_path`` group the transcribed legacy composition paired,
    and it is covered by the frozen trace digest exactly as the invocation trace is -- so the
    expectation moved without the artifact being regenerated, which is what keeps this an
    independent expectation rather than a restatement of the new code.

    A unique 1x1 group forms exactly one candidate: the population is the group, so the cross
    product is the pair itself. A one-sided unique group forms none and appears in neither list,
    which is the same fact ``forms_candidates`` states on the production side.
    """
    trace = oracle_trace(old_tree.nodes, new_tree.nodes)
    expected: dict[tuple[int, int], set] = defaultdict(set)
    for invocation in trace["invocations"]:
        which = EXPECTED_INVOCATION[invocation["phase"]]
        for old_ordinal in invocation["old"]:
            for new_ordinal in invocation["new"]:
                expected[(old_ordinal, new_ordinal)].add(which)
    for old_ordinal, new_ordinal in trace["unique_selections"]:
        expected[(old_ordinal, new_ordinal)].add(EXPECTED_INVOCATION["unique"])
    return dict(expected)


def actual_candidate_provenance(candidates) -> dict[tuple[int, int], set]:
    """The production ``CandidateSet``, projected the same way, with its addressing checked."""
    projected: dict[tuple[int, int], set] = {}
    for candidate in candidates.candidates():
        assert candidate.old.side == OLD and candidate.new.side == NEW, (
            f"a candidate pairs {candidate.old.side} with {candidate.new.side}"
        )
        key = (candidate.old.ordinal, candidate.new.ordinal)
        assert key not in projected, f"{key} appears as two candidates; one pair is one candidate"
        projected[key] = set(candidate.invocations)
    return projected


@pytest.mark.slow
@pytest.mark.parametrize("old_path,new_path", manifest_version_pairs(), ids=lambda p: p.stem)
def test_the_candidate_set_materialises_exactly_what_retrieval_considered(old_path: Path, new_path: Path):
    """Membership, addressing, provenance and deduplication, against an independent expectation.

    Binds all four at once because they fail together: a dropped pair moves membership, a
    mis-attributed proposal moves provenance, and a pair recorded twice moves deduplication.
    """
    old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
    _pairs, candidates = match_nodes_with_retrieval(old_tree, new_tree)

    expected = expected_candidate_provenance(old_tree, new_tree)
    actual = actual_candidate_provenance(candidates)
    key = pair_key(old_path, new_path)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    assert not missing, f"{key}: {len(missing)} considered pairs never reached the candidate set, e.g. {missing[:4]}"
    assert not extra, f"{key}: {len(extra)} candidates were never considered by retrieval, e.g. {extra[:4]}"

    mismatched = {k: (actual[k], expected[k]) for k in expected if actual[k] != expected[k]}
    assert not mismatched, f"{key}: {len(mismatched)} candidates carry the wrong invocation provenance"

    # Complete-sequence addressing: every ordinal indexes a real node of its own side.
    n_old, n_new = len(old_tree.nodes), len(new_tree.nodes)
    for old_ordinal, new_ordinal in actual:
        assert 0 <= old_ordinal < n_old and 0 <= new_ordinal < n_new


@pytest.mark.slow
def test_the_candidate_population_is_non_vacuous():
    """The gate above would pass on two empty dicts; this refuses that reading."""
    total = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        total += len(match_nodes_with_retrieval(old_tree, new_tree)[1])
    assert total > 1000, f"only {total} candidates materialised over the corpus; the gate is near-vacuous"


def test_a_one_sided_population_contributes_no_candidates():
    """A division present on one side forms no pair, so it must propose nothing.

    Asserted on the real retrieval stage rather than a hand-built value: the interleaved fixture
    has division Y on the old side only and division Z on the new side only.
    """
    old_nodes, new_nodes = interleaved_division_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    populations = retrieve_within_division_populations(old_nodes, new_nodes, registry)

    one_sided = [p for p in populations if not p.forms_candidates]
    assert one_sided, "the fixture stopped producing a one-sided division, so this proves nothing"

    candidates = CandidateSet()
    for population in one_sided:
        population.propose_into(candidates)
    assert len(candidates) == 0, "a one-sided population proposed a candidate pair"

    # And the paired direction, so this is not an assertion that propose_into never works.
    two_sided = [p for p in populations if p.forms_candidates]
    assert two_sided, "the fixture stopped producing a two-sided division"
    for population in two_sided:
        population.propose_into(candidates)
    assert len(candidates) == sum(len(p.old) * len(p.new) for p in two_sided)


def test_two_invocations_proposing_one_pair_keep_both_provenances():
    """The bridge from B1's populations to ``CandidateSet``'s multi-proposal accumulation.

    Current policy happens to produce no pair proposed by both round-1 invocations on the
    committed corpus, and this does not pretend otherwise -- it drives the accumulation directly
    with two populations naming the same observations under different invocations, which is the
    shape the cross-division round can legitimately produce.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    (population,) = retrieve_within_division_populations(old_nodes, new_nodes, registry)

    cross = retrieve_cross_division_population(list(population.old), list(population.new), registry)
    assert cross is not None and cross.invocation != population.invocation

    candidates = CandidateSet()
    population.propose_into(candidates)
    cross.propose_into(candidates)

    assert len(candidates) == len(population.old) * len(population.new), "the same pair became two candidates"
    for candidate in candidates.candidates():
        assert set(candidate.invocations) == {population.invocation, cross.invocation}, (
            f"candidate {candidate.ordinal_pair} lost a proposal's provenance: {candidate.invocations}"
        )


def dropping_propose_into(self, candidates):
    """``propose_into`` with exactly one real pair omitted per invocation. Nothing else moves.

    A **candidate-materialisation** fault and nothing more: the population it is called on is
    untouched -- same nodes, same refs, same order -- and every other pair is proposed under the
    same invocation. So it isolates the one question the admission boundary exists to answer,
    which is what happens when the set and the population disagree about what was retrieved.
    """
    dropped = False
    for old_ref in self.old_refs:
        for new_ref in self.new_refs:
            if not dropped:
                dropped = True
                continue
            candidates.propose(old_ref, new_ref, self.invocation)


def test_an_omitted_candidate_cannot_reach_assignment(monkeypatch):
    """THE B2 admission control: a CandidateSet-only fault, and the boundary refusing it.

    **This replaces B1's expectation that a candidate omission stays invisible to matching.**
    That control was right for B1, where the set was observational and needed an independent gate
    to certify itself. B2 is the slice where ``CandidateSet -> evidence -> assignment`` becomes
    the real path, so it is now *expected* that a corrupted set stops matching. Unfaulted
    behaviour is unchanged and still byte-identical; what changed is behaviour under a fault,
    which was never frozen methodology.

    One fault, four claims, on the duplicate-id fixture whose 2x2 competition selects both pairs:

    **A.** the ``RetrievedPopulation`` is unchanged -- same nodes, same refs, same order -- so
    this is a candidate-only defect and not a retrieval one wearing its name.
    **B.** the candidate set really is missing that pair.
    **C.** the evidence stage fails closed on it, naming the pair, rather than reconstructing it
    from population membership.
    **D.** assignment never sees it. Proven materially rather than by absence: the omitted pair
    is one the clean run *selects*, so a reconstructing implementation would have gone on to
    choose a link retrieval never admitted.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    population = population_of(old_nodes, new_nodes)
    honest = admitted(population)

    # D's premise: the pair about to be dropped is one the clean run actually selects. Without
    # this the control could be refusing a candidate that would have lost anyway.
    omitted = (population.old_refs[0], population.new_refs[0])
    clean_links = {
        link.evidence.link for link in assign_group(population, group_correspondence_evidence(population, honest)).links
    }
    assert omitted in clean_links, (
        "the pair this control drops is not selected by the unfaulted run, so proving it cannot "
        "reach assignment says nothing about a link that would otherwise have been chosen"
    )

    monkeypatch.setattr(RetrievedPopulation, "propose_into", dropping_propose_into)
    faulted = CandidateSet()
    population.propose_into(faulted)

    # A. the population is untouched by the fault.
    after = population_of(old_nodes, new_nodes)
    assert (population.old_refs, population.new_refs) == (after.old_refs, after.new_refs)
    assert [n.element_id for n in population.old] == [n.element_id for n in after.old]
    assert [n.element_id for n in population.new] == [n.element_id for n in after.new]
    assert population.invocation == after.invocation

    # B. the set is missing exactly that pair, and nothing else.
    assert faulted.candidate_for(*omitted) is None, "the fault did not omit the pair it was supposed to"
    assert len(faulted) == len(honest) - 1, "the fault omitted more than one pair; it is no longer isolating"

    # C. the evidence stage refuses it rather than reconstructing it from the population.
    with pytest.raises(ValueError, match="never admitted"):
        group_correspondence_evidence(population, faulted)

    # D. and so nothing downstream can select it: the whole engine fails closed on this group.
    with pytest.raises(ValueError, match="never admitted"):
        match_nodes(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))


def test_a_candidate_missing_this_invocations_provenance_is_refused():
    """The second admission failure: the pair was considered, but not by this invocation.

    Distinct from absence, and the distinction is real rather than defensive. Candidates are
    comparison-scoped and the cross-division round can legitimately re-propose a pair the
    within-division round already offered, so a set holding a pair proves only that *somebody*
    retrieved it. Admitting on that basis would let one invocation describe -- and assignment
    then select -- a pair that invocation never retrieved, which is the same boundary violation
    arriving through provenance instead of membership.

    Driven with a set built entirely under the *other* round-1 invocation, which is the shape the
    cross-division round produces for pairs the within-division round also saw.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    population = population_of(old_nodes, new_nodes)

    other = CandidateSet()
    for old_ref in population.old_refs:
        for new_ref in population.new_refs:
            other.propose(old_ref, new_ref, EXPECTED_INVOCATION["cross"])

    assert other.candidate_for(population.old_refs[0], population.new_refs[0]) is not None, (
        "the pair is absent from this set, so the refusal below would be about membership rather "
        "than about provenance and the two failures would not be distinguished"
    )
    assert population.invocation != EXPECTED_INVOCATION["cross"]

    with pytest.raises(ValueError, match="carries no proposal from"):
        group_correspondence_evidence(population, other)


@pytest.mark.slow
def test_the_admission_boundary_fails_closed_across_the_corpus(monkeypatch):
    """The same fault at corpus scale: every pair with a collision group now refuses to match.

    The synthetic control above is exact about which pair and why. This one answers the question
    it cannot: whether the boundary is wired on the path the engine actually takes over real
    bills, or only on the one a hand-built population reaches.

    Pairs whose ``match_path`` groups never collide produce no candidate at all, so there is
    nothing for the fault to omit and nothing to refuse. They are counted rather than assumed
    away, and the two sets must agree exactly -- which is also what stops this passing on a run
    where the fault silently did nothing.
    """
    clean_have_candidates = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        if len(match_nodes_with_retrieval(old_tree, new_tree)[1]):
            clean_have_candidates.append(pair_key(old_path, new_path))
    assert clean_have_candidates, "no committed pair materialises a candidate; the fault has nothing to omit"

    monkeypatch.setattr(RetrievedPopulation, "propose_into", dropping_propose_into)

    failed_closed = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        try:
            match_nodes(old_tree, new_tree)
        except ValueError as exc:
            assert "never admitted" in str(exc)
            failed_closed.append(pair_key(old_path, new_path))

    assert failed_closed == clean_have_candidates, (
        "the pairs that fail closed under a candidate omission are not exactly the pairs that "
        f"materialise candidates: only-failed={sorted(set(failed_closed) - set(clean_have_candidates))}, "
        f"only-candidates={sorted(set(clean_have_candidates) - set(failed_closed))}"
    )


def test_the_materialisation_gate_can_still_see_a_candidate_only_defect():
    """The corpus materialisation gate's projection, shown to distinguish a dropped proposal.

    That gate is kept, and kept independent -- it compares production's set against an
    expectation expanded from the ORACLE's invocation trace, so it answers a question the
    fail-closed boundary cannot: whether the set holds the *right* pairs under the *right*
    invocations, rather than merely agreeing with whatever the evidence stage went on to ask for.

    Its negative control moved here from the old corpus fault-injection test. It could no longer
    live there: under a faulted candidate set production now raises before returning a set to
    project, which is the reviewed behaviour change and is proved by the two controls above. What
    still needs proving is the narrower thing -- that ``actual_candidate_provenance`` is capable
    of telling a dropped proposal from an intact set -- and that needs no corpus and no engine.
    """
    population = population_of(*duplicate_element_id_fixture())
    faulted = CandidateSet()
    dropping_propose_into(population, faulted)

    assert actual_candidate_provenance(faulted) != actual_candidate_provenance(admitted(population)), (
        "the projection behind the materialisation gate cannot distinguish a candidate set that is "
        "missing a proposal, so that gate is comparing something other than what it claims to"
    )


# --- B2: the evidence/assignment boundary, bound where the frozen stream cannot see it -------
#
# B1 left one function computing every similarity, running the greedy competition and breaking
# ties on local position. B2 splits it: `group_correspondence_evidence` describes every retrieved
# candidate, `assign_group` decides which of them correspond.
#
# Nothing above can tell a real separation from a cosmetic one. A stage that recomputed the
# measurement it was handed, or that described only the winners, or that quietly acquired the
# later similarity rule's threshold, produces a byte-identical pairing stream on every committed
# pair. These bind the boundary itself.

#: The evidence signal name, spelled literally for the reason ``EXPECTED_INVOCATION`` is:
#: importing production's constant would let a rename move expectation and actual together.
_WORD_OVERLAP = "word_overlap"

#: Which retrieval round produced a population, keyed on the invocations rebuilt above rather
#: than read off a production attribute. The phase is a fact about which retriever ran.
_PHASE_OF_INVOCATION = {invocation: phase for phase, invocation in EXPECTED_INVOCATION.items()}


def _refuse_to_measure(*_args, **_kwargs):
    """A ``text_similarity`` that cannot be called. Bombs rather than returning a wrong answer.

    Returning a sentinel would let a stage that recomputes carry on and *usually* agree, because
    the recomputed value is normally the same one the evidence carries. The whole question is
    whether the call happens at all, so the call is what fails.
    """
    raise AssertionError("text_similarity was called by a stage that must not measure anything")


def observed_group_evidence(old_tree, new_tree) -> list[dict]:
    """Every evidence-stage output production produced, in order, addressed by ADR 0019 ordinal.

    ``None`` where a signal was **not computed**, read off ``.names`` rather than off ``.get``,
    so "absent" stays distinguishable from "present and null" -- the distinction
    :func:`_similarity_signals` documents on the other similarity rule and the one a 1x1
    population's empty record turns on.

    Saved and restored by hand rather than through ``monkeypatch`` for the reason
    :func:`observed_retrieval_populations` gives: across a corpus loop an accumulating patch
    would wrap the previous iteration's spy.
    """
    from deltatrack import diff_bill as db

    seen: list[dict] = []
    real = db.group_correspondence_evidence

    def spy(population, candidates):
        evidence = real(population, candidates)
        seen.append(
            {
                "phase": _PHASE_OF_INVOCATION[population.invocation],
                "links": [
                    [
                        item.old.ordinal,
                        item.new.ordinal,
                        round(item.get(_WORD_OVERLAP), 12) if _WORD_OVERLAP in item.names else None,
                    ]
                    for item in evidence
                ],
            }
        )
        return evidence

    db.group_correspondence_evidence = spy
    try:
        match_nodes(old_tree, new_tree)
    finally:
        db.group_correspondence_evidence = real
    return seen


def expected_group_evidence(old_tree, new_tree) -> list[dict]:
    """What the ORACLE says each evidence call must describe, and with what number.

    Independent by construction. The oracle records, per invocation, the exact ``(similarity,
    oi, ni)`` tuples the fused matcher built -- in generation order, before the competition sorts
    them -- and the branch it took. Expanding those local positions back through the invocation's
    own ordinal lists produces the expected evidence without ever asking the evidence stage what
    it meant to compute.

    A ``shortcut_1x1`` invocation expects exactly one record carrying **no** number. That is the
    preserved behaviour, not a gap in the expectation: the fused matcher paired a sole candidate
    without calling ``text_similarity`` at all.
    """
    expected: list[dict] = []
    for invocation in oracle_trace(old_tree.nodes, new_tree.nodes)["invocations"]:
        old_ordinals, new_ordinals = invocation["old"], invocation["new"]
        if invocation["branch"] == "shortcut_1x1":
            links = [[old_ordinals[0], new_ordinals[0], None]]
        else:
            links = [[old_ordinals[oi], new_ordinals[ni], score] for score, oi, ni in invocation["candidates"]]
        expected.append({"phase": invocation["phase"], "links": links})
    return expected


@pytest.mark.slow
def test_the_evidence_stage_describes_exactly_the_candidates_retrieval_admitted():
    """Completeness, fidelity and order, against an expectation the stage did not produce.

    Binds all three at once because they fail together and they fail invisibly:

    - **completeness** -- one record per retrieved candidate, no missing, no extra. An
      implementation that described only the greedy winners would halve most of these lists
      while selecting exactly the same links.
    - **fidelity** -- each record's ``word_overlap`` is the ratio the fused matcher computed for
      that pair, to twelve places.
    - **membership** -- the pairs described are the invocation's own, expanded from the frozen
      trace's local positions through its ordinal lists, so evidence for a pair retrieval never
      admitted shows up as an extra row rather than as a silently wider competition.

    The sequence of calls is compared too, phase included, so flattening the within-division and
    cross-division rounds into one competition moves this even where it leaves the stream intact.

    **Scoped to the collision path's two invocations, because that is what the frozen invocation
    trace records.** B3 brought the unique path through the same evidence stage, so production
    now also calls it once per non-colliding 1x1 group. Those calls are held to the oracle's
    ``unique_selections`` instead, by
    :func:`test_the_unique_path_evidence_stage_describes_the_frozen_unique_selections` -- a
    separate frozen expectation covered by the same trace digest. Folding them in here would have
    meant regenerating the artifact to make a refactor green, which is the one thing this file
    exists to refuse. Their interleaving with these calls is not left unbound: the pairing stream
    is emitted in traversal order, so a unique group resolved out of turn moves the durable gate.
    """
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        observed = [call for call in observed_group_evidence(old_tree, new_tree) if call["phase"] != "unique"]
        expected = expected_group_evidence(old_tree, new_tree)
        key = pair_key(old_path, new_path)

        assert len(observed) == len(expected), (
            f"{key}: production ran {len(observed)} evidence stages, the frozen trace expects {len(expected)}"
        )
        for index, (seen, want) in enumerate(zip(observed, expected)):
            assert seen == want, f"{key}: evidence call {index} ({want['phase']}) differs from the frozen expectation"
        checked += 1

    assert checked, "the evidence comparison ran over zero version pairs"


@pytest.mark.slow
def test_the_evidence_comparison_is_non_vacuous():
    """The gate above would pass on two empty lists; this refuses that reading."""
    scored = described = unique_calls = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        for call in observed_group_evidence(old_tree, new_tree):
            if call["phase"] == "unique":
                unique_calls += 1
                continue
            described += len(call["links"])
            scored += sum(1 for link in call["links"] if link[2] is not None)
    assert described > 1000, f"only {described} candidates were described over the corpus; the gate is near-vacuous"
    assert scored, "no candidate carried a word_overlap, so the fidelity half of that gate compared nothing"
    # And that the filter above is removing a real population rather than silently matching
    # nothing -- if B3's calls stopped arriving, the gate it defers them to would be vacuous too.
    assert unique_calls > 1000, (
        f"only {unique_calls} unique-path evidence calls reached the stage; the phase filter in the "
        "gate above is excluding a population that is no longer there"
    )


def production_similarity_calls(old_tree, new_tree) -> int:
    """How many times ``match_nodes`` calls ``text_similarity``. A measurement, not a proxy.

    Counted at production's own module global, which is where every round-1 measurement resolves.
    Restored by hand for the reason :func:`observed_group_evidence` gives.
    """
    from deltatrack import diff_bill as db

    real = db.text_similarity
    calls = 0

    def counting(old_text, new_text):
        nonlocal calls
        calls += 1
        return real(old_text, new_text)

    db.text_similarity = counting
    try:
        match_nodes(old_tree, new_tree)
    finally:
        db.text_similarity = real
    return calls


@pytest.mark.slow
def test_production_measures_exactly_the_frozen_set_of_similarities():
    """THE call-behaviour gate: production's measurement set, against the frozen count.

    The pairing stream cannot see how a decision was reached, only what it decided. This can,
    and it is the one gate that catches every way the evidence stage could quietly change *what
    gets measured* while selecting identically:

    - a 1x1 population that starts scoring its sole candidate inflates the count (593 shortcut
      invocations on the committed corpus);
    - reusing :func:`_similarity_signals` -- which computes the diff first and skips the ratio
      entirely for unchanged bodies -- deflates it;
    - describing only the greedy winners deflates it;
    - describing a pair retrieval never admitted inflates it.

    The frozen count comes from the oracle, so this is production measured against an
    independent expectation rather than against its own intent.
    """
    frozen = load_frozen()
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)
        expected = frozen[key]["counts"]["similarity_calls"]
        assert production_similarity_calls(old_tree, new_tree) == expected, (
            f"{key}: production's round-1 similarity calls differ from the frozen expectation of {expected}"
        )
        checked += 1

    assert checked, "the call-count comparison ran over zero version pairs"


@pytest.mark.slow
def test_the_call_count_gate_can_fire(monkeypatch):
    """The negative control: scoring a 1x1 sole candidate must move the count.

    Without this the gate is an equality that has only ever been satisfied. The mutation is the
    exact tidy-up ADR 0020's audit rejected -- make the architecture uniform by measuring the
    sole candidate too -- and it changes no pairing anywhere, so nothing else here sees it.

    The measurement goes through ``db.text_similarity`` rather than this module's own import,
    which is not a style choice: :func:`production_similarity_calls` counts at production's
    module global, so a mutation calling the function by any other route would add a real
    measurement that the counter never sees -- and the control would report "cannot fire" while
    the fault it injected was in fact invisible for a second, unrelated reason.
    """
    from deltatrack import diff_bill as db

    real = db.group_correspondence_evidence

    def scores_the_sole_candidate(population, candidates):
        if population.forms_candidates and len(population.old) == 1 and len(population.new) == 1:
            old_text = " ".join(population.old[0].body_text.split())
            new_text = " ".join(population.new[0].body_text.split())
            return (
                CorrespondenceEvidence.of(
                    population.old_refs[0],
                    population.new_refs[0],
                    **{_WORD_OVERLAP: db.text_similarity(old_text, new_text)},
                ),
            )
        return real(population, candidates)

    monkeypatch.setattr(db, "group_correspondence_evidence", scores_the_sole_candidate)

    frozen = load_frozen()
    inflated = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)
        if production_similarity_calls(old_tree, new_tree) != frozen[key]["counts"]["similarity_calls"]:
            inflated.append(key)

    assert inflated, (
        "scoring every 1x1 sole candidate left production's similarity-call count unchanged on every "
        "committed pair; the call-count gate cannot see the optimisation regression it exists for"
    )


# --- Driving the two stages directly, on the fixtures the corpus cannot supply ---------------


def population_of(old_nodes: list[BillNode], new_nodes: list[BillNode]) -> RetrievedPopulation:
    """The single within-division population a one-division fixture retrieves."""
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    (population,) = retrieve_within_division_populations(old_nodes, new_nodes, registry)
    return population


def admitted(*populations: RetrievedPopulation) -> CandidateSet:
    """The candidate set retrieval materialises for these populations.

    The evidence stage now refuses a pair the set does not admit, so a test driving that stage
    has to supply the admission as well as the population. Built through production's own
    ``propose_into`` deliberately: these tests are about what happens *after* admission, and
    hand-rolling the set here would put a second, divergent materialisation rule in the harness.
    The one control that needs a *faulted* set builds it explicitly instead.
    """
    candidates = CandidateSet()
    for population in populations:
        population.propose_into(candidates)
    return candidates


def sole_candidate_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """One collision group, two divisions, each a 1x1 -- so every population takes the shortcut.

    Division B's two bodies are deliberately **dissimilar**. A fixture whose sole candidates
    happened to match would leave "no ratio was computed" indistinguishable from "a ratio was
    computed and came out high", which is the reading the shortcut exists to make impossible.
    """
    old_nodes = [
        node(MP, "oA", "alpha alpha alpha division a body text", "A"),
        node(MP, "oB", "bravo bravo bravo division b body text", "B"),
    ]
    new_nodes = [
        node(MP, "nA", "alpha alpha alpha division a body text", "A"),
        node(MP, "nB", "utterly unrelated wording sharing nothing whatsoever", "B"),
    ]
    return old_nodes, new_nodes


def test_a_1x1_population_is_described_without_measuring_anything(monkeypatch):
    """E: the shortcut's real effect, retargeted onto the stage that inherited it.

    The pairing stream cannot show this -- selecting a sole candidate is what the greedy would
    do anyway. What the shortcut changes is that **no ratio exists**, and B2 had an obvious way
    to lose that while looking tidier: give every candidate a number so the architecture reads
    uniformly. So the record is required to be present (the candidate does reach assignment and
    every such candidate is described) and required to carry no signal at all.

    ``text_similarity`` is bombed rather than counted, so a stage that measured would fail here
    even if it discarded the result.

    The sole pair is admitted through the candidate set like any other -- the shortcut is about
    what is *measured*, not about skipping the boundary -- so the population is materialised
    first and the admission is asserted before the record is inspected.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = sole_candidate_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    populations = retrieve_within_division_populations(old_nodes, new_nodes, registry)
    assert [(len(p.old), len(p.new)) for p in populations] == [(1, 1), (1, 1)], (
        "the fixture stopped producing two 1x1 populations, so this proves nothing"
    )
    candidates = admitted(*populations)

    monkeypatch.setattr(db, "text_similarity", _refuse_to_measure)

    for population in populations:
        candidate = candidates.candidate_for(population.old_refs[0], population.new_refs[0])
        assert candidate is not None and population.invocation in candidate.invocations, (
            "the sole pair was not admitted under its own invocation, so the shortcut is bypassing the boundary"
        )

        evidence = group_correspondence_evidence(population, candidates)
        assert len(evidence) == 1, "a 1x1 population must still describe its sole candidate"
        assert evidence[0].names == (), f"the sole candidate was given an invented signal: {evidence[0].signals}"
        assert evidence[0].link == (population.old_refs[0], population.new_refs[0])

        assignment = assign_group(population, evidence)
        assert [(link.old, link.new) for link in assignment.links] == [(population.old[0], population.new[0])]
        assert assignment.links[0].evidence is evidence[0]
        assert (assignment.leftover_old, assignment.leftover_new) == ((), ())


def test_production_measures_nothing_on_an_all_1x1_group():
    """The same claim end to end, so it binds the engine and not only the two stages."""
    old_nodes, new_nodes = sole_candidate_fixture()
    calls = production_similarity_calls(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    assert calls == 0, f"a collision group of 1x1 populations measured {calls} similarities"
    assert production_stream(old_nodes, new_nodes) == [[0, 0], [1, 1]], "the shortcut stopped pairing both divisions"


def test_assignment_follows_the_supplied_evidence_and_never_recomputes_it(monkeypatch):
    """C: THE decisive control. Evidence that disagrees with the texts, and who wins.

    The duplicate-id fixture pairs like for like: old 0 and new 0 carry one body, old 1 and new
    1 another, so recomputing the texts scores the **diagonal** 1.0 and the crossed pairs near
    zero. The mutation inverts exactly that -- crossed pairs 1.0, diagonal 0.0 -- while leaving
    the population, the addresses and the record count untouched.

    An assignment stage reading the evidence selects the crossed pairs. One that recomputes
    selects the diagonal. So the two hypotheses are separated by the *result*, not merely by
    whether a call happened, and ``text_similarity`` is additionally bombed so a recomputing
    implementation cannot even reach a wrong answer quietly.

    The honest direction is asserted too, under the same bomb: hand assignment the evidence
    production actually computed and it must reproduce the frozen selection without measuring.
    That is what stops this passing because assignment ignores evidence in some third way.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = duplicate_element_id_fixture()
    population = population_of(old_nodes, new_nodes)
    honest = group_correspondence_evidence(population, admitted(population))
    assert len(honest) == 4, "the fixture stopped producing a 2x2 competition"

    # What recomputing the texts says, checked rather than assumed -- the mutation below is only
    # a disagreement if the diagonal really is what the measurement prefers.
    scored = {(item.old.ordinal, item.new.ordinal): item.get(_WORD_OVERLAP) for item in honest}
    assert scored[(0, 0)] == scored[(1, 1)] == 1.0
    assert scored[(0, 1)] < 0.5 and scored[(1, 0)] < 0.5

    inverted = tuple(
        CorrespondenceEvidence.of(
            item.old,
            item.new,
            **{_WORD_OVERLAP: 0.0 if item.old.ordinal == item.new.ordinal else 1.0},
        )
        for item in honest
    )

    monkeypatch.setattr(db, "text_similarity", _refuse_to_measure)

    def selected(evidence):
        links = assign_group(population, evidence).links
        return [(link.evidence.old.ordinal, link.evidence.new.ordinal) for link in links]

    assert selected(honest) == [(1, 1), (0, 0)], (
        "assignment did not reproduce the frozen selection from the evidence production computed"
    )
    assert selected(inverted) == [(1, 0), (0, 1)], (
        "assignment ignored the supplied evidence and selected the pairing the node texts imply; "
        "the evidence boundary is decorative"
    )


def test_the_evidence_authority_control_would_be_blind_without_the_disagreement():
    """The premise the control above rests on: the two hypotheses really do differ.

    If the inverted evidence selected the same links as the honest evidence, the control would
    pass on an implementation that recomputed everything. Stated as its own assertion so that a
    fixture change which collapses the difference reddens here rather than silently emptying the
    control next door.
    """
    population = population_of(*duplicate_element_id_fixture())
    honest = group_correspondence_evidence(population, admitted(population))
    inverted = tuple(
        CorrespondenceEvidence.of(
            item.old, item.new, **{_WORD_OVERLAP: 0.0 if item.old.ordinal == item.new.ordinal else 1.0}
        )
        for item in honest
    )
    links = {
        label: {
            (link.evidence.old.ordinal, link.evidence.new.ordinal) for link in assign_group(population, evidence).links
        }
        for label, evidence in (("honest", honest), ("inverted", inverted))
    }
    assert links["honest"].isdisjoint(links["inverted"]), (
        f"the inverted evidence selects {links['inverted']} and the honest evidence {links['honest']}; "
        "they overlap, so the authority control cannot separate reading from recomputing"
    )


def test_assignment_breaks_ties_on_invocation_local_position(monkeypatch):
    """D: local position decides, and the ADR 0019 ordinal would decide differently.

    Driven on the interleaved fixture's fallback population, which is the one place the two
    numberings disagree: it holds ``[X2, Y1]`` -- local positions 0 and 1, complete-sequence
    ordinals 2 and 1 -- and both candidates tie at 1.0, so the tie is what picks the winner.

    Descending **local** position selects ``Y1``; descending **ordinal** selects ``X2``. The
    alternative is computed here rather than described, so a change that made the two agree
    reddens this test instead of quietly emptying it.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = interleaved_division_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    # The population round 1a's assignment leaves: X2 (ordinal 2) then Y1 (ordinal 1).
    cross = retrieve_cross_division_population([old_nodes[2], old_nodes[1]], [new_nodes[1]], registry)
    assert cross is not None
    assert [ref.ordinal for ref in cross.old_refs] == [2, 1], "the fallback population lost its concatenation order"

    evidence = group_correspondence_evidence(cross, admitted(cross))
    assert len({item.get(_WORD_OVERLAP) for item in evidence}) == 1, "the fallback candidates no longer tie"

    # The evidence came out in POPULATION order, not the candidate set's canonical ordinal-pair
    # order. On this population the two disagree -- local [2, 1] against canonical [1, 2] -- which
    # is what makes the admission boundary safe to have wired: the set gates membership and has
    # no way to reach the sequence assignment reads.
    assert [item.old.ordinal for item in evidence] == [2, 1], (
        "the evidence stage emitted the candidate set's canonical order rather than the population's"
    )
    assert [candidate.old.ordinal for candidate in admitted(cross).candidates()] == [1, 2]

    monkeypatch.setattr(db, "text_similarity", _refuse_to_measure)
    (link,) = assign_group(cross, evidence).links
    assert link.old.element_id == "Y1", (
        f"assignment selected {link.old.element_id!r}; descending invocation-local position selects 'Y1', "
        "and 'X2' is what substituting the ADR 0019 ordinal would select"
    )

    by_ordinal = max(evidence, key=lambda item: (item.get(_WORD_OVERLAP), item.old.ordinal, item.new.ordinal))
    assert by_ordinal.old.ordinal == 2, (
        "an ordinal-keyed competition now picks the same candidate as a local-position one; the "
        "fixture no longer distinguishes the two orderings"
    )


def test_losing_candidates_keep_their_evidence_after_assignment():
    """F: the competition stays inspectable, losers included.

    The false-green this refuses is an implementation where "evidence" quietly means "evidence
    for winners". It satisfies every per-link requirement -- each selected link carries exactly
    one record -- while destroying the reason ADR 0020 invariant 8 exists: that a correspondence
    decision can be re-examined against the alternatives it beat.

    The 2x2 duplicate-id fixture runs a real competition: four candidates reach assignment, two
    links are selected, and two candidates lose to greedy exclusivity rather than to a score.
    """
    population = population_of(*duplicate_element_id_fixture())
    evidence = group_correspondence_evidence(population, admitted(population))
    assignment = assign_group(population, evidence)

    assert len(assignment.evidence) == 4, (
        f"assignment retained {len(assignment.evidence)} of 4 candidates' evidence; the losers were discarded"
    )
    assert set(assignment.evidence) == set(evidence), "assignment altered the evidence it was handed"
    assert len(assignment.links) == 2

    selected = {link.evidence for link in assignment.links}
    losers = [item for item in assignment.evidence if item not in selected]
    assert len(losers) == 2
    assert all(_WORD_OVERLAP in item.names for item in losers), (
        "a losing candidate's record carries no signal, so what it lost on is not inspectable"
    )

    # And the other half: a selected link names exactly the record that selected it, not merely
    # some record about the same pair.
    for link in assignment.links:
        assert link.evidence in evidence
        assert link.evidence.link == (
            population.old_refs[list(population.old).index(link.old)],
            population.new_refs[list(population.new).index(link.new)],
        )


def test_a_selection_cannot_be_severed_from_its_evidence():
    """The retention invariant is enforced by the type, not only observed on a fixture."""
    population = population_of(*duplicate_element_id_fixture())
    evidence = group_correspondence_evidence(population, admitted(population))
    assignment = assign_group(population, evidence)
    stranger = CorrespondenceEvidence.of(population.old_refs[0], population.new_refs[0], **{_WORD_OVERLAP: 0.5})

    with pytest.raises(ValueError, match="absent from the retained set"):
        GroupAssignment(
            evidence=(),
            links=assignment.links,
            leftover_old=(),
            leftover_new=(),
        )
    with pytest.raises(ValueError, match="absent from the retained set"):
        GroupAssignment(
            evidence=evidence,
            links=(SelectedLink(population.old[0], population.new[0], stranger),),
            leftover_old=(),
            leftover_new=(),
        )


@pytest.mark.slow
def test_every_candidate_that_reached_assignment_keeps_its_evidence_on_the_corpus():
    """The retained-evidence invariant on the result-bearing path, over every committed pair.

    :func:`match_nodes_with_stage_outputs` is what makes this reachable: without it the
    assignments would be internal values that no caller could inspect, and "evidence is
    retained" would be a claim about a variable that goes out of scope.
    """
    total_candidates = total_links = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)
        _pairs, _candidates, assignments = match_nodes_with_stage_outputs(old_tree, new_tree)
        for index, assignment in enumerate(assignments):
            described = {item.link for item in assignment.evidence}
            assert len(described) == len(assignment.evidence), f"{key}: assignment {index} repeats an evidence link"
            for link in assignment.links:
                assert link.evidence in assignment.evidence, (
                    f"{key}: assignment {index} selected a link whose evidence it did not retain"
                )
            assert len(assignment.links) <= len(assignment.evidence)
            total_candidates += len(assignment.evidence)
            total_links += len(assignment.links)

    assert total_candidates > total_links > 0, (
        f"{total_candidates} candidates produced {total_links} links; with no losing candidate anywhere "
        "on the corpus this gate cannot distinguish retained evidence from winners-only evidence"
    )


@pytest.mark.slow
def test_the_evidence_population_is_exactly_the_materialised_candidate_set():
    """The CandidateSet is not decoration: it holds precisely the pairs evidence describes.

    The two are the same facts written twice -- ``propose_into`` materialises the comparison-wide
    set, the evidence stage describes each invocation's own view -- and nothing forces them to
    agree except this. Written as a set comparison in both directions because they fail
    differently: a pair described but never proposed is evidence for something retrieval did not
    admit, and a pair proposed but never described is a candidate that reached assignment
    undescribed.

    Why the evidence stage does not simply *consume* the set: every within-division population of
    a comparison runs under one ``RetrieverInvocation``, so the set carries no division-local
    partition to filter on and no local ordering to assign by. The population is the only
    structure that has both.
    """
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        _pairs, candidates, assignments = match_nodes_with_stage_outputs(old_tree, new_tree)
        described = {item.link for assignment in assignments for item in assignment.evidence}
        materialised = {(candidate.old, candidate.new) for candidate in candidates.candidates()}
        key = pair_key(old_path, new_path)
        assert described == materialised, (
            f"{key}: {len(described - materialised)} described pairs were never proposed and "
            f"{len(materialised - described)} proposed pairs were never described"
        )
        checked += 1

    assert checked, "the evidence/candidate comparison ran over zero version pairs"


def below_threshold_group_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """A 2x2 competition whose best candidate scores far under the similarity rule's cutoff.

    Each pairing shares exactly one word out of twelve, so the best score is about 0.17 against
    a ``SIMILARITY_THRESHOLD`` of 0.4 at the time of writing. The group competition is
    unthresholded, so both pairs must still be selected -- revoking them is the separate,
    later rule's job.
    """
    old_nodes = [
        node(MP, "o1", "alpha bravo charlie delta echo foxtrot", "A"),
        node(MP, "o2", "golf hotel india juliet kilo lima", "A"),
    ]
    new_nodes = [
        node(MP, "n1", "alpha mike november oscar papa quebec", "A"),
        node(MP, "n2", "golf sierra tango uniform victor whiskey", "A"),
    ]
    return old_nodes, new_nodes


def test_the_group_competition_applies_no_threshold():
    """The composition B2 must not collapse: an unthresholded claim, revoked later or not at all.

    The tempting tidy-up is to give the new assignment stage the threshold the *other* round-1
    similarity rule owns, on the reasoning that a stage which decides correspondence ought to own
    its cutoff. It would delete a whole assignment act: the group competition selects the best
    available pairing however weak, and ``apply_similarity_assignment_rule`` is what afterwards
    turns a weak one into a removal plus an addition. Fold them together and a pairing that
    should have been selected and then revoked is instead never selected -- which changes what
    round 1b's fallback population contains.

    Both halves are asserted. The stage selects everything it can at 0.17, and it selects a
    hand-authored 0.01 candidate too, which no plausible threshold would admit.
    """
    old_nodes, new_nodes = below_threshold_group_fixture()
    population = population_of(old_nodes, new_nodes)
    evidence = group_correspondence_evidence(population, admitted(population))

    best = max(item.get(_WORD_OVERLAP) for item in evidence)
    assert 0 < best < 0.2, f"the fixture's best candidate scores {best}; it must sit well under the 0.4 cutoff"

    assignment = assign_group(population, evidence)
    assert len(assignment.links) == 2, (
        f"the group competition selected {len(assignment.links)} of 2 possible links on sub-threshold "
        "evidence; it has acquired a cutoff that belongs to apply_similarity_assignment_rule"
    )
    assert (assignment.leftover_old, assignment.leftover_new) == ((), ())

    # And at a score no threshold in this codebase would admit.
    negligible = tuple(
        CorrespondenceEvidence.of(
            item.old, item.new, **{_WORD_OVERLAP: 0.01 if item.old.ordinal == item.new.ordinal else 0.0}
        )
        for item in evidence
    )
    assert len(assign_group(population, negligible).links) == 2

    # End to end, so this binds the engine's round-1 output and not only the stage.
    assert production_stream(old_nodes, new_nodes) == [[1, 1], [0, 0]]


def test_assignment_leftovers_are_what_the_cross_round_retrieves():
    """G: assignment emits the leftovers round 1b's retrieval needs, read at the stage boundary.

    B2 moved this. The fused matcher returned its leftovers inline in the pairing stream, so
    their membership and order were only ever observable through the stream; they are now a
    field on :class:`GroupAssignment`, and this is what binds that field to the population the
    fallback is entitled to see.

    **Scoped to the stage, deliberately.** It composes the stages itself, so it cannot see the
    orchestrator wiring them up wrongly -- an implementation of ``_match_collision_group`` that
    built the fallback from the observations no division ever paired, dropping the ones
    assignment declined, leaves this green. Fault injection confirmed that:
    :func:`test_assignment_leftovers_reach_the_cross_division_fallback` is the control that
    reddens there, because it reads production's own stream. The two are complementary and
    neither is redundant -- this one would stay green if ``assign_group`` returned the right
    stream with the wrong leftovers, which the other cannot distinguish.
    """
    old_nodes, new_nodes = assignment_leftover_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))

    candidates = CandidateSet()
    unmatched_old: list[BillNode] = []
    unmatched_new: list[BillNode] = []
    for population in retrieve_within_division_populations(old_nodes, new_nodes, registry):
        if not population.forms_candidates:
            unmatched_old.extend(population.old)
            unmatched_new.extend(population.new)
            continue
        population.propose_into(candidates)
        assignment = assign_group(population, group_correspondence_evidence(population, candidates))
        unmatched_old.extend(assignment.leftover_old)
        unmatched_new.extend(assignment.leftover_new)

    assert [n.element_id for n in unmatched_old] == ["oA2"], "within-division assignment stopped leaving oA2 over"
    assert [n.element_id for n in unmatched_new] == ["nB2"]

    cross = retrieve_cross_division_population(unmatched_old, unmatched_new, registry)
    assert cross is not None
    assert [ref.ordinal for ref in cross.old_refs] == [1] and [ref.ordinal for ref in cross.new_refs] == [2]

    cross.propose_into(candidates)
    (link,) = assign_group(cross, group_correspondence_evidence(cross, candidates)).links
    assert (link.old.element_id, link.new.element_id) == ("oA2", "nB2")


# --- B3: the unique path, brought under the same four stages ---------------------------------
#
# Before B3, a non-colliding `match_path` group was paired by a tuple construction: no candidate,
# no evidence record, no assignment. That is 14,001 of the corpus's selected round-1 pairings --
# the great majority -- reaching the stream without passing any ADR 0020 boundary, which is why
# the candidate set was collision-path-complete and a recall figure read off it was wrong by the
# size of that population.
#
# The frozen stream cannot see this slice at all: the unique path selected the only pairing
# available before and still does. What these bind is that the selection now goes THROUGH the
# stages -- admitted by the candidate set, described by the evidence stage, decided by
# assignment -- and that the fast path's measured cost profile survived the migration.


def unique_path_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """Two non-colliding ``match_path`` groups and one observation with no counterpart.

    Every group here takes the unique path: ``sec-1`` and ``sec-2`` are 1x1, and ``sec-3`` is
    old-side only. Nothing collides, so :func:`_match_collision_group` is never reached and a
    claim proved on this fixture is a claim about the unique path alone.

    The two 1x1 groups are deliberately in **different divisions** on either side. A unique path
    pairs across division lines -- ``match_path`` is the grouping key and division is never
    consulted -- and 730 committed corpus pairings do exactly this, so a migration that quietly
    acquired a division constraint has somewhere to fail.
    """
    old_nodes = [
        node(("sec-1",), "o1", "alpha alpha alpha appropriations for salaries and expenses", "A"),
        node(("sec-2",), "o2", "bravo bravo bravo appropriations for construction accounts", "A"),
        node(("sec-3",), "o3", "charlie charlie charlie with no counterpart at all", "A"),
    ]
    new_nodes = [
        node(("sec-1",), "n1", "alpha alpha alpha appropriations for salaries and expenses", "B"),
        node(("sec-2",), "n2", "bravo bravo bravo appropriations for construction accounts", "B"),
    ]
    return old_nodes, new_nodes


def unique_path_populations(old_nodes: list[BillNode], new_nodes: list[BillNode]) -> list[RetrievedPopulation]:
    """The unique-path retrieval stage's populations for a synthetic fixture, one per group.

    ``None`` results are dropped rather than represented: the stage's eligibility gate returns
    one for a group that can form no pair, which is not a population at all. The count is
    asserted where it matters, so a stage that started returning ``None`` for everything would
    not quietly shorten this list into agreement.
    """
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    old_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    new_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    for item in old_nodes:
        old_groups[item.match_path].append(item)
    for item in new_nodes:
        new_groups[item.match_path].append(item)
    populations = []
    for path in dict.fromkeys(list(old_groups) + list(new_groups)):
        group_old, group_new = old_groups.get(path, []), new_groups.get(path, [])
        assert len(group_old) <= 1 and len(group_new) <= 1, f"{path} collides; this fixture is for the unique path"
        population = retrieve_unique_path_population(group_old, group_new, registry)
        if population is not None:
            populations.append(population)
    return populations


def test_a_one_sided_unique_group_is_not_retrieved_at_all():
    """The eligibility gate, and that it is a gate rather than an empty population.

    A group with one observation and no counterpart forms no pair, so there is nothing to
    consider and no invocation to record. Returning an empty-sided population instead would put
    ``path_unique_group`` provenance on a retrieval that never happened -- and, at 15,587 such
    groups on the committed corpus, would do it more often than for the ones that pair.

    The lone observation still reaches the stream, which is the half a gate could plausibly
    break, so both are asserted.
    """
    old_nodes, new_nodes = unique_path_fixture()
    registry = observation_registry(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))
    lone = [item for item in old_nodes if item.element_id == "o3"]
    assert lone, "the fixture stopped carrying an observation with no counterpart"

    assert retrieve_unique_path_population(lone, [], registry) is None
    assert retrieve_unique_path_population([], new_nodes[:1], registry) is None
    assert retrieve_unique_path_population(old_nodes[:1], new_nodes[:1], registry) is not None

    assert [2, None] in production_stream(old_nodes, new_nodes), (
        "the unretrieved observation stopped reaching the pairing stream; a gate that drops it is "
        "deleting an observation rather than routing it unclaimed"
    )


def refusing_candidate_set(refused: tuple[int, int]):
    """A ``CandidateSet`` that declines to record ONE observation pair. Nothing else changes.

    The B3 counterpart of :func:`dropping_propose_into`, and deliberately faulted at the other
    end. ``dropping_propose_into`` mutates the *proposer*; this leaves ``propose_into`` and the
    ``RetrievedPopulation`` completely untouched and refuses the entry inside the set itself. So
    the population still says the pair was retrieved, every other pair is admitted normally, and
    the only thing that has moved is whether the admission authority holds this one.

    That is the exact shape of the defect the boundary exists to make unreachable: retrieval and
    the candidate set disagreeing about what was considered, while the pairing that results still
    looks correct.
    """

    class _Refusing(CandidateSet):
        def propose(self, old, new, invocation, *, rank=None, score=None):
            if (old.ordinal, new.ordinal) == refused:
                return
            super().propose(old, new, invocation, rank=rank, score=score)

    return _Refusing


@pytest.mark.slow
def test_the_unique_path_evidence_stage_describes_the_frozen_unique_selections():
    """B3's evidence calls, against the oracle's independently frozen unique-path record.

    ``unique_selections`` is the transcribed legacy composition's ordered list of every
    non-colliding group it paired, addressed by ADR 0019 ordinal and covered by the frozen trace
    digest. It was recorded by B0, before any of this existed, so it is an expectation the
    migration cannot have shaped.

    Three claims, all of which a migration could get wrong while leaving the stream intact: the
    unique path describes exactly those pairs, in that order, and each record carries **no
    signal at all** -- the 1x1 shortcut reached through the stage rather than around it.
    """
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)
        observed = [call for call in observed_group_evidence(old_tree, new_tree) if call["phase"] == "unique"]
        expected = oracle_trace(old_tree.nodes, new_tree.nodes)["unique_selections"]

        assert [call["links"] for call in observed] == [
            [[old_ordinal, new_ordinal, None]] for old_ordinal, new_ordinal in expected
        ], (
            f"{key}: the unique path's evidence records differ from the frozen unique selections "
            f"({len(observed)} described vs {len(expected)} expected)"
        )
        checked += 1

    assert checked, "the unique-path evidence comparison ran over zero version pairs"


@pytest.mark.slow
def test_no_round_1_pairing_reaches_the_stream_without_an_assignment_selecting_it():
    """THE B3 completeness gate: no two-sided round-1 output is paired by a tuple construction.

    The claim the slice exists to make true, and the one that fails silently. A bypass left in
    place for any group shape produces an identical pairing stream -- it selected the same
    pairing, just without passing a boundary -- so nothing else here can see it. This can: every
    1:1 pairing in the round-1 stream must be a :class:`SelectedLink` of some
    :class:`GroupAssignment`, and the two sets must agree exactly in both directions.

    A pairing in the stream with no link behind it is a surviving bypass. A link with no pairing
    in the stream is an assignment whose decision was discarded, which would be the same defect
    inverted.
    """
    total = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)
        ordinals = complete_sequence_ordinals(old_tree.nodes, new_tree.nodes)
        pairs, _candidates, assignments = match_nodes_with_stage_outputs(old_tree, new_tree)

        streamed = [
            (ordinals[id(old_node)], ordinals[id(new_node)])
            for old_node, new_node in pairs
            if old_node is not None and new_node is not None
        ]
        selected = [
            (ordinals[id(link.old)], ordinals[id(link.new)]) for assignment in assignments for link in assignment.links
        ]
        assert sorted(streamed) == sorted(selected), (
            f"{key}: {len(set(streamed) - set(selected))} round-1 pairings reached the stream with no "
            f"assignment selecting them, and {len(set(selected) - set(streamed))} selected links never "
            "reached the stream"
        )
        total += len(streamed)

    assert total > 1000, f"only {total} round-1 pairings over the corpus; this gate is near-vacuous"


def test_the_unique_path_selection_carries_the_record_admission_produced():
    """The selected link's evidence IS the object the evidence stage built, not an equal copy.

    ADR 0020 requires every selected link to carry the evidence that selected it. An
    implementation that rebuilt an equivalent record on the way out would satisfy every equality
    check in this file while severing the selection from its grounds -- and the rebuilt record
    would not have passed through admission at all.

    So this is an **identity** assertion, taken on the objects the stage returned. Captured by
    spying on the evidence stage, which is the only point downstream of
    ``candidate_for`` and upstream of assignment.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = unique_path_fixture()
    produced: list[CorrespondenceEvidence] = []
    real = db.group_correspondence_evidence

    def spy(population, candidates):
        evidence = real(population, candidates)
        produced.extend(evidence)
        return evidence

    db.group_correspondence_evidence = spy
    try:
        _pairs, _candidates, assignments = match_nodes_with_stage_outputs(
            _TreeStandIn(old_nodes), _TreeStandIn(new_nodes)
        )
    finally:
        db.group_correspondence_evidence = real

    assert len(produced) == 2, f"the evidence stage produced {len(produced)} records for two 1x1 groups"
    links = [link for assignment in assignments for link in assignment.links]
    assert len(links) == 2, f"the unique path selected {len(links)} of 2 available pairings"
    for link in links:
        assert any(link.evidence is item for item in produced), (
            "a selected link carries an evidence record the evidence stage never returned; the "
            "selection has been severed from the grounds admission produced"
        )


def test_the_unique_path_measures_nothing(monkeypatch):
    """The fast path's cost property, preserved through the stages rather than around them.

    ``text_similarity`` is bombed rather than counted, so a stage that measured would fail here
    even if it discarded the result. The pairing stream cannot show this -- selecting the sole
    candidate is what the greedy would do anyway -- and it is the property #623 measured the
    tidy-up of at +21%.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = unique_path_fixture()
    monkeypatch.setattr(db, "text_similarity", _refuse_to_measure)

    assert production_stream(old_nodes, new_nodes) == [[0, 0], [1, 1], [2, None]], (
        "the unique path stopped pairing both 1x1 groups, or stopped routing the one-sided group"
    )


def test_refusing_a_unique_pair_the_candidate_set_fails_closed(monkeypatch):
    """THE B3 DECISIVE CONTROL: the admission authority made load-bearing on the unique path.

    One fault, and it is a candidate-set-only fault: the entry for a real unique pair is refused
    while :func:`retrieve_unique_path_population` still returns that pair, under that invocation,
    in that order. Retrieval and the set then disagree about what was considered, which is
    precisely the state ADR 0020's intermediate value exists to make unreachable.

    Five claims:

    **A.** the population is unchanged -- same nodes, same refs, same invocation -- so this is a
    candidate defect and not a retrieval one wearing its name.
    **B.** the clean run selects that pair, so refusing it withholds something that would
    otherwise have been chosen rather than something that would have lost anyway.
    **C.** the set really is missing exactly that entry and nothing else.
    **D.** the evidence stage fails closed, naming the pair, rather than reconstructing it from
    population membership -- which is the tempting recovery and the whole hole this closes.
    **E.** production fails closed too, and **emits nothing**. The pair does not reappear through
    a retained fast path, a caught exception, an unmatched ``(old, None)`` plus ``(None, new)``,
    or any other fallback: no stream is returned at all. That is the half a "the pair is absent
    from the output" assertion could not distinguish from a bypass that merely re-labelled it.
    """
    from deltatrack import diff_bill as db

    old_nodes, new_nodes = unique_path_fixture()
    paired = unique_path_populations(old_nodes, new_nodes)
    assert len(paired) == 2, "the fixture stopped producing two 1x1 unique populations"

    target = paired[0]
    refused = (target.old_refs[0].ordinal, target.new_refs[0].ordinal)

    # B. the clean run selects this exact pair.
    clean = production_stream(old_nodes, new_nodes)
    assert list(refused) in clean, (
        f"the unfaulted run does not select {refused}, so refusing it proves nothing about a "
        "pairing that would otherwise have been made"
    )

    monkeypatch.setattr(db, "CandidateSet", refusing_candidate_set(refused))

    # A. the population the retrieval stage produces is untouched by the fault.
    after = unique_path_populations(old_nodes, new_nodes)
    assert [(p.old_refs, p.new_refs, p.invocation) for p in after] == [
        (p.old_refs, p.new_refs, p.invocation) for p in paired
    ], "the fault moved the retrieved population; it is no longer a candidate-set-only defect"

    # C. the set is missing exactly that entry.
    faulted = db.CandidateSet()
    honest = CandidateSet()
    for population in paired:
        population.propose_into(faulted)
        population.propose_into(honest)
    assert faulted.candidate_for(target.old_refs[0], target.new_refs[0]) is None, "the fault refused nothing"
    assert len(faulted) == len(honest) - 1, "the fault refused more than one pair; it is no longer isolating"

    # D. the evidence stage refuses it rather than reconstructing it from the population.
    with pytest.raises(ValueError, match="never admitted"):
        group_correspondence_evidence(target, faulted)

    # E. and production emits nothing at all rather than falling back.
    with pytest.raises(ValueError, match="never admitted"):
        match_nodes(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))


@pytest.mark.slow
def test_refusing_a_unique_pair_fails_closed_on_the_committed_corpus(monkeypatch):
    """The same fault on real bills, where the unique path carries most of the pairings.

    The synthetic control is exact about which pair and why; this answers the question it cannot,
    which is whether the boundary is wired on the path the engine takes over real documents.

    The refused pair is chosen from each comparison's own clean unique-path selections, so the
    fault is aimed at a pairing that comparison really makes. Every committed pair must fail
    closed: unlike the collision path, whose groups some comparisons may not have, every
    comparison in this corpus has unique 1x1 groups.
    """
    from deltatrack import diff_bill as db

    real_candidate_set = db.CandidateSet
    failed_closed = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        key = pair_key(old_path, new_path)

        selections = oracle_trace(old_tree.nodes, new_tree.nodes)["unique_selections"]
        assert selections, f"{key}: no unique-path selection to refuse"
        refused = (selections[0][0], selections[0][1])

        monkeypatch.setattr(db, "CandidateSet", refusing_candidate_set(refused))
        try:
            with pytest.raises(ValueError, match="never admitted"):
                match_nodes(old_tree, new_tree)
        finally:
            monkeypatch.setattr(db, "CandidateSet", real_candidate_set)
        failed_closed += 1

    assert failed_closed == len(manifest_version_pairs()), (
        f"only {failed_closed} committed comparisons failed closed under a refused unique candidate"
    )


def test_the_refusal_control_is_not_refusing_everything():
    """The negative control for the control: an unfaulted set still admits the pair it targets.

    Without this, a ``refusing_candidate_set`` that dropped every proposal -- or one whose ordinal
    comparison never matched and which therefore reddened production for some unrelated reason --
    would look exactly like a decisive result.
    """
    old_nodes, new_nodes = unique_path_fixture()
    paired = unique_path_populations(old_nodes, new_nodes)
    target, other = paired[0], paired[1]
    refused = (target.old_refs[0].ordinal, target.new_refs[0].ordinal)

    faulted = refusing_candidate_set(refused)()
    for population in paired:
        population.propose_into(faulted)

    assert faulted.candidate_for(target.old_refs[0], target.new_refs[0]) is None
    assert faulted.candidate_for(other.old_refs[0], other.new_refs[0]) is not None, (
        "the refusal dropped a pair it was not aimed at, so a fail-closed result would not be "
        "attributable to the pair the control names"
    )
    # And the untargeted group still resolves through the stages under the faulted set.
    evidence = group_correspondence_evidence(other, faulted)
    assert len(assign_group(other, evidence).links) == 1


def test_the_unique_path_runs_no_collision_machinery():
    """Structural: the migration reached the stages without reaching the expensive path.

    ADR 0020 §13 ruled to keep the fast path's cost rather than route every unique group through
    ``_match_collision_group``. B3 keeps that by orchestrating the SAME stages differently, not by
    adding a second implementation of them -- so the guard is two-sided: the unique orchestrator
    must call the shared stages, and must not reach the division partition or the cross-division
    round, neither of which can do anything for a group holding at most one observation per side.

    A structural guard rather than a timing assertion, deliberately. A wall-clock threshold in the
    suite would be a flake on a loaded machine and would say nothing about *why* the cost moved.
    What this pins is the shape -- which stages the unique path may reach -- and that is the part
    worth keeping; the cost comparison behind the B3 ruling was a closed question and lives in
    PR #632 rather than in a benchmark this suite has to keep alive.
    """
    import inspect

    from deltatrack.diff_bill import _match_unique_path_group

    tree = ast.parse(textwrap.dedent(inspect.getsource(_match_unique_path_group)))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert {"group_correspondence_evidence", "assign_group", "retrieve_unique_path_population"} <= called, (
        f"the unique path no longer runs the shared stages; it calls {sorted(called)}"
    )
    forbidden = called & {
        "_match_collision_group",
        "retrieve_within_division_populations",
        "retrieve_cross_division_population",
    }
    assert not forbidden, (
        f"the unique path reaches collision machinery {sorted(forbidden)}; the audit measured that "
        "routing at 2.57x and §13 ruled to keep the fast path's cost"
    )


def test_a_non_colliding_group_resolves_under_only_the_unique_path_invocation():
    """Behavioural: which retrieval provenance admits a group holding at most one per side.

    ADR 0020 §13 ruled to keep the fast path's cost by orchestrating the shared stages
    differently for a non-colliding ``match_path`` group, rather than routing it through
    ``_match_collision_group``. Until now that routing was owned only by a structural guard over
    ``_match_unique_path_group``'s AST and by preservation tests backed by the legacy oracle.
    This owns it from the outside, on the stage outputs production actually produced.

    **What makes the routing observable without reading an implementation.** The three round-1
    retrievers are distinguishable by the invocation each records on the proposals it makes.
    A collision group is partitioned by division and proposed under ``path_division_group``,
    and its leftovers get a second round under ``path_group_cross_division``. Neither can do
    anything for a group with at most one observation per side, so a unique group that reached
    collision machinery would carry one of those two invocations on the candidate that admitted
    it -- whatever pairing it went on to select. Provenance is the thing that moves; the pairing
    stream is not, which is why the frozen stream never saw this and a stream comparison cannot
    replace this test.

    **Production against production.** The candidate set and the assignments are both elements of
    one ``match_nodes_with_stage_outputs`` call, and the invocation is rebuilt from the literal
    retriever name rather than imported from the module under test -- an implementation that
    renamed the constant's *value* would move an imported expectation along with it.

    **The mutation.** Delegate ``_match_unique_path_group`` to ``_match_collision_group``: the
    two candidates are then proposed under ``path_division_group`` / ``path_group_cross_division``
    and the first assertion fails. Observed red before this test was relied on (issue #659).

    The link assertion is the premise control rather than decoration. A candidate set that
    admitted nothing would satisfy every "no collision invocation" claim above vacuously, so what
    the group actually decided is asserted alongside the provenance it decided under.
    """
    unique_path = RetrieverInvocation.of("path_unique_group", round=1)
    collision_retrievers = {"path_division_group", "path_group_cross_division"}

    old_nodes, new_nodes = unique_path_fixture()
    _pairs, candidates, assignments = match_nodes_with_stage_outputs(_TreeStandIn(old_nodes), _TreeStandIn(new_nodes))

    admitted = candidates.candidates()
    assert len(admitted) == 2, (
        f"the two 1x1 groups produced {len(admitted)} candidates; the fixture stopped presenting two "
        "pairable non-colliding groups, so what this proves about the unique path is not what it says"
    )
    for candidate in admitted:
        assert candidate.invocations == (unique_path,), (
            f"candidate {candidate.ordinal_pair} was admitted by "
            f"{[invocation.retriever for invocation in candidate.invocations]}; a non-colliding group "
            "must be considered once, by the unique path, under its own provenance"
        )
    reached = {invocation.retriever for candidate in admitted for invocation in candidate.invocations}
    assert not reached & collision_retrievers, (
        f"the unique path reached collision machinery {sorted(reached & collision_retrievers)}; the audit "
        "measured that routing at 2.96x and §13 ruled to keep the fast path's cost"
    )

    links = [link for assignment in assignments for link in assignment.links]
    assert sorted((link.old.element_id, link.new.element_id) for link in links) == [("o1", "n1"), ("o2", "n2")], (
        "the unique path stopped selecting the two available pairings, so the provenance asserted above "
        "is the provenance of a group that decided nothing"
    )


# --- Independence, enforced structurally --------------------------------------------------

#: Every round-1 symbol the oracle must not reach, B1's, B2's and B3's included. The set was
#: written before those stages existed, and naming them ahead of time was the point: it refused
#: in advance the change that would quietly make this harness self-validating. It is maintained
#: the same way now -- a stage added later belongs here before it has a caller, not after.
FORBIDDEN_IN_ORACLE = frozenset(
    {
        # today's production round 1
        "match_nodes",
        "_match_collision_group",
        "similarity_correspondence_evidence",
        "apply_similarity_assignment_rule",
        "_similarity_rule_keeps",
        "_similarity_signals",
        # B1's retrieval stages, under the names they actually shipped with. The pre-B1 version
        # of this set guessed `retrieve_division_candidates` /
        # `retrieve_cross_division_candidates`, which no longer name anything -- a guard listing
        # symbols that do not exist protects nothing, so these are corrected to the real ones.
        "retrieve_within_division_populations",
        "retrieve_cross_division_population",
        "match_nodes_with_retrieval",
        "RetrievedPopulation",
        # B2's stages and result types, under the names they shipped with. `_similarity_pair` is
        # gone from this set for the reason B1 corrected its own guesses: B2 replaced it with the
        # two below, and a guard listing a symbol that no longer exists protects nothing.
        "group_correspondence_evidence",
        "assign_group",
        "GroupAssignment",
        "SelectedLink",
        "match_nodes_with_stage_outputs",
        "_refuse_a_candidate_retrieval_did_not_admit",
        # B3's unique-path retriever and its orchestrator, under the names they shipped with. The
        # oracle transcribes the fast path as a tuple append and must keep doing so: wiring it to
        # the migrated path is exactly how the expectation would come to move with the code.
        "retrieve_unique_path_population",
        "_match_unique_path_group",
        # and the module they would arrive through
        "diff_bill",
    }
)

ORACLE_FUNCTIONS = (
    legacy_normalize,
    legacy_similarity_pair,
    legacy_collision_group,
    legacy_match_nodes,
    oracle_trace,
)


def test_the_oracle_names_no_round_1_production_symbol():
    """The oracle cannot self-validate, proven over its own source rather than asserted.

    Walks each oracle function's AST for any Name or Attribute matching a round-1 production
    symbol -- current or planned. A wrapper that merely delegated would name one of them, and
    so would an import of ``diff_bill`` inside the oracle.
    """
    for fn in ORACLE_FUNCTIONS:
        tree = ast.parse(inspect.getsource(fn))
        named = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        named |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        offending = named & FORBIDDEN_IN_ORACLE
        assert not offending, (
            f"{fn.__name__} names round-1 production symbols {sorted(offending)}; the oracle would "
            "move with the code it exists to check"
        )


def test_the_independence_guard_can_fire():
    """The negative control for the guard above: a delegating oracle must be caught.

    Without this, the guard is an assertion of absence that would pass just as happily if the
    AST walk were looking at the wrong thing.
    """

    def delegating_oracle(old_tree, new_tree):
        return match_nodes(old_tree, new_tree)

    # dedent because getsource on a nested function keeps its indentation, which ast.parse
    # rejects. The guard above reads module-level functions and does not hit this.
    source = textwrap.dedent(inspect.getsource(delegating_oracle))
    named = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert named & FORBIDDEN_IN_ORACLE, "the guard failed to see a plainly delegating oracle"


def test_the_oracle_module_reaches_diff_bill_only_for_the_production_comparison():
    """``diff_bill`` may be imported here, but only where production is being MEASURED.

    The module-level import of ``match_nodes`` is legitimate -- the durable gate has to call
    production. What must not happen is the oracle body reaching it, which the AST guard
    above covers. This pins the import surface so a new production import arrives as a
    deliberate edit rather than a convenience.
    """
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("deltatrack"):
            imported |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names if a.name.startswith("deltatrack")}

    assert imported == {
        "deltatrack.bill_tree.BillNode",
        "deltatrack.bill_tree.normalize_bill",
        "deltatrack.diff_bill.match_nodes",
        "deltatrack.similarity.text_similarity",
        # The module itself, for the stage-boundary observer and the retrieval-order mutations,
        # both of which have to reach into production to patch the stage they measure.
        "deltatrack.diff_bill",
        # B1's retrieval stages and their output type, imported so the candidate-materialisation
        # gate can drive and inspect them. They are the code UNDER TEST, never the source of the
        # expected value: the expectation is expanded from the oracle's invocation trace, and the
        # AST guard above refuses every one of these names inside an oracle function.
        "deltatrack.diff_bill.RetrievedPopulation",
        "deltatrack.diff_bill.match_nodes_with_retrieval",
        "deltatrack.diff_bill.observation_registry",
        "deltatrack.diff_bill.retrieve_cross_division_population",
        "deltatrack.diff_bill.retrieve_within_division_populations",
        # B2's evidence and assignment stages, their result types and the projection that
        # returns them. Same standing as the line above: driven and inspected, never consulted
        # for what the answer should be. The injection harness also builds a `GroupAssignment`,
        # which is re-expressing the ORACLE's pairing stream in production's result type rather
        # than delegating a decision to production.
        "deltatrack.diff_bill.GroupAssignment",
        "deltatrack.diff_bill.SelectedLink",
        "deltatrack.diff_bill.assign_group",
        "deltatrack.diff_bill.group_correspondence_evidence",
        "deltatrack.diff_bill.match_nodes_with_stage_outputs",
        # Contract vocabulary from `matching`, which holds no matching policy: the two side
        # constants, the candidate container, the invocation type the expectation rebuilds, and
        # the evidence record the B2 controls hand to assignment by hand.
        "deltatrack.matching.CandidateSet",
        "deltatrack.matching.CorrespondenceEvidence",
        "deltatrack.matching.NEW",
        "deltatrack.matching.OLD",
        "deltatrack.matching.RetrieverInvocation",
        # Read for their SOURCE only, by the two structural checks: that assignment cannot
        # receive the candidate set, and that the evidence path reaches it by lookup rather than
        # by iterating it. Neither is called from this module, and the AST guard above still
        # refuses either name inside an oracle function.
        "deltatrack.diff_bill._match_collision_group",
        "deltatrack.diff_bill._refuse_a_candidate_retrieval_did_not_admit",
        # B3's unique-path retriever, driven and inspected by the unique-path controls. Same
        # standing as B1's and B2's stages: it is the code UNDER TEST, and the expectation it is
        # held to is the oracle's `unique_selections`, which B0 froze before any of it existed.
        "deltatrack.diff_bill.retrieve_unique_path_population",
        # Read for its SOURCE only, by the guard that the unique orchestrator runs the shared
        # stages without reaching the collision machinery.
        "deltatrack.diff_bill._match_unique_path_group",
    }, f"the production import surface moved: {sorted(imported)}"


# --- ADR 0019: where an ordinal is allowed to come from --------------------------------------


def test_an_ordinal_is_refused_for_a_node_outside_the_complete_sequence():
    """The bridge fails closed rather than inventing an address.

    A node the parse never emitted has no ordinal. Returning ``None`` would put a null in the
    trace that compares equal to every other null -- the same collapse that keying on a repeated
    ``element_id`` causes, arriving by a different route.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    rec = Recorder(complete_sequence_ordinals(old_nodes, new_nodes))
    stranger = node(MP, "not-in-this-parse", "text from another document", "D")

    with pytest.raises(ValueError, match="absent from the complete emitted sequence"):
        rec.ordinal(stranger)


def test_ordinals_are_not_derived_from_an_invocation_population():
    """The ADR 0019 hazard, demonstrated on the fixture where the two numberings disagree.

    ADR 0019 names indexing a filtered or re-sorted view as a real hazard because the resulting
    address looks valid and points at the wrong node. The cross-division fallback population is
    exactly such a view: on the interleaved fixture it holds [X2, Y1], whose complete-sequence
    ordinals are [2, 1] while their positions *within that population* are [0, 1].

    The trace must carry the former. If it ever carried the latter, every fallback address in
    the frozen artifact would silently name a different observation.
    """
    old_nodes, new_nodes = interleaved_division_fixture()
    trace = oracle_trace(old_nodes, new_nodes)
    cross = next(i for i in trace["invocations"] if i["phase"] == "cross")

    complete = complete_sequence_ordinals(old_nodes, new_nodes)
    by_complete_sequence = [complete[id(n)] for n in (old_nodes[2], old_nodes[1])]  # X2, Y1
    by_population_position = list(range(len(cross["old"])))

    assert by_complete_sequence == [2, 1]
    assert by_population_position == [0, 1]
    assert by_complete_sequence != by_population_position, (
        "the fixture no longer distinguishes the two numberings, so this proves nothing"
    )
    assert cross["old"] == by_complete_sequence, (
        f"the fallback population is addressed by {cross['old']}, which is not the complete "
        "emitted sequence ordinal -- ADR 0019's filtered-view hazard"
    )


@pytest.mark.slow
def test_every_frozen_ordinal_indexes_a_real_node_of_its_side():
    """Range check over the whole artifact: no address falls outside its side's sequence.

    Cheap, and it closes the one way a complete-sequence ordinal can still be wrong without any
    digest noticing: an off-by-one or a side mix-up produces a valid-looking integer.
    """
    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        trace = oracle_trace(old_tree.nodes, new_tree.nodes)
        n_old, n_new = len(old_tree.nodes), len(new_tree.nodes)

        for old_ordinal, new_ordinal in trace["stream"]:
            assert old_ordinal is None or 0 <= old_ordinal < n_old
            assert new_ordinal is None or 0 <= new_ordinal < n_new
        for invocation in trace["invocations"]:
            assert all(0 <= o < n_old for o in invocation["old"])
            assert all(0 <= n < n_new for n in invocation["new"])
        checked += 1

    assert checked, "the range check ran over zero version pairs"


# --- The two synthetic fixtures the corpus cannot supply -----------------------------------


class _TreeStandIn:
    """The one attribute ``observation_registry`` and ``match_nodes`` read off a tree.

    A synthetic fixture is a node list, not a parsed bill, and the registry only ever needs the
    complete emitted sequence for each side. Building a real ``BillTree`` would mean inventing a
    congress, bill type and version that nothing here reads.
    """

    def __init__(self, nodes: list[BillNode]) -> None:
        self.nodes = nodes


def node(match_path, element_id, body, division_key) -> BillNode:
    return BillNode(
        match_path=match_path,
        display_path=match_path,
        tag="section",
        element_id=element_id,
        header_text="",
        body_text=body,
        section_number="1",
        division_label=division_key,
        division_key=division_key,
    )


MP = ("sec-1",)


def assignment_leftover_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """Division A leaves an OLD over, division B leaves a NEW over; only the fallback can pair them.

    The shape the committed corpus never presents: 238 groups produce within-division
    assignment leftovers and 30 reach the fallback, but never the same group.
    """
    old_nodes = [
        node(MP, "oA1", "alpha alpha alpha the quick brown fox", "A"),
        node(MP, "oA2", "zulu zulu zulu unmatched leftover old text", "A"),
        node(MP, "oB1", "bravo bravo bravo jumps over the lazy dog", "B"),
    ]
    new_nodes = [
        node(MP, "nA1", "alpha alpha alpha the quick brown fox", "A"),
        node(MP, "nB1", "bravo bravo bravo jumps over the lazy dog", "B"),
        node(MP, "nB2", "zulu zulu zulu unmatched leftover old text", "B"),
    ]
    return old_nodes, new_nodes


#: The body two fallback participants share, so their scores against ``nZ1`` are equal and the
#: tie -- not the similarity -- decides which one wins.
_TIED_BODY = "xray xray xray leftover from division x"


def interleaved_division_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """Divisions interleave in parser order AND the fallback's two candidates tie.

    Both halves are needed, and the first alone is not enough -- which the negative control
    below is what established. Old parser order is X1(0), Y1(1), X2(2). Division X leaves X2
    over; division Y is one-sided and contributes Y1; so the fallback population is
    [X2, Y1] -- ordinals [2, 1], out of parser order.

    ``X2`` and ``Y1`` carry the SAME body, so both score 1.0 against ``nZ1`` and the
    ``(similarity, oi, ni)`` tie is what picks the winner. Descending local position picks
    ``Y1`` (local 1); descending parser ordinal would pick ``X2`` (ordinal 2). Without the
    tie the similarities differ, the tiebreak never fires, and an implementation that
    substituted ordinals for local positions would pass here as well as on the corpus.
    """
    old_nodes = [
        node(MP, "X1", "alpha alpha alpha shared opening text here", "X"),
        node(MP, "Y1", _TIED_BODY, "Y"),
        node(MP, "X2", _TIED_BODY, "X"),
    ]
    new_nodes = [
        node(MP, "nX1", "alpha alpha alpha shared opening text here", "X"),
        node(MP, "nZ1", _TIED_BODY, "Z"),
    ]
    return old_nodes, new_nodes


#: The id two distinct old observations share in the fixture below. ``bill_tree`` reads the
#: attribute as ``attrib.get("id", "")``, so a repeated -- or empty -- id is representable in
#: real markup; ADR 0019 measured 144 synthesized ids across 48 documents and refuses to rest
#: identity on a property of externally authored XML that can only ever be sampled.
_DUPLICATE_ID = "dup"


def duplicate_element_id_fixture() -> tuple[list[BillNode], list[BillNode]]:
    """Two distinct old observations carrying the SAME ``element_id``, both of which get paired.

    One ``match_path`` group, one division, two old and two new observations, so the greedy
    runs and claims both pairs. The two old observations are genuinely different provisions --
    different bodies, different ordinals -- and differ only in that the source markup gave them
    the same id.

    This is what makes an element-id-keyed trace unable to answer "which of these two
    corresponds to which", and it is the population
    :func:`test_a_swap_between_same_id_observations_is_invisible_to_element_ids` mutates.
    """
    old_nodes = [
        node(MP, _DUPLICATE_ID, "alpha alpha alpha appropriations for salaries and expenses", "D"),
        node(MP, _DUPLICATE_ID, "bravo bravo bravo appropriations for construction accounts", "D"),
    ]
    new_nodes = [
        node(MP, "n-alpha", "alpha alpha alpha appropriations for salaries and expenses", "D"),
        node(MP, "n-bravo", "bravo bravo bravo appropriations for construction accounts", "D"),
    ]
    return old_nodes, new_nodes


def production_stream(old_nodes: list[BillNode], new_nodes: list[BillNode]) -> list[list[int | None]]:
    """Production's pairing stream for a synthetic node list, addressed by ADR 0019 ordinal."""

    class _Tree:
        def __init__(self, nodes):
            self.nodes = nodes

    ordinals = complete_sequence_ordinals(old_nodes, new_nodes)
    return [
        [ordinals[id(o)] if o is not None else None, ordinals[id(n)] if n is not None else None]
        for o, n in match_nodes(_Tree(old_nodes), _Tree(new_nodes))
    ]


def test_assignment_leftovers_reach_the_cross_division_fallback():
    """The behaviour no corpus gate can observe, pinned exactly -- oracle and production.

    ``oA2`` (old ordinal 1) is left over by within-division ASSIGNMENT in division A; ``nB2``
    (new ordinal 2) is left over in division B. They pair only because the fallback's population
    includes observations that assignment declined, which is the dependency the whole separation
    has to preserve.

    Addresses are ordinals: old ``[oA1, oA2, oB1]`` = 0,1,2 and new ``[nA1, nB1, nB2]`` = 0,1,2.
    """
    old_nodes, new_nodes = assignment_leftover_fixture()
    trace = oracle_trace(old_nodes, new_nodes)

    assert [(i["phase"], i["old"], i["new"]) for i in trace["invocations"]] == [
        ("within", [0, 1], [0]),
        ("within", [2], [1, 2]),
        ("cross", [1], [2]),
    ]
    assert trace["stream"] == [[0, 0], [2, 1], [1, 2]]
    assert production_stream(old_nodes, new_nodes) == [[0, 0], [2, 1], [1, 2]]


def test_the_fallback_population_is_not_in_parser_ordinal_order():
    """Local fallback positions and parser ordinals disagree -- constructible, never in the corpus.

    Pins the divergence itself, so a later implementation that reads ``ObservationRef``
    ordinals where production reads local positions is caught here rather than on a bill.

    Old ``[X1, Y1, X2]`` = ordinals 0,1,2; new ``[nX1, nZ1]`` = 0,1.
    """
    old_nodes, new_nodes = interleaved_division_fixture()
    trace = oracle_trace(old_nodes, new_nodes)

    cross = [i for i in trace["invocations"] if i["phase"] == "cross"]
    assert len(cross) == 1, "the fixture stopped exercising the cross-division fallback"

    # The population is [X2, Y1] -- ordinals [2, 1], i.e. NOT ascending. Local position 0 is
    # ordinal 2 and local position 1 is ordinal 1, which is what makes the two keys disagree.
    assert cross[0]["old"] == [2, 1], "the fallback population lost its concatenation order"
    assert cross[0]["old"] != sorted(cross[0]["old"]), (
        "the fixture no longer produces a fallback population out of parser-ordinal order, so the "
        "ordinal-substitution control below cannot fire"
    )

    # The tie is the other half. Without it the two candidates are separated by similarity and
    # the tiebreak never runs, which is how the first version of this fixture failed to bind
    # the ordinal-substitution control at all.
    scores = {(oi, ni): s for s, oi, ni in (tuple(c) for c in cross[0]["candidates"])}
    assert len(set(scores.values())) == 1, f"the fallback candidates no longer tie: {scores}"

    # Descending LOCAL position picks local 1 (= Y1, ordinal 1). Descending parser ordinal would
    # pick local 0 (= X2, ordinal 2). `selected` stays in LOCAL positions: it is legacy ordering
    # machinery, not an address, and #590 measured that substituting ordinals moves selection.
    assert cross[0]["selected"] == [[1, 0]]
    assert production_stream(old_nodes, new_nodes) == [[0, 0], [1, 1], [2, None]]


# --- The decisive control for the identity representation -----------------------------------


def test_the_duplicate_id_fixture_really_does_repeat_one_id():
    """The premise, checked, so the control below cannot pass for the wrong reason.

    If the two old observations stopped sharing an id -- or stopped being two -- the swap would
    be visible to both representations and would prove nothing about either.
    """
    old_nodes, _new_nodes = duplicate_element_id_fixture()
    assert len(old_nodes) == 2
    assert old_nodes[0].element_id == old_nodes[1].element_id == _DUPLICATE_ID
    assert old_nodes[0].body_text != old_nodes[1].body_text, "the two observations must be distinct"

    # Both pairs score 1.0, so the `(similarity, oi, ni)` descending tiebreak emits local 1
    # before local 0 -- the stream is [[1,1],[0,0]] rather than [[0,0],[1,1]].
    trace = oracle_trace(*duplicate_element_id_fixture())
    assert trace["stream"] == [[1, 1], [0, 0]], "the fixture must pair both old observations"


def test_a_swap_between_same_id_observations_is_invisible_to_element_ids():
    """THE control for this correction. Both halves, on one mutation.

    The mutation exchanges which of the two same-id old observations corresponds to which new
    observation, leaving the emitted row order and both new partners untouched. A matcher could
    do exactly this and be wrong about every pairing it reports.

    **A. The superseded representation cannot see it.** Keyed by ``element_id``, both rows read
    ``("dup", <new id>)`` before and after, so the streams are textually identical and any
    digest over them is equal. A gate built on that representation is green on a matcher that
    has swapped two provisions.

    **B. The corrected representation does see it**, because the two observations have distinct
    ADR 0019 ordinals -- which is the property ADR 0019 says is unique by construction, where
    ``element_id``'s uniqueness is only ever sampled.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    swap = frozenset({"swap_first_two_old_partners"})

    # A. element_id projection: identical, so the old gate stays green on a swapped matcher.
    #    Row order is the greedy's: both pairs score 1.0 and the descending tiebreak emits the
    #    higher local position first, so "n-bravo" leads.
    baseline_ids = element_id_projection(old_nodes, new_nodes)
    swapped_ids = element_id_projection(old_nodes, new_nodes, swap)
    assert baseline_ids == swapped_ids == [["dup", "n-bravo"], ["dup", "n-alpha"]], (
        f"the element-id projection was expected to be blind to the swap; got {baseline_ids} then {swapped_ids}"
    )
    assert stream_digest(baseline_ids) == stream_digest(swapped_ids), (
        "an element-id-keyed digest distinguished the swap, so this fixture no longer demonstrates "
        "the false green the ordinal representation exists to close"
    )

    # B. ordinal projection: the correspondence actually moved, and the digest says so.
    #    Baseline pairs old 1 with new 1 and old 0 with new 0; the swap crosses them.
    baseline = oracle_trace(old_nodes, new_nodes)
    swapped = oracle_trace(old_nodes, new_nodes, swap)
    assert baseline["stream"] == [[1, 1], [0, 0]]
    assert swapped["stream"] == [[0, 1], [1, 0]], "the mutation did not exchange the two old partners"
    assert stream_digest(baseline["stream"]) != stream_digest(swapped["stream"])
    assert trace_digest(baseline) != trace_digest(swapped)


def test_the_named_gate_reddens_on_the_same_id_swap():
    """The gate that must go red, named and exercised end to end.

    :func:`test_production_reproduces_the_frozen_pairing_stream` compares
    ``stream_digest`` of production's ordinal-addressed stream against the frozen
    ``stream_sha256``. This reproduces that comparison against the swapped matcher on the
    duplicate-id fixture, and requires it to fail -- while the element-id comparison it
    replaced passes.
    """
    old_nodes, new_nodes = duplicate_element_id_fixture()
    frozen_stream_sha = stream_digest(oracle_trace(old_nodes, new_nodes)["stream"])
    swapped = oracle_trace(old_nodes, new_nodes, frozenset({"swap_first_two_old_partners"}))

    assert stream_digest(swapped["stream"]) != frozen_stream_sha, (
        "test_production_reproduces_the_frozen_pairing_stream's comparison stayed green on a "
        "swapped correspondence; the corrected representation is not actually binding"
    )
    superseded_sha = stream_digest(element_id_projection(old_nodes, new_nodes))
    superseded_swapped = stream_digest(
        element_id_projection(old_nodes, new_nodes, frozenset({"swap_first_two_old_partners"}))
    )
    assert superseded_sha == superseded_swapped, (
        "the element-id comparison also reddened, so this no longer isolates the representation "
        "as the thing that made the difference"
    )


# --- Negative controls --------------------------------------------------------------------
#
# Each entry is a mutation of the oracle. The claim under test is that the FROZEN expectation
# can distinguish it -- i.e. that a production implementation carrying this defect would be
# caught rather than shipping green. A mutation that changed nothing would prove the gate
# blind, which is the failure mode ADR 0020 invariant 12 names.

CORPUS_CONTROLS = [
    "ascending_tie",
    "flatten_divisions",
    "reorder_winners",
    "reorder_leftovers",
    "candidate_set_order",
    "unique_path_needs_same_division",
]

SYNTHETIC_CONTROLS = ["ordinal_tiebreak", "no_assignment_leftovers", "extra_cross_candidate"]


@pytest.mark.slow
@pytest.mark.parametrize("mutation", CORPUS_CONTROLS)
def test_a_corpus_visible_mutation_reddens_the_frozen_trace(mutation: str):
    """Each mutation must move the frozen digest on at least one committed pair."""
    frozen = load_frozen()
    moved = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        mutated = oracle_trace(old_tree.nodes, new_tree.nodes, frozenset({mutation}))
        if trace_digest(mutated) != frozen[pair_key(old_path, new_path)]["sha256"]:
            moved.append(pair_key(old_path, new_path))
    assert moved, (
        f"the {mutation!r} mutation changed nothing on any committed pair, so the frozen trace "
        "cannot detect it and this gate is blind to that defect"
    )


def inject_into_production(monkeypatch, mutation: str | None) -> None:
    """Replace production's ``assign_group`` with the oracle's competition, optionally mutated.

    **Retargeted from ``_similarity_pair`` to the stage that inherited its selection policy.**
    B2 split the fused scorer, so the seam a round-1 assignment regression would actually live
    behind is now :func:`assign_group`; injecting at the old name would patch nothing and the
    control would read green while testing an unpatched engine.

    The adapter is deliberately thin. The oracle still decides -- it is handed the population's
    two ordered node lists and returns a pairing stream exactly as before -- and this only
    re-expresses that stream in the stage's result type, routing matched pairs to links and the
    rest to leftovers. Each selected link is given the record that already describes it, taken
    from the evidence production computed, so the injected stage satisfies the same
    every-link-carries-its-evidence invariant without inventing a signal.

    ``monkeypatch`` restores it, including on failure.
    """
    variant = frozenset({mutation}) if mutation else frozenset()

    def replacement(population, evidence):
        by_link = {item.link: item for item in evidence}
        old_ref_of = {id(node): ref for node, ref in zip(population.old, population.old_refs)}
        new_ref_of = {id(node): ref for node, ref in zip(population.new, population.new_refs)}

        links: list[SelectedLink] = []
        leftover_old: list[BillNode] = []
        leftover_new: list[BillNode] = []
        for old_node, new_node in legacy_similarity_pair(
            list(population.old), list(population.new), Recorder.selection_only(), "injected", variant
        ):
            if old_node is None:
                leftover_new.append(new_node)
            elif new_node is None:
                leftover_old.append(old_node)
            else:
                link = (old_ref_of[id(old_node)], new_ref_of[id(new_node)])
                links.append(SelectedLink(old_node, new_node, by_link[link]))

        return GroupAssignment(
            evidence=evidence,
            links=tuple(links),
            leftover_old=tuple(leftover_old),
            leftover_new=tuple(leftover_new),
        )

    monkeypatch.setattr("deltatrack.diff_bill.assign_group", replacement)


@pytest.mark.slow
def test_the_injection_harness_alone_changes_nothing(monkeypatch):
    """The control for the control: an UNMUTATED injection must reproduce the frozen stream.

    Without it, the fault-injection test below could be reddening because the oracle differs
    from production rather than because the mutation bites -- a drifted copy mistaken for a
    detected fault, which is exactly what ``probe_canonical_sensitivity`` guards against on
    the round-2 side.
    """
    frozen = load_frozen()
    inject_into_production(monkeypatch, None)
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        ordinals = complete_sequence_ordinals(old_tree.nodes, new_tree.nodes)
        produced = [
            [ordinals[id(o)] if o is not None else None, ordinals[id(n)] if n is not None else None]
            for o, n in match_nodes(old_tree, new_tree)
        ]
        key = pair_key(old_path, new_path)
        assert stream_digest(produced) == frozen[key]["stream_sha256"], (
            f"{key}: substituting the oracle for production's own assign_group moved the stream, "
            "so the oracle is not a faithful transcription and every control below is unreadable"
        )


@pytest.mark.slow
def test_the_durable_gate_reddens_on_a_fault_injected_into_PRODUCTION(monkeypatch):
    """The gate fires against production, not merely against a mutated oracle.

    Every other control here mutates the oracle and shows the frozen expectation can tell the
    difference. This one puts the fault where a regression would actually live -- inside the
    function ``match_nodes`` calls -- and confirms the durable production gate goes red.
    """
    frozen = load_frozen()
    inject_into_production(monkeypatch, "ascending_tie")

    moved = []
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        ordinals = complete_sequence_ordinals(old_tree.nodes, new_tree.nodes)
        produced = [
            [ordinals[id(o)] if o is not None else None, ordinals[id(n)] if n is not None else None]
            for o, n in match_nodes(old_tree, new_tree)
        ]
        if stream_digest(produced) != frozen[pair_key(old_path, new_path)]["stream_sha256"]:
            moved.append(pair_key(old_path, new_path))

    assert moved, (
        "flipping the tie direction inside production changed no committed pair's pairing stream; "
        "the durable gate cannot see a real round-1 assignment regression"
    )


@pytest.mark.parametrize("mutation", SYNTHETIC_CONTROLS)
def test_a_corpus_invisible_mutation_reddens_a_synthetic_fixture(mutation: str):
    """The three mutations no corpus gate can see, each caught by a synthetic fixture.

    Without these fixtures every one of them ships green: the corpus supplies no fallback
    participant produced by assignment, and no greedy population out of ordinal order.
    """
    variant = frozenset({mutation})
    fixtures = {
        "assignment_leftover": assignment_leftover_fixture(),
        "interleaved_division": interleaved_division_fixture(),
    }
    moved = []
    for name, (old_nodes, new_nodes) in fixtures.items():
        baseline = oracle_trace(old_nodes, new_nodes)
        mutated = oracle_trace(old_nodes, new_nodes, variant)
        if trace_digest(mutated) != trace_digest(baseline):
            moved.append(name)
    assert moved, f"the {mutation!r} mutation changed neither synthetic fixture; the fixtures do not bind it"


@pytest.mark.slow
def test_the_corpus_cannot_see_the_two_fixture_bound_mutations():
    """The claim the fixtures rest on, measured rather than asserted.

    ``ordinal_tiebreak`` and ``no_assignment_leftovers`` leave every committed pair's digest
    untouched. That is precisely why the fixtures are mandatory -- and if this test ever goes
    red, the corpus has grown a case that exercises them and the finding needs revisiting.
    """
    frozen = load_frozen()
    for mutation in ("ordinal_tiebreak", "no_assignment_leftovers"):
        moved = []
        for old_path, new_path in manifest_version_pairs():
            old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
            mutated = oracle_trace(old_tree.nodes, new_tree.nodes, frozenset({mutation}))
            if trace_digest(mutated) != frozen[pair_key(old_path, new_path)]["sha256"]:
                moved.append(pair_key(old_path, new_path))
        assert not moved, (
            f"{mutation!r} now moves the corpus on {moved}; the audit's claim that this behaviour is "
            "corpus-invisible no longer holds and the synthetic-fixture rationale needs restating"
        )


# --- The 1x1 shortcut's performance property ------------------------------------------------


@pytest.mark.slow
def test_the_1x1_shortcut_computes_no_word_overlap():
    """An OPTIMISATION preservation gate, not a matching one.

    The shortcut selects the sole candidate, which is what the greedy would do anyway, so the
    pairing stream cannot show whether a ratio was computed. What changes is the count of
    ``text_similarity`` calls -- 593 invocations skip it today. #623 measured the equivalent
    tidy-up at +21% on ``diff_bills`` and rejected it; this keeps that decision visible.
    """
    frozen = load_frozen()
    total_calls = total_shortcuts = 0
    for old_path, new_path in manifest_version_pairs():
        counts = frozen[pair_key(old_path, new_path)]["counts"]
        total_calls += counts["similarity_calls"]
        total_shortcuts += counts["shortcut_1x1"]

    assert total_shortcuts, "no invocation took the shortcut, so its absence assertion proves nothing"

    inflated = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        mutated = oracle_trace(old_tree.nodes, new_tree.nodes, frozenset({"shortcut_computes_similarity"}))
        inflated += mutated["similarity_calls"]

    assert inflated > total_calls, (
        "computing the ratio on every 1x1 did not raise the call count, so this gate cannot see the "
        "optimisation regression it exists for"
    )
