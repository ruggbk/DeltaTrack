"""Skeletal evaluator for the Pass 2 anchor dataset -- the executable form of the data contract.

`pass2-protocol.md` §2.4 promised this file and it did not exist. Round 1 listed it as non-blocking
on the reasoning that metrics are needed after labeling, not before. Round 2's challenge to that
holds: the risk is not that the metrics are late, it is that the SCHEMA cannot produce them, and
the only way to find out is to compute them.

Round 3 then found that computing them is not the same as computing them VALIDLY. v1 of this file
printed YES for all five targets while three of the five were consuming truth that could not
support their arithmetic. So the design changed from "compute each metric over the records" to
"compute each metric over the records whose oracle can establish the proposition that metric
assumes, and say out loud which records were refused and why".

What "skeletal" still means: every promised metric is computed and its population is enforced.
Deliberately absent: confidence intervals, per-stratum breakdowns, inter-rater agreement, held-out
execution, weighting, and report formatting. Those are reporting concerns and can follow the labels.
The contract cannot.

THE FIVE TARGETS and the truth each one needs. The requirement is DATA, in
`pass2_schema.METRIC_TRUTH_REQUIREMENTS`, not prose here -- so that enforcement is testable and a
future metric cannot be added without declaring what it assumes.

  1 candidate recall   needs `complete-in-document`. The denominator is "counterparts that exist",
                       and an oracle that searched one region cannot enumerate it. Note the bias
                       runs by SELECTION rather than by a wrong label: an anchor whose counterpart
                       was never findable is dropped from the population, and those are exactly the
                       anchors retrieval failed on, so an incomplete oracle inflates recall.
  2 ranking            needs `affirmed-positive` only. Where the true counterpart ranked does not
                       depend on whether a second one exists elsewhere. This is the one target the
                       cheap oracle genuinely supports.
  3 assignment         needs `complete-in-document`, for every anchor in the collision group. An
                       unfound competitor makes a wrong assignment look right.
  4 diff correctness   needs `complete-in-document`. `removed` vs `moved` IS the question of whether
                       a counterpart exists elsewhere in the document.
  5 failure modes      per stratum: an existence claim needs a positive, an absence claim needs
                       completeness. The stratum declares it in `challenge_requires`.

Run (no corpus needed; defaults to the synthetic contract fixture):
    .venv/bin/python docs/research/provision-matching/probes/eval_pass2.py
    .venv/bin/python docs/research/provision-matching/probes/eval_pass2.py path/to/labels.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pass2_schema import (  # noqa: E402
    METRIC_TRUTH_REQUIREMENTS,
    establishes,
    observation_id,
    validate_dataset,
)

FIXTURE = Path(__file__).parent / "fixtures" / "eval_contract_synthetic.json"

#: Relations that assert a counterpart exists. `uncertain` is excluded from every metric that
#: needs a right answer, and counted separately, so it can never be silently read as `none`.
POSITIVE = ("one-to-one", "one-to-many", "many-to-one")


def _key(ref: dict) -> tuple:
    """Node identity for joining truth against candidates and against the system's output.

    `(source_sha256, parser_commit, element_id)` -- an OBSERVATION identity, not a content hash.

    v1 joined on `(bill, version, text_sha256)`. Rejecting `match_path` was right (it is the
    unstable key this program exists because of), but the replacement assumed body text identifies
    a node, and R9 measured that it does not: 33% of documents in this corpus contain at least one
    body shared by two or more provisions, up to 12 copies of one text, reaching every version of
    all four answer-key bills. A content-hash join collapses them, and it fails OPTIMISTICALLY -- a
    recall miss against provision X scores as a hit whenever any boilerplate twin is in the
    candidate set.
    """
    return observation_id(ref)


def _admits(rec: dict, metric: str) -> bool:
    """Can this record's truth support the proposition `metric` assumes?

    `establishes` takes the whole truth block in v3, because `complete-in-document` now depends on
    measured review coverage rather than only on which oracle steps ran.
    """
    need = METRIC_TRUTH_REQUIREMENTS[metric]["requires"]
    if need == "per-stratum":
        need = rec.get("challenge_requires", "affirmed-positive")
    return establishes(rec["truth"], need)


def _partition(records: list[dict], metric: str) -> tuple[list[dict], list[dict]]:
    """(admitted, refused) for one metric. Refusal is reported, never silent."""
    admitted, refused = [], []
    for r in records:
        (admitted if _admits(r, metric) else refused).append(r)
    return admitted, refused


def _refusal_report(refused: list[dict], metric: str) -> dict:
    need = METRIC_TRUTH_REQUIREMENTS[metric]["requires"]
    return {
        "count": len(refused),
        "requires": need,
        "anchors": [
            {"anchor_id": r["anchor_id"], "oracles": r["truth"]["oracles"], "relation": r["truth"]["relation"]}
            for r in refused
        ],
    }


def candidate_recall(records: list[dict]) -> dict:
    """Target 1. Population: truth that can enumerate the counterpart set document-wide."""
    admitted, refused = _partition(records, "candidate_recall")
    eligible = [r for r in admitted if r["truth"]["relation"] in POSITIVE]
    found = total = full_anchor = 0
    missed = []
    for r in eligible:
        cands = {_key(c) for c in r["candidates"]}
        hits = 0
        for cp in r["truth"]["counterparts"]:
            total += 1
            if _key(cp) in cands:
                found += 1
                hits += 1
            else:
                missed.append((r["anchor_id"], cp["found_via"]))
        if hits == len(r["truth"]["counterparts"]):
            full_anchor += 1
    return {
        "counterpart_recall": _rate(found, total),
        "counterparts_found": found,
        "counterparts_total": total,
        "anchors_fully_recalled": _rate(full_anchor, len(eligible)),
        "anchors_eligible": len(eligible),
        "misses": missed,
        "refused": _refusal_report(refused, "candidate_recall"),
    }


def ranking(records: list[dict]) -> dict:
    """Target 2. Over one-to-one anchors whose affirmed counterpart the retrievers DID surface."""
    admitted, refused = _partition(records, "ranking")
    top1 = 0
    rr = 0.0
    n = 0
    for r in admitted:
        t = r["truth"]
        if t["relation"] != "one-to-one":
            continue
        target = _key(t["counterparts"][0])
        keys = [_key(c) for c in sorted(r["candidates"], key=lambda c: c["rank"])]
        if target not in keys:
            continue  # a retrieval miss, already counted in target 1
        n += 1
        pos = keys.index(target) + 1
        top1 += pos == 1
        rr += 1.0 / pos
    return {
        "n": n,
        "top1": _rate(top1, n),
        "mrr": (rr / n) if n else None,
        "refused": _refusal_report(refused, "ranking"),
    }


def assignment(records: list[dict]) -> dict:
    """Target 3. Over anchors that COMPETE: two or more anchors contending for one new node.

    Collision groups are derived, not annotated. A human ruling one anchor at a time cannot see
    that two anchors claim the same target, so asking them to record it would be asking for
    something they are not positioned to know.

    A group is only scorable if EVERY anchor in it has document-complete truth -- an unfound
    competitor makes a wrong assignment look right, so one refused member disqualifies the group
    rather than just itself.
    """
    admitted, refused = _partition(records, "assignment")
    claims: dict[tuple, list[str]] = {}
    for r in records:  # contention is derived over ALL records, including refused ones
        for cp in r["truth"]["counterparts"]:
            claims.setdefault(_key(cp), []).append(r["anchor_id"])
        for c in r["candidates"]:
            claims.setdefault(_key(c), []).append(r["anchor_id"])
    contended = {k for k, v in claims.items() if len(set(v)) > 1}
    refused_ids = {r["anchor_id"] for r in refused}

    def in_group(r: dict) -> bool:
        return any(_key(c) in contended for c in r["candidates"]) or any(
            _key(cp) in contended for cp in r["truth"]["counterparts"]
        )

    groups: dict[tuple, set[str]] = {k: set(v) for k, v in claims.items() if k in contended}
    tainted = {k for k, members in groups.items() if members & refused_ids}

    scorable, disqualified = [], []
    for r in admitted:
        if not in_group(r):
            continue
        keys = {_key(c) for c in r["candidates"]} | {_key(cp) for cp in r["truth"]["counterparts"]}
        (disqualified if keys & tainted else scorable).append(r)

    correct = 0
    wrong = []
    for r in scorable:
        truth_set = {_key(cp) for cp in r["truth"]["counterparts"]}
        sys_set = {_key(a) for a in r["system"]["assigned"]}
        if truth_set == sys_set:
            correct += 1
        else:
            wrong.append(r["anchor_id"])
    return {
        "collision_groups": len(contended),
        "collision_groups_tainted": len(tainted),
        "anchors_in_collision": len(scorable),
        "anchors_disqualified_by_a_group_member": [r["anchor_id"] for r in disqualified],
        "accuracy": _rate(correct, len(scorable)),
        "wrong": wrong,
        "refused": _refusal_report(refused, "assignment"),
    }


def diff_correctness(records: list[dict]) -> dict:
    """Target 4. The staffer-visible outcome: a confusion matrix over document-complete anchors."""
    admitted, refused = _partition(records, "diff_correctness")
    matrix: Counter[tuple[str, str]] = Counter()
    for r in admitted:
        matrix[(r["truth"]["change_type"], r["system"]["change_type"])] += 1
    correct = sum(v for (t, s), v in matrix.items() if t == s)
    total = sum(matrix.values())
    return {
        "accuracy": _rate(correct, total),
        "n": total,
        "matrix": {f"truth={t} -> system={s}": v for (t, s), v in sorted(matrix.items())},
        "refused": _refusal_report(refused, "diff_correctness"),
    }


def _mode_occurred(rec: dict) -> bool:
    """Did the failure this stratum claims actually happen, for this record?

    The test depends on what the stratum is claiming, which is why `challenge_requires` is data.
    v2 applied one test to every stratum -- "does the system's assignment differ from truth's
    counterpart set" -- which is only correct for the completeness strata, and which silently
    required document-wide truth for a claim that is purely pairwise.
    """
    sys_set = {_key(a) for a in rec["system"]["assigned"]}
    if rec.get("challenge_requires") == "affirmed-negative":
        # "the matcher kept a pair a human ruled DIFFERENT". Purely pairwise: it needs the rejected
        # node and the system's output, and nothing about where the anchor's real counterpart is.
        rejected = {_key(x) for x in rec["truth"].get("rejected", [])}
        return bool(sys_set & rejected)
    return {_key(cp) for cp in rec["truth"]["counterparts"]} != sys_set


def failure_modes(records: list[dict]) -> dict:
    """Target 5. Challenge strata only. A RATE within a rigged population, never a precision."""
    out: dict[str, dict] = {}
    refused_all = []
    for r in records:
        stratum = r.get("stratum")
        if not stratum or not r.get("is_challenge"):
            continue
        if not _admits(r, "failure_modes"):
            refused_all.append(r)
            continue
        b = out.setdefault(stratum, {"n": 0, "mode_occurred": 0, "requires": r.get("challenge_requires")})
        b["n"] += 1
        b["mode_occurred"] += _mode_occurred(r)
    for b in out.values():
        b["rate"] = _rate(b["mode_occurred"], b["n"])
        b["NOT_a_precision"] = "base rate is rigged by construction (protocol §7)"
    return {"strata": out, "refused": _refusal_report(refused_all, "failure_modes")}


def _rate(k: int, n: int) -> float | None:
    return (k / n) if n else None


def evaluate(records: list[dict]) -> dict:
    validate_dataset(records)
    uncertain = [r["anchor_id"] for r in records if r["truth"]["relation"] == "uncertain"]
    scored = [r for r in records if r["truth"]["relation"] != "uncertain"]
    return {
        "n_records": len(records),
        "n_uncertain_excluded": len(uncertain),
        "uncertain": uncertain,
        "candidate_recall": candidate_recall(scored),
        "ranking": ranking(scored),
        "assignment": assignment(scored),
        "diff_correctness": diff_correctness(scored),
        # v3: challenge records see EVERY record, `uncertain` included. The blanket exclusion was
        # right for the four metrics that need to know the anchor's counterpart set and wrong here:
        # a pairwise false-keep claim ("this proposed pair is not the same provision") has a
        # definite answer even when nobody has established where the anchor's real counterpart is.
        # Forcing `relation` to something other than `uncertain` in order to be scored would have
        # made the labeler assert a counterpart set they never determined.
        "failure_modes": failure_modes(records),
    }


def contract_check(result: dict) -> dict:
    """Can this dataset answer each question over a population adequate for that question?

    Round 3 raised the bar from "the code produced a number" to this. A metric with an empty
    admitted population reports NO -- which is the honest answer, and the one v1 could not give,
    because v1 computed four of the five over every record regardless of oracle.
    """
    return {
        "1 candidate recall": result["candidate_recall"]["counterparts_total"] > 0,
        "2 ranking / MRR": result["ranking"]["n"] > 0,
        "3 assignment accuracy": result["assignment"]["anchors_in_collision"] > 0,
        "4 final diff correctness": result["diff_correctness"]["n"] > 0,
        "5 failure-mode rates": bool(result["failure_modes"]["strata"]),
    }


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE
    records = json.loads(path.read_text())["records"]
    print(f"dataset: {path}")
    result = evaluate(records)
    print(json.dumps(result, indent=2))

    print()
    print("=" * 96)
    print("CONTRACT CHECK -- can each question be answered over an ADEQUATE population?")
    print("=" * 96)
    ok = contract_check(result)
    for k, v in ok.items():
        print(f"  {k:<28} {'YES' if v else 'NO -- no record has truth adequate for it'}")

    print()
    print("  Records refused per metric (truth cannot support what the metric assumes):")
    for metric in ("candidate_recall", "ranking", "assignment", "diff_correctness", "failure_modes"):
        node = result[metric]["refused"] if metric != "failure_modes" else result[metric]["refused"]
        if node["count"]:
            ids = ", ".join(a["anchor_id"] for a in node["anchors"])
            print(f"    {metric:<20} needs {node['requires']:<22} refused {node['count']}: {ids}")
    print()
    print("  Answering the gate question -- if labels are collected using the frozen sampling and")
    print("  oracle workflow, can every promised metric be computed over a population whose ground")
    print(f"  truth is adequate for that metric? {'YES' if all(ok.values()) else 'NO'}")


if __name__ == "__main__":
    main()
