"""x23 -- A39.3 / A40: the N-A/N-B/N-C source fixtures, their manifest, and the G6 validator.

NOT CONFIRMATORY. DEVELOPMENT + SYNTHETIC only. No holdout material appears anywhere in the
fixture chain, nothing is adjudicated or scored, and no canonical confirmatory artifact is
created. Evidence: `results/x23_control_fixtures.json`.

The A40 contract fixed every rule and control below BEFORE this probe existed. Each control
states the fact that would make it fail, and every G6 negative independently mutates a VALID
manifest -- so a validator that silently accepted anything would be caught rather than flattered.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import control_fixtures as CF  # noqa: E402

OUT = EV / "results" / "x23_control_fixtures.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def reasons(defects) -> list[str]:
    return sorted({d["reason"] for d in defects})


def part_mutations() -> dict:
    """A40.2/A40.4/A40.5 -- the three classes, proven structurally on synthetic strings."""
    print("\n== A40: the three mutation classes are LIVE ==")
    before = "SALARIES AND EXPENSES"
    d_after, _ = CF.delete_one_word(before)
    w_after, _ = CF.weld_two_words(before)
    s_after, _ = CF.split_one_word(before)

    d = CF.mutation_evidence(before, d_after, CF.DELETE_ONE_WORD)
    w = CF.mutation_evidence(before, w_after, CF.WELD_TWO_WORDS)
    s = CF.mutation_evidence(before, s_after, CF.SPLIT_ONE_WORD)

    check(
        "DELETE changes the NON-SPACE character sequence",
        (True, False),
        (d["live"], d["non_space_unchanged"]),
        "deleting a word leaves the non-space sequence intact, i.e. nothing was removed",
    )
    check(
        "WELD leaves non-space identical and removes exactly ONE boundary (1 -> 0)",
        (True, True, [[1, 0]]),
        (w["live"], w["non_space_unchanged"], w["boundary_transitions"]),
        "weld changed a character, or moved more than one boundary -- it would then be a "
        "content corruption rather than the missing-boundary class M3 distinguishes",
    )
    check(
        "SPLIT leaves non-space identical and inserts exactly ONE boundary (0 -> 1)",
        (True, True, [[0, 1]]),
        (s["live"], s["non_space_unchanged"], s["boundary_transitions"]),
        "split changed a character, or moved more than one boundary",
    )
    check(
        "SPLIT is the exact complement of WELD",
        ([[0, 1]], [[1, 0]]),
        (s["boundary_transitions"], w["boundary_transitions"]),
        "the two classes are not complementary, so N-A no longer spans both M3 directions",
    )
    check(
        "the SPLIT example matches the A40.2 illustration",
        "SALA RIES AND EXPENSES",
        s_after,
        "the frozen floor(len/2) target produces a different string than A40.2 specifies",
    )
    dead = CF.mutation_evidence(before, before, CF.SPLIT_ONE_WORD)
    check(
        "NEGATIVE -- a DEAD mutation (before == after) is not live",
        (False, False),
        (dead["live"], dead["changed"]),
        "an unchanged string is accepted as a mutation, which is exactly the A39.3 failure "
        "the size control was retired for",
    )
    check(
        "NEGATIVE -- the RETIRED size variant can never be live",
        False,
        CF.mutation_evidence(before, before, CF.RETIRED_VARIANT)["live"],
        "PULL_HEADING_TO_BODY_SIZE is still treated as a valid mutation class",
    )
    check(
        "both SPLIT pieces are at least 3 characters",
        True,
        all(len(p) >= CF.MIN_SPLIT_PIECE for p in CF.split_one_word(before)[1]["pieces"]),
        "a split leaves a 1-2 character fragment, which is a different failure mode",
    )
    return {"before": before, "delete": d_after, "weld": w_after, "split": s_after}


def part_manifest(manifest: dict) -> dict:
    """The realized fixtures, and what the generated PDFs actually print."""
    print("\n== A39.3/A40: the realized fixture set ==")
    na = [f for f in manifest["fixtures"] if f["control_kind"] == "N-A"]
    nb = [f for f in manifest["fixtures"] if f["control_kind"] == "N-B"]
    nc = [f for f in manifest["fixtures"] if f["control_kind"] == "N-C"]

    check(
        "the manifest holds exactly 8 N-A, 8 N-B, 4 N-C",
        {"N-A": 8, "N-B": 8, "N-C": 4},
        manifest["counts"],
        "a control class is under- or over-populated, so a Rule 3 blocker is not satisfied",
    )
    allocation = {v: sum(1 for f in na if f["variant"] == v) for v in CF.NA_VARIANTS}
    check(
        "N-A realizes the frozen 3 / 3 / 2 allocation",
        CF.NA_EXPECTED_ALLOCATION,
        allocation,
        "the index-mod-3 schedule was not applied, so the three M3 directions are not balanced as A40.1 freezes them",
    )
    check(
        "every N-A mutation is LIVE on the realized fixtures",
        (8, True),
        (len(na), all(f["mutation_evidence"]["live"] for f in na)),
        "a realized control cannot fire, so it reports coverage the study does not have",
    )
    check(
        "the RETIRED variant appears nowhere in the realized set",
        [],
        [f["canonical_identity"] for f in na if f["variant"] == CF.RETIRED_VARIANT],
        "PULL_HEADING_TO_BODY_SIZE survived the A40 retirement",
    )
    check(
        "every N-C expects EXACTLY no headings",
        [[] for _ in nc],
        [f["expected_adjudicated_headings"] for f in nc],
        "a constructionally heading-free region expects a heading, so the over-triggering control could never fail",
    )
    check(
        "every N-A and N-B carries paired GPO XML corroboration",
        (16, 16),
        (len(na) + len(nb), sum(1 for f in na + nb if f.get("xml_evidence") and f.get("xml_sha256"))),
        "a control's truth rests on something other than the independent source -- in the "
        "worst case on H or X's own output",
    )
    check(
        "all 20 control identities are unique",
        20,
        len({f["canonical_identity"] for f in manifest["fixtures"]}),
        "two controls share an identity, so one would silently overwrite the other",
    )

    # WHAT THE GENERATED PDF ACTUALLY PRINTS -- the recipe is truth, but a fixture whose
    # rendering did not take would hand the adjudicator the UNMUTATED heading.
    import pymupdf

    printed_ok, original_gone = [], []
    for f in na:
        doc = pymupdf.open(str(EV / f["generated_path"]))
        try:
            text = " ".join(doc[f["page_number"] - 1].get_text().split())
        finally:
            doc.close()
        printed_ok.append(" ".join(f["expected_after"].split()) in text)
        original_gone.append(" ".join(f["expected_before"].split()) not in text)
    check(
        "every generated N-A PDF actually PRINTS the mutated heading",
        (8, True),
        (len(printed_ok), all(printed_ok)),
        "the mutation did not reach the page, so the adjudicator would transcribe something "
        "other than the committed truth",
    )
    check(
        "...and the ORIGINAL heading is gone from that page",
        (8, True),
        (len(original_gone), all(original_gone)),
        "the unmutated heading survives alongside the mutation, so the region shows both and "
        "the control cannot distinguish an oracle that saw the alteration",
    )
    return {
        "counts": manifest["counts"],
        "allocation": allocation,
        "eligible_population": manifest["eligible_population"],
        "na": [
            {
                "index": f["schedule_index"],
                "variant": f["variant"],
                "source": f["source_document"],
                "page": f["page_number"],
                "before": f["expected_before"],
                "after": f["expected_after"],
                "boundary_transitions": f["mutation_evidence"]["boundary_transitions"],
                "non_space_unchanged": f["mutation_evidence"]["non_space_unchanged"],
                "generated_sha256": f["generated_sha256"][:16],
            }
            for f in na
        ],
        "nb": [
            {
                "index": f["schedule_index"],
                "source": f["source_document"],
                "page": f["page_number"],
                "expected_text": f["expected_adjudicated_headings"][0]["text"],
                "xml_path": f["xml_path"],
                "xml_sha256": f["xml_sha256"][:16],
            }
            for f in nb
        ],
        "nc": [
            {"index": f["schedule_index"], "generated_sha256": f["generated_sha256"][:16], "expected": []} for f in nc
        ],
    }


def part_g6(manifest: dict) -> dict:
    """A39.4 -- G6's validator, with every required negative independently injected."""
    print("\n== A39.4: G6 validation, positive and negative ==")
    check(
        "G6 PASSES on the realized manifest",
        [],
        CF.validate_manifest(manifest),
        "the validator rejects a correctly built fixture set, so it could never authorize one",
    )

    def injected(mutate) -> list[str]:
        broken = copy.deepcopy(manifest)
        mutate(broken)
        return reasons(CF.validate_manifest(broken))

    def first_na(m):
        return next(f for f in m["fixtures"] if f["control_kind"] == "N-A")

    def drop(kind):
        def go(m):
            for i, f in enumerate(m["fixtures"]):
                if f["control_kind"] == kind:
                    del m["fixtures"][i]
                    m["counts"][kind] -= 1
                    return

        return go

    negatives = {
        "N-A count wrong": (drop("N-A"), "WRONG_CONTROL_COUNT"),
        "N-B count wrong": (drop("N-B"), "WRONG_CONTROL_COUNT"),
        "N-C count wrong": (drop("N-C"), "WRONG_CONTROL_COUNT"),
        "N-A allocation wrong": (
            lambda m: first_na(m).update(variant=CF.WELD_TWO_WORDS),
            "WRONG_NA_ALLOCATION",
        ),
        "RETIRED size variant reintroduced": (
            lambda m: first_na(m).update(variant=CF.RETIRED_VARIANT),
            "RETIRED_VARIANT_PRESENT",
        ),
        "N-A mutation before == after": (
            lambda m: first_na(m).update(expected_after=first_na(m)["expected_before"]),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "WELD changes non-space characters": (
            lambda m: _set_variant(m, CF.WELD_TWO_WORDS, lambda f: f.update(expected_after="TOTALLY DIFFERENT TEXT")),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "SPLIT changes non-space characters": (
            lambda m: _set_variant(m, CF.SPLIT_ONE_WORD, lambda f: f.update(expected_after="TOTALLY DIFFERENT TEXT")),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "WELD moves more than one boundary": (
            lambda m: _set_variant(
                m, CF.WELD_TWO_WORDS, lambda f: f.update(expected_after=f["expected_before"].replace(" ", ""))
            ),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "SPLIT moves a boundary the wrong way": (
            lambda m: _set_variant(
                m, CF.SPLIT_ONE_WORD, lambda f: f.update(expected_after=f["expected_before"].replace(" ", "", 1))
            ),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "stale source SHA": (lambda m: first_na(m).update(source_sha256="0" * 64), "STALE_SHA256"),
        "stale generated PDF SHA": (lambda m: first_na(m).update(generated_sha256="0" * 64), "STALE_SHA256"),
        "duplicate control identity": (
            lambda m: m["fixtures"][1].update(canonical_identity=m["fixtures"][0]["canonical_identity"]),
            "DUPLICATE_CONTROL_IDENTITY",
        ),
        "missing expected truth": (
            lambda m: first_na(m).update(expected_adjudicated_headings=[]),
            "MISSING_EXPECTED_TRUTH",
        ),
        "N-B missing XML corroboration": (
            lambda m: _set_kind(m, "N-B", lambda f: f.update(xml_evidence=None, xml_sha256=None)),
            "MISSING_XML_CORROBORATION",
        ),
        "N-C expected headings non-empty": (
            lambda m: _set_kind(m, "N-C", lambda f: f.update(expected_adjudicated_headings=[{"text": "X"}])),
            "NC_EXPECTED_HEADINGS_NOT_EMPTY",
        ),
        "holdout provenance in the chain": (
            lambda m: first_na(m).update(source_document="116-hr-7611/1"),
            "HOLDOUT_PROVENANCE",
        ),
        "mutation recipe disagrees with variant": (
            lambda m: first_na(m).update(mutation_recipe={"variant": CF.SPLIT_ONE_WORD}),
            "MUTATION_RECIPE_VARIANT_MISMATCH",
        ),
    }
    results = {}
    for label, (mutate, expected_reason) in negatives.items():
        got = injected(mutate)
        results[label] = {"expected": expected_reason, "fired": expected_reason in got, "reasons": got}
    check(
        "EVERY injected defect makes G6 FAIL with its own reason",
        {k: True for k in negatives},
        {k: v["fired"] for k, v in results.items()},
        "an injected defect passes validation -- a green G6 would then certify a fixture set "
        "that cannot satisfy its Rule 3 blockers",
    )

    # the stale-hash negatives must react to real BYTES, not just a changed string
    on_disk = copy.deepcopy(manifest)
    target = next(f for f in on_disk["fixtures"] if f["control_kind"] == "N-A")
    generated = EV / target["generated_path"]
    original_bytes = generated.read_bytes()
    try:
        generated.write_bytes(original_bytes + b"\n% mutated after the manifest was written\n")
        byte_defects = reasons(CF.validate_manifest(on_disk))
    finally:
        generated.write_bytes(original_bytes)
    check(
        "NEGATIVE -- changing the generated PDF BYTES with a stale manifest hash FAILS",
        True,
        "STALE_SHA256" in byte_defects,
        "the validator compares recorded strings rather than recomputing from the file, so a "
        "silently edited fixture would keep certifying",
    )
    check(
        "...and restoring the bytes makes G6 pass again",
        [],
        CF.validate_manifest(on_disk),
        "the byte-level control left the fixture set permanently invalid",
    )
    return {"negatives": {k: {"expected": v["expected"], "fired": v["fired"]} for k, v in results.items()}}


def _set_variant(manifest, variant, mutate):
    mutate(next(f for f in manifest["fixtures"] if f.get("variant") == variant))


def _set_kind(manifest, kind, mutate):
    mutate(next(f for f in manifest["fixtures"] if f["control_kind"] == kind))


def main() -> int:
    mutations = part_mutations()
    manifest = CF.build_manifest()
    CF.write_manifest(manifest)
    realized = part_manifest(manifest)
    g6 = part_g6(manifest)

    doc = {
        "population": "DEVELOPMENT + SYNTHETIC -- no confirmatory holdout material anywhere",
        "contract": "A39.3 (control sources) as amended by A40 (live boundary control)",
        "manifest": str(CF.MANIFEST_PATH.relative_to(EV)),
        "mutation_classes": mutations,
        "realized": realized,
        "g6": g6,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
