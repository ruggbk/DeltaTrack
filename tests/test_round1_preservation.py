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

## What is frozen, and what it gates

``tests/data/round1_legacy_trace.json`` holds, per committed version pair, a SHA-256 over
the oracle's full ordered trace plus the structural counts behind it. It is generated from
the ORACLE, never from production, so production is always being compared against an
independent expectation.

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
import inspect
import json
import os
import textwrap
from collections import defaultdict
from pathlib import Path

import pytest

from deltatrack.bill_tree import BillNode, normalize_bill
from deltatrack.diff_bill import match_nodes
from deltatrack.similarity import text_similarity
from tests.conftest import assert_manifest_committed, manifest_version_pairs, manifest_xml_ids
from tests.corpus_paths import DATA_DIR

_FROZEN = DATA_DIR / "round1_legacy_trace.json"


# --- The oracle: the legacy composition, transcribed -----------------------------------
#
# Nothing below may call diff_bill. See the module docstring and the independence guard.


def legacy_normalize(text: str) -> str:
    """``diff_bill._normalize_text``, transcribed."""
    return " ".join(text.split())


class Recorder:
    """Collects the ordered trace as the oracle runs, and counts similarity calls.

    The count is its own assertion rather than a by-product: the 1x1 shortcut's whole effect
    is that no ratio is computed, and that is a performance property the pairing stream
    cannot show. Pinning it keeps a later "tidy it up by always computing the ratio" visible
    as what it is -- an optimisation regression, not a matching change.
    """

    def __init__(self, ordinals: dict[int, int] | None = None) -> None:
        self.invocations: list[dict] = []
        self.unique_selections: list[tuple[str, str]] = []
        self.similarity_calls = 0
        self.ordinals = ordinals or {}

    def ordinal(self, node: BillNode) -> int | None:
        return self.ordinals.get(id(node))

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
    record: dict = {
        "phase": phase,
        "old": [n.element_id for n in old_nodes],
        "new": [n.element_id for n in new_nodes],
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
                rec.unique_selections.append((group_old[0].element_id, group_new[0].element_id))
            pairs.append((group_old[0] if group_old else None, group_new[0] if group_new else None))
        else:
            pairs.extend(legacy_collision_group(group_old, group_new, rec, variant))

    return pairs


# --- Trace shape and digest -------------------------------------------------------------


def oracle_trace(old_nodes, new_nodes, variant: frozenset[str] = frozenset()) -> dict:
    """The oracle's full ordered trace for one comparison."""
    ordinals = {id(n): i for i, n in enumerate(old_nodes)}
    ordinals.update({id(n): i for i, n in enumerate(new_nodes)})
    rec = Recorder(ordinals)
    pairs = legacy_match_nodes(old_nodes, new_nodes, rec, variant)
    return {
        "stream": [[o.element_id if o else None, n.element_id if n else None] for o, n in pairs],
        "unique_selections": [list(p) for p in rec.unique_selections],
        "invocations": rec.invocations,
        "similarity_calls": rec.similarity_calls,
    }


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


def frozen_record(old_path: Path, new_path: Path) -> dict:
    old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
    trace = oracle_trace(old_tree.nodes, new_tree.nodes)
    return {
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
def test_production_reproduces_the_frozen_pairing_stream(old_path: Path, new_path: Path):
    """THE DURABLE GATE. Whatever round 1 becomes internally, this must still hold.

    Compares production's observable output -- the ordered pairing stream by element id --
    against the independently frozen expectation. It survives B1 and B2 because it names no
    internal function.
    """
    key = pair_key(old_path, new_path)
    frozen = load_frozen()[key]
    old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
    produced = [[o.element_id if o else None, n.element_id if n else None] for o, n in match_nodes(old_tree, new_tree)]

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


@pytest.mark.slow
def test_production_internals_reproduce_the_frozen_invocation_trace():
    """Today's corroboration at the stage boundary, by wrapping the LEGACY internals.

    ``_similarity_pair`` and ``_match_collision_group`` exist now and may not after B1, so
    this test is explicitly transitional: B1 and B2 replace it with assertions on their own
    stage outputs, compared against the same frozen invocation trace. What it buys today is
    that the oracle's invocation-level expectation is not merely self-consistent -- it is the
    shape production actually runs.
    """
    from deltatrack import diff_bill as db

    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)
        seen: list[dict] = []
        real_pair = db._similarity_pair
        real_group = db._match_collision_group
        state = {"both_sided": 0, "n": 0}

        def spy_pair(old_nodes, new_nodes, _real=real_pair, _seen=seen, _state=state):
            _state["n"] += 1
            phase = "within" if _state["n"] <= _state["both_sided"] else "cross"
            result = _real(old_nodes, new_nodes)
            _seen.append(
                {
                    "phase": phase,
                    "old": [n.element_id for n in old_nodes],
                    "new": [n.element_id for n in new_nodes],
                }
            )
            return result

        def spy_group(old_nodes, new_nodes, _real=real_group, _state=state):
            _state["n"] = 0
            _state["both_sided"] = len({n.division_key for n in old_nodes} & {n.division_key for n in new_nodes})
            return _real(old_nodes, new_nodes)

        db._similarity_pair = spy_pair
        db._match_collision_group = spy_group
        try:
            match_nodes(old_tree, new_tree)
        finally:
            db._similarity_pair = real_pair
            db._match_collision_group = real_group

        expected = [
            {"phase": i["phase"], "old": i["old"], "new": i["new"]}
            for i in oracle_trace(old_tree.nodes, new_tree.nodes)["invocations"]
        ]
        assert seen == expected, f"{pair_key(old_path, new_path)}: invocation populations differ from the oracle"
        checked += 1

    assert checked, "the invocation comparison ran over zero version pairs"


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
        # The transitional internals wrapper, which B1 removes along with the test that uses it.
        "deltatrack.diff_bill",
    }, f"the production import surface moved: {sorted(imported)}"


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


def production_stream(old_nodes: list[BillNode], new_nodes: list[BillNode]) -> list[tuple]:
    """Production's pairing stream for a synthetic node list, via a minimal tree stand-in."""

    class _Tree:
        def __init__(self, nodes):
            self.nodes = nodes

    return [
        (o.element_id if o else None, n.element_id if n else None)
        for o, n in match_nodes(_Tree(old_nodes), _Tree(new_nodes))
    ]


def test_assignment_leftovers_reach_the_cross_division_fallback():
    """The behaviour no corpus gate can observe, pinned exactly -- oracle and production.

    ``oA2`` is left over by within-division ASSIGNMENT in division A. ``nB2`` is left over in
    division B. They pair only because the fallback's population includes observations that
    assignment declined, which is the dependency the whole separation has to preserve.
    """
    old_nodes, new_nodes = assignment_leftover_fixture()
    trace = oracle_trace(old_nodes, new_nodes)

    assert [(i["phase"], i["old"], i["new"]) for i in trace["invocations"]] == [
        ("within", ["oA1", "oA2"], ["nA1"]),
        ("within", ["oB1"], ["nB1", "nB2"]),
        ("cross", ["oA2"], ["nB2"]),
    ]
    assert trace["stream"] == [["oA1", "nA1"], ["oB1", "nB1"], ["oA2", "nB2"]]
    assert production_stream(old_nodes, new_nodes) == [("oA1", "nA1"), ("oB1", "nB1"), ("oA2", "nB2")]


def test_the_fallback_population_is_not_in_parser_ordinal_order():
    """Local fallback positions and parser ordinals disagree -- constructible, never in the corpus.

    Pins the divergence itself, so a later implementation that reads ``ObservationRef``
    ordinals where production reads local positions is caught here rather than on a bill.
    """
    old_nodes, new_nodes = interleaved_division_fixture()
    trace = oracle_trace(old_nodes, new_nodes)

    cross = [i for i in trace["invocations"] if i["phase"] == "cross"]
    assert len(cross) == 1, "the fixture stopped exercising the cross-division fallback"
    assert cross[0]["old"] == ["X2", "Y1"], "the fallback population lost its concatenation order"

    ordinals = {n.element_id: i for i, n in enumerate(old_nodes)}
    positions = [ordinals[e] for e in cross[0]["old"]]
    assert positions == [2, 1], positions
    assert positions != sorted(positions), (
        "the fixture no longer produces a fallback population out of parser-ordinal order, so the "
        "ordinal-substitution control below cannot fire"
    )

    # The tie is the other half. Without it the two candidates are separated by similarity and
    # the tiebreak never runs, which is how the first version of this fixture failed to bind
    # the ordinal-substitution control at all.
    scores = {(oi, ni): s for s, oi, ni in (tuple(c) for c in cross[0]["candidates"])}
    assert len(set(scores.values())) == 1, f"the fallback candidates no longer tie: {scores}"

    # Descending LOCAL position picks Y1 (local 1). Descending parser ordinal would pick X2
    # (ordinal 2). Production agrees with the oracle, and the control below shows the
    # substitution moving it.
    assert cross[0]["selected"] == [[1, 0]]
    assert production_stream(old_nodes, new_nodes) == [("X1", "nX1"), ("Y1", "nZ1"), ("X2", None)]


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
        return legacy_similarity_pair(old_nodes, new_nodes, Recorder(), "injected", variant)

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
        produced = [
            [o.element_id if o else None, n.element_id if n else None] for o, n in match_nodes(old_tree, new_tree)
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
        produced = [
            [o.element_id if o else None, n.element_id if n else None] for o, n in match_nodes(old_tree, new_tree)
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
