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
    PATH_ROUND,
    POSITIONAL_REPLACE,
    PdfRound1StageOutputs,
    _AlignedPairing,
    _block_key,
    _round1_invocations,
    diff_pdfs,
    pdf_round1_with_stage_outputs,
    pdf_similarity_correspondence_evidence,
    retrieve_pdf_round1_candidates,
)
from deltatrack.matching import NEW, OLD, CandidateSet, ObservationRef, RetrieverInvocation
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


#: The two round-1 invocations, **stated here rather than imported from production**.
#:
#: ``ALIGNMENT``/``POSITIONAL`` above come from ``_round1_invocations()``, which makes them
#: useless as an oracle for provenance: asking production what it recorded and then checking the
#: answer against itself agrees whatever it recorded. These are written out independently, so a
#: pair relabelled from ``positional_replace`` to ``block_key_alignment``, or a config that
#: claims ``autojunk=True`` while the matcher actually ran with ``False``, is a disagreement
#: rather than a matching pair of wrong values.
#:
#: The round is the literal 1 rather than ``PATH_ROUND`` for the same reason, with
#: ``test_the_transcribed_round_number_matches_production`` pinning the two together — so a
#: change to the constant reddens here instead of propagating into the expectation silently.
EXPECTED_ALIGNMENT = RetrieverInvocation.of("block_key_alignment", round=1, autojunk=False)
EXPECTED_POSITIONAL = RetrieverInvocation.of("positional_replace", round=1)


def legacy_considered_pairs(
    v1_blocks: list[_Block], v2_blocks: list[_Block]
) -> list[tuple[int, int, RetrieverInvocation]]:
    """Every pair the pre-slice-7 aligner formed, with the rule that formed it, in stream order.

    Transcribed from the opcode walk rather than imported: an oracle that asked
    ``retrieve_pdf_round1_candidates`` what it considered could not detect that what it considers
    changed, which is the one failure this slice can have.

    **It returns provenance, not only membership.** Membership alone leaves a real false green:
    relabel a pair the positional rule formed as ``block_key_alignment`` and the pairing stream,
    the candidate set, admission and the canonical baseline all stay correct — the pairing and
    the set simply agree on the same wrong attribution — while ``RetrieverInvocation`` has
    stopped answering the question it exists for.
    """
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )
    considered: list[tuple[int, int, RetrieverInvocation]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for offset in range(min(i2 - i1, j2 - j1)):
                considered.append((i1 + offset, j1 + offset, EXPECTED_ALIGNMENT))
        elif op == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                considered.append((i1 + k, j1 + k, EXPECTED_POSITIONAL))
    return considered


def test_the_transcribed_round_number_matches_production() -> None:
    """The one production constant the expectations above inline, pinned rather than imported."""
    assert PATH_ROUND == 1, "round 1 is no longer 1; the transcribed invocations above are stale"


def test_the_corpus_pair_list_is_not_empty() -> None:
    """A parametrization list that silently empties is the fail-open shape (#542)."""
    assert len(_PAIRS) >= 20, f"only {len(_PAIRS)} adjacent PDF pairs discovered; the corpus holds more"


# --- Membership AND provenance equal the legacy considered population ----------------------


def _admitted_provenance(candidates) -> dict[tuple[int, int], frozenset[RetrieverInvocation]]:
    """What the candidate set says: which invocations surfaced each ordinal pair."""
    return {candidate.ordinal_pair: frozenset(candidate.invocations) for candidate in candidates.candidates()}


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_candidate_provenance_equals_the_legacy_considered_population(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Exactly the pairs the legacy aligner formed, each attributed to the rule that formed it.

    Membership alone is not enough, and that gap was a real false green. Relabelling a
    positional pair as ``block_key_alignment`` leaves the pairing stream, the candidate set's
    membership, admission and the canonical baseline all correct — the pairing and the set agree
    on the same wrong attribution — while ``RetrieverInvocation`` stops answering the question it
    exists for. So this compares the whole ``{pair: {invocations}}`` mapping against the
    independently transcribed walk, which also catches a config that misreports ``autojunk``.

    Widening retrieval shows up here as extra keys; dropping the positional rule as missing ones.
    """
    old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    _pairings, candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)

    expected: dict[tuple[int, int], frozenset[RetrieverInvocation]] = {}
    for old_ordinal, new_ordinal, invocation in legacy_considered_pairs(old_blocks, new_blocks):
        expected[(old_ordinal, new_ordinal)] = frozenset({invocation})

    assert _admitted_provenance(candidates) == expected


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_every_provisional_pairing_carries_its_retrievers_provenance(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Each 1:1 names the rule that formed it, and each unmatched side names none.

    Checked against the independently transcribed expectation, pairing for pairing in stream
    order, rather than against ``_round1_invocations()``. The earlier version asserted only that
    the invocation was *one of the two production returned*, which agrees with production
    whatever production recorded.
    """
    old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    pairings, _candidates = retrieve_pdf_round1_candidates(old_blocks, new_blocks, registry)

    expected = legacy_considered_pairs(old_blocks, new_blocks)
    aligned = [p for p in pairings if p.old is not None and p.new is not None]
    assert len(aligned) == len(expected), f"{len(aligned)} aligned pairings against {len(expected)} expected"

    for pairing, (old_ordinal, new_ordinal, invocation) in zip(aligned, expected):
        assert registry.ref(OLD, pairing.old).ordinal == old_ordinal
        assert registry.ref(NEW, pairing.new).ordinal == new_ordinal
        assert pairing.invocation == invocation, (
            f"pair ({old_ordinal}, {new_ordinal}) is attributed to {pairing.invocation}, but the "
            f"transcribed opcode walk says {invocation} formed it"
        )

    for pairing in pairings:
        if pairing.old is None or pairing.new is None:
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
def test_diff_pdfs_consumes_the_stage_output_helper_rather_than_its_own_round_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pdf_round1_with_stage_outputs`` is the single implementation, proved by substitution.

    The earlier version of this test called the helper twice and compared it with itself, which
    is no control at all: ``diff_pdfs`` could inline an equivalent round 1, ignore the helper
    entirely, and produce byte-identical canonical output while the stage-output API quietly
    stopped being the implementation.

    So this substitutes a **different** stage result and requires the diff to follow it. The
    natural round 1 keeps one particular pairing as a surviving 1:1; the fake splits that pairing
    into two unmatched observations, which no threshold or policy change would do. If
    ``diff_pdfs`` builds its own round 1, the hunks come back matching the natural result and the
    substitution goes unnoticed — which is exactly what this must refuse.

    The call tripwire proves the helper was reached; the output comparison proves its return
    value was used. Both halves are needed: a raise-only patch shows only the first.
    """
    _bill, old_pdf, new_pdf = _PAIRS[0]
    v1_pages, v2_pages = cached_pages(old_pdf), cached_pages(new_pdf)

    natural = diff_pdfs(v1_pages, v2_pages)
    calls: list[int] = []
    real = diff_pdf.pdf_round1_with_stage_outputs

    def _substituted(v1_blocks, v2_blocks, registry, *, threshold):
        calls.append(1)
        outputs = real(v1_blocks, v2_blocks, registry, threshold=threshold)
        split_at = next(
            (i for i, p in enumerate(outputs.pairings) if p.old is not None and p.new is not None),
            None,
        )
        assert split_at is not None, "this fixture must contain a surviving 1:1 to split"
        victim = outputs.pairings[split_at]
        mutated = (
            *outputs.pairings[:split_at],
            _AlignedPairing(victim.old, None),
            _AlignedPairing(None, victim.new),
            *outputs.pairings[split_at + 1 :],
        )
        return PdfRound1StageOutputs(
            provisional=outputs.provisional,
            candidates=outputs.candidates,
            evidence=outputs.evidence,
            pairings=mutated,
        )

    monkeypatch.setattr(diff_pdf, "pdf_round1_with_stage_outputs", _substituted)
    substituted = diff_pdfs(v1_pages, v2_pages)

    assert calls, "diff_pdfs never called pdf_round1_with_stage_outputs; it is running its own round 1"
    assert substituted.hunks != natural.hunks, (
        "diff_pdfs produced the natural result while the stage helper returned a different "
        "pairing stream; the helper's return value is not what the diff is built from"
    )
