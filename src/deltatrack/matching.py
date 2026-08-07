"""Data contracts for the four matching stages (ADR 0020).

ADR 0020 splits one fused decision into retrieval, identity evidence, assignment and
classification. This module holds the values that pass between them, and nothing else:
no retriever, no measure, no threshold, no orchestration. It is the vocabulary the
stages will be written against, introduced ahead of them so that moving behaviour is a
separate, byte-identical change.

**Nothing imports this yet, and that is the design.** ADR 0020's implementation rule is
to introduce the contracts behaviour-preservingly before changing matching policy, with
canonical JSON byte-identical across the corpus as the acceptance criterion
(``tests/test_canonical_baseline.py``). A slice that both defined the types and rewired
the differ could not report that criterion as evidence of anything, because the two
changes would be inseparable in the result.

The line the whole record turns on, restated here because every type below is placed by
it:

    Retrieval policy controls consideration. Assignment policy controls correspondence.

**This module imports nothing from ``deltatrack``, and a test enforces that.** It is the
mechanism behind ADR 0020's requirement that the contracts survive an unsettled PDF
observation representation: a type that cannot name a ``BillNode``, a text run or a glyph
cannot come to depend on whether a PDF observation is reconstructed from glyphs, read
from PDFium's character stream, or produced by a hybrid. An import of the engine is the
first step of that dependency, so the import graph is where it is cheapest to refuse.

## What an observation reference is, and is not

[ADR 0019](../../docs/decisions/0019-observation-identity.md) identifies a parsed
observation by ``(source_sha256, parser_revision, node_ordinal)``. Within one comparison
the first two are constant per side: every old-side observation shares one source digest
and one parser revision, likewise every new-side one. So :class:`ObservationRef` carries
only what varies — the side and the ordinal — and the document-level half of the identity
is a property of the comparison rather than of each reference.

That is a deliberate narrowing with a stated cost. A reference is meaningful **only
within the comparison that produced it**, so nothing here may be stored, compared across
runs, or written into a fixture without re-attaching the digest and the revision. ADR
0019 governs stored artifacts and says explicitly that it changes no engine runtime
behaviour; carrying a content hash of the parser on every candidate would be that change,
for a benefit no in-run consumer has.

Why not skip the ordinal and reference the node object? Because the ordinal is what makes
a candidate set inspectable, comparable between runs of the same input, and expressible
in a research artifact — the whole reason ADR 0020 wants the set materialised. It also
generalises to PDF where ``element_id`` does not.

## Rules that shape these types

- **A candidate exists once per observation pair**, however many retrievers found it.
- **Rank and score belong to a proposal, not to a candidate** — a pair proposed by two
  retrievers has no single rank, and their scores are on unrelated scales.
- **A retriever need not produce a number.** A proposal with null rank and score is
  fully valid; requiring a score pushes retrievers into inventing one, and an invented
  score is worse than an absent field because it looks comparable.
- **Proposals are provenance, not votes.** Duplicate proposals change neither candidate
  multiplicity nor assignment weight.
- **Evidence carries no correspondence verdict**, and no assignment policy.
- **Correspondence is first-class and not pair-shaped**, so a consolidation has a
  production shape to be measured against.

## Deliberately absent

- Any retriever, similarity measure or threshold. Retrieval and assignment policy are
  the next slices' work; ``deltatrack.similarity`` remains the only home for a cutoff.
- The canonical projection of a non-binary correspondence. ADR 0020 settles that it
  degrades explicitly and never duplicates a side's amounts, but no producer emits a
  non-binary correspondence yet, and a projection with no caller is a rule pinned by a
  test rather than by use.
- Serialization. ADR 0020 freezes semantics, not wire format, and no consumer needs one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

#: Values a retriever configuration or an evidence signal may carry. Restricted to
#: hashable primitives so every type here stays a hashable, orderable value: a config
#: holding a list would make its invocation unhashable, and the invocation is what
#: proposals deduplicate on.
Scalar = bool | int | float | str | None

#: The two sides of one comparison. Within a run these stand in for ADR 0019's
#: ``source_sha256``, which is constant per side (see the module docstring).
OLD = "old"
NEW = "new"
SIDES = frozenset({OLD, NEW})


def _freeze(mapping: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]]) -> tuple[tuple[str, Scalar], ...]:
    """A mapping as a name-sorted tuple of pairs.

    Sorted rather than insertion-ordered so that two callers building the same
    configuration or signal set in different orders produce equal values. Without it,
    equality and hashing would depend on keyword order, and a deduplication keyed on a
    configuration would silently keep two copies of one invocation.
    """
    items = tuple(mapping.items()) if isinstance(mapping, Mapping) else tuple(mapping)
    names = [name for name, _ in items]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate names: {sorted({n for n in names if names.count(n) > 1})}")
    return tuple(sorted(items, key=lambda pair: pair[0]))


@dataclass(frozen=True, order=True)
class ObservationRef:
    """Address of one parsed observation within one comparison (ADR 0019).

    See the module docstring for why this is the side and the ordinal alone, and for the
    constraint that follows: a reference is meaningless outside the comparison that
    produced it.

    ``ordinal`` indexes the parser's **complete emitted sequence** for that side. ADR
    0019 names indexing a filtered or re-sorted view as a genuine hazard, because the
    resulting address looks valid and points at the wrong node.
    """

    side: str
    ordinal: int

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"side must be one of {sorted(SIDES)}, got {self.side!r}")
        if self.ordinal < 0:
            raise ValueError(f"ordinal must be non-negative, got {self.ordinal}")


@dataclass(frozen=True, order=True)
class RetrieverInvocation:
    """One retriever running under one configuration in one round.

    The unit a proposal is attributable to, which is what makes a candidate-recall figure
    reproducible: a recall number without the configuration that produced it cannot be
    compared against another run.

    ``config`` records the bounds, cutoffs and K the retriever ran under. It is a
    name-sorted tuple rather than a dict so an invocation is hashable and two callers
    spelling the same configuration in different orders produce equal invocations.
    """

    retriever: str
    round: int = 0
    config: tuple[tuple[str, Scalar], ...] = ()

    def __post_init__(self) -> None:
        if not self.retriever:
            raise ValueError("retriever must be named")
        if self.round < 0:
            raise ValueError(f"round must be non-negative, got {self.round}")

    @classmethod
    def of(cls, retriever: str, *, round: int = 0, **config: Scalar) -> RetrieverInvocation:
        """Build one from keyword configuration: ``of("path_group", threshold=0.4)``."""
        return cls(retriever=retriever, round=round, config=_freeze(config))


@dataclass(frozen=True, order=True)
class Proposal:
    """One retriever invocation's claim that a pair is worth evaluating.

    ``rank`` and ``score`` are *that invocation's*, and both may be absent. A structural
    retriever emits membership and provenance and nothing else; ADR 0020 rejects a
    required score on the ground that an invented one looks comparable when it is not.

    A retrieval score is not identity evidence. It exists for observability and for
    recall and ranking analysis. If one turns out to be informative about identity, the
    way to use it is as a named :class:`Evidence` signal, where it can be measured.
    """

    invocation: RetrieverInvocation
    rank: int | None = None
    score: float | None = None

    def __post_init__(self) -> None:
        if self.rank is not None and self.rank < 0:
            raise ValueError(f"rank must be non-negative, got {self.rank}")


@dataclass(frozen=True)
class Candidate:
    """One observation pair worth evaluating, with the provenance that surfaced it.

    Its identity is the pair and nothing else, so equality and hashing read ``old`` and
    ``new`` only — two candidates for the same pair are the same candidate whatever
    proposed them. ``proposals`` is provenance carried alongside, which is why it is
    excluded from comparison rather than folded into it.

    A candidate cannot exist without at least one proposal. A pair that reached
    evaluation without a recorded retriever invocation is a pair whose recall cannot be
    attributed, which is the observability the candidate boundary exists to buy.
    """

    old: ObservationRef
    new: ObservationRef
    proposals: tuple[Proposal, ...] = field(compare=False, default=())

    def __post_init__(self) -> None:
        if self.old.side != OLD or self.new.side != NEW:
            raise ValueError(f"a candidate pairs one old-side and one new-side observation, got {self.old}, {self.new}")
        if not self.proposals:
            raise ValueError(f"candidate {self.pair} has no retrieval provenance")

    @property
    def pair(self) -> tuple[int, int]:
        """The ordinal pair, for ordering and for reading in a failure message."""
        return (self.old.ordinal, self.new.ordinal)

    @property
    def invocations(self) -> tuple[RetrieverInvocation, ...]:
        """The invocations that surfaced this candidate, in the order they proposed it."""
        return tuple(proposal.invocation for proposal in self.proposals)


class CandidateSet:
    """The pairs one comparison considered, accumulated across retriever invocations.

    A builder rather than a frozen value, because retrieval composes: several retrievers,
    possibly several rounds, each adding to one set. :meth:`candidates` is the value it
    produces.

    Deduplication is the whole point, and ADR 0020 warns it can fail in two opposite
    directions — deduplicating too eagerly drops a proposal's metadata, not deduplicating
    lets one pair reach assignment twice. So:

    - the same pair proposed again yields one candidate, never two;
    - a proposal from a *different* invocation is retained beside the existing ones;
    - the same invocation proposing the same pair again is idempotent when the metadata
      matches, and raises when it does not.

    That last rule is why conflicting metadata is an error rather than a silent choice.
    One invocation offering a pair at rank 1 and again at rank 7 has no defensible
    answer; keeping the first makes the recorded provenance a function of iteration
    order, which is exactly the unattributable number the candidate boundary exists to
    prevent.

    This set is scoped to one comparison. :class:`ObservationRef` carries no document
    identity, so merging two sets built from different comparisons would silently
    conflate observations — see the module docstring.
    """

    def __init__(self) -> None:
        self._proposals: dict[tuple[ObservationRef, ObservationRef], dict[RetrieverInvocation, Proposal]] = {}

    def propose(
        self,
        old: ObservationRef,
        new: ObservationRef,
        invocation: RetrieverInvocation,
        *,
        rank: int | None = None,
        score: float | None = None,
    ) -> None:
        """Record that ``invocation`` surfaced ``(old, new)`` as worth evaluating."""
        proposal = Proposal(invocation=invocation, rank=rank, score=score)
        if old.side != OLD or new.side != NEW:
            raise ValueError(f"a candidate pairs one old-side and one new-side observation, got {old}, {new}")
        by_invocation = self._proposals.setdefault((old, new), {})
        existing = by_invocation.get(invocation)
        if existing is not None and existing != proposal:
            raise ValueError(
                f"{invocation.retriever} proposed ({old.ordinal}, {new.ordinal}) twice in one invocation with "
                f"different metadata: {existing} then {proposal}. One invocation's view of one pair is single-valued; "
                "re-proposing under a changed configuration is a new invocation."
            )
        by_invocation[invocation] = proposal

    def candidates(self) -> tuple[Candidate, ...]:
        """Every considered pair, ordered by ordinal pair.

        Ordered by ``(old.ordinal, new.ordinal)`` rather than by insertion, so the set is
        a function of *which* pairs were proposed and not of which retriever ran first.
        That keeps each stage a deterministic function of its input (ADR 0008) even as
        retrieval grows from one retriever to a union of several.

        Proposals within a candidate keep insertion order, because that order is the
        round order and carries meaning a sort would destroy.
        """
        return tuple(
            Candidate(old=old, new=new, proposals=tuple(by_invocation.values()))
            for (old, new), by_invocation in sorted(self._proposals.items(), key=lambda item: item[0])
        )

    def __len__(self) -> int:
        return len(self._proposals)

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self.candidates())

    def __contains__(self, pair: object) -> bool:
        return pair in self._proposals


@dataclass(frozen=True)
class Evidence:
    """Named identity signals for one candidate pair. Decides nothing.

    Evidence describes; assignment decides. There is deliberately no verdict field, no
    confidence, and no threshold: ADR 0020 rejects a policy-bearing evidence object on
    the ground that one score already serves several policies, so an object carrying its
    own would either pick one — wrong — or grow one per consumer, which is the present
    coupling with more indirection.

    ``signals`` is a name-sorted tuple of scalars, so an evidence value is hashable and
    order-independent. Booleans are welcome (header equality, path equality); what is not
    welcome is a name that answers "do these correspond?".

    Growing the vocabulary means adding a signal, never a field.
    ``tests/test_matching_contracts.py`` pins the field set for that reason: a new field
    is the shape a verdict would arrive in.
    """

    old: ObservationRef
    new: ObservationRef
    signals: tuple[tuple[str, Scalar], ...] = ()

    @classmethod
    def of(cls, old: ObservationRef, new: ObservationRef, **signals: Scalar) -> Evidence:
        """Build evidence from named signals: ``Evidence.of(o, n, header_equal=True)``."""
        return cls(old=old, new=new, signals=_freeze(signals))

    @property
    def names(self) -> tuple[str, ...]:
        """The signal names carried, sorted."""
        return tuple(name for name, _ in self.signals)

    def get(self, name: str, default: Scalar = None) -> Scalar:
        """One signal's value, or ``default`` when it was not computed."""
        for signal_name, value in self.signals:
            if signal_name == name:
                return value
        return default


@dataclass(frozen=True)
class Correspondence:
    """Which observations correspond. Assignment's output, and the only place that decides.

    Sides are tuples rather than one node each, so 1:1, 1:0, 0:1, 1:N and N:1 are all
    representable without loss — and N:M falls out, which is honest rather than
    accidental: nothing here forbids it, and a type that permitted the five but not the
    sixth would be arbitrary.

    **Representable is not produced.** The current assigner emits only 1:1, 1:0 and 0:1,
    and ADR 0020 does not change that. What changes is that the type stops being the
    reason a real legislative shape cannot be expressed, so a later algorithm change is
    not also a type migration through every consumer.

    ``evidence`` carries the evidence that selected each link, so a 1:N holds N entries
    and a 1:0 holds none. Each entry must name observations this correspondence actually
    relates; evidence about some other pair would make the record unreadable and is
    refused.
    """

    old: tuple[ObservationRef, ...] = ()
    new: tuple[ObservationRef, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.old and not self.new:
            raise ValueError("a correspondence relates at least one observation")
        for ref in self.old:
            if ref.side != OLD:
                raise ValueError(f"old side holds a {ref.side!r}-side reference: {ref}")
        for ref in self.new:
            if ref.side != NEW:
                raise ValueError(f"new side holds an {ref.side!r}-side reference: {ref}")
        for side, refs in (("old", self.old), ("new", self.new)):
            if len(set(refs)) != len(refs):
                raise ValueError(f"{side} side repeats an observation: {refs}")
        for item in self.evidence:
            if item.old not in self.old or item.new not in self.new:
                raise ValueError(f"evidence names a pair outside this correspondence: {item.old}, {item.new}")

    @property
    def cardinality(self) -> tuple[int, int]:
        """``(len(old), len(new))`` — 1:1 is ``(1, 1)``, a removal ``(1, 0)``."""
        return (len(self.old), len(self.new))

    @property
    def shape(self) -> str:
        """The cardinality as ADR 0020 names it: ``1:1``, ``1:0``, ``0:1``, ``1:N``, ``N:1``, ``N:M``."""
        old_n, new_n = self.cardinality
        if old_n <= 1 and new_n <= 1:
            return f"{old_n}:{new_n}"
        if old_n == 1:
            return "1:N"
        if new_n == 1:
            return "N:1"
        return "N:M"

    @property
    def is_binary(self) -> bool:
        """Whether the canonical contract can carry this correspondence as a single row.

        ADR 0020's "Where the canonical contract cannot follow": a canonical ``Change`` is
        a binary row, so 1:1, 1:0 and 0:1 map directly and anything else has no faithful
        representation and must degrade explicitly. No projection lives here yet — see
        the module docstring's "Deliberately absent".
        """
        return len(self.old) <= 1 and len(self.new) <= 1


class CorrespondenceSet:
    """Every correspondence settled for one comparison, with each observation claimed once.

    The exclusivity rule is **measured, not assumed**. Over all 27 adjacent version pairs
    of the committed manifest, ``diff_bill.match_nodes`` claims every node of both trees
    exactly once: no node appears in two pairs, none is omitted, none is invented. So
    encoding it here describes what the current assigner already does rather than
    imposing a policy on the refactor that would move it, and a Phase 1 extraction that
    tripped this would have changed assignment.

    Reproduce with ``scripts/probe_matching_stages.py``'s corpus walk, or read
    ``tests/test_matching_contracts.py::test_the_corpus_assigner_claims_each_observation_once``.

    This is the per-anchor competition policy only. Global collision resolution is a
    separate question with different correctness criteria, and ADR 0020 defers it
    without choosing an algorithm; nothing here anticipates one.
    """

    def __init__(self, correspondences: Iterable[Correspondence] = ()) -> None:
        self._correspondences: list[Correspondence] = []
        self._claimed: dict[ObservationRef, Correspondence] = {}
        for correspondence in correspondences:
            self.add(correspondence)

    def add(self, correspondence: Correspondence) -> None:
        """Settle one correspondence, refusing an observation already claimed."""
        for ref in (*correspondence.old, *correspondence.new):
            claimed_by = self._claimed.get(ref)
            if claimed_by is not None:
                raise ValueError(
                    f"{ref} is already claimed by {claimed_by.shape} correspondence "
                    f"{claimed_by.old}->{claimed_by.new}; an observation corresponds at most once"
                )
        for ref in (*correspondence.old, *correspondence.new):
            self._claimed[ref] = correspondence
        self._correspondences.append(correspondence)

    def correspondences(self) -> tuple[Correspondence, ...]:
        """Settled correspondences, in the order assignment produced them."""
        return tuple(self._correspondences)

    def claiming(self, ref: ObservationRef) -> Correspondence | None:
        """The correspondence claiming ``ref``, or ``None`` if nothing does."""
        return self._claimed.get(ref)

    def __len__(self) -> int:
        return len(self._correspondences)

    def __iter__(self) -> Iterator[Correspondence]:
        return iter(self._correspondences)
