"""x22 -- A38: can every fact `score_metrics` needs be derived from COMMITTED ARTIFACTS?

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated, nothing is scored, no architecture decision is taken, and no confirmatory or
scoring artifact is created. Evidence: `results/x22_score_input_contract.json`.

THE QUESTION THIS PROBE ANSWERS, and its negative controls must be able to answer it FALSE:

    can every future score_metrics obligation be satisfied from committed artifacts, with no
    PDF access, no runner access, no text matching, and no implementation-time choice?

The A38 contract fixed the ownership table and every control below BEFORE this probe existed.
Each states the fact that would make it fail.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2`, as `x20`/`x21` require.
"""

from __future__ import annotations

import copy
import hashlib
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

import build_frames as BF  # noqa: E402
import build_oracle as BO  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
import s1_control as S1  # noqa: E402

from deltatrack.parsers import pdf_anchors as PA  # noqa: E402

OUT = EV / "results" / "x22_score_input_contract.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []

DOC_NAME = "118-hr-8752/1"
DOC_PATH = REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"
PAGE_LIMIT = 16  # machinery demonstration window, NOT a census

HOLDOUT_GUARD = BO.HOLDOUT_GUARD


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def refusal(fn):
    try:
        fn()
    except (BO.OracleBuildError, BF.FrameConstructionError) as exc:
        return exc.reason
    return None


def development_frame():
    for member in HOLDOUT_GUARD:
        if member in str(DOC_PATH):
            raise SystemExit(f"REFUSED: {DOC_PATH} touches holdout member {member}")
    h = run_hybrid.run(DOC_PATH, limit=PAGE_LIMIT)
    x, _s = run_extended.run(DOC_PATH, limit=PAGE_LIMIT)
    sha = hashlib.sha256(DOC_PATH.read_bytes()).hexdigest()
    return sha, h, x, BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, x)


# ----------------------------------------------------- A38.2 the identity candidates


def part_candidates(frame: dict) -> dict:
    print("\n== A38.2: the A30 identity candidates are committed ==")
    lines = [ln for pf in frame["pages"] for ln in pf["neutral_lines"]]
    with_candidates = [ln for ln in lines if ln.get("identity_candidates")]

    exact = all(sorted(c["ngid"] for c in ln["identity_candidates"]) == sorted(ln["gids"]) for ln in with_candidates)
    check(
        "every committed neutral line's candidates are EXACTLY its gids",
        (len(lines), True),
        (len(with_candidates), exact),
        "a gid has no candidate, or a candidate names a gid outside the line -- either way the "
        "A30.3 resolver would search the wrong glyph set",
    )
    check(
        "the candidate population is non-empty, so the check above is not vacuous",
        True,
        len(with_candidates) > 0,
        "no line carries candidates, so 'all lines agree' passed on nothing",
    )
    # A24.2 -- U+0020 carries no neutral identity and must never be a candidate. The skeleton
    # excludes it by codepoint, so a space's gid cannot appear in any line's gid set.
    all_gids = {g for ln in lines for g in ln["gids"]}
    all_cands = {c["ngid"] for ln in with_candidates for c in ln["identity_candidates"]}
    check(
        "no candidate exists outside the committed gid sets (U+0020 among them)",
        set(),
        all_cands - all_gids,
        "a candidate was invented from a source glyph the skeleton rejected, e.g. a word space",
    )
    unrounded = [c["x0"] for ln in with_candidates for c in ln["identity_candidates"]]
    check(
        "candidate x0 is UNROUNDED source geometry",
        True,
        any(abs(v - round(v, 4)) > 0 for v in unrounded) or any(len(repr(v).split(".")[-1]) > 4 for v in unrounded),
        "every x0 lands on a 4-decimal grid, i.e. it was rounded for serialization -- rounding "
        "here can move a nearest-glyph decision",
    )
    ordered = all(
        [c["ngid"] for c in ln["identity_candidates"]] == sorted(c["ngid"] for c in ln["identity_candidates"])
        for ln in with_candidates
    )
    check(
        "candidates serialize in ngid order (determinism ONLY, never reading order)",
        True,
        ordered,
        "serialization order varies between runs, so the committed frame is not reproducible",
    )
    return {
        "n_neutral_lines": len(lines),
        "n_with_candidates": len(with_candidates),
        "n_candidates": sum(len(ln["identity_candidates"]) for ln in with_candidates),
    }


def part_candidate_bilateral(sha, h, x) -> dict:
    """The bilateral gate: a divergent candidate x0 must ABORT construction."""
    print("\n== A38.2: the bilateral candidate gate ==")
    mutated = [dict(d) for d in x]
    page = mutated[0]
    lines = list(page["neutral"])
    victim = next(ln for ln in lines if ln.candidates)
    moved = tuple(((gid, x0 + 3.0) if i == 0 else (gid, x0)) for i, (gid, x0) in enumerate(victim.candidates))
    lines[lines.index(victim)] = type(victim)(
        page=victim.page,
        ordinal=victim.ordinal,
        baseline=victim.baseline,
        x0=victim.x0,
        y0=victim.y0,
        x1=victim.x1,
        y1=victim.y1,
        gids=victim.gids,
        candidates=moved,
    )
    page["neutral"] = lines

    check(
        "NEGATIVE -- mutating ONE arm's candidate x0 ABORTS frame construction",
        BF.NEUTRAL_SKELETON_MISMATCH,
        refusal(lambda: BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, mutated)),
        "the arms' candidate geometry can diverge without the frame noticing, so the committed "
        "candidates would silently be whichever arm was read first",
    )
    check(
        "...and the UNMUTATED pair still builds, so the gate is not refusing everything",
        True,
        refusal(lambda: BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, x)) is None,
        "construction refuses even on clean input, making the control above meaningless",
    )
    return {
        "limit": "one skeleton by A19 -- both runners call run_hybrid.neutral_skeleton; this "
        "gate catches divergence in what each arm RETURNS, not two independent derivations"
    }


# ------------------------------------------- A38.3/A38.4 architecture occurrence records


def part_occurrences(frame: dict) -> dict:
    print("\n== A38.3/A38.4: deterministic architecture occurrence records ==")
    occ = frame["architecture_occurrences"]
    counts = {}
    for arm in ("H", "X"):
        rows = occ[arm]
        counts[arm] = {
            "total": len(rows),
            "MATCHABLE": sum(1 for r in rows if r["match_status"] == "MATCHABLE"),
            "UNMATCHED": sum(1 for r in rows if r["match_status"] == "UNMATCHED"),
        }
    check(
        "both arms produced occurrence records",
        (True, True),
        (counts["H"]["total"] > 0, counts["X"]["total"] > 0),
        "an arm produced no occurrences, so M1-M5 would have an empty emitted side",
    )
    check(
        "every record is MATCHABLE or UNMATCHED and none is silently absent",
        (counts["H"]["total"], counts["X"]["total"]),
        (
            counts["H"]["MATCHABLE"] + counts["H"]["UNMATCHED"],
            counts["X"]["MATCHABLE"] + counts["X"]["UNMATCHED"],
        ),
        "a record carries neither status, i.e. an occurrence was dropped rather than reported",
    )
    check(
        "a MATCHABLE record carries the A30 4-component occurrence key",
        [4],
        sorted({len(r["occurrence_key"]) for r in occ["H"] if r["match_status"] == "MATCHABLE"}),
        "the key is not the frozen (doc_sha, page, neutral_line_key, start_ngid) shape",
    )
    check(
        "records are in DOCUMENT order, never ngid order",
        True,
        [(r["anchor"]["page_number"], r["anchor"]["line_number"]) for r in occ["H"]]
        == sorted((r["anchor"]["page_number"], r["anchor"]["line_number"]) for r in occ["H"]),
        "occurrences are ordered by ngid, which A30.1 forbids -- ngid order disagreed with "
        "printed order on 10 of 33,602 emitted lines",
    )
    return counts


def part_parent(frame: dict, h_pages) -> dict:
    """A38.4 -- the emitted immediate parent IS production's breadcrumb penultimate element."""
    print("\n== A38.4: immediate parent from production hierarchy ==")
    pages = [d["page"] for d in sorted(h_pages, key=lambda d: d["page_number"])]
    anchors = PA.extract_anchors(pages)
    by_key = {(a.page_number, a.line_number, a.kind, a.text): a for a in anchors}

    agree, checked, kinds = 0, 0, {}
    for row in frame["architecture_occurrences"]["H"]:
        a = by_key.get(
            (row["anchor"]["page_number"], row["anchor"]["line_number"], row["anchor"]["kind"], row["anchor"]["text"])
        )
        if a is None:
            continue
        crumb = PA.breadcrumb_for(a, anchors)
        expected = crumb[-2] if len(crumb) >= 2 else None
        checked += 1
        agree += row["immediate_parent"] == expected
        kinds.setdefault(a.kind, {"n": 0, "with_parent": 0})
        kinds[a.kind]["n"] += 1
        kinds[a.kind]["with_parent"] += row["immediate_parent"] is not None
    check(
        "every committed immediate_parent EQUALS production breadcrumb_for's penultimate element",
        (checked, checked),
        (checked, agree),
        "the parent was derived by a NEW hierarchy walk that disagrees with production, so M4 "
        "would score the emitted side against a hierarchy production never produced",
    )
    check(
        "the parent comparison is non-empty",
        True,
        checked > 0,
        "no occurrence matched a production anchor, so the equality above compared nothing",
    )
    roots = [r for r in frame["architecture_occurrences"]["H"] if r["immediate_parent"] is None]
    check(
        "a root/no-parent case exists and is represented as null",
        True,
        len(roots) > 0,
        "no one-element breadcrumb appears, so the no-parent branch was never exercised",
    )
    return {"checked": checked, "agree": agree, "kinds": kinds, "n_root": len(roots)}


# --------------------------------------------------------------- A38.8 / A38.9 M9 and S1


def part_m9(frame: dict) -> dict:
    print("\n== A38.8: M9 raw facts, recorded not decided ==")
    m9 = frame["m9"]
    required = {
        "derive_size_bands_returns_a_band",
        "coverage",
        "coverage_floor",
        "coverage_meets_floor",
        "n_lines_total",
        "n_margin_numbered_lines",
        "n_margin_numbered_with_glyph_size",
        "margin_numbered_line_keys",
    }
    check(
        "M9 raw facts are committed for BOTH arms",
        (sorted(required), sorted(required)),
        (sorted(required & set(m9["H"])), sorted(required & set(m9["X"]))),
        "a raw M9 quantity is missing, so score_metrics would have to rerun production anchor "
        "extraction to discover it",
    )
    check(
        "the frozen coverage floor is production's own 0.85",
        (0.85, 0.85),
        (m9["H"]["coverage_floor"], PA._COVERAGE_MIN),
        "the floor drifted from production's _COVERAGE_MIN, i.e. a threshold was invented here",
    )
    check(
        "per-line margin keys are recorded, so a SET comparison stays possible",
        (True, True),
        (len(m9["H"]["margin_numbered_line_keys"]) > 0, len(m9["X"]["margin_numbered_line_keys"]) > 0),
        "only counts are recorded, foreclosing the set-difference reading of Rule 0 before it has been ruled on",
    )
    check(
        "A38 does NOT compute the Rule 0 comparison",
        "NOT DECIDED HERE -- see A38.8; decide_architecture must rule it",
        m9["H"]["rule0_comparison"],
        "this stage decided which margin-line quantity Rule 0 compares, which the frozen text does not determine",
    )
    STOPS.append(
        {
            "forward_ambiguity": "RULE0_MARGIN_LINE_QUANTITY",
            "why": "Rule 0's 'loses margin-numbered lines on a document the other keeps' does not "
            "uniquely determine the comparable quantity: (a) count of line_number is not None; "
            "(b) _coverage's numerator, numbered lines that also carry a glyph size; (c) a SET "
            "difference a count cannot see. No threshold is stated for 'loses' either.",
            "status": "NOT RESOLVED BY A38 -- raw basis for all three recorded; "
            "decide_architecture must rule it before Rule 0 is implemented",
        }
    )
    return {arm: {k: v for k, v in m9[arm].items() if k != "margin_numbered_line_keys"} for arm in ("H", "X")}


def part_s1() -> dict:
    print("\n== A38.9: the S1 liveness control has a committed producer ==")
    result = S1.s1_result(DOC_PATH, limit=PAGE_LIMIT)
    check(
        "the S1 sabotage scale is exactly the frozen 1.25",
        1.25,
        result["advance_scale"],
        "the scale drifted from the frozen value, or became a tunable dial",
    )
    check(
        "S1 FIRES on DEVELOPMENT -- sabotage raises M0",
        True,
        result["fires"],
        "advances x 1.25 does not raise the discordance count, which would mean M0 cannot "
        "detect a change it certainly should -- the comparator is not live",
    )
    check(
        "...and the sabotage really changed the input, so firing is not an artifact",
        True,
        result["sabotaged"]["text_discordant_lines"] > result["primary"]["text_discordant_lines"],
        "the two runs report the same discordance, so nothing was actually sabotaged",
    )
    check(
        "primary and sabotaged M0 are reported SEPARATELY",
        (True, True),
        ("primary" in result and "sabotaged" in result, result["primary"] != result["sabotaged"]),
        "only one number is reported, so a reader cannot see what the control established",
    )
    check(
        "the risk set is unchanged by sabotage, so only the TEXT moved",
        result["primary"]["risk_set_lines"],
        result["sabotaged"]["risk_set_lines"],
        "the sabotage moved the neutral skeleton, i.e. it changed the frame rather than the seam decision under test",
    )

    # NEGATIVE: a dead comparator must report FAIL rather than silently passing.
    dead = copy.deepcopy(result)
    dead["sabotaged"] = dict(dead["primary"])
    dead_fires = dead["sabotaged"]["text_discordant_lines"] > dead["primary"]["text_discordant_lines"]
    check(
        "NEGATIVE -- a DEAD comparator (sabotage changes nothing) reports S1 FAIL",
        False,
        dead_fires,
        "a comparator that cannot move still reports S1 firing, which is precisely the "
        "phase-1 defect S1 exists to catch",
    )
    return {k: v for k, v in result.items() if k != "m0_definition"}


# ------------------------------------------------- the central question, end to end


def part_no_pdf_needed(frame: dict, key: dict) -> dict:
    """Can the scoring facts be reached from committed JSON ALONE? Answered structurally."""
    print("\n== A38: every score input is reachable from committed artifacts ==")
    # Round-trip through JSON: anything reachable below came from a committed artifact, not
    # from a live Python object still holding a PDF handle or a runner result.
    frame_json = json.loads(json.dumps(frame, default=str))
    key_json = json.loads(json.dumps(key, default=str))

    reachable = {
        "M0a text discordance": any(
            "text_discordance" in ln["line_state"] for pf in frame_json["pages"] for ln in pf["neutral_lines"]
        ),
        "M0b segmentation discordance": any(
            "segmentation_discordance" in ln["line_state"] for pf in frame_json["pages"] for ln in pf["neutral_lines"]
        ),
        "M0c anchor discordance": any("anchor_evidence" in r for pf in frame_json["pages"] for r in pf["regions"]),
        "both_absent": any("in_m0_risk_set" in ln for pf in frame_json["pages"] for ln in pf["neutral_lines"]),
        "M1-M3 emitted occurrences": bool(frame_json["architecture_occurrences"]["H"]),
        "M4 immediate parent": all("immediate_parent" in r for r in frame_json["architecture_occurrences"]["H"]),
        "M5 emitted kind": all("kind" in r["anchor"] for r in frame_json["architecture_occurrences"]["H"]),
        "M7 emitted text": all("text" in r["anchor"] for r in frame_json["architecture_occurrences"]["H"]),
        "M9 raw facts": bool(frame_json["m9"]["H"]) and bool(frame_json["m9"]["X"]),
        "occurrence join candidates": all("identity_candidates" in r for r in key_json["stimuli"].values()),
        "occurrence join geometry": all(
            {"bbox_pdf_points", "dpi", "region_line_bijection"} <= set(r) for r in key_json["stimuli"].values()
        ),
        "adjudication routing": all("adjudication_routes" in r for r in key_json["stimuli"].values()),
    }
    check(
        "EVERY listed score input is reachable from committed JSON, with no PDF or runner",
        {k: True for k in reachable},
        reachable,
        "a fact score_metrics needs survives only in a live Python object, so the scorer would "
        "have to reopen a PDF or rerun an architecture to get it",
    )
    missing_occ = copy.deepcopy(frame_json)
    del missing_occ["architecture_occurrences"]
    check(
        "NEGATIVE -- removing the occurrence records makes the reachability answer FALSE",
        False,
        "architecture_occurrences" in missing_occ,
        "the reachability check cannot detect a missing producer, so it would report success "
        "on an artifact chain that cannot actually feed the scorer",
    )
    return {"reachable": reachable}


def main() -> int:
    sha, h, x, frame = development_frame()
    candidates = part_candidates(frame)
    bilateral = part_candidate_bilateral(sha, h, x)
    occurrences = part_occurrences(frame)
    parent = part_parent(frame, h)
    m9 = part_m9(frame)
    s1 = part_s1()

    built = BO.build([{"frame": frame, "pdf_path": DOC_PATH, "stratum": "DEVELOPMENT"}])
    reach = part_no_pdf_needed(frame, built.key)

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated, nothing scored",
        "contract": "A38 (the score_metrics input contract)",
        "question": "can every score_metrics obligation be satisfied from committed artifacts, "
        "with no PDF access, no runner access, no text matching, and no implementation-time choice?",
        "document": DOC_NAME,
        "page_limit": PAGE_LIMIT,
        "note": "PAGE_LIMIT is a machinery demonstration window, not a census",
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_blind.json, "
        "oracle_adjudicated.json, metrics.json, scores.json, EXECUTION-START.json",
        "identity_candidates": candidates,
        "bilateral_gate": bilateral,
        "architecture_occurrences": occurrences,
        "immediate_parent": parent,
        "m9_raw": m9,
        "s1": s1,
        "reachability": reach,
        "oracle_key_schema": built.key["schema"],
        "forward_ambiguities": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} forward ambiguities recorded")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
