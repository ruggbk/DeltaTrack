"""Assign candidates to reviewers: disjoint shards for throughput + a stratified overlap set
for inter-annotator agreement (protocol §6/§8, multi-reviewer extension).

Team labeling (3-4 CivicTech reviewers, possibly one). Each candidate is assigned to one or
more reviewers:
  - overlap set: a small stratified subset assigned to EVERY reviewer, so we can measure real
    agreement (kappa) where it is hardest, instead of over-relying on one reviewer.
  - disjoint remainder: round-robin across reviewers (deterministic by id hash) for throughput.

Only NEW (unassigned) candidate ids are assigned, and existing assignments are preserved, so
re-running after miners add examples never reshuffles work already handed out. With one
reviewer the overlap is skipped (no agreement possible) and everything goes to them.

Run (reviewers as args; default ["will"]):
    PYTHONPATH=docs/research/provision-matching/probes .venv/bin/python \
        docs/research/provision-matching/probes/make_assignments.py will alice bob
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).parent
_WORKLIST = _HERE / "worklist.json"
_OUT = _HERE / "assignments.json"
OVERLAP_TARGET = 24  # shared items (stratified) when >=2 reviewers


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


def main() -> None:
    reviewers = sys.argv[1:] or ["will"]
    reviewers = sorted(dict.fromkeys(reviewers))  # de-dup, stable
    entries = json.loads(_WORKLIST.read_text(encoding="utf-8"))["entries"]

    prev, prev_reviewers = {}, None
    if _OUT.exists():
        prev_doc = json.loads(_OUT.read_text(encoding="utf-8"))
        prev = prev_doc.get("assignments", {})
        prev_reviewers = prev_doc.get("reviewers")

    # The reviewer set is FIXED at first run: the disjoint partition + overlap set were handed out for
    # that set, so silently changing it strands new reviewers (0 work, no agreement set) or orphans
    # handed-out work. Only miner-ADDS are incremental. Refuse a changed set loudly.
    if prev_reviewers is not None and sorted(prev_reviewers) != reviewers:
        sys.exit(
            f"reviewer set changed: assignments.json was built for {sorted(prev_reviewers)}, requested "
            f"{reviewers}. Work is already handed out for the old set — to re-partition, delete "
            f"assignments.json and re-run (loses in-progress assignments); else re-run the original set."
        )

    # group unassigned ids by stratum (deterministic order by id hash)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    strata_of = {}
    for e in entries:
        strata_of[e["id"]] = e["stratum"]
        if e["id"] not in prev:
            by_stratum[e["stratum"]].append(e["id"])
    for s in by_stratum:
        by_stratum[s].sort(key=_h)

    assignments = dict(prev)
    overlap_ids: list[str] = []
    if len(reviewers) >= 2:
        # stratified overlap, but count overlap ALREADY handed out toward the target so re-runs after
        # miner-adds don't balloon the shared agreement set past OVERLAP_TARGET.
        existing_overlap = sum(1 for a in prev.values() if a.get("overlap"))
        budget = max(0, OVERLAP_TARGET - existing_overlap)
        total_new = sum(len(v) for v in by_stratum.values()) or 1
        for s, ids in by_stratum.items():
            if budget <= 0 or not ids:
                continue
            take = min(len(ids), budget, max(1, round(OVERLAP_TARGET * len(ids) / total_new)))
            overlap_ids += ids[:take]
            budget -= take
        for cid in overlap_ids:
            assignments[cid] = {"reviewers": list(reviewers), "overlap": True, "stratum": strata_of[cid]}
    overlap = set(overlap_ids)

    # disjoint remainder: POSITIONAL round-robin over the hash-sorted ids (stable order,
    # but evenly balanced — hash-bucket assignment left one reviewer ~25% heavier). The
    # counter carries across strata so each reviewer gets a balanced mix of all strata.
    rr = 0
    for s, ids in by_stratum.items():
        for cid in ids:
            if cid in overlap:
                continue
            who = reviewers[rr % len(reviewers)]
            assignments[cid] = {"reviewers": [who], "overlap": False, "stratum": strata_of[cid]}
            rr += 1

    # report load per reviewer
    load: dict[str, int] = defaultdict(int)
    for a in assignments.values():
        for r in a["reviewers"]:
            load[r] += 1
    total_overlap = sum(1 for a in assignments.values() if a.get("overlap"))
    idle = [r for r in reviewers if load.get(r, 0) == 0]
    _OUT.write_text(
        json.dumps(
            {
                "_about": "Reviewer assignments for Pass 2 labeling. overlap=True items are labeled by "
                "all reviewers (agreement set); others are disjoint. The reviewer set is fixed at first "
                "run; only new ids are added on re-run, and the overlap set is capped at overlap_target.",
                "reviewers": reviewers,
                "overlap_target": OVERLAP_TARGET if len(reviewers) >= 2 else 0,
                "n_overlap": total_overlap,
                "load_per_reviewer": dict(load),
                "assignments": assignments,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"reviewers: {reviewers}  overlap: {total_overlap}  total assigned: {len(assignments)}")
    print(f"load per reviewer: {dict(load)}")
    if idle:
        print(
            f"!! WARNING: {idle} received 0 items — all ids may already be assigned; add candidates "
            "or delete assignments.json to re-partition for the current reviewer set."
        )


if __name__ == "__main__":
    main()
