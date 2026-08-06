"""x04 -- audit the freeze invariants. Exit non-zero if the study may not proceed.

PRE-REGISTRATION.md, "Execution gate". Every property below is one a reviewer would
otherwise have to take on trust, and each has a known-bad case so a green run means the
check ran rather than that it could not fail.

  F1  membership exists, is committed, and records a SHA-256 for every file
  F2  every file on disk still hashes to its recorded SHA-256
  F3  NO member appears in ANY contamination class -- the freshness gate
  F4  the pre-registration is committed, and its commit is an ancestor of (or equal to)
      the membership commit, so the protocol was frozen no later than the population
  F5  nothing that would count as a confirmatory score exists yet
  F6  the answer key, if it exists, was committed BEFORE the adjudication -- checked by
      git log order, never by file mtime

Run with --self-test to prove F3 can fail: it re-runs the freshness gate against a member
list deliberately seeded with a known-contaminated bill and requires a FAIL.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[3]

MEMBERSHIP = EV / "results" / "holdout_membership.json"
CONTAM = EV / "results" / "contamination.json"
PREREG = EV / "PRE-REGISTRATION.md"
DOCS_DIR = EV / "holdout"
KEY = EV / "results" / "oracle_key.json"
ADJ = EV / "results" / "oracle_adjudicated.json"
SCORES = EV / "results" / "scores.json"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()


def committed(path: Path) -> bool:
    rel = path.relative_to(REPO)
    return bool(git("ls-files", "--error-unmatch", str(rel)))


def first_commit(path: Path) -> str:
    rel = path.relative_to(REPO)
    out = git("log", "--reverse", "--format=%H", "--", str(rel))
    return out.splitlines()[0] if out else ""


def is_ancestor(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    r = subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=REPO, capture_output=True, check=False)
    return r.returncode == 0


def contaminated(members: list[dict], contam: dict) -> list[tuple[str, str]]:
    """Members appearing in ANY exposure class. This is the gate F3 enforces, factored
    out so --self-test can drive it with a known-bad input."""
    classes = contam["classes"]
    lookup: dict[str, set[str]] = {}
    for name, block in classes.items():
        ids = set(block.get("bills", [])) | {r.upper() for r in block.get("reports", [])}
        if name == "xml_only_not_excluded":
            continue  # recorded, deliberately not excluded (PRE-REGISTRATION 4.3)
        lookup[name] = ids
    hits = []
    for m in members:
        mid = m["id"].upper() if m.get("kind") == "report" else m["id"]
        for name, ids in lookup.items():
            if mid in ids or m["id"] in ids:
                hits.append((m["id"], name))
    return hits


def main(argv: list[str]) -> int:
    if not CONTAM.exists():
        print("FATAL: contamination.json missing; run x01 first.")
        return 2
    contam = json.loads(CONTAM.read_text())

    if "--self-test" in argv:
        # Known-bad case for F3. A gate that has never produced a positive result cannot
        # distinguish "clean" from "broken".
        poisoned = [{"id": contam["excluded_bills"][0], "kind": "bill"}]
        hits = contaminated(poisoned, contam)
        ok = bool(hits)
        print(f"F3 self-test: seeded {poisoned[0]['id']} -> {'DETECTED' if ok else 'MISSED'} {hits}")
        print("SELF-TEST PASS" if ok else "SELF-TEST FAIL -- the freshness gate cannot fire")
        return 0 if ok else 1

    results: list[tuple[str, bool, str]] = []

    # F1
    if not MEMBERSHIP.exists():
        results.append(("F1 membership exists", False, "holdout_membership.json not written"))
        members = []
    else:
        doc = json.loads(MEMBERSHIP.read_text())
        members = doc.get("members", [])
        missing = [f["path"] for m in members for f in m["files"] if not f.get("sha256")]
        results.append(
            (
                "F1 membership exists, committed, every file hashed",
                bool(members) and not missing and committed(MEMBERSHIP),
                f"{len(members)} members, {sum(len(m['files']) for m in members)} files, "
                f"{len(missing)} unhashed, committed={committed(MEMBERSHIP) if MEMBERSHIP.exists() else False}",
            )
        )

    # F2
    # F2 and F3 are ASSERTIONS OVER THE MEMBERS. With no members they are satisfied
    # vacuously, and a vacuous pass is indistinguishable from a real one -- which is the
    # failure mode this whole study exists to avoid. They report VACUOUS and do not hold.
    n_files = sum(len(m["files"]) for m in members)
    bad = []
    for m in members:
        for f in m["files"]:
            p = DOCS_DIR / f["path"]
            if not p.exists():
                bad.append(f"{f['path']}: absent")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                bad.append(f"{f['path']}: hash mismatch")
    results.append(
        (
            "F2 every holdout file matches its recorded SHA-256",
            bool(n_files) and not bad,
            "; ".join(bad) or (f"{n_files} files match" if n_files else "VACUOUS -- no files to check"),
        )
    )

    # F3
    hits = contaminated(members, contam)
    results.append(
        (
            "F3 no member appears in any contamination class",
            bool(members) and not hits,
            "; ".join(f"{i} in {c}" for i, c in hits)
            or (f"{len(members)} members clean" if members else "VACUOUS -- no members to check"),
        )
    )

    # F4
    pc, mc = first_commit(PREREG), first_commit(MEMBERSHIP) if MEMBERSHIP.exists() else ""
    results.append(
        (
            "F4 pre-registration committed no later than membership",
            bool(pc) and (not mc or is_ancestor(pc, mc)),
            f"prereg={pc[:8] or 'UNCOMMITTED'} membership={mc[:8] or 'UNCOMMITTED'}",
        )
    )

    # F5
    results.append(("F5 no confirmatory score exists yet", not SCORES.exists(), str(SCORES.exists())))

    # F6
    if KEY.exists() and ADJ.exists():
        kc, ac = first_commit(KEY), first_commit(ADJ)
        results.append(
            (
                "F6 answer key committed before adjudication",
                bool(kc) and bool(ac) and is_ancestor(kc, ac) and kc != ac,
                f"key={kc[:8] or 'UNCOMMITTED'} adjudication={ac[:8] or 'UNCOMMITTED'}",
            )
        )
    else:
        results.append(("F6 answer key ordering", True, "not applicable yet -- adjudication has not run"))

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} invariants hold")
    if failed:
        print("EXECUTION GATE CLOSED: " + "; ".join(failed))
        return 1
    print("EXECUTION GATE OPEN")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
