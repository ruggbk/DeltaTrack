"""x21 -- A35: the adjudicator prompt and `build_oracle`, with executable controls.

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated, nothing is scored, and no confirmatory oracle artifact is created. Evidence:
`results/x21_build_oracle.json`.

The A35 contract fixed every rule and control below BEFORE this probe existed. Each control
states the fact that would make it FAIL, and no control compares a helper with itself where an
independent mutation or injection was possible: the leakage gate is falsified by injecting
forbidden content, the join by misassociating the key, the blind-id scheme by replacing it
wholesale, and each fail-closed geometry refusal by corrupting committed geometry.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2` (pinned to the project's
version), exactly as `x20` requires -- `pymupdf` is deliberately absent from the project venv.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pymupdf

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
import methodology_contracts as MC  # noqa: E402
import oracle_geometry as OG  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402

OUT = EV / "results" / "x21_build_oracle.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
]
PAGE_LIMIT = 20  # machinery demonstration, NOT a census -- every count below is reported as-is


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def refusal(fn) -> str | None:
    """The refusal class a callable raises, or None if it returned. Never swallows the reason."""
    try:
        fn()
    except (BO.OracleBuildError, OG.OracleGeometryError) as exc:
        return exc.reason
    except (MC.BlindIdCollision, MC.DuplicateStimulusIdentity) as exc:
        return type(exc).__name__
    return None


# ------------------------------------------------------------------ synthetic material


# One 8-line region per synthetic page. 20 is not decorative: the R1 draw takes
# floor(n * 0.10), so a smaller fixture yields ZERO repeats and controls 2, 3, 8, 12 and 20
# then pass on an empty population -- which is how a vacuous control suite looks. The
# non-vacuity guards beside those controls exist to make that failure visible rather than green.
N_SYNTHETIC_REGIONS = 20
SYNTHETIC_LINES_PER_REGION = 8


def synthetic_pdf(tmp: Path, rotation: int = 0, n_pages: int = N_SYNTHETIC_REGIONS) -> Path:
    """A deterministic multi-page PDF whose geometry we choose, so injections are exact."""
    doc = pymupdf.open()
    for p in range(n_pages):
        page = doc.new_page(width=612, height=792)
        for i in range(SYNTHETIC_LINES_PER_REGION):
            page.insert_text((100.0, 120.0 + i * 20.0), f"SYNTHETIC HEADING P{p} LINE {i}", fontsize=11)
        if rotation:
            page.set_rotation(rotation)
    path = tmp / f"synthetic_{rotation}_{n_pages}.pdf"
    doc.save(path)
    doc.close()
    return path


def synthetic_page_frame(page_number: int) -> dict:
    lines, keys = [], []
    for i in range(SYNTHETIC_LINES_PER_REGION):
        baseline = 792.0 - (120.0 + i * 20.0)
        bbox = [100.0, baseline - 3.0, 300.0, baseline + 9.0]
        lines.append(
            {
                "key": [page_number, i],
                "baseline": baseline,
                "bbox": bbox,
                "gids": [i * 10],
                "region_ordinal": 0,
                "in_m0_risk_set": True,
                "line_state": {"state": "BOTH_PRESENT", "h_text": f"LINE {i}", "x_text": f"LINE {i}"},
            }
        )
        keys.append([page_number, i])
    return {
        "page_number": page_number,
        "neutral_lines": lines,
        "regions": [
            {
                "page_number": page_number,
                "region_ordinal": 0,
                "neutral_line_keys": keys,
                "short_trailing": False,
                "line_count": SYNTHETIC_LINES_PER_REGION,
                "d_frame": False,
                "d_reasons": [],
                "c_frame": True,
            }
        ],
    }


def synthetic_frame(
    document_sha256="synthsha0123456789", document_id="SYNTHETIC/1", n_pages: int = N_SYNTHETIC_REGIONS
) -> dict:
    """A frame in `build_frames`' emitted shape, with bboxes we control exactly."""
    return {
        "document": document_id,
        "document_sha256": document_sha256,
        "population": BF.P_HEAD,
        "region_size": SYNTHETIC_LINES_PER_REGION,
        "pages": [synthetic_page_frame(p + 1) for p in range(n_pages)],
    }


def synthetic_documents(tmp: Path, rotation: int = 0, n_pages: int = N_SYNTHETIC_REGIONS) -> list[dict]:
    return [
        {
            "frame": synthetic_frame(n_pages=n_pages),
            "pdf_path": synthetic_pdf(tmp, rotation, n_pages),
            "stratum": "SYNTHETIC",
            "architecture_output": {f"{p + 1}:0": {"H": ["LINE 0"], "X": ["LINE 0"]} for p in range(n_pages)},
        }
    ]


# --------------------------------------------------------------- the prompt controls


def part_prompt() -> dict:
    print("\n== the adjudicator prompt: what it asks, and what it must never say ==")
    text = BO.PROMPT_PATH.read_text()
    report = BO.prompt_report(text)

    check(
        "18. the prompt asks NO M6 / amount-attribution question",
        [],
        report["m6_questions"],
        "an amount-to-account or total-the-figures question appears; M6 is deferred by A20",
    )
    check(
        "19. the prompt carries the A33.5 visible-character instruction",
        True,
        "first character's own visible ink" in text and "strike-through" in text,
        "the A33.5 wording is missing, so start_x_px would be collected under a different "
        "definition and nothing downstream could tell",
    )
    check(
        "the prompt forbids a text-box / bounding-box edge (A33.5)",
        True,
        "text-box" in text,
        "an adjudicator could mark a bounding-box edge instead of the character's own ink",
    )
    check(
        "the prompt says start_x_px is an identity annotation only",
        True,
        "position annotation" in text,
        "start_x_px could be read as evidence about text, parent or role",
    )
    check(
        "the prompt requires text, parent and role to be judged independently",
        True,
        "judged independently" in text or "independently of it" in text,
        "one field could be adjusted to agree with another",
    )
    check(
        "the prompt leaks no forbidden architecture / frame / stratum / control token",
        [],
        report["forbidden"],
        "any of H/X, hybrid, extended glyph, architecture, C/D-frame, stratum, control status, "
        "repeat status or DPI appears in the adjudicator's instructions",
    )
    check(
        "the prompt carries every required instruction",
        [],
        report["missing_required"],
        "a required question or instruction is absent",
    )
    check(
        "the committed prompt LOADS -- the gate accepts it",
        True,
        refusal(lambda: BO.load_prompt()) is None,
        "the committed prompt is refused by its own gate",
    )

    # THE NEGATIVE CONTROLS. A gate that has never rejected anything is not evidence.
    injections = {
        "architecture name": "The hybrid architecture produced this text.",
        "arm letter": "Compare arm H against arm X.",
        "frame label": "This is a C-frame region.",
        "stratum": "Stratum: appropriations-house.",
        "control status": "This is a negative control item.",
        "repeat status": "This is the R1 reliability repeat.",
        "render scale": "Rendered at 300 dpi.",
        "engine name": "Extracted with pypdfium2.",
    }
    caught = {}
    for label, snippet in injections.items():
        caught[label] = bool(BO.scan_forbidden(text + "\n" + snippet))
    check(
        "10a. NEGATIVE -- every injected forbidden disclosure is CAUGHT by the prompt gate",
        {k: True for k in injections},
        caught,
        "an injected architecture / frame / stratum / control / scale disclosure passes the gate, "
        "which would mean the gate cannot see the leak it exists to stop",
    )

    m6_injection = "Also report which account each dollar amount belongs to."
    check(
        "10b. NEGATIVE -- an injected M6 question is CAUGHT",
        True,
        bool(BO.prompt_report(text + "\n" + m6_injection)["m6_questions"]),
        "an amount-attribution question could be added without the gate firing",
    )
    stripped = text.replace("first character's own visible ink", "first character")
    check(
        "10c. NEGATIVE -- removing the A33.5 wording makes the completeness gate FAIL",
        True,
        "a33_5_visible_ink" in BO.prompt_report(stripped)["missing_required"],
        "the required-instruction gate cannot detect the A33.5 instruction going missing",
    )
    check(
        "...and a prompt carrying an injected leak is REFUSED, not merely reported",
        BO.PROMPT_LEAKS,
        refusal(lambda: _load_text(text + "\nCompare arm H against arm X.")),
        "load_prompt returns a leaking prompt instead of refusing it",
    )
    return {
        "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "prompt_chars": len(text),
        "forbidden_patterns_checked": sorted(BO.FORBIDDEN_PATTERNS),
        "required_instructions_checked": sorted(BO.REQUIRED_INSTRUCTIONS),
        "injections_caught": caught,
    }


def _load_text(text: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "p.md"
        p.write_text(text)
        return BO.load_prompt(p)


# ------------------------------------------------------- selection / blinding controls


def part_blinding(tmp: Path) -> dict:
    print("\n== selection, blind ids, and presentation order ==")
    docs = synthetic_documents(tmp)
    result = BO.build(docs)
    specs = BO.plan_document_stimuli(docs[0]["frame"], "SYNTHETIC")
    specs = specs + BO.plan_r1_repeats(specs)

    selected_before = [MC.canonical(s.final_identity) for s in specs]
    order_before = [MC.canonical(s.final_identity) for s in BO.presentation_order(specs)]

    # NEGATIVE: replace the blind-id scheme WHOLESALE, canonical identities held fixed.
    real = MC.blind_id
    try:
        MC.blind_id = lambda ident: "SCHEME2-" + real(ident)[::-1]
        specs2 = BO.plan_document_stimuli(docs[0]["frame"], "SYNTHETIC")
        specs2 = specs2 + BO.plan_r1_repeats(specs2)
        selected_after = [MC.canonical(s.final_identity) for s in specs2]
        order_after = [MC.canonical(s.final_identity) for s in BO.presentation_order(specs2)]
        alias_changed = real(specs[0].final_identity) != MC.blind_id(specs[0].final_identity)
    finally:
        MC.blind_id = real

    check(
        "6. changing the blind-ID scheme changes NO selected stimulus",
        selected_before,
        selected_after,
        "sampling consumes a blind id, so the alias scheme could move the sample (A28.3)",
    )
    check(
        "7. ...and changes NO presentation rank",
        order_before,
        order_after,
        "blind-order ranks blind ids rather than canonical final identities",
    )
    check(
        "...and the alias itself DID change, so the control is not vacuous",
        True,
        alias_changed,
        "the substituted scheme returns the same alias, proving nothing",
    )

    # NEGATIVE: force a collision. Must abort -- never salt, re-roll, overwrite or merge.
    collided = MC.blind_id
    try:
        MC.blind_id = lambda ident: "CONSTANT"
        outcome = refusal(lambda: BO.build(docs))
    finally:
        MC.blind_id = collided
    check(
        "8. NEGATIVE -- an injected blind-ID collision ABORTS the build",
        "BlindIdCollision",
        outcome,
        "the build completes with a collision, silently overwriting or merging two stimuli (I14)",
    )

    n = result.key["n_stimuli"]
    check(
        "20. realized blind-ID uniqueness holds over the COMPLETE set, repeats included",
        n,
        len({r["png_sha256"] and bid for bid, r in result.key["stimuli"].items()}),
        "two realized stimuli share an adjudicator-facing id",
    )
    check(
        "...and the uniqueness assertion is made over instances that INCLUDE R1 repeats",
        True,
        any(r["is_r1_repeat"] for r in result.key["stimuli"].values()),
        "no repeat exists in the realized set, so control 20 never exercised the repeat case",
    )
    return {
        "n_stimuli": n,
        "n_r1_repeats": sum(1 for r in result.key["stimuli"].values() if r["is_r1_repeat"]),
        "blind_id_scheme_swap_changed_selection": selected_before != selected_after,
        "blind_id_scheme_swap_changed_order": order_before != order_after,
    }


# --------------------------------------------------------------- render / scale controls


def part_render(tmp: Path) -> dict:
    print("\n== rendering: determinism, scale, and geometry-only input ==")
    docs = synthetic_documents(tmp)
    frame = docs[0]["frame"]
    page_frame = frame["pages"][0]
    bbox = OG.region_bbox(page_frame, 0)

    doc = pymupdf.open(docs[0]["pdf_path"])
    page = doc[0]
    a, _w, _h = BO.render_region(page, bbox, 300)
    b, _w2, _h2 = BO.render_region(page, bbox, 300)
    check(
        "1. same bbox + renderer + DPI re-renders to an IDENTICAL PNG hash",
        hashlib.sha256(a).hexdigest(),
        hashlib.sha256(b).hexdigest(),
        "the renderer is not deterministic, so a stored png_sha256 could not detect a re-render",
    )

    # 4. the renderer consumes PDF GEOMETRY. Rendering the same clip straight from pymupdf,
    # with no frame and no architecture output in scope at all, must give the same bytes.
    height = page.rect.height
    clip = pymupdf.Rect(bbox[0], height - bbox[3], bbox[2], height - bbox[1])
    direct = page.get_pixmap(matrix=pymupdf.Matrix(OG.scale(300), OG.scale(300)), clip=clip, alpha=False)
    check(
        "4. the renderer consumes PDF geometry only -- bytes match a frame-free direct render",
        hashlib.sha256(direct.tobytes("png")).hexdigest(),
        hashlib.sha256(a).hexdigest(),
        "the frame contributes something to the pixels, i.e. an arm's output could reach the image (I6)",
    )

    r330, _w3, _h3 = BO.render_region(page, bbox, 330)
    check(
        "17. the PNG hash CHANGES when the rendered stimulus really changes",
        True,
        hashlib.sha256(a).hexdigest() != hashlib.sha256(r330).hexdigest(),
        "two genuinely different renders hash the same, so the hash cannot detect a substitution",
    )
    doc.close()

    # 5. mutate every H/X text in the frame; the pixels may not move.
    mutated = copy.deepcopy(docs)
    for line in mutated[0]["frame"]["pages"][0]["neutral_lines"]:
        line["line_state"]["h_text"] = "MUTATED-H-" * 4
        line["line_state"]["x_text"] = "MUTATED-X-" * 4
    mutated[0]["architecture_output"] = {"1:0": {"H": ["TOTALLY DIFFERENT"], "X": ["ALSO DIFFERENT"]}}
    base_hashes = {r["png_sha256"] for r in BO.build(docs).key["stimuli"].values()}
    mutated_hashes = {r["png_sha256"] for r in BO.build(mutated).key["stimuli"].values()}
    check(
        "5. changing H/X text cannot change ANY rendered PNG",
        base_hashes,
        mutated_hashes,
        "an arm's text reaches the renderer or the crop, which would let the thing under test choose its own stimulus",
    )

    # 2 + 3. the R1 repeat shares the primary's bbox exactly; only the raster scale differs.
    result = BO.build(docs)
    pairs = {}
    for record in result.key["stimuli"].values():
        pairs.setdefault(record["base_identity"], []).append(record)
    same_bbox, only_scale = [], []
    for records in pairs.values():
        primary = next((r for r in records if not r["is_r1_repeat"]), None)
        repeat = next((r for r in records if r["is_r1_repeat"]), None)
        if primary and repeat:
            same_bbox.append(primary["bbox_pdf_points"] == repeat["bbox_pdf_points"])
            only_scale.append(
                primary["dpi"] == 300
                and repeat["dpi"] == 330
                and primary["png_sha256"] != repeat["png_sha256"]
                and primary["document_sha256"] == repeat["document_sha256"]
                and primary["page_number"] == repeat["page_number"]
                and primary["region_ordinal"] == repeat["region_ordinal"]
            )
    check(
        "2. every R1 repeat renders the EXACT same PDF bbox as its primary",
        (len(same_bbox), True),
        (sum(same_bbox), all(same_bbox) and bool(same_bbox)),
        "a repeat is cropped differently, so a text disagreement could be a crop artifact (A28.4)",
    )
    check(
        "3. ...and differs from it ONLY by raster scale (300 -> 330)",
        (len(only_scale), True),
        (sum(only_scale), all(only_scale) and bool(only_scale)),
        "a repeat differs in source region, page or document, or is not 330 DPI",
    )

    # 13. the crop is EXACTLY the committed frame geometry -- minimal union, zero padding.
    committed = [
        line["bbox"]
        for line in page_frame["neutral_lines"]
        if list(line["key"]) in page_frame["regions"][0]["neutral_line_keys"]
    ]
    union = [
        min(b[0] for b in committed),
        min(b[1] for b in committed),
        max(b[2] for b in committed),
        max(b[3] for b in committed),
    ]
    # the record for THIS page, not merely the first in presentation order
    rendered_bbox = next(
        r["bbox_pdf_points"]
        for r in result.key["stimuli"].values()
        if r["page_number"] == page_frame["page_number"] and not r["is_r1_repeat"]
    )
    check(
        "13. the crop equals the committed-frame minimal union EXACTLY, zero padding",
        union,
        rendered_bbox,
        "the builder padded, expanded to column or page, re-clustered from the PDF, or repaired "
        "the bbox -- each would show the adjudicator something other than the committed region",
    )
    return {
        "synthetic_bbox": list(bbox),
        "expected_width_300": OG.expected_image_width(bbox[0], bbox[2], 300),
        "expected_width_330": OG.expected_image_width(bbox[0], bbox[2], 330),
        "n_r1_pairs_checked": len(same_bbox),
    }


# --------------------------------------------------------------- fail-closed geometry


def part_fail_closed(tmp: Path) -> dict:
    print("\n== fail-closed: corrupt geometry ABORTS, and never becomes a skip ==")
    clean = synthetic_documents(tmp)
    n_clean = BO.build(clean).key["n_stimuli"]

    outside = copy.deepcopy(clean)
    outside[0]["frame"]["pages"][0]["neutral_lines"][0]["bbox"] = [100.0, 600.0, 9999.0, 640.0]
    check(
        "14. NEGATIVE -- a region bbox extending past the page ABORTS",
        OG.REGION_BBOX_OUTSIDE_PAGE,
        refusal(lambda: BO.build(outside)),
        "an out-of-page bbox is clipped, intersected or padded instead of refused (A33.1)",
    )

    nonpositive = copy.deepcopy(clean)
    nonpositive[0]["frame"]["pages"][0]["neutral_lines"][2]["bbox"] = [300.0, 600.0, 100.0, 640.0]
    check(
        "15. NEGATIVE -- a non-positive committed line bbox ABORTS",
        OG.NON_POSITIVE_LINE_BBOX,
        refusal(lambda: BO.build(nonpositive)),
        "a degenerate line passes because its siblings make the union positive, so defective "
        "committed geometry would render and never be seen",
    )

    missing = copy.deepcopy(clean)
    missing[0]["frame"]["pages"][0]["neutral_lines"][1]["bbox"] = None
    check(
        "NEGATIVE -- a missing committed line bbox ABORTS",
        OG.MISSING_LINE_BBOX,
        refusal(lambda: BO.build(missing)),
        "a line with no geometry is skipped, silently shrinking the crop",
    )

    nonfinite = copy.deepcopy(clean)
    nonfinite[0]["frame"]["pages"][0]["neutral_lines"][3]["bbox"] = [100.0, float("nan"), 300.0, 640.0]
    check(
        "NEGATIVE -- a non-finite committed line bbox ABORTS",
        OG.NON_FINITE_LINE_BBOX,
        refusal(lambda: BO.build(nonfinite)),
        "a NaN coordinate propagates into a clip rectangle",
    )

    # 16. rotation aborts -- and the abort may not degrade into a smaller study.
    rotated = [
        {
            "frame": synthetic_frame(),
            "pdf_path": synthetic_pdf(tmp, rotation=90),
            "stratum": "SYNTHETIC",
        }
    ]
    rot_reason = refusal(lambda: BO.build(rotated))
    check(
        "16. NEGATIVE -- a non-zero page rotation ABORTS oracle construction",
        OG.NONZERO_PAGE_ROTATION,
        rot_reason,
        "a rotated page renders anyway, though start_x_px would no longer be a PDF x offset (A33.4)",
    )
    n_rotated = None
    try:
        n_rotated = BO.build(rotated).key["n_stimuli"]
    except (BO.OracleBuildError, OG.OracleGeometryError):
        pass
    check(
        "16b. ...and the rotation refusal CANNOT become a skipped stimulus",
        None,
        n_rotated,
        "the build returns a result with the rotated page's regions dropped, turning an "
        "unrepresentable condition into a quietly smaller study with no visible loss",
    )
    check(
        "...and a clean build of the same shape DOES produce stimuli, so 16b is not vacuous",
        True,
        n_clean > 0,
        "the clean case produces nothing either, so 'None' proved nothing about rotation",
    )

    # the holdout guard, and the pre-execution write boundary
    holdout = copy.deepcopy(clean)
    holdout[0]["frame"]["document"] = "116-hr-7611/1"
    check(
        "NEGATIVE -- a confirmatory holdout member is REFUSED by document id",
        BO.DOCUMENT_IS_HOLDOUT,
        refusal(lambda: BO.build(holdout)),
        "a holdout document can be opened before execution is authorised",
    )
    check(
        "NEGATIVE -- writing the CANONICAL oracle artifact is refused pre-execution",
        BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
        refusal(lambda: BO.assert_write_permitted(EV / "results" / "oracle_key.json")),
        "results/oracle_key.json can be created while the execution boundary is absent",
    )
    check(
        "...and a scratch path is NOT refused, so the write guard is not blanket-refusing",
        None,
        refusal(lambda: BO.assert_write_permitted(tmp / "oracle_key.json")),
        "the guard refuses everything, which would make the control above meaningless",
    )
    return {
        "n_clean_stimuli": n_clean,
        "rotation_refusal": rot_reason,
        "rotation_build_returned": n_rotated,
        "refusal_classes": [
            OG.MISSING_LINE_BBOX,
            OG.NON_FINITE_LINE_BBOX,
            OG.NON_POSITIVE_LINE_BBOX,
            OG.REGION_BBOX_OUTSIDE_PAGE,
            OG.NONZERO_PAGE_ROTATION,
        ],
    }


# ------------------------------------------------------------- leakage and the join


def part_leakage_and_join(tmp: Path) -> dict:
    print("\n== the blind file leaks nothing, and the private key is load-bearing ==")
    docs = synthetic_documents(tmp)
    result = BO.build(docs)
    report = BO.leakage_report(result.blind, result.key)

    check(
        "9. the adjudicator-facing artifact carries ONLY id, image and question",
        [],
        report["unexpected_keys"],
        "a field beyond the blinding allowlist reaches the adjudicator",
    )
    check(
        "9b. ...and no private VALUE appears anywhere in its serialization",
        0,
        report["n_leaked_values"],
        "a document sha, canonical identity or png hash is smuggled inside an allowed field",
    )
    check(
        "9c. ...and no forbidden architecture / frame / stratum token appears in it",
        [],
        report["forbidden_text"],
        "the blind file names an architecture, frame, stratum, control or repeat",
    )

    # 10. NEGATIVE -- inject each private field into the blind file and require the gate to fire.
    injected_caught = {}
    for fname in ("document_sha256", "canonical_identity", "png_sha256"):
        leaked = copy.deepcopy(result.blind)
        value = next(iter(result.key["stimuli"].values()))[fname]
        leaked["items"][0]["question"] = leaked["items"][0]["question"] + f"\n{value}"
        rep = BO.leakage_report(leaked, result.key)
        injected_caught[fname] = rep["n_leaked_values"] > 0
    structural = copy.deepcopy(result.blind)
    structural["items"][0]["frame"] = "C"
    structural["items"][0]["stratum"] = "appropriations-house"
    injected_caught["structural_frame_and_stratum"] = bool(BO.leakage_report(structural, result.key)["unexpected_keys"])
    textual = copy.deepcopy(result.blind)
    textual["items"][0]["question"] = textual["items"][0]["question"] + "\nThis is a C-frame region."
    injected_caught["forbidden_text"] = bool(BO.leakage_report(textual, result.key)["forbidden_text"])
    check(
        "10. NEGATIVE -- every injected leak makes the leakage gate FAIL",
        {k: True for k in injected_caught},
        injected_caught,
        "an injected private value, an extra structural field, or a forbidden token passes the "
        "gate -- which would mean a green leakage report proves nothing",
    )
    check(
        "...and write_artifacts REFUSES a leaking blind file rather than writing it",
        BO.BLIND_ARTIFACT_LEAKS,
        refusal(lambda: BO.write_artifacts(_leaky(result), tmp / "leaky")),
        "a leaking artifact is written and the leak survives to the adjudicator",
    )

    # 11 + 12. the private key must carry the join, and the join must be load-bearing.
    check(
        "11. the private key carries every field the downstream join needs",
        [],
        BO.verify_join(result),
        "a join field is missing, so an adjudication could not be bound back to its region",
    )
    shuffled = BO.BuildResult(key=copy.deepcopy(result.key), blind=result.blind, images=result.images)
    bids = list(shuffled.key["stimuli"])
    if len(bids) >= 2:
        rotated_records = [shuffled.key["stimuli"][b] for b in bids[1:]] + [shuffled.key["stimuli"][bids[0]]]
        shuffled.key["stimuli"] = dict(zip(bids, rotated_records))
    defects = BO.verify_join(shuffled)
    check(
        "12. NEGATIVE -- a misassociated private key BREAKS the join, proving it load-bearing",
        True,
        len(defects) > 0,
        "adjudications still align after the key is shuffled, which would mean the join is fake and the key decorative",
    )
    check(
        "...and the shuffle was real: at least two distinct stimuli existed to permute",
        True,
        len(bids) >= 2,
        "fewer than two stimuli, so the shuffle was a no-op and control 12 was vacuous",
    )
    return {
        "n_stimuli": result.key["n_stimuli"],
        "blind_allowed_keys": sorted(BO.BLIND_ALLOWED_KEYS),
        "injected_leaks_caught": injected_caught,
        "shuffled_key_defects": len(defects),
    }


def _leaky(result):
    leaked = BO.BuildResult(key=result.key, blind=copy.deepcopy(result.blind), images=result.images)
    leaked.blind["items"][0]["stratum"] = "appropriations-house"
    return leaked


# ------------------------------------------------------ the region-line bijection (A35.2)


def part_start_line(tmp: Path) -> dict:
    print("\n== A35.2: the printed-line index maps onto committed neutral lines ==")
    frame = synthetic_frame()
    page_frame = frame["pages"][0]
    bijection = BO.region_line_bijection(page_frame, 0)
    committed = [list(k) for k in page_frame["regions"][0]["neutral_line_keys"]]

    check(
        "the bijection covers EXACTLY the region's committed neutral lines",
        sorted(map(tuple, committed)),
        sorted(map(tuple, bijection)),
        "a printed line maps to a line outside the region, or a region line is unreachable",
    )
    check(
        "...and it is a bijection, not a multimap",
        len(committed),
        len({tuple(k) for k in bijection}),
        "two printed-line indices resolve to the same committed line",
    )
    check(
        "printed order is committed-ordinal order, top to bottom",
        [k[1] for k in bijection],
        sorted(k[1] for k in bijection),
        "the bijection is not sorted by ordinal, so line 1 is not the topmost printed line",
    )
    check(
        "start_physical_line 1 resolves to the topmost committed line",
        tuple(bijection[0]),
        BO.resolve_start_line(bijection, 1),
        "the 1-based index is off by one",
    )
    check(
        "NEGATIVE -- an out-of-range printed-line index REFUSES rather than guessing",
        BO.START_LINE_OUT_OF_RANGE,
        refusal(lambda: BO.resolve_start_line(bijection, len(bijection) + 1)),
        "an impossible line index resolves to some line anyway, which would hand the nearest-x "
        "resolver a confident and wrong start_ngid",
    )
    check(
        "NEGATIVE -- a zero or negative index REFUSES",
        BO.START_LINE_OUT_OF_RANGE,
        refusal(lambda: BO.resolve_start_line(bijection, 0)),
        "0 is accepted, silently reading as the last line under Python indexing",
    )
    return {"region_lines": len(bijection), "bijection": bijection}


# --------------------------------------------------------------- DEVELOPMENT end-to-end


def part_development() -> dict:
    """Real PDFs, real committed frames. Demonstration of behaviour, NOT a census."""
    print("\n== DEVELOPMENT end-to-end (real PDFs, real frames) ==")
    docs, overlaps, per_doc = [], [], []
    for name, path in DOCS:
        for member in BO.HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            continue
        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _s = run_extended.run(path, limit=PAGE_LIMIT)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = BF.build_document_frame(sha, name, BF.P_HEAD, h_pages, x_pages)

        regions = [r for pf in frame["pages"] for r in pf["regions"]]
        both = [r for r in regions if r["c_frame"] and r["d_frame"]]
        per_doc.append(
            {
                "document": name,
                "pages_consumed": PAGE_LIMIT,
                "regions": len(regions),
                "c_frame": sum(1 for r in regions if r["c_frame"]),
                "d_frame": sum(1 for r in regions if r["d_frame"]),
                "c_and_d": len(both),
            }
        )
        overlaps.extend(
            {"document": name, "page_number": r["page_number"], "region_ordinal": r["region_ordinal"]} for r in both
        )
        docs.append({"frame": frame, "pdf_path": path, "stratum": "DEVELOPMENT"})

    # THE A35 STOP, demonstrated on real material rather than argued.
    stop_reason = refusal(lambda: BO.build(copy.deepcopy(docs)))
    check(
        "the C-and-D overlap REFUSES construction rather than resolving it silently",
        BO.REGION_IN_BOTH_FRAMES,
        stop_reason,
        "the builder proceeds, silently deciding who adjudicates an overlapping region and "
        "which denominators move -- a choice the frozen sources do not license",
    )
    if overlaps:
        STOPS.append(
            {
                "stop": BO.REGION_IN_BOTH_FRAMES,
                "why": "A region can be in the C-frame and the D-frame. 5.5.1 routes C to AI "
                "adjudication and D to human adjudication item by item; A28.3's base identity "
                "has no frame component so two instances of one region are unrepresentable; and "
                "neither the route nor the denominators are determined by the frozen sources.",
                "measured_on": "DEVELOPMENT frames, first %d pages of each document" % PAGE_LIMIT,
                "n_overlapping_regions": len(overlaps),
                "instances": overlaps[:24],
            }
        )

    # Everything downstream of the ruling is exercised on the unambiguous regions. The overlap
    # is NOT dropped from any denominator -- it is recorded above as an open STOP.
    resolvable = copy.deepcopy(docs)
    n_set_aside = 0
    for doc in resolvable:
        for page_frame in doc["frame"]["pages"]:
            for region in page_frame["regions"]:
                if region["c_frame"] and region["d_frame"]:
                    region["d_frame"] = False
                    n_set_aside += 1

    result = BO.build(resolvable)
    report = BO.leakage_report(result.blind, result.key)
    defects = BO.verify_join(result)

    widths = [r["image_width_px"] for r in result.key["stimuli"].values()]
    width_ok = [
        r["image_width_px"] == OG.expected_image_width(r["bbox_pdf_points"][0], r["bbox_pdf_points"][2], r["dpi"])
        for r in result.key["stimuli"].values()
    ]
    check(
        "every DEVELOPMENT stimulus renders at the frozen width for its own DPI",
        (len(width_ok), True),
        (sum(width_ok), all(width_ok)),
        "a rendered image is not the width the A34 derivation predicts for its bbox and scale",
    )
    check(
        "every planned DEVELOPMENT stimulus was rendered, so no denominator is a sample",
        result.key["n_stimuli"],
        len(result.images),
        "a stimulus was planned but not rendered, which would shrink the study invisibly",
    )
    check(
        "the DEVELOPMENT blind file leaks nothing",
        (0, [], []),
        (report["n_leaked_values"], report["unexpected_keys"], report["forbidden_text"]),
        "a private value or forbidden token reaches the adjudicator on real material",
    )
    check(
        "the DEVELOPMENT join is complete",
        [],
        defects,
        "a real stimulus cannot be bound back to its region",
    )
    check(
        "the DEVELOPMENT population is non-empty, so these controls are not vacuous",
        True,
        result.key["n_stimuli"] > 0 and len(docs) > 0,
        "no document or no stimulus was produced, so every check above passed on nothing",
    )
    return {
        "documents": per_doc,
        "page_limit": PAGE_LIMIT,
        "note": "PAGE_LIMIT is a machinery demonstration window, not a census",
        "n_stimuli": result.key["n_stimuli"],
        "n_r1_repeats": sum(1 for r in result.key["stimuli"].values() if r["is_r1_repeat"]),
        "n_images": len(result.images),
        "image_width_px_min": min(widths) if widths else None,
        "image_width_px_max": max(widths) if widths else None,
        "c_and_d_overlap_regions": len(overlaps),
        "c_and_d_set_aside_for_downstream_controls": n_set_aside,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prompt = part_prompt()
        blinding = part_blinding(tmp)
        render = part_render(tmp)
        fail_closed = part_fail_closed(tmp)
        leakage = part_leakage_and_join(tmp)
        start_line = part_start_line(tmp)
        development = part_development()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated, nothing scored",
        "contract": "A35 (adjudicator prompt + build_oracle), implementing A19-A34 and HARNESS-PLAN 3-4",
        "renderer": "MuPDF (pymupdf)",
        "renderer_version": str(pymupdf.version),
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_adjudicated.json, "
        "metrics.json, scores.json, EXECUTION-START.json",
        "prompt": prompt,
        "blinding": blinding,
        "render": render,
        "fail_closed": fail_closed,
        "leakage_and_join": leakage,
        "start_line_bijection": start_line,
        "development": development,
        "stop_conditions": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} stop conditions")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
