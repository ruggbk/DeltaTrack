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

import dataclasses
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


def validation_and_r1(key, adj):
    """Validation + R1 ONLY. Deliberately NOT called `full_path`.

    Closure review caught the previous name: it asserted on `validate_adjudicated` plus
    `r1_reliability` and was described as the scorer's path, while `score()` went on consuming a
    human answer for every D primary through `heading_metrics`. The arms below that need the
    real result-bearing path call `real_score` instead; this one is kept where the semantics
    under test really are validation and R1.
    """
    BO.validate_adjudicated(adj, key)
    return SM.r1_reliability(key, adj)


def real_score(frame, key, adj):
    """The ACTUAL result-bearing scorer, over a complete valid ScoreInputs."""
    return SM.score(X27.inputs([frame], key=key, adjudicated=adj))


def real_decision(frame, key, adj):
    """score() -> decide(). The whole path a result has to traverse."""
    import decide_architecture as DA

    payload = real_score(frame, key, adj)
    return DA.decide(DA.DecisionInputs(metrics=payload, frames=(frame,), x2a="PASS", x2b="PASS"))


def scorable(n_d, n_c, tmp):
    """A REAL frame + REAL oracle key that `score()` can actually consume, at a chosen census."""
    pages = ([X27.page_input(i + 1, start_gid=i * 100, text_differs={0}) for i in range(n_d)]
             + [X27.page_input(n_d + i + 1, start_gid=(n_d + i) * 100) for i in range(n_c)])
    frame = X27.frame(pages)
    built = BO.build([{"frame": frame, "pdf_path": X27.synthetic_pdf(tmp, len(pages)), "stratum": "SYNTHETIC"}])
    return frame, built.key, X27.synthesize_adjudication(built.key)


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


def part_real_scoring(tmp):
    """The arms closure review added: the REAL scorer and decider, not validation + R1.

    The A48-minimal adjudication is whatever `synthesize_adjudication` produces for a key whose
    routes A48 already narrowed, so it carries exactly the required AI answers, the C-audit
    human answers and the control human answers, and NO D-only human answers.
    """
    import decide_architecture as DA

    frame61, key61, adj61 = scorable(61, 30, tmp)
    frame60, key60, adj60 = scorable(60, 30, tmp)

    check("premise: the scorable fixtures realize the intended censuses",
          key61["d_frame_census"] == 61 and not key61["d_decision_route_required"]
          and key60["d_frame_census"] == 60 and key60["d_decision_route_required"],
          "the census drives the predicate on a frame `score()` can consume",
          f"61->{key61['d_decision_route_required']} 60->{key60['d_decision_route_required']}")

    # --- D=61 must traverse the REAL scorer and the REAL decider -----------------
    try:
        payload = real_score(frame61, key61, adj61)
        scored, why = True, sorted(payload["headings_pooled"])
    except Exception as exc:  # noqa: BLE001
        scored, why = False, f"{type(exc).__name__}: {str(exc)[:120]}"
    check("REAL SCORE D=61 with the A48-minimal adjudication COMPLETES", scored,
          "absent non-required D human evidence must not stop C/RQ2 scoring", why)
    check("REAL SCORE D=61 omits the D estimand rather than zeroing it",
          scored and "D" not in why and "C" in why,
          "a zero D block would assert the arms were measured and agreed on nothing", why)
    try:
        decision = real_decision(frame61, key61, adj61)
        decided, outcome = True, decision["outcome"]
    except Exception as exc:  # noqa: BLE001
        decided, outcome = False, f"{type(exc).__name__}: {str(exc)[:120]}"
    check("REAL DECIDE D=61 reaches an outcome on the same inputs", decided,
          "the decider reads the full census from the frames and applies the budget itself", outcome)

    # --- D<=60 must still refuse a missing required D human answer ---------------
    d_primary = next(b for b, r in key60["stimuli"].items()
                     if r["in_d_frame"] and not r["is_r1_repeat"] and r["control_kind"] is None)
    ok, obs = refuses(lambda: real_score(frame60, key60, drop(adj60, BO.ROUTE_HUMAN, d_primary)))
    check("REAL SCORE D<=60 missing a required D-human PRIMARY REFUSES", ok,
          "within budget Rule 1's evidence is required and the scorer must not proceed", obs)
    d_repeat = next((b for b, r in key60["stimuli"].items()
                     if r["is_r1_repeat"] and BO.ROUTE_HUMAN in r["adjudication_routes"]), None)
    if d_repeat:
        ok, obs = refuses(lambda: real_score(frame60, key60, drop(adj60, BO.ROUTE_HUMAN, d_repeat)))
        check("REAL SCORE D<=60 missing a required D-human R1 REPEAT REFUSES", ok,
              "the repeat inherits its primary's required route (A36.6)", obs)
    check("REAL SCORE D<=60 with complete D evidence is ACCEPTED",
          bool(real_score(frame60, key60, adj60)),
          "non-vacuity: the within-budget path must still succeed", "scored")

    # --- the key may not self-certify a false budget state -----------------------
    liar = json.loads(json.dumps(key60))
    liar["d_frame_census"] = 61
    liar["d_decision_route_required"] = False
    for bid, rec in liar["stimuli"].items():
        if rec["in_d_frame"] and not rec["is_c_audit_selected"] and rec["control_kind"] is None:
            rec["adjudication_routes"] = [r for r in rec["adjudication_routes"] if r != BO.ROUTE_HUMAN]
            rec["human_answer_purposes"] = [p for p in rec["human_answer_purposes"] if p != "d_decision"]
            rec["n_human_tasks"] = 1 if BO.ROUTE_HUMAN in rec["adjudication_routes"] else 0
    trimmed = {"schema": adj60["schema"], BO.ROUTE_AI: dict(adj60[BO.ROUTE_AI]),
               BO.ROUTE_HUMAN: {b: a for b, a in adj60[BO.ROUTE_HUMAN].items()
                                if BO.ROUTE_HUMAN in liar["stimuli"][b]["adjudication_routes"]}}
    ok, obs = refuses(lambda: real_score(frame60, liar, trimmed))
    check("a COORDINATED key claiming D=61 over a real 60-census REFUSES", ok,
          "a true census of 60 lets Rule 1 select X; a key must not certify itself out of that "
          "evidence, however internally consistent its own metadata is", obs)

    # --- a frame with no declared census is unusable, not empty -------------------
    blind_frame = json.loads(json.dumps(frame61))
    blind_frame["counts"].pop("d_frame_census", None)
    ok, obs = refuses(lambda: BO.build([{"frame": blind_frame,
                                         "pdf_path": X27.synthetic_pdf(tmp, 3), "stratum": "SYNTHETIC"}]))
    check("a frame declaring NO d_frame_census REFUSES at build", ok,
          "absent must not be read as 0, which is within budget and would excuse Rule 1's evidence",
          obs)

    # --- MUTATION: restore unconditional D scoring -------------------------------
    real_hm = SM.heading_metrics
    def unconditional(inputs):
        k = inputs.oracle_key
        patched = {**k, "d_decision_route_required": True}
        return real_hm(dataclasses.replace(inputs, oracle_key=patched))
    SM.heading_metrics = unconditional
    try:
        ok, obs = refuses(lambda: real_score(frame61, key61, adj61))
    finally:
        SM.heading_metrics = real_hm
    check("MUTATION unconditional D scoring makes the D=61 REAL SCORE arm RED", ok,
          "proves the end-to-end arm is caused by the budget predicate inside score()", obs)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        part_real_scoring(tmp)
        over, under = build(61, 30, tmp), build(60, 30, tmp)

        check("premise: D=61 is over budget, D=60 is within it",
              over["d_frame_census"] == 61 and not over["d_decision_route_required"]
              and under["d_frame_census"] == 60 and under["d_decision_route_required"],
              "the realized census drives the predicate",
              f"61->{over['d_decision_route_required']} 60->{under['d_decision_route_required']}")

        full_over, full_under = X27.synthesize_adjudication(over), X27.synthesize_adjudication(under)

        # ---- A: D-only human answers absent must NOT fail anything -------------------
        minimal = a48_minimal(over, full_over)
        ok, obs = refuses(lambda: validation_and_r1(over, minimal))
        check("A D=61: absent D-only human answers do NOT fail the real path",
              not ok, "A27.3 made that route non-decision-bearing, so its absence blocks nothing", obs)
        check("A ...and no D-only stimulus claims the human route",
              all(BO.ROUTE_HUMAN not in r["adjudication_routes"]
                  for r in over["stimuli"].values()
                  if r["in_d_frame"] and not r["in_c_frame"] and not r["is_c_audit_selected"]
                  and r["control_kind"] is None),
              "a non-required route is ABSENT, not NOT_EVALUABLE", "")
        r1 = validation_and_r1(over, minimal)
        check("A ...and R1's required-route population is AI only",
              sorted(r1["per_route"]) == [BO.ROUTE_AI],
              "no human R1 arm is created by D membership alone", sorted(r1["per_route"]))

        # ---- B: a required AI answer is still mandatory -------------------------------
        ai_repeat = next(b for b, r in over["stimuli"].items()
                         if r["is_r1_repeat"] and BO.ROUTE_AI in r["adjudication_routes"])
        ok, obs = refuses(lambda: validation_and_r1(over, drop(minimal, BO.ROUTE_AI, ai_repeat)))
        check("B D=61: a C-bearing R1 pair missing its AI answer REFUSES", ok,
              "the AI route stays result-bearing and complete", obs)

        # ---- C: AI reliability below threshold must FAIL ------------------------------
        r1_bad = SM.r1_reliability(over, mangle_route_text(over, minimal, BO.ROUTE_AI))
        check("C D=61: AI R1 agreement below threshold FAILS", r1_bad["text"]["status"] == "FAIL",
              "R1 must still be falsifiable on the route that remains required", r1_bad["text"]["status"])

        # ---- D: within budget, a missing D human answer still REFUSES -----------------
        d_repeat = next(b for b, r in under["stimuli"].items()
                        if r["is_r1_repeat"] and BO.ROUTE_HUMAN in r["adjudication_routes"])
        ok, obs = refuses(lambda: validation_and_r1(under, drop(full_under, BO.ROUTE_HUMAN, d_repeat)))
        check("D D<=60: a D-bearing R1 pair missing its human answer REFUSES", ok,
              "within budget the D decision route is required and complete", obs)

        # ---- E: within budget, human reliability below threshold must FAIL ------------
        r1_u = SM.r1_reliability(under, mangle_route_text(under, full_under, BO.ROUTE_HUMAN))
        check("E D<=60: human R1 agreement below threshold FAILS", r1_u["text"]["status"] == "FAIL",
              "the human arm stays falsifiable while it is required", r1_u["text"]["status"])

        # ---- F/G/H: audit and control completeness are untouched ----------------------
        audit_bid = next(b for b, r in over["stimuli"].items() if r["is_c_audit_selected"])
        ok, obs = refuses(lambda: validation_and_r1(over, drop(minimal, BO.ROUTE_HUMAN, audit_bid)))
        check("F D=61: omitting a required C-audit human answer REFUSES", ok,
              "the audit is independently selected and stays required", obs)

        ctrl = next(b for b, r in over["stimuli"].items() if r["control_kind"] is not None)
        ok, obs = refuses(lambda: validation_and_r1(over, drop(minimal, BO.ROUTE_HUMAN, ctrl)))
        check("G D=61: omitting a required human CONTROL answer REFUSES", ok,
              "A36.6 -- a control exercises every result-bearing route; N-A/N-B/N-C stay complete", obs)
        ok, obs = refuses(lambda: validation_and_r1(over, drop(minimal, BO.ROUTE_AI, ctrl)))
        check("H D=61: omitting a required AI CONTROL answer REFUSES", ok,
              "same, on the AI route", obs)

        # ---- MUTATION 1: unconditional D -> human -------------------------------------
        real = BO.frame_required_routes
        BO.frame_required_routes = lambda frames, d_required: real(frames, True)
        try:
            over_mut = build(61, 30, tmp)
            mut_min = a48_minimal(over_mut, X27.synthesize_adjudication(over_mut))
            ok, obs = refuses(lambda: validation_and_r1(over_mut, mut_min))
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
            ok2, obs2 = refuses(lambda: validation_and_r1(under_mut, trimmed))
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
