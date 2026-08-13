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
structurally rather than by convention, and it lists the stage names B1 and B2 will
introduce so that wiring the oracle to a *future* stage is refused in advance.

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

Measured in the round-1 audit and reproduced by
``docs/research/provision-matching/probes/round1_decisive.py``: over all 27 committed
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
from deltatrack.diff_bill import match_nodes
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
        """A recorder for running the oracle as a drop-in ``_similarity_pair``, recording nothing."""
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
    which is the boundary B2 will consume, so this survives ``_similarity_pair`` being split
    into evidence and assignment.
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
    """Structural: ``CandidateSet`` iteration order cannot become assignment order.

    ADR 0020's candidate set is canonically ordered by ordinal pair, and B0 measured that using
    that order as assignment order changes the selected links on 174 of 329 greedy invocations.
    The protection is the call signature rather than a convention: the scorer is handed two
    ordered lists and has no reference to the set, so no ordering it carries can reach a
    selection.
    """
    import inspect

    from deltatrack.diff_bill import _match_collision_group, _similarity_pair

    assert "candidates" not in inspect.signature(_similarity_pair).parameters

    body = inspect.getsource(_match_collision_group)
    tree = ast.parse(textwrap.dedent(body))
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        if call.func.id != "_similarity_pair":
            continue
        named = {n.id for arg in call.args for n in ast.walk(arg) if isinstance(n, ast.Name)}
        assert "candidates" not in named, (
            f"the scorer is called with the candidate set in scope as an argument: {sorted(named)}"
        )


# --- Independence, enforced structurally --------------------------------------------------

#: Every round-1 symbol the oracle must not reach, including the ones B1 and B2 will
#: introduce. Naming the future stages here is the point: it refuses in advance the change
#: that would quietly make this harness self-validating.
FORBIDDEN_IN_ORACLE = frozenset(
    {
        # today's production round 1
        "match_nodes",
        "_match_collision_group",
        "_similarity_pair",
        "similarity_correspondence_evidence",
        "apply_similarity_assignment_rule",
        "_similarity_rule_keeps",
        "_similarity_signals",
        # the stages B1 and B2 will add
        "retrieve_division_candidates",
        "retrieve_cross_division_candidates",
        "group_correspondence_evidence",
        "assign_group",
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
        # Read for their SIGNATURE and source only, by the structural check that assignment
        # cannot receive the candidate set. Neither is called from this module, and the AST guard
        # above still refuses either name inside an oracle function.
        "deltatrack.diff_bill._match_collision_group",
        "deltatrack.diff_bill._similarity_pair",
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
    """Replace production's ``_similarity_pair`` with the oracle's, optionally mutated.

    Signature-compatible, so ``match_nodes`` and ``_match_collision_group`` drive it exactly
    as they drive their own. ``monkeypatch`` restores it, including on failure.
    """
    variant = frozenset({mutation}) if mutation else frozenset()

    def replacement(old_nodes, new_nodes):
        return legacy_similarity_pair(old_nodes, new_nodes, Recorder.selection_only(), "injected", variant)

    monkeypatch.setattr("deltatrack.diff_bill._similarity_pair", replacement)


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
            f"{key}: substituting the oracle for production's own _similarity_pair moved the stream, "
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
