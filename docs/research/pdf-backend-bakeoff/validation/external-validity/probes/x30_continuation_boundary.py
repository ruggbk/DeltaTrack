"""x30 -- the executable control over A47: boundary continuity and the A45 4.7 labelling.

NOT CONFIRMATORY. Opens no holdout document, measures nothing, and never writes the real
`results/EXECUTION-START.json`. Every arm that could write a marker redirects
`x04.EXECUTION_MARKER` to a disposable path and restores it in a `finally`.

WHAT EACH CONTROL PRESERVES, AND THE MUTATION THAT MUST BREAK IT
---------------------------------------------------------------

A. Pristine re-authorization of an EXPOSED population is refused.
   Preserves: these 17 members can never be given a second pristine boundary, whatever
   happens to branches, archives or the original marker. Matters because the marker is
   write-once, so a false attestation inside it could never be corrected.
   Mutation that must break it: make the apparatus ignore the prior-boundary evidence
   (arm B literally does this, and shows the false marker gets written).

B. The refusal is CAUSED by the prior-boundary evidence.
   Preserves: arm A is not passing for an unrelated reason. This is the isolation lesson
   A45.4 recorded about its own G5 arm -- asserting only "it refused" passes for ANY
   refusal, including one from a gate that happens to be red.
   Mutation: with exposure suppressed, authorization SUCCEEDS and the marker carries the
   pristine sentence. If it still refused, the refusal was never about exposure.

C. Absent evidence reads UNKNOWN, never pristine.
   Preserves: fail-closed. Deleting a file must not restore the pristine reading.
   Mutation: a `continuation_state` that returns ok on a missing record.

D. The record is scoped to the POPULATION, not the branch.
   Preserves: a genuinely new study with a new freeze does not inherit this exposure, and
   this population cannot shed it by moving branches.
   Mutation: a record naming a different population that is still accepted.

E. The continuation marker is TRUTHFUL.
   Preserves: the one artifact that outlives every branch says what actually happened.
   Mutation: the pristine attestation reappearing on the continuation path -- which a later
   literal key in the marker dict would silently cause.

F. G7 sees a result-bearing toolchain change.
   Preserves: PyMuPDF renders the oracle stimuli and decides the cross-engine qualification.
   It is now declared and pinned (A47.11), but a declaration binds `uv run` and not an
   interpreter invoked around it, so the gate-time version read still does real work.
   Mutation: a version bump that the gate reports as green.

G. UNDER-LABELLING: every A45-affected surface carries the 4.7 status.
   Preserves: no A45-dependent result can be read as confirmatory.
   Mutation: suppress the status -- the control must FAIL.

H. OVER-LABELLING: results with no A45 dependency stay unlabelled.
   Preserves: the distinction the deviation register exists to record. Marking everything
   non-confirmatory would be indistinguishable from marking nothing.
   Mutation: label globally -- the control must FAIL.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import continuation_provenance as CP  # noqa: E402
import score_metrics as SM  # noqa: E402
import x04_freeze_check as X04  # noqa: E402
from x27_score_metrics import cross_engine_artifact  # noqa: E402

EV = HERE.parents[1]
DISPOSABLE = EV / "results" / ".x30-EXECUTION-START.json"


def check(results, name, ok, why, observed=""):
    results.append({"check": name, "pass": bool(ok), "expected": why, "observed": str(observed)[:300]})


@contextlib.contextmanager
def green_gates():
    """Both gates forced open, so any refusal is attributable to the boundary logic alone.

    Without this the arms below would run against ambient tree state and their premise would
    be "whatever the tree happens to be" rather than a constructed known-bad case.
    """
    real_f, real_g = X04.check_freeze, X04.check_execution
    X04.check_freeze = lambda m, lk: [("F-stub", True, "")]
    X04.check_execution = lambda m: [("G-stub", True, "")]
    try:
        yield
    finally:
        X04.check_freeze, X04.check_execution = real_f, real_g


@contextlib.contextmanager
def disposable_marker():
    """Redirect the marker path so no arm can create the real execution boundary."""
    real = X04.EXECUTION_MARKER
    X04.EXECUTION_MARKER = DISPOSABLE
    try:
        yield DISPOSABLE
    finally:
        DISPOSABLE.unlink(missing_ok=True)
        X04.EXECUTION_MARKER = real


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = X04.main(argv)
    return rc, buf.getvalue()


# --------------------------------------------------------------------------- A and B


def part_reauthorization(results):
    """A: pristine authorization refused. B: and refused BECAUSE of the exposure evidence."""
    assert CP.is_exposed(CP.load()), "premise: the committed record marks this population EXPOSED"

    with green_gates(), disposable_marker() as marker:
        rc, out = run(["--authorize-execution"])
        # THE REASON, NOT THE BOOLEAN. A bare `rc != 0` passes for any refusal at all.
        named = "ALREADY crossed an execution boundary" in out
        check(
            results,
            "A pristine --authorize-execution on an EXPOSED population is REFUSED",
            rc != 0 and named and not marker.exists(),
            "refuses, names the prior boundary as the reason, and writes no marker",
            f"rc={rc} named_reason={named} marker_written={marker.exists()}",
        )
        check(
            results,
            "A ...and the refusal names --authorize-continuation as the lawful path",
            "--authorize-continuation" in out,
            "the operator is told what IS permitted, not merely that this is not",
            out.strip().splitlines()[-1][:120] if out.strip() else "",
        )

    # B -- THE MUTATION. Suppress the prior-boundary evidence and the SAME call must now
    # succeed and write the FALSE attestation. This is the pre-repair behaviour, reproduced.
    with green_gates(), disposable_marker() as marker:
        real_exposed = X04.population_exposed
        X04.population_exposed = lambda: False
        try:
            rc, out = run(["--authorize-execution"])
            written = json.loads(marker.read_text()) if marker.exists() else {}
        finally:
            X04.population_exposed = real_exposed
        false_claim = "no confirmatory H/X extraction had been run" in written.get("process_attestation", "")
        check(
            results,
            "B MUTATION removing the prior-boundary evidence makes pristine authorization SUCCEED",
            rc == 0 and marker.exists() and false_claim,
            "proves arm A's refusal is caused by the evidence and nothing else; this is the "
            "defect as it existed before A47",
            f"rc={rc} wrote_marker={bool(written)} false_attestation={false_claim}",
        )


def part_fail_closed(results):
    """C: a missing record is UNKNOWN. D: a foreign-population record is rejected."""
    saved = X04.CONTINUATION.read_text()
    try:
        X04.CONTINUATION.unlink()
        rec, ok, detail = X04.continuation_state()
        check(
            results,
            "C absent continuation record is NOT read as pristine",
            not ok and not X04.population_exposed() and "not pristine" in detail,
            "fails closed: UNKNOWN, and F12 red",
            detail,
        )
        with green_gates(), disposable_marker() as marker:
            rc, out = run(["--authorize-execution"])
            check(
                results,
                "C ...and authorization is refused while the record is missing",
                rc != 0 and not marker.exists(),
                "an unverifiable continuation state blocks authorization",
                f"rc={rc} marker_written={marker.exists()}",
            )

        # D -- a record about a DIFFERENT population must not describe this one.
        #
        # Tested on the SCOPING PREDICATE directly. Writing a mutated file to disk makes it
        # uncommitted, so `continuation_state` refuses one layer earlier and the arm would
        # pass without the scoping check ever running -- a pass for the wrong reason. The
        # two layers are therefore asserted separately.
        real_rec = json.loads(saved)
        pop = real_rec["population"]
        check(
            results,
            "D the scoping predicate ACCEPTS the real frozen population (non-vacuity)",
            CP.describes_population(real_rec, pop["population_freeze_commit"], pop["membership_blob"]),
            "a predicate that never accepts anything cannot distinguish populations",
            f"{pop['population_freeze_commit'][:8]} / {pop['membership_blob'][:8]}",
        )
        # The two per-field MUTATION arms that stood here were REMOVED as redundant: arm I
        # applies the same two mutations (population_freeze_commit, membership_blob) through the
        # REAL F12 path rather than the predicate alone, so it fails on every mutation these did
        # and on more of the path. What is kept here is what arm I cannot cover -- the positive
        # control on the predicate itself, and the uncommitted-record layer, which arm I
        # deliberately stubs out in order to isolate the identity anchor.

        # ...and the committed-file layer, asserted in its own right.
        X04.CONTINUATION.write_text(json.dumps({**real_rec, "population_status": "PRISTINE"}))
        _r, ok_uncommitted, detail_uncommitted = X04.continuation_state()
        check(
            results,
            "D an UNCOMMITTED continuation record is refused",
            not ok_uncommitted and "not committed" in detail_uncommitted,
            "an edit to the record on disk cannot silently downgrade the population to pristine",
            detail_uncommitted,
        )
    finally:
        X04.CONTINUATION.write_text(saved)


def part_truthful_marker(results):
    """E: the continuation marker states what actually happened."""
    with green_gates(), disposable_marker() as marker:
        rc, _out = run(["--authorize-continuation"])
        written = json.loads(marker.read_text()) if marker.exists() else {}
    attest = written.get("process_attestation", "")
    check(
        results,
        "E --authorize-continuation writes a TRUTHFUL marker",
        rc == 0
        and written.get("authorization_kind") == "CONTINUATION OF THE INAUGURAL EXECUTION"
        and written.get("prior_boundary_commit", "").startswith("89360b30")
        and "ALREADY measured" in attest,
        "names the prior boundary and says the population was already measured",
        f"kind={written.get('authorization_kind')} prior={written.get('prior_boundary_commit', '')[:8]}",
    )
    check(
        results,
        "E ...and the PRISTINE sentence is absent from it",
        "no confirmatory H/X extraction had been run" not in attest,
        "a later literal key overriding the spread would silently restore the false sentence",
        attest[:140],
    )


def part_toolchain(results):
    """F: G7 sees a result-bearing version change."""
    rec = CP.load()
    clean = CP.toolchain_drift(rec, CP.observed_toolchain())
    check(
        results,
        "F G7 is GREEN on the recorded toolchain (non-vacuity, positive direction)",
        clean == [],
        "a check that can never pass is as useless as one that can never fail",
        clean,
    )
    for dist, bad in (("pymupdf", "1.29.0"), ("pypdfium2", "5.13.0"), ("python", "3.13.0")):
        observed = {**CP.observed_toolchain(), dist: bad}
        drift = CP.toolchain_drift(rec, observed)
        check(
            results,
            f"F MUTATION {dist} -> {bad} is reported as drift",
            any(d.startswith(dist) for d in drift),
            "a silent version change on a result-bearing dependency must be visible at gate time",
            drift,
        )


# --------------------------------------------------------------------------- G and H


def _surfaces(payload, document):
    """Every place the A45 qualification channel surfaces for one document."""
    doc = payload["per_document"][document]
    out = [doc, doc["M0"], doc["M7"], doc["M9"], *doc.get("headings_by_frame", {}).values()]
    out += [e for e in payload["section8"]["per_document"] if e.get("document") == document]
    for pop in payload["section8"]["paired"]["by_population"].values():
        for quantity in pop.values():
            out += [d for d in quantity["per_document"] if d.get("document") == document]
    return out


def part_labelling(results, payload_builder):
    """G: under-labelling is caught. H: over-labelling is caught."""
    payload = payload_builder()
    document = next(iter(payload["per_document"]))
    surfaces = _surfaces(payload, document)
    # THE ORACLE IS THE CODE CONSTANT, not `a45_status(load())`. Reading the expected value
    # from the same record the artifact was stamped from is how this control read green while a
    # fabricated "CONFIRMATORY" flowed all the way into a scored row: the authority, the result
    # and the oracle all moved together. Section 4.7 is a REQUIREMENT, so the expectation must
    # be independent of the thing under test.
    status = CP.NON_CONFIRMATORY

    check(
        results,
        "G every A45-affected surface carries the 4.7 status",
        surfaces and all(s.get("qualification_status") == status for s in surfaces),
        "no A45-dependent result can be read as confirmatory",
        f"{sum(1 for s in surfaces if s.get('qualification_status') == status)}/{len(surfaces)} surfaces",
    )

    # G MUTATION -- suppress the status. The check above must now FAIL.
    real = SM._qual_keys
    SM._qual_keys = lambda label, doc: {"qualification": label.get("per_document", {}).get(doc)}
    try:
        suppressed = _surfaces(payload_builder(), document)
    finally:
        SM._qual_keys = real
    check(
        results,
        "G MUTATION suppressing the status makes the labelling check FAIL",
        not all(s.get("qualification_status") == status for s in suppressed),
        "proves the check is not vacuous: it can distinguish labelled from unlabelled",
        f"{sum(1 for s in suppressed if s.get('qualification_status') == status)}/{len(suppressed)} still labelled",
    )

    # G -- the scorer refuses BOTH shapes of bad provenance. Merged into one control: the
    # missing-field case alone proved only that `_require` fires, and said nothing about a
    # nonempty but WRONG status, which is the shape that actually produced a mislabelled
    # result. Two separate controls would fail on different mutations but cost two things to
    # maintain for one property, so the older presence-only arm is gone.
    import x27_score_metrics as X27

    check(
        results,
        "G the scorer's required status is INDEPENDENT of the provenance module's constant",
        SM.REQUIRED_CONFIRMATORY_STATUS == CP.NON_CONFIRMATORY,
        "two constants held separately (the allowlist forbids the scorer importing CP) must "
        "not drift apart silently",
        SM.REQUIRED_CONFIRMATORY_STATUS,
    )
    frames = [X27.frame([X27.page_input(1)])]
    docs = [f["document"] for f in frames]
    for label, bad in (("MISSING", None), ("WRONG (nonempty)", "CONFIRMATORY")):
        ce = X27.cross_engine_artifact(docs, confirmatory_status=bad)
        try:
            SM.score(X27.inputs(frames, cross_engine=ce))
            refused, why = False, f"ACCEPTED an artifact whose status was {bad!r}"
        except Exception as exc:  # noqa: BLE001
            refused, why = True, f"{type(exc).__name__}: {exc}"
        check(
            results,
            f"G a cross-engine artifact with a {label} confirmatory_status is REFUSED",
            refused,
            "section 4.7 status is validated against a requirement, never accepted as supplied",
            why,
        )

    # H -- OVER-LABELLING. Surfaces with no A45 dependency must stay clean.
    unaffected = [payload["adequacy_4_5"], payload["s1"]]
    check(
        results,
        "H results with NO A45 dependency carry no qualification status",
        all("qualification_status" not in u for u in unaffected),
        "S1 liveness and section 4.5 adequacy do not depend on the cross-engine sample",
        [sorted(u)[:4] for u in unaffected],
    )
    check(
        results,
        "H METRIC VALUES are not modified to transport provenance",
        "qualification_status" not in payload["per_document"][document]["M0"]["M0a_text_rate"],
        "the status is an additive sibling key; no metric value carries or is derived from it",
        sorted(payload["per_document"][document]["M0"]["M0a_text_rate"])[:5],
    )

    # H MUTATION -- label globally. The over-labelling check must now FAIL.
    globally = {**payload, "adequacy": {**payload["adequacy_4_5"], "qualification_status": status}}
    check(
        results,
        "H MUTATION labelling everything non-confirmatory makes the over-labelling check FAIL",
        not all("qualification_status" not in globally[k] for k in ("adequacy", "s1")),
        "proves the over-labelling check can fire; a global label is not a free safety margin",
        sorted(globally["adequacy"])[-3:],
    )


def part_identity_anchor(results):
    """I: a COMMITTED, VALID historical rewrite must not pass F12 (no self-certification).

    The threat is not malformed JSON and not an uncommitted edit -- both are already refused
    by arm C/D and neither is interesting. It is a syntactically valid, internally consistent,
    COMMITTED record whose historical identity has been quietly rewritten. If the record is
    the only witness to its own identity, it certifies itself and F12 proves nothing.

    So `committed` is STUBBED TRUE for the whole arm. That deliberately removes the check
    that would otherwise do the rejecting, leaving the identity anchor as the only thing that
    can refuse. A pass here therefore cannot be a pass for the wrong reason.
    """
    saved = X04.CONTINUATION.read_text()
    real_committed = X04.committed
    X04.committed = lambda path: True
    try:
        # POSITIVE CONTROL first: with `committed` stubbed, the UNMUTATED record is accepted.
        # Without this the refusals below could all be an arm that refuses everything.
        _rec, ok_clean, detail_clean = X04.continuation_state()
        check(
            results,
            "I the unmutated committed record is ACCEPTED (non-vacuity)",
            ok_clean and X04.population_exposed(),
            "the arm must be able to say yes, or its refusals mean nothing",
            detail_clean,
        )

        rec = json.loads(saved)
        mutations = {
            "prior_execution.boundary_commit": lambda r: r["prior_execution"].update(
                {"boundary_commit": "1" * 40}
            ),
            "population.population_freeze_commit": lambda r: r["population"].update(
                {"population_freeze_commit": "2" * 40}
            ),
            "population.membership_blob": lambda r: r["population"].update({"membership_blob": "3" * 40}),
        }
        for field, mutate in mutations.items():
            m = json.loads(json.dumps(rec))
            mutate(m)
            # Syntactically valid and internally consistent: schema, every required key, and
            # population_status all survive untouched. Only the historical identity moved.
            X04.CONTINUATION.write_text(json.dumps(m, indent=1))
            _r, ok, detail = X04.continuation_state()
            authorizable = ok and X04.population_exposed()
            check(
                results,
                f"I MUTATION committed rewrite of {field} makes the authority NON-AUTHORIZABLE",
                not ok and not authorizable,
                "a valid committed record must not be the only witness to its own historical "
                "identity; F12 must fail and the population must not become authorizable",
                detail,
            )
    finally:
        X04.committed = real_committed
        X04.CONTINUATION.write_text(saved)


def part_status_invariant(results):
    """J: a committed record claiming a WRONG 4.7 status cannot authorize or produce.

    The measured false-green this closes: with the status read verbatim from the record,
    `confirmatory_status = "CONFIRMATORY"` left F12 GREEN, made `a45_status` return the
    fabricated value, let the REAL cross-engine producer stamp it into an artifact, and
    produced a scored row reading "CONFIRMATORY" -- while the test oracle moved with it.
    """
    saved = X04.CONTINUATION.read_text()
    real_committed = X04.committed
    X04.committed = lambda path: True
    try:
        m = json.loads(saved)
        m["a45"]["confirmatory_status"] = "CONFIRMATORY"
        X04.CONTINUATION.write_text(json.dumps(m, indent=1))

        _r, ok, detail = X04.continuation_state()
        check(
            results,
            "J MUTATION a committed record claiming CONFIRMATORY makes F12 FAIL",
            not ok and not X04.population_exposed(),
            "4.7 status is a requirement; a record asserting a different one is not a lawful "
            "continuation authority",
            detail,
        )

        try:
            got = CP.a45_status(CP.load())
            accessor_refused, observed = False, got
        except Exception as exc:  # noqa: BLE001
            accessor_refused, observed = True, f"{type(exc).__name__}: {exc}"
        check(
            results,
            "J ...and the status accessor REFUSES rather than returning the fabricated value",
            accessor_refused,
            "the producer stamps through this accessor, so refusing here stops a fabricated "
            "status reaching any artifact",
            observed,
        )
    finally:
        X04.committed = real_committed
        X04.CONTINUATION.write_text(saved)

    # The accessor returns the CONSTANT on a good record, so the producer cannot stamp a
    # record-supplied string even when the record is otherwise valid.
    check(
        results,
        "J the accessor returns the required CONSTANT on a valid record (non-vacuity)",
        CP.a45_status(CP.load()) == CP.NON_CONFIRMATORY,
        "must still say yes to a lawful record, or the refusals above mean nothing",
        CP.a45_status(CP.load()),
    )


def main() -> int:
    results = []
    part_reauthorization(results)
    part_fail_closed(results)
    part_truthful_marker(results)
    part_toolchain(results)
    part_identity_anchor(results)
    part_status_invariant(results)

    try:
        from x30_labelling_fixture import build_payload

        part_labelling(results, build_payload)
    except ImportError as exc:
        check(results, "G/H labelling controls", False, "fixture must import", exc)

    failed = [r for r in results if not r["pass"]]
    for r in results:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['check']}")
        if not r["pass"]:
            print(f"       expected: {r['expected']}")
            print(f"       observed: {r['observed']}")
    print(f"\nx30 {len(results) - len(failed)}/{len(results)}")
    # The real boundary must not exist as a side effect of running the controls.
    real_marker = EV / "results" / "EXECUTION-START.json"
    assert not real_marker.exists(), "x30 must never create the real execution marker"
    assert not DISPOSABLE.exists(), "x30 left its disposable marker behind"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
