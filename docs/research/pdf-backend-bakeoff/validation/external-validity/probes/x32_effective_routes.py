"""x32 -- A54. A pre-A48 immutable key routes by EFFECTIVE requirement, not by its stored bytes.

NOT CONFIRMATORY. SYNTHETIC populations only; opens no holdout document and no real oracle
image, and writes no canonical artifact. The real-tree routing-only control and the
byte-identity checks on the frozen artifacts are recorded in the A54 deviation, not run here.

THE BEHAVIOUR THIS PRESERVES
----------------------------
A48 gave A27.3's budget an executable owner but left `key.get("d_decision_route_required",
True)` at the consumers, so a key predating those fields kept meaning what it meant when built.
That is correct for every key but the one frozen confirmatory artifact: its realized census is
13,992, A27.3 has already made the D decision route non-decision-bearing, and defaulting to
True demands a human answer on all 15,417 stored human routes before ANY metric can be
produced. Not conservative, unsatisfiable.

Measured on the real frozen key BEFORE this repair: `validate_adjudicated` refused a complete
45-item human review with ADJUDICATION_ROUTE_MISSING {'route': 'human'}. AFTER: accepted.

The compatibility path is pinned to that ONE artifact's identity. A key that merely omits the
A48 fields is NOT granted it, so a newly produced key whose stored routes contradict the frozen
predicate still refuses.

THE MUTATIONS THAT MUST BREAK IT
--------------------------------
  * `effective_d_decision_required` always True   -> the D=61 arm goes RED
  * `effective_record_routes` returns stored bytes -> the D=61 arm goes RED
  * `is_pre_a48_frozen_key` always True            -> the scoping arm goes RED
All three are injected into the real functions below, not into copies of their output.
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
import x21_build_oracle as X21  # noqa: E402
import x31_dframe_budget_routes as X31  # noqa: E402

RESULTS: list[dict] = []


def check(name, ok, why, observed=""):
    RESULTS.append({"check": name, "pass": bool(ok), "expected": why, "observed": str(observed)[:200]})


def stale(key: dict) -> dict:
    """A synthetic key aged back to the PRE-A48 encoding.

    Drops the two A48 fields and restores the pre-A48 derivation, in which raw D membership
    alone created an unconditional human route and a `d_decision` purpose. This is the shape the
    frozen confirmatory key really has; nothing here is written anywhere.
    """
    out = json.loads(json.dumps(key))
    out.pop("d_frame_census", None)
    out.pop("d_decision_route_required", None)
    for record in out["stimuli"].values():
        purposes = list(record.get("human_answer_purposes") or ())
        routes = set(record.get("adjudication_routes") or ())
        if record.get("in_d_frame"):
            if BO.PURPOSE_D_DECISION not in purposes:
                purposes.append(BO.PURPOSE_D_DECISION)
            routes.add(BO.ROUTE_HUMAN)
        record["human_answer_purposes"] = purposes
        record["adjudication_routes"] = [r for r in BO.ROUTE_ORDER if r in routes]
    return out


def build_mixed(n_c_only: int, n_d_only: int, n_both: int, tmp) -> dict:
    """A real BO.build over a synthetic population that CONTAINS C-and-D overlap.

    `X31.build` lays out C-only and D-only pages, so it cannot exercise the overlap the real
    population actually has (72 overlapping regions, 19 of them C-audit-selected). The C audit
    is drawn from the C frame, so once overlap exists some audit picks are necessarily also D
    members, which is the configuration the narrowing must not shrink.
    """
    mem = [(True, False)] * n_c_only + [(True, True)] * n_both + [(False, True)] * n_d_only
    docs = X21.synthetic_documents(tmp, n_pages=len(mem), memberships=mem)
    controls = BO.control_specs(json.loads(CF.MANIFEST_PATH.read_text()), EV, REPO)
    return BO.build(docs, controls=controls).key


def identity_of(key: dict) -> dict:
    return {field: key.get(field) for field in BO.PRE_A48_FROZEN_KEY_IDENTITY}


def effective_human(key: dict) -> set:
    d_required = BO.effective_d_decision_required(key)
    return {b for b, r in key["stimuli"].items() if BO.ROUTE_HUMAN in BO.effective_record_routes(r, d_required)}


def effective_ai(key: dict) -> set:
    d_required = BO.effective_d_decision_required(key)
    return {b for b, r in key["stimuli"].items() if BO.ROUTE_AI in BO.effective_record_routes(r, d_required)}


def non_d_human(key: dict) -> set:
    """The C-audit plus control human population, independent of any route byte."""
    out = set()
    for bid, record in key["stimuli"].items():
        purposes = set(record.get("human_answer_purposes") or ())
        if purposes & {BO.PURPOSE_C_AUDIT, BO.PURPOSE_CONTROL_HUMAN}:
            out.add(bid)
    return out


def answers(key: dict, human_ids, ai_ids) -> dict:
    def one(bid):
        return {"id": bid, "headings": [], "notes": []}

    return {BO.ROUTE_AI: {b: one(b) for b in ai_ids}, BO.ROUTE_HUMAN: {b: one(b) for b in human_ids}}


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        over_live, under_live = X31.build(61, 30, tmp), X31.build(60, 30, tmp)
        over, under = stale(over_live), stale(under_live)
        pristine = json.loads(json.dumps(BO.PRE_A48_FROZEN_KEY_IDENTITY))

        check("premise: the synthetic keys really are pre-A48 shaped",
              "d_decision_route_required" not in over and "d_frame_census" not in over,
              "the A48 fields are absent, as in the frozen artifact",
              sorted(over)[:6])

        # ---- SCOPING: shape alone earns nothing --------------------------------------
        check("SCOPING: an unpinned pre-A48-shaped key does NOT get the compatibility path",
              BO.effective_d_decision_required(over) is True,
              "only the pinned frozen artifact is excepted, so a newly produced contradictory "
              "key still requires its stored D routes",
              BO.effective_d_decision_required(over))

        try:
            # ---- D=61, pinned: the effective population is the non-D human set -------
            BO.PRE_A48_FROZEN_KEY_IDENTITY = identity_of(over)
            check("pinned D=61: is_pre_a48_frozen_key recognises it",
                  BO.is_pre_a48_frozen_key(over), "identity match, A48 fields absent", "")
            check("pinned D=61: the D decision route is NOT result-bearing",
                  BO.effective_d_decision_required(over) is False,
                  "census 61 exceeds the 60-region budget, so A27.3 denies the route",
                  BO.effective_d_decision_required(over))

            want = non_d_human(over)
            got = effective_human(over)
            check("A D=61 with stale raw D routes: effective human population is the C-audit "
                  "plus controls, and nothing else",
                  got == want,
                  "the stored bytes still say human on every D member; the effective owner does not",
                  f"effective={len(got)} want={len(want)}")

            adj = answers(over, want, effective_ai(over))
            ok, obs = X31.refuses(lambda: BO.validate_adjudicated(adj, over))
            check("A ...and validate_adjudicated ACCEPTS exactly that population",
                  not ok, "no answer is required on a route A27.3 denied", obs)

            check("A ...and no D-only stimulus is human-required",
                  not any(BO.ROUTE_HUMAN in BO.effective_record_routes(r, False)
                          for r in over["stimuli"].values()
                          if r.get("in_d_frame") and not r.get("in_c_frame")
                          and not r.get("is_c_audit_selected") and r.get("control_kind") is None),
                  "a non-required route is ABSENT, not unevaluable", "")

            # The overlap arm needs a population that HAS overlap; the layout above has none.
            mixed = stale(build_mixed(10, 31, 30, tmp))
            saved_pin = BO.PRE_A48_FROZEN_KEY_IDENTITY
            BO.PRE_A48_FROZEN_KEY_IDENTITY = identity_of(mixed)
            overlap = [b for b, r in mixed["stimuli"].items()
                       if r.get("is_c_audit_selected") and r.get("in_d_frame")]
            mixed_human = effective_human(mixed)
            check("B premise: the mixed population really contains C-and-D audit overlap",
                  bool(overlap), "otherwise the next check would pass vacuously on an empty set",
                  f"{len(overlap)} overlapping audit items")
            check("B every C-and-D audit-selected item stays human-required for the C audit",
                  bool(overlap) and all(b in mixed_human for b in overlap),
                  "the C audit is a frozen 25-item instrument; D membership must not shrink it",
                  f"{len(overlap)} overlapping audit items")
            real_routes_b = BO.effective_record_routes
            try:
                BO.effective_record_routes = lambda record, d: (
                    () if record.get("in_d_frame") else real_routes_b(record, d))
                check("MUTATION drop-overlap: the C-audit overlap arm goes RED",
                      not all(b in effective_human(mixed) for b in overlap),
                      "narrowing that also drops overlapping audit items must be caught",
                      "")
            finally:
                BO.effective_record_routes = real_routes_b
            BO.PRE_A48_FROZEN_KEY_IDENTITY = saved_pin

            audit_ids = [b for b, r in over["stimuli"].items() if r.get("is_c_audit_selected")]
            ok, obs = X31.refuses(
                lambda: BO.validate_adjudicated(X31.drop(dict(adj, schema="x"), BO.ROUTE_HUMAN, audit_ids[0]), over))
            check("C omitting a C-audit human answer REFUSES", ok,
                  "the C audit stays complete and falsifiable", obs)

            control_ids = [b for b, r in over["stimuli"].items() if r.get("control_kind") is not None]
            ok, obs = X31.refuses(
                lambda: BO.validate_adjudicated(X31.drop(dict(adj, schema="x"), BO.ROUTE_HUMAN, control_ids[0]), over))
            check("C omitting a human control answer REFUSES", ok,
                  "controls are what keep the human arm falsifiable", obs)

            check("D AI requirements do not move",
                  effective_ai(over) == {b for b, r in over["stimuli"].items()
                                         if BO.ROUTE_AI in (r.get("adjudication_routes") or ())},
                  "the repair narrows the human route only", len(effective_ai(over)))

            # ---- mutations that must break the D=61 arm --------------------------------
            real_d, real_routes = BO.effective_d_decision_required, BO.effective_record_routes
            try:
                BO.effective_d_decision_required = lambda key: True
                check("MUTATION always-required: the D=61 arm goes RED",
                      effective_human(over) != want,
                      "forcing the budget True must reintroduce the D human population",
                      len(effective_human(over)))
            finally:
                BO.effective_d_decision_required = real_d
            try:
                BO.effective_record_routes = lambda record, d: tuple(record.get("adjudication_routes") or ())
                check("MUTATION stored-bytes routes: the D=61 arm goes RED",
                      effective_human(over) != want,
                      "reading the stale bytes must reintroduce the D human population",
                      len(effective_human(over)))
            finally:
                BO.effective_record_routes = real_routes

            # ---- D=60: the complete census is still required --------------------------
            BO.PRE_A48_FROZEN_KEY_IDENTITY = identity_of(under)
            check("E D=60 pinned: the D decision route IS still result-bearing",
                  BO.effective_d_decision_required(under) is True,
                  "a census within budget is exactly where Rule 1 MAY select X",
                  BO.effective_d_decision_required(under))
            u_human = effective_human(under)
            d_members = [b for b, r in under["stimuli"].items()
                         if r.get("in_d_frame") and r.get("control_kind") is None]
            check("E ...and the COMPLETE D census stays human-required",
                  all(b in u_human for b in d_members),
                  "within budget nothing is narrowed", f"{len(d_members)} D members")
            u_adj = answers(under, u_human, effective_ai(under))
            ok, obs = X31.refuses(
                lambda: BO.validate_adjudicated(X31.drop(dict(u_adj, schema="x"), BO.ROUTE_HUMAN, d_members[0]), under))
            check("E ...and dropping one D human answer REFUSES", ok,
                  "the D route is result-bearing at this census", obs)

            # ---- mutation that must break the scoping arm ------------------------------
            real_is = BO.is_pre_a48_frozen_key
            try:
                BO.is_pre_a48_frozen_key = lambda key: True
                BO.PRE_A48_FROZEN_KEY_IDENTITY = pristine
                check("MUTATION unpinned exception: the SCOPING arm goes RED",
                      BO.effective_d_decision_required(over) is not True,
                      "granting the exception on shape alone must let an unpinned key narrow itself",
                      BO.effective_d_decision_required(over))
            finally:
                BO.is_pre_a48_frozen_key = real_is
        finally:
            BO.PRE_A48_FROZEN_KEY_IDENTITY = pristine

    failed = [r for r in RESULTS if not r["pass"]]
    for r in RESULTS:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['check']}")
        if not r["pass"]:
            print(f"         expected: {r['expected']}")
            print(f"         observed: {r['observed']}")
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks pass")
    (EV / "results" / "x32_effective_routes.json").write_text(
        json.dumps({"schema": "x32_effective_routes/1", "checks": RESULTS}, indent=1)
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
