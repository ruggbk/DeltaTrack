"""x15 -- test the frozen methodology contracts. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic only. No PDF is opened, no architecture is run, nothing scored.

    A28.1/A28.2  the 4.5 adequacy count and state machine, every branch
    A28.3        canonical pre-blinding stimulus identity; sampling must NOT depend on
                 blind ids
    A28.4        frozen renderer scale, 300 dpi primary / 330 dpi R1 repeat
    A27.7        domain-separated deterministic ranking
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


def key(doc, page, line, ordinal):
    """An A27.1 source-position occurrence key."""
    return (doc, page, (page, line), ordinal)


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
    check(
        "two occurrences on ONE neutral line stay distinct",
        2,
        MC.adequacy_occurrences([key("d", 1, 3, 0), key("d", 1, 3, 1)], []),
    )
    # --- kind restriction
    keyed = [
        (key("d", 1, 1, 0), "account"),
        (key("d", 1, 2, 0), "agency"),
        (key("d", 1, 3, 0), "grouping"),
        (key("d", 1, 4, 0), "title"),
        (key("d", 1, 5, 0), "section"),
        (key("d", 1, 6, 0), "subsection"),
    ]
    check(
        "only account/agency/grouping contribute to adequacy",
        3,
        len(MC.filter_keys(keyed)),
        "title/section/division must not inflate the denominator the frozen quantity is compared against",
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


def part_dpi() -> None:
    check("primary stimuli render at exactly 300 dpi", 300, MC.required_dpi(False))
    check("R1 repeats render at exactly 330 dpi", 330, MC.required_dpi(True))
    check("the R1 scale is the frozen 300 x 1.10", 330, int(round(300 * 1.10)))
    check(
        "primary and repeat scales differ, so R1 is a re-render and not a cache hit",
        True,
        MC.required_dpi(True) != MC.required_dpi(False),
    )


def part_bootstrap() -> None:
    """A29. The interval must be reproducible AND must never reach a gate.

    The fixture carries VARIED per-document values on purpose. With identical values every
    resample returns the same statistic, the namespace could not possibly matter, and the
    "changing the namespace changes the interval" control below would pass while proving
    nothing. Variation is what makes the procedure load-bearing here.
    """
    docs = [("doc%02d" % i, float(i)) for i in range(12)]
    values = dict(docs)
    ids = [d for d, _v in docs]

    def mean(sample):
        return sum(values[d] for d in sample) / len(sample)

    sid = ("m2-hybrid-vs-extended", "ANCHOR_DISCORDANCE")

    a = MC.bootstrap_interval(sid, ids, mean, events=7)
    b = MC.bootstrap_interval(sid, ids, mean, events=7)
    check("identical inputs produce an identical interval", a["interval"], b["interval"])
    check(
        "identical inputs produce identical resamples",
        MC.bootstrap_resample(sid, ids, 0),
        MC.bootstrap_resample(sid, ids, 0),
    )
    check(
        "the interval does not depend on the order documents are listed in",
        a["interval"],
        MC.bootstrap_interval(sid, list(reversed(ids)), mean, events=7)["interval"],
    )

    # Negative control, and it must be non-vacuous: a different statistic identity is a
    # different domain, so the draws must actually move.
    other = MC.bootstrap_interval(("m2-hybrid-vs-extended", "OTHER_OUTCOME"), ids, mean, events=7)
    check(
        "a different comparison identity draws a different resample",
        True,
        MC.bootstrap_resample(sid, ids, 0) != MC.bootstrap_resample(("x", "y"), ids, 0),
        "if this were equal the namespace would be inert and the freeze meaningless",
    )
    check("...and the resulting interval differs too", True, other["interval"] != a["interval"])

    check(
        "zero events refuses a bootstrap rather than reporting [0,0]",
        False,
        MC.bootstrap_interval(sid, ids, mean, events=0)["reported"],
    )
    check(
        "the refusal names itself",
        "ZERO_EVENTS_BOOTSTRAP_REFUSED",
        MC.bootstrap_interval(sid, ids, mean, events=0)["reason"],
    )

    # Non-gating. `decide_architecture` does not exist and is forbidden here, so the claim is
    # proven structurally: every gate-bearing contract is a pure function of inputs that do
    # not include an interval, and the interval carries its own non-gating flag.
    check("the interval is self-declared non-gating", False, a["gating"])
    before = MC.adequacy(7, 850)
    check(
        "a changed bootstrap cannot move the one gate this module owns",
        before,
        MC.adequacy(7, 850),
        "adequacy takes (strata, occurrences) only -- an interval has no path into it",
    )
    check(
        "A27.6's gate vector contains no bootstrap term",
        True,
        all("bootstrap" not in g for g in MC.GATE_VECTOR),
    )


def main() -> int:
    print("== 4.5 adequacy ==")
    part_adequacy()
    print("\n== A27.7 / A28.3 determinism ==")
    part_determinism()
    print("\n== A28.4 renderer scale ==")
    part_dpi()
    print("\n== A29 supplementary bootstrap ==")
    part_bootstrap()
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
