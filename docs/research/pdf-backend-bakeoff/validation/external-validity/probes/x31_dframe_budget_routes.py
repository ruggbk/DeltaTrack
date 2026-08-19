"""x31 -- A48. The D DECISION route is required only while A27.3's budget allows Rule 1.

NOT CONFIRMATORY. SYNTHETIC populations only; opens no holdout document and no real oracle
image, and writes no canonical artifact.

THE BEHAVIOUR THIS PRESERVES
----------------------------
When the realized complete D-frame region census exceeds A27.3's 60-region budget, Rule 1's
full-D human decision evidence is not required, and its absence must not block C-frame/RQ2
scoring, Rule 0, Rule 3, or the budget-driven architecture outcome. Every route that REMAINS
result-bearing must still be complete and falsifiable.

Measured before the repair: a census of 13,992 made 15,372 human answers a hard prerequisite
for producing any metric at all, for a route A27.3 had already made non-decision-bearing.

THE MUTATIONS THAT MUST BREAK IT
--------------------------------
  * restore unconditional `D_FRAME -> human`  -> the D=61 arm goes RED
  * make D-human globally optional            -> the D<=60 arm goes RED
Both are injected below, into the real functions, not into copies of their output.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
for _p in (str(HERE.parent), str(REPO / "src"), str(BAKE / "probes"), str(BAKE / "probes" / "backends")):
    sys.path.insert(0, _p)

import build_oracle as BO  # noqa: E402
import control_fixtures as CF  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import score_metrics as SM  # noqa: E402
import x21_build_oracle as X21  # noqa: E402
import x27_score_metrics as X27  # noqa: E402

RESULTS = []


def check(name, ok, why, observed=""):
    RESULTS.append({"check": name, "pass": bool(ok), "expected": why, "observed": str(observed)[:200]})


def build(n_d, n_c, tmp):
    """A real BO.build over a synthetic population with a chosen D census."""
    mem = [(True, False)] * n_c + [(False, True)] * n_d
    docs = X21.synthetic_documents(tmp, n_pages=len(mem), memberships=mem)
    controls = BO.control_specs(json.loads(CF.MANIFEST_PATH.read_text()), EV, REPO)
    return BO.build(docs, controls=controls).key


def refuses(fn):
    try:
        fn()
        return False, "ACCEPTED"
    except Exception as exc:  # noqa: BLE001
        return True, f"{type(exc).__name__}: {str(exc)[:120]}"


def drop(adj, route, bid):
    out = {"schema": adj["schema"], BO.ROUTE_AI: dict(adj[BO.ROUTE_AI]), BO.ROUTE_HUMAN: dict(adj[BO.ROUTE_HUMAN])}
    out[route].pop(bid, None)
    return out


def full_path(key, adj):
    """The REAL validation + R1 path a scorer runs, and the only thing these arms assert on."""
    BO.validate_adjudicated(adj, key)
    return SM.r1_reliability(key, adj)


def mangle_route_text(key, adj, route):
    """Force R1 disagreement on `route` by changing every REPEAT's transcription."""
    out = {"schema": adj["schema"], BO.ROUTE_AI: dict(adj[BO.ROUTE_AI]), BO.ROUTE_HUMAN: dict(adj[BO.ROUTE_HUMAN])}
    for bid, ans in list(out[route].items()):
        if not key["stimuli"].get(bid, {}).get("is_r1_repeat"):
            continue
        headings = [{**h, "text": (h.get("text") or "") + " XX"} for h in ans.get("headings", [])]
        out[route][bid] = {**ans, "headings": headings}
    return out


def a48_minimal(key, adj):
    """Drop human answers whose ONLY purpose was the (now non-required) Rule-1 D decision."""
    keep = {}
    for bid, ans in adj[BO.ROUTE_HUMAN].items():
        purposes = set(key["stimuli"][bid].get("human_answer_purposes") or ())
        if purposes and purposes != {"d_decision"}:
            keep[bid] = ans
    return {"schema": adj["schema"], BO.ROUTE_AI: dict(adj[BO.ROUTE_AI]), BO.ROUTE_HUMAN: keep}


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        over, under = build(61, 30, tmp), build(60, 30, tmp)

        check("premise: D=61 is over budget, D=60 is within it",
              over["d_frame_census"] == 61 and not over["d_decision_route_required"]
              and under["d_frame_census"] == 60 and under["d_decision_route_required"],
              "the realized census drives the predicate",
              f"61->{over['d_decision_route_required']} 60->{under['d_decision_route_required']}")

        full_over, full_under = X27.synthesize_adjudication(over), X27.synthesize_adjudication(under)

        # ---- A: D-only human answers absent must NOT fail anything -------------------
        minimal = a48_minimal(over, full_over)
        ok, obs = refuses(lambda: full_path(over, minimal))
        check("A D=61: absent D-only human answers do NOT fail the real path",
              not ok, "A27.3 made that route non-decision-bearing, so its absence blocks nothing", obs)
        check("A ...and no D-only stimulus claims the human route",
              all(BO.ROUTE_HUMAN not in r["adjudication_routes"]
                  for r in over["stimuli"].values()
                  if r["in_d_frame"] and not r["in_c_frame"] and not r["is_c_audit_selected"]
                  and r["control_kind"] is None),
              "a non-required route is ABSENT, not NOT_EVALUABLE", "")
        r1 = full_path(over, minimal)
        check("A ...and R1's required-route population is AI only",
              sorted(r1["per_route"]) == [BO.ROUTE_AI],
              "no human R1 arm is created by D membership alone", sorted(r1["per_route"]))

        # ---- B: a required AI answer is still mandatory -------------------------------
        ai_repeat = next(b for b, r in over["stimuli"].items()
                         if r["is_r1_repeat"] and BO.ROUTE_AI in r["adjudication_routes"])
        ok, obs = refuses(lambda: full_path(over, drop(minimal, BO.ROUTE_AI, ai_repeat)))
        check("B D=61: a C-bearing R1 pair missing its AI answer REFUSES", ok,
              "the AI route stays result-bearing and complete", obs)

        # ---- C: AI reliability below threshold must FAIL ------------------------------
        r1_bad = SM.r1_reliability(over, mangle_route_text(over, minimal, BO.ROUTE_AI))
        check("C D=61: AI R1 agreement below threshold FAILS", r1_bad["text"]["status"] == "FAIL",
              "R1 must still be falsifiable on the route that remains required", r1_bad["text"]["status"])

        # ---- D: within budget, a missing D human answer still REFUSES -----------------
        d_repeat = next(b for b, r in under["stimuli"].items()
                        if r["is_r1_repeat"] and BO.ROUTE_HUMAN in r["adjudication_routes"])
        ok, obs = refuses(lambda: full_path(under, drop(full_under, BO.ROUTE_HUMAN, d_repeat)))
        check("D D<=60: a D-bearing R1 pair missing its human answer REFUSES", ok,
              "within budget the D decision route is required and complete", obs)

        # ---- E: within budget, human reliability below threshold must FAIL ------------
        r1_u = SM.r1_reliability(under, mangle_route_text(under, full_under, BO.ROUTE_HUMAN))
        check("E D<=60: human R1 agreement below threshold FAILS", r1_u["text"]["status"] == "FAIL",
              "the human arm stays falsifiable while it is required", r1_u["text"]["status"])

        # ---- F/G/H: audit and control completeness are untouched ----------------------
        audit_bid = next(b for b, r in over["stimuli"].items() if r["is_c_audit_selected"])
        ok, obs = refuses(lambda: full_path(over, drop(minimal, BO.ROUTE_HUMAN, audit_bid)))
        check("F D=61: omitting a required C-audit human answer REFUSES", ok,
              "the audit is independently selected and stays required", obs)

        ctrl = next(b for b, r in over["stimuli"].items() if r["control_kind"] is not None)
        ok, obs = refuses(lambda: full_path(over, drop(minimal, BO.ROUTE_HUMAN, ctrl)))
        check("G D=61: omitting a required human CONTROL answer REFUSES", ok,
              "A36.6 -- a control exercises every result-bearing route; N-A/N-B/N-C stay complete", obs)
        ok, obs = refuses(lambda: full_path(over, drop(minimal, BO.ROUTE_AI, ctrl)))
        check("H D=61: omitting a required AI CONTROL answer REFUSES", ok,
              "same, on the AI route", obs)

        # ---- MUTATION 1: unconditional D -> human -------------------------------------
        real = BO.frame_required_routes
        BO.frame_required_routes = lambda frames, d_required: real(frames, True)
        try:
            over_mut = build(61, 30, tmp)
            mut_min = a48_minimal(over_mut, X27.synthesize_adjudication(over_mut))
            ok, obs = refuses(lambda: full_path(over_mut, mut_min))
        finally:
            BO.frame_required_routes = real
        check("MUTATION unconditional D->human makes the D=61 arm RED", ok,
              "proves arm A is caused by the budget predicate and nothing else", obs)

        # ---- MUTATION 2: D-human globally optional ------------------------------------
        BO.frame_required_routes = lambda frames, d_required: real(frames, False)
        try:
            under_mut = build(60, 30, tmp)
            full_mut = X27.synthesize_adjudication(under_mut)
            d_rep = [b for b, r in under_mut["stimuli"].items()
                     if r["is_r1_repeat"] and r["in_d_frame"] and r["control_kind"] is None]
            trimmed = full_mut
            for b in d_rep:
                trimmed = drop(trimmed, BO.ROUTE_HUMAN, b)
            ok2, obs2 = refuses(lambda: full_path(under_mut, trimmed))
        finally:
            BO.frame_required_routes = real
        check("MUTATION D-human globally optional makes the D<=60 arm RED", not ok2,
              "within budget a missing D human answer must still refuse; a global opt-out hides it",
              obs2)

    failed = [r for r in RESULTS if not r["pass"]]
    for r in RESULTS:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['check']}")
        if not r["pass"]:
            print(f"       expected: {r['expected']}")
            print(f"       observed: {r['observed']}")
    print(f"\nx31 {len(RESULTS) - len(failed)}/{len(RESULTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
