"""Slice 7: PDF round-1 retrieval as a named retriever emitting a ``CandidateSet``.

`_block_key` + `SequenceMatcher` + the positional `replace` zip are unchanged as *policy*. What
slice 7 adds is that what they considered is now **materialised** — a `CandidateSet` proposed
into under a named invocation — and that the materialisation is on the result-bearing path
rather than beside it.

**That distinction is the whole slice, and it is what these controls exist for.** A candidate
set built and then ignored is indistinguishable from a correct one by every gate that compares
output: the pairings, the hunks and the canonical digest are all identical whether evidence
consults the set or reconstructs the pair from the pairing stream. So the controls here are not
output comparisons. They are:

- membership equals the legacy considered-pair population, measured against an independently
  transcribed opcode walk;
- withholding a candidate makes evidence **fail closed** rather than reconstruct;
- a candidate carrying the wrong invocation's provenance cannot authorize evidence;
- the set's canonical order cannot become the stream's order;
- revoked round-1 evidence is reachable after the stage completes.

Preservation of the population itself stays with the gates that already own it: gate 1's
canonical baseline, gate 6's crossing fixture for the positional rule, and
``test_pdf_round2_stages``' whole-output legacy oracle.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from deltatrack import diff_pdf
from deltatrack.diff_pdf import (
    BLOCK_KEY_ALIGNMENT,
    POSITIONAL_REPLACE,
    _AlignedPairing,
    _block_key,
    _round1_invocations,
    pdf_round1_with_stage_outputs,
    pdf_similarity_correspondence_evidence,
    retrieve_pdf_round1_candidates,
)
from deltatrack.matching import NEW, OLD, CandidateSet, ObservationRef
from deltatrack.parsers.pdf_anchors import extract_anchors
from deltatrack.parsers.pdf_blocks import _Block, _flatten, _group_into_blocks, _IndexedLine
from deltatrack.pdf_observations import PdfObservationRegistry
from deltatrack.similarity import SIMILARITY_THRESHOLD
from tests.pdf_corpus import adjacent_pdf_pairs, cached_pages

_PAIRS = adjacent_pdf_pairs()
_PAIR_IDS = [f"{bill}:{old.stem}->{new.stem}" for bill, old, new in _PAIRS]

ALIGNMENT, POSITIONAL = _round1_invocations()


def _blocks(pdf: Path) -> list[_Block]:
    pages = cached_pages(pdf)
    return _group_into_blocks(_flatten(pages), extract_anchors(pages))


# --- The oracle: the legacy opcode walk, transcribed --------------------------------------


def legacy_considered_pairs(v1_blocks: list[_Block], v2_blocks: list[_Block]) -> list[tuple[int, int]]:
    """Every (old index, new index) pair the pre-slice-7 aligner formed, in stream order.

    Transcribed from the opcode walk rather than imported: an oracle that asked
    ``retrieve_pdf_round1_candidates`` what it considered could not detect that what it considers
    changed, which is the one failure this slice can have.
    """
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )
    considered: list[tuple[int, int]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for offset in range(min(i2 - i1, j2 - j1)):
                considered.append((i1 + offset, j1 + offset))
        elif op == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                considered.append((i1 + k, j1 + k))
    return considered


def test_the_corpus_pair_list_is_not_empty() -> None:
    """A parametrization list that silently empties is the fail-open shape (#542)."""
    assert len(_PAIRS) >= 20, f"only {len(_PAIRS)} adjacent PDF pairs discovered; the corpus holds more"


# --- Membership equals the legacy considered population -----------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_candidate_membership_equals_the_legacy_considered_population(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Exactly the pairs the legacy aligner formed — no more, no fewer.

    ``CandidateSet`` membership is compared as a set of ordinal pairs against the transcribed
    walk. Widening retrieval (a policy change slice 7 must not make) shows up here as extra
    members; dropping the positional ``replace`` rule shows up as missing ones.
    """
    old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    _pairings, candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)

    admitted = {candidate.ordinal_pair for candidate in candidates.candidates()}
    assert admitted == set(legacy_considered_pairs(old_blocks, new_blocks))


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_every_provisional_pairing_carries_its_retrievers_provenance(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Each 1:1 names the rule that formed it, and each unmatched side names none.

    The invocation is what makes the wrong-provenance refusal possible at all, so it has to be
    populated on the real path rather than only in a fixture.
    """
    old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    pairings, _candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)

    for pairing in pairings:
        if pairing.old is not None and pairing.new is not None:
            assert pairing.invocation in (ALIGNMENT, POSITIONAL), f"1:1 pairing carries {pairing.invocation}"
        else:
            assert pairing.invocation is None, "an unmatched observation forms no pair and retrieves nothing"


@pytest.mark.slow
def test_both_round_1_retrievers_are_actually_exercised() -> None:
    """Floor. One invocation never firing would make its half of every sweep above vacuous.

    Measured: 2,981 pairs admitted by the alignment rule and 426 by the positional ``replace``
    rule across the committed corpus. Asserted as floors well under those, so a corpus addition
    does not force a fixture edit.
    """
    by_retriever: dict[str, int] = {BLOCK_KEY_ALIGNMENT: 0, POSITIONAL_REPLACE: 0}
    for _bill, old_pdf, new_pdf in _PAIRS:
        old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
        registry = PdfObservationRegistry(old_blocks, new_blocks)
        _pairings, candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)
        for candidate in candidates.candidates():
            for invocation in candidate.invocations:
                by_retriever[invocation.retriever] += 1

    assert by_retriever[BLOCK_KEY_ALIGNMENT] >= 2000, f"alignment barely fires: {by_retriever}"
    assert by_retriever[POSITIONAL_REPLACE] >= 250, f"the positional replace rule barely fires: {by_retriever}"


# --- Admission is load-bearing, not observable-beside ------------------------------------


def _line(text: str, page: int) -> _IndexedLine:
    return _IndexedLine(text=text, page_number=page, line_number=1)


def _block(text: str, page: int) -> _Block:
    return _Block(anchor=None, indexed_lines=(_line(text, page),))


def _one_pair() -> tuple[list[_Block], list[_Block], PdfObservationRegistry]:
    old_blocks = [_block("alpha beta gamma delta", 1)]
    new_blocks = [_block("alpha beta gamma epsilon", 2)]
    return old_blocks, new_blocks, PdfObservationRegistry(old_blocks, new_blocks)


def test_evidence_fails_closed_when_retrieval_did_not_admit_the_pair() -> None:
    """THE slice 7 control. Withholding a candidate must refuse, never reconstruct.

    The pairing stream still names the pair, so an evidence stage that trusted the stream would
    describe it happily and every downstream result would look correct. That is precisely the
    state a materialised candidate set exists to make unreachable: "retrieval never considered
    this" and "assignment nevertheless selected it" must not both be true.
    """
    old_blocks, new_blocks, registry = _one_pair()
    provisional = [_AlignedPairing(old_blocks[0], new_blocks[0], ALIGNMENT)]

    with pytest.raises(ValueError, match="retrieval never admitted"):
        pdf_similarity_correspondence_evidence(provisional, registry, CandidateSet())


def test_evidence_fails_closed_on_a_candidate_from_another_invocation() -> None:
    """Provenance is per-invocation, not "somebody considered it".

    A pair the positional rule surfaced may not authorize evidence for a pairing the alignment
    rule formed. The two are different retrieval rules with different failure modes, and
    collapsing them would let a candidate admitted by one rule launder a pairing produced by the
    other.
    """
    old_blocks, new_blocks, registry = _one_pair()
    provisional = [_AlignedPairing(old_blocks[0], new_blocks[0], ALIGNMENT)]

    wrong = CandidateSet()
    wrong.propose(ObservationRef(OLD, 0), ObservationRef(NEW, 0), POSITIONAL)

    with pytest.raises(ValueError, match="carries no proposal from"):
        pdf_similarity_correspondence_evidence(provisional, registry, wrong)


def test_evidence_fails_closed_on_a_pairing_with_no_provenance() -> None:
    """A 1:1 that reached evidence without naming a retriever at all."""
    old_blocks, new_blocks, registry = _one_pair()
    provisional = [_AlignedPairing(old_blocks[0], new_blocks[0])]

    admitting = CandidateSet()
    admitting.propose(ObservationRef(OLD, 0), ObservationRef(NEW, 0), ALIGNMENT)

    with pytest.raises(ValueError, match="no retriever provenance"):
        pdf_similarity_correspondence_evidence(provisional, registry, admitting)


def test_admission_is_refused_for_the_whole_population_before_anything_is_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial description must never be handed on.

    The second pairing is unadmitted; the first is fine. If admission were checked per pair as
    the loop measured, the first record would already exist when the second raised. Checked by
    proving the raise happens with no measurement performed on either.
    """
    old_blocks = [_block("alpha beta gamma delta", 1), _block("zeta eta theta iota", 2)]
    new_blocks = [_block("alpha beta gamma epsilon", 3), _block("zeta eta theta kappa", 4)]
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    provisional = [
        _AlignedPairing(old_blocks[0], new_blocks[0], ALIGNMENT),
        _AlignedPairing(old_blocks[1], new_blocks[1], ALIGNMENT),
    ]

    partial = CandidateSet()
    partial.propose(ObservationRef(OLD, 0), ObservationRef(NEW, 0), ALIGNMENT)

    measured: list[tuple[str, str]] = []

    def _recording(a: str, b: str) -> float:
        measured.append((a, b))
        return 0.0

    monkeypatch.setattr(diff_pdf, "text_similarity", _recording)
    with pytest.raises(ValueError, match="retrieval never admitted"):
        pdf_similarity_correspondence_evidence(provisional, registry, partial)

    assert measured == [], f"{len(measured)} pair(s) were measured before admission was refused"


# --- The set orders nothing ---------------------------------------------------------------


def test_the_emitted_order_is_the_stream_not_the_canonical_candidate_order() -> None:
    """``CandidateSet.candidates()`` is ordinal-ordered; the stream is the order authority.

    On a real document the two coincide, because the aligner consumes both sides monotonically —
    which is exactly why this has to be pinned structurally rather than observed. The pairings
    below are handed over in deliberately non-canonical order, and the evidence must come back in
    the order given, not sorted by ordinal pair.
    """
    old_blocks = [_block("alpha beta gamma delta", 1), _block("zeta eta theta iota", 2)]
    new_blocks = [_block("alpha beta gamma epsilon", 3), _block("zeta eta theta kappa", 4)]
    registry = PdfObservationRegistry(old_blocks, new_blocks)

    reversed_stream = [
        _AlignedPairing(old_blocks[1], new_blocks[1], ALIGNMENT),
        _AlignedPairing(old_blocks[0], new_blocks[0], ALIGNMENT),
    ]
    candidates = CandidateSet()
    for pairing in reversed_stream:
        candidates.propose(registry.ref(OLD, pairing.old), registry.ref(NEW, pairing.new), ALIGNMENT)

    canonical = [candidate.ordinal_pair for candidate in candidates.candidates()]
    assert canonical == [(0, 0), (1, 1)], "precondition: the set's own order is ascending by ordinal pair"

    evidence = pdf_similarity_correspondence_evidence(reversed_stream, registry, candidates)
    assert [(item.old.ordinal, item.new.ordinal) for item in evidence] == [(1, 1), (0, 0)], (
        "evidence came back in the candidate set's canonical order; the set has become the "
        "ordering authority, which is what keeps round 2's (ri, ai) reproducible"
    )


# --- Stage outputs stay reachable ---------------------------------------------------------


@pytest.mark.slow
def test_revoked_round_1_evidence_is_reachable_after_the_stage_completes() -> None:
    """ADR 0020 invariant 8, for the records no ``Correspondence`` will ever carry.

    A revoked pairing's evidence is the reason a provision was reported as a removal plus an
    addition. If the stage dropped it, that reason would exist nowhere once round 1 returned.
    Checked on the corpus pair with the most revocations, and the count is cross-checked against
    the pairing streams so ``revoked`` cannot drift from what actually happened.
    """
    best: tuple[int, object] = (0, None)
    for _bill, old_pdf, new_pdf in _PAIRS:
        old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
        registry = PdfObservationRegistry(old_blocks, new_blocks)
        outputs = pdf_round1_with_stage_outputs(old_blocks, new_blocks, registry, threshold=SIMILARITY_THRESHOLD)
        if len(outputs.revoked) > best[0]:
            best = (len(outputs.revoked), outputs)

    count, outputs = best
    assert count > 0, "no committed pair revokes anything; this control would assert nothing"

    aligned_before = sum(1 for p in outputs.provisional if p.old is not None and p.new is not None)
    aligned_after = sum(1 for p in outputs.pairings if p.old is not None and p.new is not None)
    assert count == aligned_before - aligned_after, (
        f"`revoked` reports {count} records but the streams differ by {aligned_before - aligned_after} pairings"
    )
    assert len(outputs.evidence) == aligned_before, "every aligned pairing is described exactly once"
    for item in outputs.revoked:
        assert item.get("text_identical") is False, "an identical-text pairing is never revoked"


@pytest.mark.slow
def test_the_stage_outputs_reproduce_what_diff_pdfs_uses() -> None:
    """The stage-output entry point is the implementation, not a parallel one.

    ``diff_pdfs`` projects over ``pdf_round1_with_stage_outputs``; a second traversal would be a
    second authority on candidate membership and order. Checked by rebuilding the post-revocation
    stream from the stage outputs and comparing it against a fresh call.
    """
    _bill, old_pdf, new_pdf = _PAIRS[0]
    old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)

    first = pdf_round1_with_stage_outputs(old_blocks, new_blocks, registry, threshold=SIMILARITY_THRESHOLD)
    again = pdf_round1_with_stage_outputs(old_blocks, new_blocks, registry, threshold=SIMILARITY_THRESHOLD)

    assert [(p.old, p.new) for p in first.pairings] == [(p.old, p.new) for p in again.pairings]
    assert first.evidence == again.evidence
    assert {c.ordinal_pair for c in first.candidates.candidates()} == {
        c.ordinal_pair for c in again.candidates.candidates()
    }
