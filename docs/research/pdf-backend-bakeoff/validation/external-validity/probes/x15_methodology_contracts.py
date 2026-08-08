"""x15 -- test the frozen methodology contracts. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic only. No PDF is opened, no architecture is run, nothing scored.

    A28.1/A28.2  the 4.5 adequacy count and state machine, every branch
    A28.3        canonical pre-blinding stimulus identity; sampling must NOT depend on
                 blind ids
    A28.4        frozen renderer scale, 300 dpi primary / 330 dpi R1 repeat
    A27.7        domain-separated deterministic ranking
    A30.4        the P-head adequacy restriction, executable rather than a caller obligation
    A30.5        blind-ID uniqueness over the REALIZED stimulus set, with collision injection
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

import methodology_contracts as MC  # noqa: E402

OUT = EV / "results" / "x15_methodology_contracts.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def key(doc, page, line, start_ngid):
    """An A27.1 source-position occurrence key, as amended by A30.1.

    The fourth component is the ABSOLUTE `start_ngid`, never an ordinal among the anchors an
    arm emitted. `x16_occurrence_identity.py` proves the derivation through the production
    path; here it only has to be an opaque distinct value.
    """
    return (doc, page, (page, line), start_ngid)


def part_adequacy() -> None:
    # --- the state machine, every branch, thresholds unchanged
    cases = [
        ("4 strata, 5000 occurrences", 4, 5000, "INADEQUATE"),
        ("5 strata, 299 occurrences  (the overlap the table left undecided)", 5, 299, "INADEQUATE"),
        ("6 strata, 299 occurrences", 6, 299, "INADEQUATE"),
        ("8 strata, 299 occurrences", 8, 299, "INADEQUATE"),
        ("7 strata, 300 occurrences  (matched NO row before)", 7, 300, "LIMITED"),
        ("8 strata, 799 occurrences  (matched NO row before)", 8, 799, "LIMITED"),
        ("5 strata, 800 occurrences", 5, 800, "LIMITED"),
        ("6 strata, 5000 occurrences", 6, 5000, "LIMITED"),
        ("7 strata, 800 occurrences", 7, 800, "GENERALISABLE"),
        ("8 strata, 5000 occurrences", 8, 5000, "GENERALISABLE"),
    ]
    bad = [f"{n}: expected {w} got {MC.adequacy(s, o)}" for n, s, o, w in cases if MC.adequacy(s, o) != w]
    check("4.5 state machine matches the frozen rows on every branch", [], bad)
    seen = sorted({MC.adequacy(s, o) for _n, s, o, _w in cases})
    check("...and all three states are reachable", ["GENERALISABLE", "INADEQUATE", "LIMITED"], seen)

    # --- the space is TOTAL: no (strata, occurrences) pair falls through
    holes = [
        (s, o)
        for s in range(0, 9)
        for o in (0, 299, 300, 799, 800, 5000)
        if MC.adequacy(s, o) not in ("INADEQUATE", "LIMITED", "GENERALISABLE")
    ]
    check("no (strata, occurrences) pair is unclassified", [], holes)

    # --- the union count
    a, b, c = key("d", 1, 3, 0), key("d", 1, 9, 0), key("d", 2, 4, 0)
    check("one physical occurrence emitted by BOTH arms counts once", 1, MC.adequacy_occurrences([a], [a]))
    check("an occurrence emitted by ONE arm still counts", 2, MC.adequacy_occurrences([a], [b]))
    check(
        "one arm missing an occurrence cannot remove the other arm's key",
        MC.adequacy_occurrences([a, b, c], [a, b, c]),
        MC.adequacy_occurrences([a, b, c], []),
        "an arm's own failure must never shrink the adequacy denominator",
    )
    # two occurrences on ONE neutral line: the real measured pair from 114-hr-2029 p66:12,
    # a `section` at ngid 617 and its inline `subsection` at ngid 627
    check(
        "two occurrences on ONE neutral line stay distinct",
        2,
        MC.adequacy_occurrences([key("d", 1, 3, 617), key("d", 1, 3, 627)], []),
    )
    # --- kind AND population restriction (A30.4)
    keyed = [
        (key("d", 1, 1, 10), "account", "P-head"),
        (key("d", 1, 2, 20), "agency", "P-head"),
        (key("d", 1, 3, 30), "grouping", "P-head"),
        (key("d", 1, 4, 40), "title", "P-head"),
        (key("d", 1, 5, 50), "section", "P-head"),
        (key("d", 1, 6, 60), "subsection", "P-head"),
    ]
    check(
        "only account/agency/grouping contribute to adequacy",
        3,
        len(MC.filter_keys(keyed)),
        "title/section/division must not inflate the denominator the frozen quantity is compared against",
    )

    # --- A30.4 NEGATIVE CONTROL: P-robust adequacy-kind keys must not move the count.
    # Before A30.4 `filter_keys` filtered on kind alone, so every one of these would have
    # been counted and the denominator would have grown silently.
    baseline_keys = MC.filter_keys(keyed)
    baseline = MC.adequacy_occurrences(baseline_keys, [])
    intruders = [
        (key("robust", 9, i, 700 + i), kind, "P-robust")
        for i, kind in enumerate(["account", "agency", "grouping"] * 40)
    ]
    polluted = MC.filter_keys(keyed + intruders)
    check(
        "adding 120 P-robust account/agency/grouping keys does not change adequacy_occurrences",
        baseline,
        MC.adequacy_occurrences(polluted, []),
        "the frozen P-head clause is now a gate rather than a caller obligation",
    )
    check(
        "...and the intruders really were adequacy-KIND keys, so the control is not vacuous",
        120,
        len({k for k, kind, _pop in intruders if kind in MC.ADEQUACY_KINDS}),
    )
    check(
        "a P-robust key is excluded even when it is the ONLY input",
        0,
        len(MC.filter_keys([(key("robust", 9, 1, 5), "account", "P-robust")])),
    )


def part_determinism() -> None:
    regions = [MC.base_stimulus_identity(f"sha{d}", p, r) for d in range(2) for p in range(1, 4) for r in range(3)]

    # --- reproducible and order-independent
    check("selection is reproducible", MC.select("cframe-select", regions, 5), MC.select("cframe-select", regions, 5))
    check(
        "selection does not depend on input listing order",
        MC.select("cframe-select", regions, 5),
        MC.select("cframe-select", list(reversed(regions)), 5),
    )
    # --- domain separation
    check(
        "different purposes select differently",
        True,
        MC.select("cframe-audit", regions, 5) != MC.select("r1-repeat", regions, 5),
        "domain separation, so one namespace's draw cannot leak into another's",
    )
    # --- canonical serialization: a tuple and a list are the same identity
    check(
        "canonical form is stable across tuple/list spelling",
        MC.rank_key("p", ("region", "sha", 1, 2)),
        MC.rank_key("p", ["region", "sha", 1, 2]),
    )

    # --- THE NEGATIVE CONTROL: sampling must not depend on the blind-id scheme.
    finals = [MC.r1_repeat_identity(r) for r in regions[:4]] + regions
    before = {
        "audit": MC.select("cframe-audit", regions, 4),
        "r1": MC.select("r1-repeat", regions, 3),
        "order": MC.order("blind-order", finals),
    }
    real_blind = MC.blind_id
    try:
        MC.blind_id = lambda ident: "SCHEME2-" + real_blind(ident)[::-1]  # a totally different alias scheme
        after = {
            "audit": MC.select("cframe-audit", regions, 4),
            "r1": MC.select("r1-repeat", regions, 3),
            "order": MC.order("blind-order", finals),
        }
    finally:
        MC.blind_id = real_blind
    check(
        "changing the blind-ID scheme changes NO selection and NO presentation rank",
        before,
        after,
        "sampling ranks canonical pre-blinding identities; the blind id is an alias only",
    )
    check(
        "...and the alias itself did change, so the control is not vacuous",
        True,
        real_blind(regions[0]) != ("SCHEME2-" + real_blind(regions[0])[::-1]),
    )
    check("blind ids are unique across distinct stimuli", len(finals), len({real_blind(f) for f in finals}))

    # --- A30.5: uniqueness over the REALIZED set, and a collision must ABORT the build.
    check(
        "the realized-set check passes on a clean stimulus set",
        len(finals),
        len(MC.assert_realized_blind_ids_unique(finals)),
    )

    def raised(fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the class IS the assertion
            return type(exc).__name__
        return None

    # COLLISION INJECTION. Without this the check has never once produced a positive
    # result, so a green run could not distinguish "no collision" from "cannot detect one".
    collided = MC.blind_id
    try:
        MC.blind_id = lambda ident: "CONSTANT"
        outcome = raised(lambda: MC.assert_realized_blind_ids_unique(finals))
    finally:
        MC.blind_id = collided
    check(
        "an injected blind-ID collision aborts the build",
        "BlindIdCollision",
        outcome,
        "no overwrite, merge, last-write-wins, salt or re-roll is permitted",
    )
    check(
        "a duplicated stimulus identity aborts the build",
        "DuplicateStimulusIdentity",
        raised(lambda: MC.assert_realized_blind_ids_unique([finals[0], finals[0]])),
    )
    check(
        "...and the collision injection did not leak past its scope",
        len(finals),
        len(MC.assert_realized_blind_ids_unique(finals)),
    )


def part_dpi() -> None:
    check("primary stimuli render at exactly 300 dpi", 300, MC.required_dpi(False))
    check("R1 repeats render at exactly 330 dpi", 330, MC.required_dpi(True))
    check("the R1 scale is the frozen 300 x 1.10", 330, int(round(300 * 1.10)))
    check(
        "primary and repeat scales differ, so R1 is a re-render and not a cache hit",
        True,
        MC.required_dpi(True) != MC.required_dpi(False),
    )


def main() -> int:
    print("== 4.5 adequacy ==")
    part_adequacy()
    print("\n== A27.7 / A28.3 determinism ==")
    part_determinism()
    print("\n== A28.4 renderer scale ==")
    part_dpi()
    doc = {
        "population": "SYNTHETIC only -- no PDF opened, no architecture run, nothing scored",
        "adequacy_kinds": sorted(MC.ADEQUACY_KINDS),
        "selection_seed": MC.SELECTION_SEED,
        "primary_dpi": MC.PRIMARY_DPI,
        "r1_repeat_dpi": MC.R1_REPEAT_DPI,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} tests pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
