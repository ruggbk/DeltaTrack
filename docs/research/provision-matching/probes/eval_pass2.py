"""Skeletal evaluator for the Pass 2 anchor dataset -- the executable form of the data contract.

`pass2-protocol.md` §2.4 promised this file and it did not exist. The 2026-08 review listed it as
non-blocking on the reasoning that metrics are needed after labeling, not before. The second review
challenged that, and the challenge holds: the risk is not that the metrics are late, it is that the
SCHEMA cannot produce them, and the only way to find out is to compute them. So this exists now, in
skeletal form, and runs against a synthetic fixture covering every shape the design has to handle.

What "skeletal" means here: every promised metric is computed, and the population each is computed
over is enforced. What is deliberately absent: confidence intervals, per-stratum breakdowns,
inter-rater agreement, held-out execution, and report formatting. Those are reporting concerns and
can follow the labels. The contract cannot.

THE FIVE TARGETS, and the population each is honestly computable over:

  1 candidate recall   did the true counterpart enter the candidate set?
                       ONLY over anchors whose truth came from an independent oracle. An anchor
                       labeled from the suggestion list cannot contribute: for it, "not retrieved"
                       and "does not exist" are the same observation. This exclusion is the whole
                       point -- see `pass2_schema`.
  2 ranking            was the true counterpart ranked first? (top-1, MRR)
                       Over anchors with exactly one true counterpart THAT IS IN the candidate set.
                       Scoring a retrieval miss as a ranking miss double-counts one failure.
  3 assignment         did the global matching resolve competition correctly?
                       Over anchors in a collision group -- two or more anchors whose truth or
                       candidates contend for the same new-version node.
  4 diff correctness   did the staffer see the right modified/moved/removed?
                       Over every anchor: a confusion matrix of system vs truth change_type.
  5 failure modes      does mode X occur, and how badly?
                       Over challenge strata only, reported as a rate with its stratum named, and
                       never as a precision -- the base rate is rigged by construction.

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

from pass2_schema import INDEPENDENT_ORACLES, validate_dataset  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "eval_contract_synthetic.json"

#: Relations that assert a counterpart exists. `uncertain` is excluded from every metric that
#: needs a right answer, and counted separately, so it can never be silently read as `none`.
POSITIVE = ("one-to-one", "one-to-many", "many-to-one")


def _key(ref: dict) -> tuple:
    """Node identity for comparing truth against candidates and against the system's output.

    Keyed on the normalized-body hash, not on `match_path`. The path is the thing that legitimately
    changes across versions -- it is the unstable key this whole research program exists because of
    -- so joining on it would make the evaluator fail exactly where the matcher is hardest.
    """
    return (ref["bill"], ref["version"], ref["text_sha256"])


def candidate_recall(records: list[dict]) -> dict:
    """Target 1. Enforced population: independent oracle + a counterpart that exists."""
    eligible = [
        r for r in records if r["truth"]["oracle"] in INDEPENDENT_ORACLES and r["truth"]["relation"] in POSITIVE
    ]
    excluded = [
        r["anchor_id"]
        for r in records
        if r["truth"]["oracle"] not in INDEPENDENT_ORACLES and r["truth"]["relation"] in POSITIVE
    ]
    found = total = 0
    full_anchor = 0
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
        "anchors_excluded_circular": excluded,
        "misses": missed,
    }


def ranking(records: list[dict]) -> dict:
    """Target 2. Over one-to-one anchors whose counterpart the retrievers DID surface."""
    top1 = 0
    rr = 0.0
    n = 0
    for r in records:
        t = r["truth"]
        if t["relation"] != "one-to-one":
            continue
        target = _key(t["counterparts"][0])
        ranked = sorted(r["candidates"], key=lambda c: c["rank"])
        keys = [_key(c) for c in ranked]
        if target not in keys:
            continue  # a retrieval miss, already counted in target 1
        n += 1
        pos = keys.index(target) + 1
        top1 += pos == 1
        rr += 1.0 / pos
    return {"n": n, "top1": _rate(top1, n), "mrr": (rr / n) if n else None}


def assignment(records: list[dict]) -> dict:
    """Target 3. Over anchors that COMPETE: two or more anchors contending for one new node.

    Collision groups are derived, not annotated. A human ruling one anchor at a time cannot see
    that two anchors claim the same target, so asking them to record it would be asking for
    something they are not positioned to know.
    """
    claims: dict[tuple, list[str]] = {}
    for r in records:
        for cp in r["truth"]["counterparts"]:
            claims.setdefault(_key(cp), []).append(r["anchor_id"])
        for c in r["candidates"]:
            claims.setdefault(_key(c), []).append(r["anchor_id"])
    contended = {k for k, v in claims.items() if len(set(v)) > 1}

    in_collision = [
        r
        for r in records
        if any(_key(c) in contended for c in r["candidates"])
        or any(_key(cp) in contended for cp in r["truth"]["counterparts"])
    ]
    correct = 0
    wrong = []
    for r in in_collision:
        truth_set = {_key(cp) for cp in r["truth"]["counterparts"]}
        sys_set = {_key(a) for a in r["system"]["assigned"]}
        if truth_set == sys_set:
            correct += 1
        else:
            wrong.append(r["anchor_id"])
    return {
        "collision_groups": len(contended),
        "anchors_in_collision": len(in_collision),
        "accuracy": _rate(correct, len(in_collision)),
        "wrong": wrong,
    }


def diff_correctness(records: list[dict]) -> dict:
    """Target 4. The staffer-visible outcome: a confusion matrix over every anchor."""
    matrix: Counter[tuple[str, str]] = Counter()
    for r in records:
        matrix[(r["truth"]["change_type"], r["system"]["change_type"])] += 1
    correct = sum(v for (t, s), v in matrix.items() if t == s)
    total = sum(matrix.values())
    return {
        "accuracy": _rate(correct, total),
        "n": total,
        "matrix": {f"truth={t} -> system={s}": v for (t, s), v in sorted(matrix.items())},
    }


def failure_modes(records: list[dict]) -> dict:
    """Target 5. Challenge strata only. A RATE within a rigged population, never a precision."""
    out: dict[str, dict] = {}
    for r in records:
        stratum = r.get("stratum")
        if not stratum or not r.get("is_challenge"):
            continue
        b = out.setdefault(stratum, {"n": 0, "mode_occurred": 0})
        b["n"] += 1
        truth_set = {_key(cp) for cp in r["truth"]["counterparts"]}
        sys_set = {_key(a) for a in r["system"]["assigned"]}
        b["mode_occurred"] += truth_set != sys_set
    for b in out.values():
        b["rate"] = _rate(b["mode_occurred"], b["n"])
        b["NOT_a_precision"] = "base rate is rigged by construction (protocol §7)"
    return out


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
        "failure_modes": failure_modes(scored),
    }


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE
    records = json.loads(path.read_text())["records"]
    print(f"dataset: {path}")
    result = evaluate(records)
    print(json.dumps(result, indent=2))

    cr = result["candidate_recall"]
    print()
    print("=" * 96)
    print("CONTRACT CHECK -- can this dataset answer the five questions?")
    print("=" * 96)
    ok = {
        "1 candidate recall": cr["counterparts_total"] > 0,
        "2 ranking / MRR": result["ranking"]["n"] > 0,
        "3 assignment accuracy": result["assignment"]["anchors_in_collision"] > 0,
        "4 final diff correctness": result["diff_correctness"]["n"] > 0,
        "5 failure-mode rates": bool(result["failure_modes"]),
    }
    for k, v in ok.items():
        print(f"  {k:<28} {'YES' if v else 'NO -- schema cannot support it'}")
    if cr["anchors_excluded_circular"]:
        print()
        print("  EXCLUDED FROM CANDIDATE RECALL (truth came from the suggestion list, so the")
        print("  candidate generator would be defining its own denominator):")
        for a in cr["anchors_excluded_circular"]:
            print(f"    {a}")
    print()
    print("  Answering the gate question -- if labels are collected exactly as designed, can we")
    print(f"  later compute all five without matcher-conditioned truth? {'YES' if all(ok.values()) else 'NO'}")


if __name__ == "__main__":
    main()
