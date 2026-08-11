"""What a pre-classification second retrieval round would have to reproduce exactly.

Investigation D for the #581 prerequisite. ADR 0020 forbids retrieval after
classification, so ``reconcile_moves`` -- a second retrieval plus assignment pass running
over already-classified changes -- eventually has to move ahead of classification. Two
things decide whether that is a behaviour-preserving move or a behaviour change, and
neither is measured by the probes committed with #586:

**A. The input population.** ``probe_splits.py`` measures that 327 path-matched pairings
are replaced by a removal plus an addition, and says explicitly that their overlap with
the move population is NOT measured. Without that overlap, "move the round earlier" is
unscoped. This measures how much of the candidate and selected-move population depends on
an observation that only exists because the similarity rule revoked its pairing.

**B. The ordering key.** Production sorts candidates by ``(similarity, ri, ai)``, where
``ri``/``ai`` are positions in the FILTERED removed/added lists. An extraction that
replaced that key with ADR 0019 ordinals would preserve behaviour only if the two
orderings agree. This runs both keys through the same greedy loop and compares the
selected correspondence -- set and order -- pair by pair.

WHAT #591 CHANGED, because it changes what A *means* without moving a single number.
Before #591 the similarity cutoff ran inside ``diff_bills``' classification loop, so the
removal and the addition it produced did not exist until classification had run, and a
retrieval round placed before classification could not have seen them at all. #591 moved
that decision into :func:`~deltatrack.diff_bill.apply_similarity_revocation`, which runs
*ahead* of the loop. The two observations are now separated before classification, so a
round-2 pass placed after that stage does see them.

    The population figure is therefore no longer evidence that the round cannot move. It
    now sizes a SEQUENCING CONSTRAINT INSIDE ASSIGNMENT: round 2 must run after the
    similarity revocation, not merely before classification. What still blocks a literal
    relocation is representational, not populational -- ``reconcile_moves`` consumes
    ``NodeDiff`` records, which are classification output, so it would have to be
    re-expressed over observations. Every field it reads (``old_text``, ``new_text``,
    ``element_id_old``/``_new``, ``display_path_*``, ``match_path``, ``section_number``,
    the amount texts) is derivable from the ``BillNode`` pair, so that is a mechanical
    change owing its own evidence rather than an obstacle.

Accordingly this says "revoked" and "revocation-produced" throughout. The pre-#591
architecture is the only place "classification-created" was ever true. The figures below
were first measured against it on this branch at c3b6387, whose base af83c28 differs from
the last pre-#591 develop (97f91ba) by documentation only; they are unchanged at 0f07dc4
(post-#591), which is itself independent evidence that #591 preserved the population.

Section E then measures the "representational, not populational" claim above rather than
leaving it as reasoning, since it is the sentence the next slice rests on.

FAIL-CLOSED throughout, because the numbers are void without it:

    - The revocation population is read from PRODUCTION's own predicate
      (``pairing_survives_similarity_rule``), not from a transcription of it. A
      lookalike condition -- ``old_norm != new_norm`` in place of the ``diff_text``
      emptiness gate -- agrees on all 15,034 corpus pairings today, and that agreement is
      a measurement rather than a guarantee. Reading production removes the question.
    - That predicate's verdict is cross-checked against what
      ``apply_similarity_revocation`` structurally *did*: one revocation must add exactly
      one tuple. If the count disagrees, the probe stops rather than reporting a
      population derived from a predicate production did not apply.
    - ``element_id`` is used only as a MEASUREMENT BRIDGE from a ``NodeDiff`` back to the
      node it came from, since ``NodeDiff`` carries no node reference. It is not proposed
      as identity (ADR 0019 refuses that). The probe asserts uniqueness and non-emptiness
      per side and stops if either fails.
    - The duplicated greedy loop must reproduce production's selected set AND order under
      the production key before any comparison figure is printed. A drifted duplicate
      would be comparing the ordinal key against itself rather than against production.
    - Section E compares unmatched observations to change records PER PAIR, not in
      aggregate, and stops on any mismatch. Two pairs whose errors cancelled would agree
      on the totals and disagree on every document.

Read-only, writes nothing. Run from the project root:

    uv run python scripts/probe_round2_migration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.compare.xml import compare_xml  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, move_candidates  # noqa: E402
from deltatrack.version_stems import label_from_stem  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

REAL_MATCH_NODES = db.match_nodes
REAL_REVOCATION = db.apply_similarity_revocation
REAL_RECONCILE = db.reconcile_moves


def capture() -> dict[str, dict]:
    """Per corpus pair: the trees, ``match_nodes`` output, the revocation stage's output,
    and ``reconcile_moves``' input.

    All captured by wrapping the production functions inside a real ``compare_xml`` run,
    so every value measured is the value production actually produced rather than a
    reconstruction of it.
    """
    captured: dict[str, dict] = {}
    holder: dict[str, str] = {}

    def match_spy(old, new):
        pairs = REAL_MATCH_NODES(old, new)
        captured.setdefault(holder["key"], {}).update(old_tree=old, new_tree=new, pairs=pairs)
        return pairs

    def revocation_spy(pairs):
        decided = REAL_REVOCATION(pairs)
        captured.setdefault(holder["key"], {})["decided"] = decided
        return decided

    def reconcile_spy(changes, threshold=MOVE_THRESHOLD):
        captured.setdefault(holder["key"], {})["changes"] = list(changes)
        return REAL_RECONCILE(changes, threshold)

    db.match_nodes = match_spy
    db.apply_similarity_revocation = revocation_spy
    db.reconcile_moves = reconcile_spy
    try:
        for key, old_path, new_path in baseline_pairs():
            holder["key"] = key
            compare_xml(
                old_path.read_bytes(),
                new_path.read_bytes(),
                start_label=label_from_stem(old_path.stem),
                end_label=label_from_stem(new_path.stem),
            )
    finally:
        db.match_nodes = REAL_MATCH_NODES
        db.apply_similarity_revocation = REAL_REVOCATION
        db.reconcile_moves = REAL_RECONCILE
    return captured


def ordinal_bridge(nodes: list, key: str) -> dict[str, int]:
    """``{element_id: ordinal}``, refusing to build if the bridge is not one-to-one."""
    ids = [node.element_id for node in nodes]
    if not all(ids):
        raise SystemExit(f"{key}: an element_id is empty; the measurement bridge is unusable")
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{key}: element_id repeats; the measurement bridge would hit the wrong node")
    return {element_id: ordinal for ordinal, element_id in enumerate(ids)}


def revoked_element_ids(pairs: list, decided: list, key: str) -> tuple[set[str], set[str]]:
    """Element ids of the observations the similarity rule left unmatched.

    Asks PRODUCTION's ``pairing_survives_similarity_rule`` rather than transcribing it,
    then checks that verdict against what ``apply_similarity_revocation`` structurally did:
    each revocation replaces one tuple with two, so the output must be longer by exactly
    the number of revocations counted here. A disagreement means the predicate being
    consulted is not the one production applied, and every figure downstream would be
    describing the wrong population.
    """
    old_ids: set[str] = set()
    new_ids: set[str] = set()
    revocations = 0
    for old_node, new_node in pairs:
        if old_node is None or new_node is None:
            continue
        if not db.pairing_survives_similarity_rule(old_node, new_node):
            revocations += 1
            old_ids.add(old_node.element_id)
            new_ids.add(new_node.element_id)

    added_tuples = len(decided) - len(pairs)
    if added_tuples != revocations:
        raise SystemExit(
            f"{key}: the revocation predicate and the revocation stage disagree -- "
            f"predicate counted {revocations}, stage added {added_tuples} tuples"
        )
    return old_ids, new_ids


def filtered_sides(changes: list) -> tuple[list, list]:
    """The removed/added lists ``reconcile_moves`` builds, in its own order."""
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]
    return removed, added


def greedy(ordered: list[tuple], removed: list, added: list) -> list[tuple[str, str]]:
    """Production's greedy exclusivity loop over an already-ordered candidate list."""
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    selected: list[tuple[str, str]] = []
    for _sim, ri, ai in ordered:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        selected.append((removed[ri][1].element_id_old, added[ai][1].element_id_new))
    return selected


def production_signature(changes: list) -> list[tuple[str, str]]:
    """The real function's selected moves, in emission order, keyed by element id."""
    return [(c.element_id_old, c.element_id_new) for c in REAL_RECONCILE(list(changes)) if c.change_type == "moved"]


def main() -> None:
    captured = capture()

    total_candidates = 0
    total_selected = 0
    cand_revoked_removal = 0
    cand_revoked_addition = 0
    cand_revoked_either = 0
    cand_revoked_both = 0
    sel_revoked_removal = 0
    sel_revoked_addition = 0
    sel_revoked_either = 0
    sel_revoked_both = 0
    revoked_removals_in_input = 0
    revoked_additions_in_input = 0
    removals_in_input = 0
    additions_in_input = 0

    monotone_removed = 0
    monotone_added = 0
    pairs_with_candidates = 0

    agreement_failures: list[str] = []
    ordinal_key_differs: list[str] = []
    ordinal_key_order_only: list[str] = []
    ordinal_selection_delta = 0

    for key in sorted(captured):
        record = captured[key]
        changes = record["changes"]
        old_at = ordinal_bridge(record["old_tree"].nodes, key + " [old]")
        new_at = ordinal_bridge(record["new_tree"].nodes, key + " [new]")
        revoked_old, revoked_new = revoked_element_ids(record["pairs"], record["decided"], key)

        removed, added = filtered_sides(changes)
        removals_in_input += len(removed)
        additions_in_input += len(added)
        revoked_removals_in_input += sum(1 for _, c in removed if c.element_id_old in revoked_old)
        revoked_additions_in_input += sum(1 for _, c in added if c.element_id_new in revoked_new)

        if not removed or not added:
            continue

        candidates = move_candidates(
            [db._normalize_text(rc.old_text or "") for _, rc in removed],
            [db._normalize_text(ac.new_text or "") for _, ac in added],
            MOVE_THRESHOLD,
        )
        if not candidates:
            continue
        pairs_with_candidates += 1
        total_candidates += len(candidates)

        removed_is_revoked = [c.element_id_old in revoked_old for _, c in removed]
        added_is_revoked = [c.element_id_new in revoked_new for _, c in added]
        for _sim, ri, ai in candidates:
            r_revoked = removed_is_revoked[ri]
            a_revoked = added_is_revoked[ai]
            cand_revoked_removal += r_revoked
            cand_revoked_addition += a_revoked
            cand_revoked_either += r_revoked or a_revoked
            cand_revoked_both += r_revoked and a_revoked

        # --- ordering: is the filtered-list order the parser-ordinal order? -----------
        removed_ordinals = [old_at[c.element_id_old] for _, c in removed]
        added_ordinals = [new_at[c.element_id_new] for _, c in added]
        monotone_removed += removed_ordinals == sorted(removed_ordinals)
        monotone_added += added_ordinals == sorted(added_ordinals)

        # --- the two keys, through one greedy loop ------------------------------------
        production_order = sorted(candidates, reverse=True)
        replayed = greedy(production_order, removed, added)
        actual = production_signature(changes)
        if replayed != actual:
            agreement_failures.append(key)
            continue

        total_selected += len(actual)
        selected_index = {
            (removed[ri][1].element_id_old, added[ai][1].element_id_new): (ri, ai) for _sim, ri, ai in production_order
        }
        for link in actual:
            ri, ai = selected_index[link]
            r_revoked = removed_is_revoked[ri]
            a_revoked = added_is_revoked[ai]
            sel_revoked_removal += r_revoked
            sel_revoked_addition += a_revoked
            sel_revoked_either += r_revoked or a_revoked
            sel_revoked_both += r_revoked and a_revoked

        ordinal_order = sorted(
            candidates,
            key=lambda c: (c[0], removed_ordinals[c[1]], added_ordinals[c[2]]),
            reverse=True,
        )
        by_ordinal = greedy(ordinal_order, removed, added)
        if by_ordinal != actual:
            if set(by_ordinal) == set(actual):
                ordinal_key_order_only.append(key)
            else:
                ordinal_key_differs.append(key)
                ordinal_selection_delta += len(set(actual) ^ set(by_ordinal))

    if agreement_failures:
        print("DUPLICATE-LOOP AGREEMENT FAILURES -- every figure below would be void:")
        for key in agreement_failures:
            print(f"  {key}")
        raise SystemExit("duplicated greedy loop disagrees with production")

    print("===== A: INPUT POPULATION OF THE SECOND PASS =====")
    print(f"removals reaching reconcile_moves: {removals_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE (path-matched then revoked): {revoked_removals_in_input}")
    print(f"additions reaching reconcile_moves: {additions_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE: {revoked_additions_in_input}")

    print("\n===== B: HOW MUCH OF THE MOVE POPULATION DEPENDS ON A REVOKED PAIRING =====")
    print(f"candidates: {total_candidates}")
    print(f"  with a revocation-produced REMOVAL: {cand_revoked_removal}")
    print(f"  with a revocation-produced ADDITION: {cand_revoked_addition}")
    print(f"  with either side revocation-produced: {cand_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {cand_revoked_both}")
    print(f"selected moves: {total_selected}")
    print(f"  with a revocation-produced REMOVAL: {sel_revoked_removal}")
    print(f"  with a revocation-produced ADDITION: {sel_revoked_addition}")
    print(f"  with either side revocation-produced: {sel_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {sel_revoked_both}")
    if total_selected:
        print(
            f"  share of selected moves touching a revoked pairing: {100.0 * sel_revoked_either / total_selected:.1f}%"
        )
    print("  (post-#591 this sizes an ORDERING constraint inside assignment -- round 2 must")
    print("   run after the revocation stage -- not a dependency on classification output.)")

    print("\n===== C: IS THE (ri, ai) ORDER THE PARSER-ORDINAL ORDER? =====")
    print(f"pairs carrying candidates: {pairs_with_candidates}")
    print(f"  removed list already in parser-ordinal order: {monotone_removed}")
    print(f"  added list already in parser-ordinal order: {monotone_added}")

    print("\n===== D: SUBSTITUTING ORDINALS FOR (ri, ai) IN THE SORT KEY =====")
    print(f"pairs where the SELECTED SET changes: {len(ordinal_key_differs)} {ordinal_key_differs}")
    print(f"pairs where only the SELECTION ORDER changes: {len(ordinal_key_order_only)} {ordinal_key_order_only}")
    print(f"selected links added or lost by the ordinal key: {ordinal_selection_delta}")
    print("\nGUARD: the replay reproduced production's set AND order on every pair above,")
    print("and the revocation predicate agreed with the revocation stage on every pair.")

    report_input_availability(captured)


def report_input_availability(captured: dict[str, dict]) -> None:
    """Is round 2's whole input population already present BEFORE classification?

    Section B says the remaining obstacle to relocating round 2 is representational
    rather than populational. That is a claim about availability, so it is measured here
    rather than argued: every ``(old, None)`` in the revocation stage's output must
    correspond to a ``removed`` record reaching ``reconcile_moves``, and every
    ``(None, new)`` to an ``added`` one. A shortfall on either side would mean some of
    round 2's input genuinely does not exist until classification has run, and the
    "representational only" reading would be wrong.

    Compared per pair, not in aggregate: two pairs whose errors cancelled would agree on
    the totals and disagree on every document.
    """
    unmatched_old = unmatched_new = records_removed = records_added = 0
    mismatches: list[tuple] = []

    for key in sorted(captured):
        decided = captured[key]["decided"]
        changes = captured[key]["changes"]
        tuples = (
            sum(1 for a, b in decided if a is not None and b is None),
            sum(1 for a, b in decided if a is None and b is not None),
        )
        records = (
            sum(1 for c in changes if c.change_type == "removed"),
            sum(1 for c in changes if c.change_type == "added"),
        )
        unmatched_old += tuples[0]
        unmatched_new += tuples[1]
        records_removed += records[0]
        records_added += records[1]
        if tuples != records:
            mismatches.append((key, tuples, records))

    print("\n===== E: IS ROUND 2's INPUT AVAILABLE BEFORE CLASSIFICATION? =====")
    print(f"(old, None) unmatched observations out of the revocation stage: {unmatched_old}")
    print(f"  'removed' records reaching reconcile_moves after classification: {records_removed}")
    print(f"(None, new) unmatched observations out of the revocation stage: {unmatched_new}")
    print(f"  'added' records reaching reconcile_moves after classification: {records_added}")
    print(f"per-pair mismatches: {len(mismatches)}")
    if mismatches:
        for row in mismatches:
            print(f"  {row}")
        raise SystemExit(
            "part of round 2's input does not exist before classification; section B's "
            "'representational, not populational' reading does not hold"
        )
    print("None. Every removal and addition round 2 consumes is already an unmatched")
    print("observation before classification runs, so what a relocation has to rebuild is")
    print("the NodeDiff representation, not the population.")


if __name__ == "__main__":
    main()
