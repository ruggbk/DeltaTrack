"""ADR 0020's invariants, made executable against the contract types.

Every case below names the invariant it enforces and the bad implementation that makes
it fail. That second half is the filter: ADR 0020 asks for enforcement tests shown
capable of failing, and warns that invariant 1 in particular can fail in two opposite
directions — deduplicating too eagerly drops a proposal's metadata, not deduplicating
lets one pair reach assignment twice — so a test asserting only "one candidate reached
assignment" passes in the first case. Both directions are covered here.

What is deliberately *not* here: any assertion about a retriever, a measure, a threshold
or a stage boundary. None exists yet. A test that mocked one would be pinning a design
this slice has not committed to.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from deltatrack import matching
from deltatrack.matching import (
    NEW,
    OLD,
    Candidate,
    CandidateSet,
    Correspondence,
    CorrespondenceSet,
    Evidence,
    ObservationRef,
    Proposal,
    RetrieverInvocation,
)


def old(ordinal: int) -> ObservationRef:
    return ObservationRef(OLD, ordinal)


def new(ordinal: int) -> ObservationRef:
    return ObservationRef(NEW, ordinal)


PATH_GROUP = RetrieverInvocation.of("path_group")
MOVE_SCAN = RetrieverInvocation.of("move_scan", round=1, threshold=0.6)


# --- Invariant 1: one observation pair, one candidate --------------------------


def test_one_pair_yields_one_candidate():
    """ADR 0020 invariant 1. Fails if the set keys on anything but the pair — on the
    proposal, say, so the same pair found twice reaches assignment twice."""
    candidates = CandidateSet()
    candidates.propose(old(3), new(7), PATH_GROUP)
    candidates.propose(old(3), new(7), PATH_GROUP)
    assert len(candidates) == 1
    assert len(candidates.candidates()) == 1


def test_two_retrievers_on_one_pair_keep_both_proposals():
    """ADR 0020 invariant 1, the other direction. Fails if deduplication keys on the pair
    alone and drops the second invocation's provenance — the eager-dedup failure the
    record names, which a bare "one candidate" assertion cannot see."""
    candidates = CandidateSet()
    candidates.propose(old(3), new(7), PATH_GROUP, rank=0, score=0.91)
    candidates.propose(old(3), new(7), MOVE_SCAN, rank=4, score=0.62)

    (candidate,) = candidates.candidates()
    assert candidate.invocations == (PATH_GROUP, MOVE_SCAN)
    assert {p.score for p in candidate.proposals} == {0.91, 0.62}


def test_a_candidate_is_identified_by_its_pair_alone():
    """ADR 0020: "its identity is that pair and nothing else". Fails if ``proposals``
    joins the comparison, which would make two records of one pair unequal and let a
    downstream set hold both."""
    a = Candidate(old(3), new(7), (Proposal(PATH_GROUP),))
    b = Candidate(old(3), new(7), (Proposal(MOVE_SCAN, rank=4, score=0.62),))
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


# --- Invariant 2: provenance is not optional -----------------------------------


def test_a_candidate_cannot_exist_without_retrieval_provenance():
    """ADR 0020 invariant 2. Fails if ``proposals`` may be empty, which would admit a
    pair whose recall cannot be attributed to any retriever or configuration."""
    with pytest.raises(ValueError, match="no retrieval provenance"):
        Candidate(old(3), new(7))


def test_a_proposal_carries_the_configuration_that_produced_it():
    """ADR 0020 invariant 2: a recall number without its configuration cannot be compared
    against another run. Fails if the invocation collapses to a bare retriever name."""
    bounded = RetrieverInvocation.of("move_scan", round=1, threshold=0.6, top_k=50)
    assert bounded.config == (("threshold", 0.6), ("top_k", 50))
    assert bounded.round == 1
    assert bounded != RetrieverInvocation.of("move_scan", round=1, threshold=0.4, top_k=50)


# --- Rank and score belong to a proposal ---------------------------------------


def test_rank_and_score_may_be_absent():
    """ADR 0020: "a retriever need not produce a number". Fails if either is required,
    which pushes a structural retriever into inventing a score that looks comparable."""
    candidates = CandidateSet()
    candidates.propose(old(3), new(7), PATH_GROUP)
    (candidate,) = candidates.candidates()
    (proposal,) = candidate.proposals
    assert proposal.rank is None
    assert proposal.score is None


def test_rank_and_score_live_on_the_proposal_not_the_candidate():
    """ADR 0020: a candidate proposed by two retrievers has no answer to "what is its
    rank", and the scores are on unrelated scales. Fails the moment either is promoted to
    a candidate field, because that forces one retriever to be picked silently."""
    candidate_fields = {f.name for f in fields(Candidate)}
    assert "rank" not in candidate_fields and "score" not in candidate_fields

    candidates = CandidateSet()
    candidates.propose(old(3), new(7), PATH_GROUP, rank=0, score=0.91)
    candidates.propose(old(3), new(7), MOVE_SCAN, rank=4, score=0.62)
    (candidate,) = candidates.candidates()
    by_retriever = {p.invocation.retriever: (p.rank, p.score) for p in candidate.proposals}
    assert by_retriever == {"path_group": (0, 0.91), "move_scan": (4, 0.62)}


# --- Invariant 3: duplicate proposals are not weight ---------------------------


def test_duplicate_proposals_add_no_multiplicity_and_no_weight():
    """ADR 0020 invariant 3. Fails if repeated proposals accumulate, which is how
    retriever agreement becomes weight "acquired accidentally from how the candidate set
    was built" — an inference the record says must be a named evidence signal if it is
    used at all."""
    candidates = CandidateSet()
    for _ in range(5):
        candidates.propose(old(3), new(7), PATH_GROUP, rank=0, score=0.91)
    (candidate,) = candidates.candidates()
    assert len(candidate.proposals) == 1


def test_one_invocation_may_not_propose_one_pair_two_different_ways():
    """ADR 0020 invariant 2, at its edge. Fails if the set silently keeps the first (or
    the last) record, which makes the stored rank a function of iteration order and so
    unattributable — the number the candidate boundary exists to make reproducible."""
    candidates = CandidateSet()
    candidates.propose(old(3), new(7), PATH_GROUP, rank=0, score=0.91)
    with pytest.raises(ValueError, match="different metadata"):
        candidates.propose(old(3), new(7), PATH_GROUP, rank=7, score=0.30)


# --- Invariant 5: evidence decides nothing -------------------------------------


def test_evidence_carries_signals_and_no_verdict():
    """ADR 0020 invariant 5. The field set is pinned because a *field* is the shape a
    verdict arrives in: ``is_match``, ``corresponds``, ``confidence``, ``above_threshold``.
    Signals grow inside ``signals``, so legitimate growth never trips this — adding a
    field does, which is the point."""
    assert {f.name for f in fields(Evidence)} == {"old", "new", "signals"}

    evidence = Evidence.of(old(3), new(7), header_equal=True, word_overlap=0.42)
    assert evidence.names == ("header_equal", "word_overlap")
    assert evidence.get("header_equal") is True
    assert evidence.get("path_equal") is None


def test_evidence_is_immutable():
    """ADR 0020 invariant 8: evidence stays retained and inspectable. Fails if a later
    stage can rewrite what it was handed, which would make a retained record describe
    something other than what assignment saw."""
    evidence = Evidence.of(old(3), new(7), header_equal=True)
    with pytest.raises(FrozenInstanceError):
        evidence.signals = ()


# --- Invariant 9: correspondence cardinality -----------------------------------


@pytest.mark.parametrize(
    ("shape", "old_refs", "new_refs"),
    [
        ("1:1", (old(3),), (new(7),)),
        ("1:0", (old(3),), ()),
        ("0:1", (), (new(7),)),
        ("1:N", (old(3),), (new(7), new(8), new(9))),
        ("N:1", (old(3), old(4)), (new(7),)),
        ("N:M", (old(3), old(4)), (new(7), new(8))),
    ],
)
def test_correspondence_represents_every_shape_without_loss(shape, old_refs, new_refs):
    """ADR 0020 invariant 9. Fails on a pair-shaped result type — today's
    ``list[tuple[BillNode | None, BillNode | None]]`` — which degrades a consolidation to
    unrelated removals and additions before any consumer can see it."""
    correspondence = Correspondence(old=old_refs, new=new_refs)
    assert correspondence.shape == shape
    assert correspondence.cardinality == (len(old_refs), len(new_refs))
    assert correspondence.old == old_refs
    assert correspondence.new == new_refs
    assert correspondence.is_binary == (len(old_refs) <= 1 and len(new_refs) <= 1)


def test_a_correspondence_relates_at_least_one_observation():
    """Fails if an empty correspondence is constructible, which would claim nothing while
    occupying a slot in the settled set."""
    with pytest.raises(ValueError, match="at least one observation"):
        Correspondence()


def test_evidence_must_name_a_pair_the_correspondence_relates():
    """ADR 0020: each link carries the evidence that selected it. Fails if unrelated
    evidence can be attached, which makes the retained record unreadable — the reader
    cannot tell which link a signal describes."""
    with pytest.raises(ValueError, match="outside this correspondence"):
        Correspondence(old=(old(3),), new=(new(7),), evidence=(Evidence.of(old(3), new(99)),))


def test_a_side_may_not_repeat_an_observation():
    """Fails if a 1:N can list the same target twice, which is the shape that would let a
    later canonical projection count one side's amounts twice — the double-count ADR 0001
    forbids and ADR 0020 invariant 10 restates."""
    with pytest.raises(ValueError, match="repeats an observation"):
        Correspondence(old=(old(3),), new=(new(7), new(7)))


def test_an_observation_corresponds_at_most_once():
    """The per-anchor competition policy, measured on the corpus below before being
    encoded. Fails if two correspondences may claim one observation, which would let a
    node appear in two changes and its money be reported twice."""
    settled = CorrespondenceSet([Correspondence(old=(old(3),), new=(new(7),))])
    with pytest.raises(ValueError, match="already claimed"):
        settled.add(Correspondence(old=(old(3),), new=(new(8),)))


# --- Invariant 11: each stage deterministic in isolation -----------------------


def test_configuration_order_does_not_change_an_invocation():
    """ADR 0008 / ADR 0020 invariant 11. Fails if the config keeps insertion order, which
    would make two spellings of one configuration unequal — and a deduplication keyed on
    the invocation would then silently keep two copies of it."""
    a = RetrieverInvocation.of("move_scan", threshold=0.6, top_k=50)
    b = RetrieverInvocation.of("move_scan", top_k=50, threshold=0.6)
    assert a == b
    assert hash(a) == hash(b)


def test_signal_order_does_not_change_evidence():
    """Same rule for evidence: two stages computing the same signals in different orders
    must produce one value, or a retained record cannot be compared between runs."""
    assert Evidence.of(old(3), new(7), b=2, a=1) == Evidence.of(old(3), new(7), a=1, b=2)


def test_candidate_order_does_not_depend_on_which_retriever_ran_first():
    """ADR 0020 invariant 11, applied to retrieval as a union. Fails if the set yields
    insertion order, which makes the candidate set a function of retriever scheduling —
    so adding a retriever reorders the pairs the next stage sees."""
    forward = CandidateSet()
    forward.propose(old(1), new(2), PATH_GROUP)
    forward.propose(old(0), new(5), MOVE_SCAN)
    reverse = CandidateSet()
    reverse.propose(old(0), new(5), MOVE_SCAN)
    reverse.propose(old(1), new(2), PATH_GROUP)

    assert [c.pair for c in forward.candidates()] == [(0, 5), (1, 2)]
    assert forward.candidates() == reverse.candidates()


def test_a_reference_names_a_side_and_a_position_in_the_complete_sequence():
    """ADR 0019's address, and its stated hazard: an ordinal indexes the complete emitted
    sequence, so a negative or side-confused reference is refused rather than pointing at
    the wrong node convincingly."""
    with pytest.raises(ValueError, match="side must be one of"):
        ObservationRef("older", 3)
    with pytest.raises(ValueError, match="ordinal must be non-negative"):
        ObservationRef(OLD, -1)
    with pytest.raises(ValueError, match="one old-side and one new-side"):
        Candidate(new(7), new(8), (Proposal(PATH_GROUP),))


# --- The PDF boundary, enforced on the import graph ----------------------------


def test_the_contracts_import_nothing_from_the_engine():
    """ADR 0020: the contracts must not care whether a PDF observation comes from glyph
    reconstruction, PDFium's character stream, or a hybrid.

    An import of the engine is the first step of that dependency — a type that can name a
    ``BillNode``, a text run or a PDF block will eventually be shaped by one. So the
    refusal lives on the import graph, where it is checkable, rather than on a convention
    that reads as satisfied right up until it is not. Proven capable of failing: adding
    ``from deltatrack.bill_tree import BillNode`` to the module reddens this.

    Scanned by AST rather than by regex, so a mention inside a docstring (there are
    several) is not read as a dependency.
    """
    source = Path(matching.__file__).read_text()
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    engine_imports = [name for name in imported if name == "deltatrack" or name.startswith("deltatrack.")]
    assert not engine_imports, (
        f"deltatrack.matching imports the engine: {engine_imports}. The matching contracts must stay "
        "agnostic about how an observation is produced — see ADR 0020 and the module docstring."
    )


# --- The measurement the exclusivity rule rests on -----------------------------


@pytest.mark.slow
class TestAssignmentExclusivityOnTheCorpus:
    """``CorrespondenceSet`` encodes "an observation corresponds at most once". That is a
    claim about the current XML assigner, so it is measured against it rather than
    assumed — and measured through the type itself, so the two cannot drift apart.

    Keyed by ``id(node)``, not by the node: ``BillNode`` is a frozen dataclass, so two
    distinct nodes carrying the same text compare equal. That is the duplicate-body
    population ADR 0019 measured (385 texts across 23 documents), and a dict keyed by the
    node would silently merge them — the optimistic failure 0019 is about, reproduced
    inside the check meant to detect it.
    """

    def test_manifest_fixtures_committed(self):
        from tests.conftest import assert_manifest_committed, manifest_version_pairs

        assert_manifest_committed(manifest_version_pairs(), "matching-exclusivity")

    def test_the_corpus_assigner_claims_each_observation_once(self):
        from deltatrack.bill_tree import normalize_bill
        from deltatrack.diff_bill import match_nodes
        from tests.conftest import manifest_version_pairs

        checked = 0
        for old_path, new_path in manifest_version_pairs():
            old_tree = normalize_bill(old_path)
            new_tree = normalize_bill(new_path)
            old_at = {id(node): i for i, node in enumerate(old_tree.nodes)}
            new_at = {id(node): i for i, node in enumerate(new_tree.nodes)}

            settled = CorrespondenceSet()
            for old_node, new_node in match_nodes(old_tree, new_tree):
                settled.add(
                    Correspondence(
                        old=() if old_node is None else (ObservationRef(OLD, old_at[id(old_node)]),),
                        new=() if new_node is None else (ObservationRef(NEW, new_at[id(new_node)]),),
                    )
                )

            label = f"{old_path.parent.name} {old_path.stem}->{new_path.stem}"
            unclaimed_old = [i for i in range(len(old_tree.nodes)) if settled.claiming(ObservationRef(OLD, i)) is None]
            unclaimed_new = [i for i in range(len(new_tree.nodes)) if settled.claiming(ObservationRef(NEW, i)) is None]
            assert not unclaimed_old, f"{label}: old observations reached no correspondence: {unclaimed_old[:8]}"
            assert not unclaimed_new, f"{label}: new observations reached no correspondence: {unclaimed_new[:8]}"
            checked += 1

        assert checked > 0, "the exclusivity measurement ran over zero version pairs"
