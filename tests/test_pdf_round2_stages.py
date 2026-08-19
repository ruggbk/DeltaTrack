"""Slice 4: PDF round 2 as four stages, running before classification.

The extraction this module guards moved round 2 off the classified hunk stream.
Pre-slice-4, ``diff_pdfs`` built classified ``PdfHunk``s and then handed them to
``_reconcile_moves``, which filtered them on ``change_type`` to decide which pairs were even
considered for a move. That is the ADR 0020 violation: a change to what classification emitted
could silently change what matching considered.

**The legacy transcription is gone (#659).** This module used to carry a rebuild of the
pre-slice-4 ``diff_pdfs`` — its own opcode walk, split rule and emit order, finishing with
``_reconcile_moves`` — and compare production's whole hunk stream and round-2 population
against it. That comparison answered a closed question: whether slice 4 preserved behaviour.
It could not answer whether the correspondence is right, and it could not survive a deliberate
change to PDF matching policy without someone re-transcribing a new "before".

What remains is what still binds something durable, and none of it names a legacy symbol:

``test_round_2_addresses_the_complete_parser_sequence``
    every address entering round 2 is a complete-sequence ordinal, which is ADR 0019's hazard
    at the one place slice 4 mints new addresses.
``test_the_production_path_does_not_run_the_legacy_reconciler``
    round 2 no longer passes through the function that consumed classification output. This is
    slice 4's structural claim, and it is the reason ``_reconcile_moves`` is still in ``src``.
``test_the_corpus_actually_exercises_round_2``
    the floor that stops the above agreeing vacuously on a corpus with no moves.

Whole-output preservation is owned by ``tests/test_pdf_canonical_baseline.py``. The one thing
the transcription covered that the baseline does not is the six ``compare.pdf`` declines, which
no user reaches and no baseline record covers; that loss is deliberate and is recorded here
rather than left to be rediscovered.

The record's §7.4 note — that PDF's move records land where the removal was, rather than
appended as in XML — is why ``PdfSettledCorrespondence`` carries a slot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deltatrack import diff_pdf
from deltatrack.diff_pdf import (
    ROUND2_UNMATCHED_RECOVERY,
    _AlignedPairing,
    apply_pdf_similarity_revocation,
    assign_pdf_moves,
    classify_pdf,
    diff_pdfs,
    pdf_move_evidence,
    pdf_similarity_correspondence_evidence,
    pdf_unmatched_population,
    retrieve_pdf_move_candidates,
    retrieve_pdf_round1_candidates,
    settle_pdf_correspondences,
)
from deltatrack.matching import NEW, OLD, ObservationRef
from deltatrack.parsers.pdf_anchors import extract_anchors
from deltatrack.parsers.pdf_blocks import _Block, _flatten, _group_into_blocks, _IndexedLine
from deltatrack.pdf_observations import PdfObservationRegistry
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD
from tests.pdf_corpus import adjacent_pdf_pairs, cached_pages

_PAIRS = adjacent_pdf_pairs()
_PAIR_IDS = [f"{bill}:{old.stem}->{new.stem}" for bill, old, new in _PAIRS]


# --- The oracle: the pre-slice-4 pipeline, transcribed -------------------------------------


def blocks_for(pdf: Path) -> list[_Block]:
    pages = cached_pages(pdf)
    return _group_into_blocks(_flatten(pages), extract_anchors(pages))


def round1_stream(old_blocks: list[_Block], new_blocks: list[_Block], registry: PdfObservationRegistry):
    """Production's post-revocation round-1 pairing stream, and the evidence behind it.

    The production side of every comparison below. Slice 5 split what used to be one call into
    align -> evidence -> revoke, so this runs the three in order rather than each test
    re-spelling them. It is **not** an oracle and must never become one: the thing being
    compared against is ``legacy_hunks_before_round2``, which is transcribed independently and
    calls none of this.
    """
    provisional, candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)
    evidence = pdf_similarity_correspondence_evidence(provisional, registry, candidates)
    pairings = apply_pdf_similarity_revocation(provisional, evidence, registry, threshold=SIMILARITY_THRESHOLD)
    return pairings, evidence


def test_the_corpus_pair_list_is_not_empty() -> None:
    """A parametrization list that silently empties is the fail-open shape (#542)."""
    assert len(_PAIRS) >= 20, f"only {len(_PAIRS)} adjacent PDF pairs discovered; the corpus holds more"


# --- Behaviour preservation over the corpus -----------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_round_2_addresses_the_complete_parser_sequence(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Every address entering round 2 is a complete-sequence ordinal, not a population index.

    ADR 0019's hazard, at the one place slice 4 creates new addresses. A population position is
    a different number that looks just as valid, and on a real bill the two diverge immediately
    because the first observation is rarely unmatched.
    """
    old_blocks, new_blocks = blocks_for(old_pdf), blocks_for(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(round1_stream(old_blocks, new_blocks, registry)[0], registry)

    for side, observations, blocks in ((OLD, population.old, old_blocks), (NEW, population.new, new_blocks)):
        for observation in observations:
            assert observation.ref.side == side
            assert registry.block(observation.ref) is observation.block
            assert blocks[observation.ref.ordinal] is observation.block


@pytest.mark.slow
def test_the_corpus_actually_exercises_round_2() -> None:
    """Floor. The sweeps above would agree vacuously on a corpus with no moves at all.

    Measured: 166 moved hunks, 8,182 unmatched observations, and 354 as the sum over pairs of
    ``min(len(old), len(new))`` — the count of moves round 2 could possibly make. Asserted as
    floors well under those, so a corpus addition does not force a fixture edit, and stated as
    two separate numbers because they fail apart: a change that emptied the population would
    leave the sweeps agreeing on nothing while ``moved`` stayed whatever it was.
    """
    moved = 0
    possible = 0
    for _bill, old_pdf, new_pdf in _PAIRS:
        hunks = diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf)).hunks
        moved += sum(1 for h in hunks if h.change_type == "moved")
        old_blocks, new_blocks = blocks_for(old_pdf), blocks_for(new_pdf)
        registry = PdfObservationRegistry(old_blocks, new_blocks)
        population = pdf_unmatched_population(round1_stream(old_blocks, new_blocks, registry)[0], registry)
        possible += min(len(population.old), len(population.new))
    assert moved >= 120, f"only {moved} moved hunks corpus-wide; the preservation sweeps assert little"
    assert possible >= 250, f"round 2 could make only {possible} moves corpus-wide; retrieval is barely exercised"


# --- Round 2 no longer reads classification ------------------------------------------------


@pytest.mark.slow
def test_the_production_path_does_not_run_the_legacy_reconciler(monkeypatch: pytest.MonkeyPatch) -> None:
    """The structural claim of slice 4, made executable.

    ``_reconcile_moves`` is the function that consumed classification output. Replacing it with
    a raise and running a real comparison end to end is what shows round 2 no longer passes
    through it — a claim that a docstring alone cannot keep true.
    """

    def _refuse(*_args, **_kwargs):
        raise AssertionError("diff_pdfs reached the legacy classified-hunk reconciler")

    monkeypatch.setattr(diff_pdf, "_reconcile_moves", _refuse)
    _bill, old_pdf, new_pdf = _PAIRS[0]
    assert diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf)).hunks


# --- The (ri, ai) equivalence the projection rests on --------------------------------------


def test_filtered_positions_order_candidates_exactly_as_absolute_indices_did() -> None:
    """``_reconcile_moves`` sorted on absolute hunk indices; the stages sort on positions.

    They order identically because the map from filtered position to absolute index is strictly
    increasing, so every pairwise comparison resolves the same way. Stated as an executable
    check rather than as reasoning in a docstring, and built to be able to fail: a
    non-monotonic map is included and must produce a different order.
    """
    absolute_removed = [3, 7, 11]  # ascending, as `enumerate` produces
    absolute_added = [4, 9, 12]
    candidates = [(0.9, 0, 1), (0.9, 2, 0), (0.7, 1, 2), (0.9, 0, 0)]

    by_position = sorted(candidates, reverse=True)
    by_absolute = sorted(
        ((s, absolute_removed[r], absolute_added[a]) for s, r, a in candidates),
        reverse=True,
    )
    assert [(r, a) for _s, r, a in by_position] == [
        (absolute_removed.index(r), absolute_added.index(a)) for _s, r, a in by_absolute
    ]

    scrambled = [11, 3, 7]
    by_scrambled = sorted(((s, scrambled[r], absolute_added[a]) for s, r, a in candidates), reverse=True)
    assert [(scrambled.index(r), absolute_added.index(a)) for _s, r, a in by_scrambled] != [
        (r, a) for _s, r, a in by_position
    ], "a non-monotonic map must reorder, or this control cannot distinguish the two rules"


# --- Retrieval and assignment read their own numbers ---------------------------------------


def _line(text: str, page: int, number: int) -> _IndexedLine:
    return _IndexedLine(text=text, page_number=page, line_number=number)


def _block(text: str, page: int, number: int = 1) -> _Block:
    return _Block(anchor=None, indexed_lines=(_line(text, page, number),))


_CORE = "None of the funds made available by this Act may be used to finalize implement or enforce the proposed rule"


def _pairings(old_blocks: list[_Block], new_blocks: list[_Block]) -> list[_AlignedPairing]:
    """One unmatched pairing per block — the shape a fully-split alignment produces."""
    return [_AlignedPairing(b, None) for b in old_blocks] + [_AlignedPairing(None, b) for b in new_blocks]


def _two_block_sides() -> tuple[list[_Block], list[_Block]]:
    old = [_block(f"{_CORE} concerning migratory bird habitat conservation published March 1 2024", 1)]
    new = [_block(f"{_CORE} concerning migratory bird habitat conservation published March 8 2024", 2)]
    return old, new


def test_assignment_can_refuse_what_retrieval_admitted() -> None:
    """The two numbers are separate inputs, shown by moving them apart.

    Production passes one constant to both, so a single shared cutoff would produce identical
    results forever and the separation would be untestable. Retrieving at a permissive bound
    and assigning at a strict one must select nothing.
    """
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_pairings(old_blocks, new_blocks), registry)

    candidates = retrieve_pdf_move_candidates(population, bound=0.1)
    evidence = pdf_move_evidence(candidates)
    assert evidence, "retrieval at a permissive bound must admit the pair, or this proves nothing"

    assert assign_pdf_moves(population, evidence, threshold=0.999) == ()
    assert len(assign_pdf_moves(population, evidence, threshold=0.1)) == 1


def test_retrieval_can_withhold_what_assignment_would_have_taken() -> None:
    """The other direction: a strict bound starves assignment even at a permissive threshold."""
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_pairings(old_blocks, new_blocks), registry)

    evidence = pdf_move_evidence(retrieve_pdf_move_candidates(population, bound=0.999))
    assert evidence == (), "a near-1.0 bound should admit nothing on this fixture"
    assert assign_pdf_moves(population, evidence, threshold=0.1) == ()


def test_a_settled_move_carries_the_evidence_that_selected_it() -> None:
    """ADR 0020: every selected link carries exactly one evidence record."""
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    pairings = _pairings(old_blocks, new_blocks)
    population = pdf_unmatched_population(pairings, registry)
    evidence = pdf_move_evidence(retrieve_pdf_move_candidates(population, bound=MOVE_THRESHOLD))
    moves = assign_pdf_moves(population, evidence, threshold=MOVE_THRESHOLD)

    assert len(moves) == 1
    move = moves[0].correspondence
    assert move.old == (ObservationRef(OLD, 0),) and move.new == (ObservationRef(NEW, 0),)
    assert len(move.evidence) == 1
    assert isinstance(move.evidence[0].get("word_overlap"), float)
    assert moves[0].move_basis == ROUND2_UNMATCHED_RECOVERY, "round-2 assignment records its own basis"

    settled = settle_pdf_correspondences(pairings, registry, moves, round1_evidence=(), round1_move_bases={})
    assert [item.round for item in settled] == [2]
    assert [item.move_basis for item in settled] == [ROUND2_UNMATCHED_RECOVERY]
    assert [h.change_type for h in classify_pdf(settled, registry)] == ["moved"]
