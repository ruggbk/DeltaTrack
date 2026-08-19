"""ADR 0019 addressing and provenance for round-1 artifacts, in one place.

Round 1 has two committed judgments about the same emitted observation sequences --
``tests/data/round1_pairing_sentinel.json`` and, until #659 retires it, the legacy trace --
and both are only meaningful relative to the parse they were recorded against. The mechanics
that establish that scope live here rather than in either module, because two copies of an
identity rule is how two artifacts come to disagree about what parse they describe.

Nothing here decides anything about matching. These are the address space
(:func:`complete_sequence_ordinals`), the provenance that scopes it
(:func:`source_sha256`, :func:`parser_revision`), the key an artifact is filed under
(:func:`pair_key`), and the digest a pairing stream is stored as (:func:`stream_digest`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

from deltatrack.bill_tree import BillNode
from tests.corpus_paths import PROJECT_ROOT

_PROBES = PROJECT_ROOT / "docs" / "research" / "provision-matching" / "probes"


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


def pair_key(old_path: Path, new_path: Path) -> str:
    return f"{old_path.parent.name}/{old_path.stem}->{new_path.stem}"
