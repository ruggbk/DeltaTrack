"""x04 -- audit the freeze and the execution gate. Exit non-zero if execution is forbidden.

PRE-REGISTRATION.md, "Execution gate".

TWO GATES, REPORTED SEPARATELY, because conflating them let this script print
"EXECUTION GATE OPEN" while the protocol's own gate listed two unmet prerequisites it
never checked. Freeze integrity is about whether the protocol and population are honestly
frozen; execution readiness is about whether the machinery the protocol requires exists.
Both must hold before anything may be scored.

FREEZE INTEGRITY
  F1  membership exists, is committed, and records a SHA-256 for every file
  F2  every file on disk still hashes to its recorded SHA-256
  F3  no member appears in any contamination class, or in the design-exposure list
  F4  the pre-registration's LAST-MODIFYING commit is an ancestor of the membership
      commit. First-commit is not enough: it proves only that SOME version of the
      protocol predated the population, which is exactly the hole the external review
      found -- the protocol was materially amended after selection.
  F5  nothing that would count as a confirmatory score exists yet
  F6  the answer key, if it exists, was committed BEFORE the adjudication, by git order

EXECUTION READINESS
  G1  the corrected extended-glyph adapter and reconstructor exist and are committed
  G2  their X2-a / X2-b assertion evidence exists, is committed, and PASSES -- recorded
      on DEVELOPMENT documents, never on the holdout
  G3  the adjudicator prompt exists and is committed
  G4  the design-exposure list exists and is non-empty

--self-test drives every gate that has a constructible known-bad case and requires each
to fail, because a gate that has never produced a negative cannot tell "ready" from
"blind".
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[4]

MEMBERSHIP = EV / "results" / "holdout_membership.json"
CONTAM = EV / "results" / "contamination.json"
EXPOSURE = EV / "results" / "design_exposure.json"
PREREG = EV / "PRE-REGISTRATION.md"
DOCS_DIR = EV / "holdout"
KEY = EV / "results" / "oracle_key.json"
ADJ = EV / "results" / "oracle_adjudicated.json"
SCORES = EV / "results" / "scores.json"

# Execution prerequisites named by PRE-REGISTRATION.md's execution gate.
ADAPTER = EV / "probes" / "pdfium_extended_corrected.py"
RECONSTRUCTOR = EV / "probes" / "reconstruct_extended_corrected.py"
X2_EVIDENCE = EV / "results" / "x2_contract_assertions.json"
ADJUDICATOR_PROMPT = EV / "probes" / "adjudicator_prompt.md"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()


def committed(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(git("ls-files", "--error-unmatch", str(path.relative_to(REPO))))


def first_commit(path: Path) -> str:
    out = git("log", "--reverse", "--format=%H", "--", str(path.relative_to(REPO)))
    return out.splitlines()[0] if out else ""


def last_commit(path: Path) -> str:
    return git("log", "-1", "--format=%H", "--", str(path.relative_to(REPO)))


def is_ancestor(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    r = subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=REPO, capture_output=True, check=False)
    return r.returncode == 0


def f4_ok(protocol_commit: str, population_commit: str) -> bool:
    """F4's predicate: the protocol must be committed STRICTLY before the population.

    Strictly, because a commit is its own ancestor -- so without the inequality a protocol
    amended in the population's own commit would pass, which is exactly how a materially
    revised protocol was once reported as having predated its own holdout.
    """
    return (
        bool(protocol_commit)
        and bool(population_commit)
        and protocol_commit != population_commit
        and is_ancestor(protocol_commit, population_commit)
    )


def exposure_ids(contam: dict, exposure: dict) -> dict[str, set[str]]:
    """Every id a frozen member must not be. Keyed by class so a hit names its class."""
    out: dict[str, set[str]] = {}
    for name, block in contam.get("classes", {}).items():
        if name == "xml_only_not_excluded":
            continue  # recorded, deliberately not excluded (PRE-REGISTRATION 4.3)
        out[name] = set(block.get("bills", [])) | {r.upper() for r in block.get("reports", [])}
    ids = set(exposure.get("design_exposed", []))
    out["design_exposed"] = ids | {i.upper() for i in ids}
    return out


def contaminated(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, str]]:
    hits = []
    for m in members:
        mid = m["id"]
        for name, ids in lookup.items():
            if mid in ids or mid.upper() in ids:
                hits.append((mid, name))
    return hits


def check_freeze(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    n_files = sum(len(m["files"]) for m in members)
    results.append(
        (
            "F1 membership exists, committed, every file hashed",
            bool(members)
            and committed(MEMBERSHIP)
            and not [f for m in members for f in m["files"] if not f.get("sha256")],
            f"{len(members)} members, {n_files} files, committed={committed(MEMBERSHIP)}"
            if members
            else "holdout_membership.json not written",
        )
    )

    # F2/F3 are assertions OVER the members. With no members they hold vacuously, and a
    # vacuous pass is indistinguishable from a real one.
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

    hits = contaminated(members, lookup)
    results.append(
        (
            "F3 no member is contaminated or design-exposed",
            bool(members) and not hits,
            "; ".join(f"{i} in {c}" for i, c in hits)
            or (f"{len(members)} members clean" if members else "VACUOUS -- no members to check"),
        )
    )

    # F4 -- the LAST-modifying commit of the protocol, not the first.
    #
    # And the LAST-modifying commit of the membership, not its first: the design-era
    # population was withdrawn and a confirmatory one written to the same path, so
    # `git log --reverse` on that path still reports the DESIGN commit. Comparing against
    # it would judge the current protocol against a population that no longer exists --
    # and it read FAIL for exactly that reason before this was fixed.
    pl, pf = last_commit(PREREG), first_commit(PREREG)
    mc = last_commit(MEMBERSHIP) if MEMBERSHIP.exists() else ""
    results.append(
        (
            "F4 FINAL protocol committed before the population",
            f4_ok(pl, mc),
            f"prereg last={pl[:8] or 'UNCOMMITTED'} (first={pf[:8] or '-'}) membership={mc[:8] or 'UNCOMMITTED'}",
        )
    )

    results.append(("F5 no confirmatory score exists yet", not SCORES.exists(), str(SCORES.exists())))

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
    return results


def check_execution() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    have_adapter = committed(ADAPTER) and committed(RECONSTRUCTOR)
    results.append(
        (
            "G1 corrected extended-glyph adapter committed",
            have_adapter,
            f"adapter={committed(ADAPTER)} reconstructor={committed(RECONSTRUCTOR)}",
        )
    )

    # G2 -- the X2 assertions must have RUN and PASSED, on development documents.
    ok, detail = False, "x2_contract_assertions.json not written"
    if X2_EVIDENCE.exists():
        try:
            ev = json.loads(X2_EVIDENCE.read_text())
            a, b = ev.get("X2a_no_u0020"), ev.get("X2b_rule_recovers_engine_spaces")
            pop = ev.get("population", "")
            ndocs = ev.get("documents_checked", 0)
            ok = bool(a) and bool(b) and pop == "DEVELOPMENT" and ndocs > 0 and committed(X2_EVIDENCE)
            detail = f"X2a={a} X2b={b} population={pop!r} docs={ndocs} committed={committed(X2_EVIDENCE)}"
        except (json.JSONDecodeError, AttributeError) as exc:
            detail = f"unreadable: {exc}"
    results.append(("G2 X2-a / X2-b assertions recorded and passing", ok, detail))

    results.append(
        (
            "G3 adjudicator prompt committed",
            committed(ADJUDICATOR_PROMPT),
            str(ADJUDICATOR_PROMPT.relative_to(EV)) if committed(ADJUDICATOR_PROMPT) else "not committed",
        )
    )

    n = 0
    if EXPOSURE.exists():
        n = len(json.loads(EXPOSURE.read_text()).get("design_exposed", []))
    results.append(
        ("G4 design-exposure list present and non-empty", bool(n) and committed(EXPOSURE), f"{n} design-exposed ids")
    )
    return results


def render(title: str, results: list[tuple[str, bool, str]]) -> list[str]:
    width = max(len(n) for n, _, _ in results)
    print(f"\n== {title} ==")
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")
    return [n for n, ok, _ in results if not ok]


def self_test(contam: dict, exposure: dict) -> int:
    """Every gate with a constructible known-bad case must fail on it."""
    checks: list[tuple[str, bool]] = []
    lookup = exposure_ids(contam, exposure)

    poisoned = [{"id": contam["excluded_bills"][0], "kind": "bill", "files": []}]
    checks.append(("F3 detects a contaminated member", bool(contaminated(poisoned, lookup))))

    exposed = [{"id": exposure["design_exposed"][0], "kind": "bill", "files": []}]
    hits = contaminated(exposed, lookup)
    checks.append(("F3 detects a design-exposed member", any(c == "design_exposed" for _, c in hits)))

    checks.append(
        (
            "F2/F3 refuse to pass vacuously on an empty member list",
            not any(ok for _, ok, _ in check_freeze([], lookup)[1:3]),
        )
    )

    # F4's predicate, driven directly with real commits from this repository.
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD~1")
    checks.append(("F4 accepts a strict-ancestor protocol", f4_ok(parent, head)))
    checks.append(("F4 rejects a protocol amended in the population's OWN commit", not f4_ok(head, head)))
    checks.append(("F4 rejects a protocol committed AFTER the population", not f4_ok(head, parent)))
    checks.append(("F4 rejects an uncommitted protocol", not f4_ok("", head)))

    # G2 must reject evidence that passed on the HOLDOUT rather than on development.
    saved = X2_EVIDENCE.read_text() if X2_EVIDENCE.exists() else None
    try:
        X2_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        X2_EVIDENCE.write_text(
            json.dumps(
                {
                    "X2a_no_u0020": True,
                    "X2b_rule_recovers_engine_spaces": True,
                    "population": "HOLDOUT",
                    "documents_checked": 5,
                }
            )
        )
        g2 = dict((n, ok) for n, ok, _ in check_execution())
        checks.append(
            ("G2 rejects assertions recorded on the HOLDOUT", not g2["G2 X2-a / X2-b assertions recorded and passing"])
        )
    finally:
        if saved is None:
            X2_EVIDENCE.unlink(missing_ok=True)
        else:
            X2_EVIDENCE.write_text(saved)

    width = max(len(n) for n, _ in checks)
    print("== SELF-TEST: every gate must fail on its known-bad case ==")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}")
    bad = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} gates demonstrably able to fail")
    if bad:
        print("SELF-TEST FAIL: " + "; ".join(bad))
        return 1
    print("SELF-TEST PASS")
    return 0


def main(argv: list[str]) -> int:
    if not CONTAM.exists() or not EXPOSURE.exists():
        print("FATAL: run x01_contamination.py and x05_design_exposure.py first.")
        return 2
    contam = json.loads(CONTAM.read_text())
    exposure = json.loads(EXPOSURE.read_text())

    if "--self-test" in argv:
        return self_test(contam, exposure)

    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    lookup = exposure_ids(contam, exposure)

    freeze_failed = render("FREEZE INTEGRITY", check_freeze(members, lookup))
    exec_failed = render("EXECUTION READINESS", check_execution())

    print()
    print(f"FREEZE INTEGRITY:    {'COMPLETE' if not freeze_failed else 'INCOMPLETE -- ' + '; '.join(freeze_failed)}")
    print(f"EXECUTION READINESS: {'OPEN' if not exec_failed else 'CLOSED -- ' + '; '.join(exec_failed)}")
    print()
    if freeze_failed or exec_failed:
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    print("EXECUTION PERMITTED.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
