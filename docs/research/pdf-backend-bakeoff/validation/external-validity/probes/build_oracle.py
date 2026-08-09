"""build_oracle -- HARNESS-PLAN section 4. Builds the two oracle artifacts.

A35. IMPLEMENTS ALREADY-FROZEN RULES AND INTRODUCES NONE. Every rule here is fixed by
PRE-REGISTRATION 5.3-5.8, HARNESS-PLAN section 4, or A19-A34. Where a frozen source does not
determine an outcome-affecting choice the obligation is to STOP and report, never to settle it
here -- see A35.1's forward finding on the M5 coarsening map, which this module neither needs
nor chooses.

WHAT IT PRODUCES, and why the two artifacts differ deliberately:

  PRIVATE KEY   blind id -> canonical pre-blinding identity, document_sha256, page,
                region_ordinal, stratum, frames ["C"]/["D"]/["C","D"] (A36.2), the required
                adjudication routes, control/repeat bookkeeping, the H/X output
                the later join needs, renderer name + version, DPI, committed bbox in PDF
                points, PNG sha256, and the region-line bijection A35.2 records.

  BLIND FILE    ONLY the opaque id, the rendered image, and the question/codebook.

The blind file is what the adjudicator reads. If any private field reaches it, the study's
blinding claim is false, so `leakage_report` gates it executably and `x21` proves the gate can
FAIL by injecting forbidden content rather than trusting inspection.

WHAT THIS MODULE MUST NOT DO. It never renders from any architecture's text; never lets a
region's H/X content influence cropping; never reveals control status; never re-derives
geometry from the PDF; never pads, clips, intersects or repairs a committed bbox; and never
turns a refusal into a skipped stimulus or a smaller denominator.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import methodology_contracts as MC
import oracle_geometry as OG
import pymupdf

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
PROMPT_PATH = HERE.parent / "adjudicator_prompt.md"

RENDERER_NAME = "MuPDF (pymupdf)"

C_FRAME = "C"
D_FRAME = "D"

# ------------------------------------------------------------------ refusal classes

DOCUMENT_IS_HOLDOUT = "DOCUMENT_IS_HOLDOUT"
PROMPT_MISSING = "PROMPT_MISSING"
PROMPT_LEAKS = "PROMPT_LEAKS"
PROMPT_ASKS_FORBIDDEN_QUESTION = "PROMPT_ASKS_FORBIDDEN_QUESTION"
PROMPT_MISSING_REQUIRED_INSTRUCTION = "PROMPT_MISSING_REQUIRED_INSTRUCTION"
BLIND_ARTIFACT_LEAKS = "BLIND_ARTIFACT_LEAKS"
WRONG_DPI_FOR_STIMULUS = "WRONG_DPI_FOR_STIMULUS"
R1_BBOX_DIFFERS_FROM_PRIMARY = "R1_BBOX_DIFFERS_FROM_PRIMARY"
EMPTY_RENDER = "EMPTY_RENDER"
RENDERED_WIDTH_DISAGREES = "RENDERED_WIDTH_DISAGREES"
START_LINE_OUT_OF_RANGE = "START_LINE_OUT_OF_RANGE"
CONFIRMATORY_WRITE_BEFORE_EXECUTION = "CONFIRMATORY_WRITE_BEFORE_EXECUTION"

UNKNOWN_ADJUDICATION_PURPOSE = "UNKNOWN_ADJUDICATION_PURPOSE"
ANSWER_MISSING_FOR_REQUIRED_ROUTE = "ANSWER_MISSING_FOR_REQUIRED_ROUTE"
ADJUDICATION_NOT_NAMESPACED = "ADJUDICATION_NOT_NAMESPACED"

# ----------------------------------------------------------- A36 C/D overlap semantics
#
# A35.5 STOPPED here because the frozen sources did not say what happens when a region is in
# BOTH frames. A36 ruled it, and the ruling is implemented rather than re-decided:
#
#   A36.1  C and D are INDEPENDENT predicates and may overlap. Neither frame drops the
#          overlap, the C draw is never replaced after observing D membership, and the frames
#          are never forced disjoint.
#   A36.2  one physical region is ONE stimulus identity -- one base identity, one 300-DPI
#          primary, one PNG, one blind id. A28.3 gains NO frame component; membership is
#          METADATA about a stimulus, carried as an explicit ordered list because the old
#          singular `frame` projection could not represent an overlap unambiguously.
#   A36.3  "never pooled" separates ESTIMANDS, not SETS: the region counts once in each
#          frame's own denominator, and |C union D| is never substituted for either.
#   A36.4  a stimulus and an adjudication are different objects, so one blind stimulus takes
#          both required routes, separately namespaced.
C_FRAME_ROUTE = "ai"
D_FRAME_ROUTE = "human"

ROUTE_AI = "ai"
ROUTE_HUMAN = "human"
# Deterministic order, so a membership set can never serialize two ways.
ROUTE_ORDER = (ROUTE_AI, ROUTE_HUMAN)
FRAME_ORDER = (C_FRAME, D_FRAME)

PURPOSE_C_METRICS = "c_metrics"
PURPOSE_D_DECISION = "d_decision"
PURPOSE_C_AUDIT = "c_audit"

# A36.4's CRITICAL PROHIBITION, as a table rather than as prose a caller might not read.
# C metrics read the AI answer even where a human answer exists, because D membership is
# CONDITIONAL ON ARCHITECTURE DISAGREEMENT -- taking human truth only on C-and-D regions would
# make C a mixed oracle whose source is selected by H/X discordance, i.e. the architectures
# would be choosing their own oracle on exactly the regions where they disagree.
PURPOSE_ROUTE = {
    PURPOSE_C_METRICS: ROUTE_AI,
    PURPOSE_D_DECISION: ROUTE_HUMAN,
    PURPOSE_C_AUDIT: ROUTE_HUMAN,
}

# A36.4 -- the adjudication artifact must carry two separately namespaced answer sets keyed by
# the SAME blind id. The schema requirement is frozen now; the artifact is not built here.
ADJUDICATION_NAMESPACES = (ROUTE_AI, ROUTE_HUMAN)


class OracleBuildError(Exception):
    """Construction cannot proceed as frozen. Deterministic, and never a value.

    Distinct from `OracleGeometryError`, which this module lets propagate UNCAUGHT: A33.4 and
    A33.1 require an unrepresentable page or bbox to abort the build, and catching either here
    to continue would be exactly the silent-reduction failure they exist to prevent.
    """

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


# ------------------------------------------------------- the confirmatory holdout guard

# The 17 confirmatory members. This module may not open one: H/X have not been run on them,
# and running them here would spend the holdout before the protocol authorises execution.
HOLDOUT_GUARD = frozenset(
    {
        "116-hr-7611",
        "115-hr-5961",
        "115-hr-6147",
        "115-s-2976",
        "115-s-1609",
        "114-s-3001",
        "115-hr-6157",
        "117-hr-3237",
        "119-hr-6938",
        "119-hr-7148",
        "CRPT-114HRPT215",
        "CRPT-119HRPT632",
        "CRPT-115HRPT699",
        "CRPT-116HRPT456",
        "CRPT-117HRPT109",
        "CRPT-118HRPT123",
        "CRPT-115SRPT275",
    }
)

# Written only once execution is authorised. Its ABSENCE is the pre-execution state, so the
# canonical artifacts below may not be written while it does not exist.
EXECUTION_MARKER = EV / "results" / "EXECUTION-START.json"
CANONICAL_ARTIFACTS = {
    (EV / "results" / "oracle_key.json").resolve(),
    (EV / "results" / "oracle_blind.json").resolve(),
}


def assert_not_holdout(document_id: str, path=None) -> None:
    """Refuse any confirmatory member, by id or by path substring."""
    haystack = f"{document_id}|{path or ''}"
    for member in HOLDOUT_GUARD:
        if member in haystack:
            raise OracleBuildError(DOCUMENT_IS_HOLDOUT, {"document": document_id, "member": member})


def assert_write_permitted(out_path: Path) -> None:
    """The canonical oracle artifacts may not be written before the execution boundary exists.

    Not a new rule: x04 already reports EXECUTION BOUNDARY ABSENT and forbids scoring, and this
    makes that boundary refuse at the one place that would otherwise create a confirmatory
    artifact by accident. It never CREATES the marker -- it only reads whether one is there.
    """
    if out_path.resolve() in CANONICAL_ARTIFACTS and not EXECUTION_MARKER.exists():
        raise OracleBuildError(CONFIRMATORY_WRITE_BEFORE_EXECUTION, {"path": str(out_path)})


# ------------------------------------------------------------------------ the prompt gate

# Tokens that would tell the adjudicator something the blinding protocol forbids it to know.
# Matched case-insensitively on word boundaries, so "extended glyph" is caught while ordinary
# prose is not. `\bH\b`/`\bX\b` are deliberately included: the arms are named by single letters
# throughout this study, and a stray "arm H" in a prompt is exactly the leak that matters.
FORBIDDEN_PATTERNS = {
    "architecture": r"\barchitectures?\b",
    "hybrid": r"\bhybrid\b",
    "extended_glyph": r"\bextended[- ]glyph\b|\bextended glyph\b",
    "arm_letter_H": r"\barm\s+H\b|\bH[- ]arm\b|\bH\s*/\s*X\b",
    "arm_letter_X": r"\barm\s+X\b|\bX[- ]arm\b",
    "pdfium": r"\bpdfium\b|\bpypdfium2?\b",
    "frame": r"\b[CD][- ]frame\b|\bcoverage frame\b|\bdiscordance frame\b",
    "stratum": r"\bstrat(um|a)\b",
    "control_status": r"\bnegative control\b|\bcontrol (region|item|stimulus)\b|\bN-[ABC]\b",
    "repeat_status": r"\brepeat(ed)? (stimulus|region|item)\b|\bR1\b|\breliability repeat\b",
    "deltatrack": r"\bdeltatrack\b|\bbilltrax\b",
    "renderer_scale": r"\b300\s*dpi\b|\b330\s*dpi\b|\bdpi\b",
    "amount_attribution": r"\bamount[- ]account\b|\battribut\w*\s+(the\s+)?(amount|figure|dollar)",
}

# M6 is DEFERRED (A20). Asking would collect data the study may not use and could bias the
# heading answers, so a prompt that asks it is refused rather than merely noted.
M6_QUESTION_PATTERNS = {
    "which_account_gets_amount": r"which account\b|\bwhich heading\b.{0,40}\b(amount|figure|dollar|sum)",
    "attribute_amount": r"\battribute\b.{0,40}\b(amount|figure|dollar|sum)",
    "total_the_amounts": r"\b(total|sum up|add up)\b.{0,30}\b(amount|figure|dollar)s?\b",
}

# What the prompt MUST contain. A prompt silently missing the A33.5 instruction would still
# collect a `start_x_px`, just a differently-defined one, and nothing downstream could tell.
REQUIRED_INSTRUCTIONS = {
    "a33_5_visible_ink": r"first character's own visible ink",
    "a33_5_ignore_marks": r"strike-through",
    "a33_5_not_bounding_box": r"do \*\*not\*\* use a text-box|do not use a text-box",
    "identity_annotation_only": r"identify \*?\*?which\*?\*? occurrence|position annotation",
    "independent_adjudication": r"judged independently|independently of it",
    "start_physical_line": r"start_physical_line",
    "start_x_px": r"start_x_px",
    "exact_printed_text": r"[Tt]ranscribe exactly as printed",
    "immediate_parent": r"immediate parent heading",
    "role_codebook": r"`account`",
}


def scan_forbidden(text: str) -> list[dict]:
    """Every forbidden pattern that matches, with the matched text, so a hit is inspectable."""
    hits = []
    for name, pattern in FORBIDDEN_PATTERNS.items():
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            hits.append({"pattern": name, "matched": m.group(0)})
    return hits


def prompt_report(prompt_text: str) -> dict:
    """Leakage / completeness report for the adjudicator prompt. Data, not a decision."""
    return {
        "forbidden": scan_forbidden(prompt_text),
        "m6_questions": [
            {"pattern": n, "matched": m.group(0)}
            for n, p in M6_QUESTION_PATTERNS.items()
            for m in re.finditer(p, prompt_text, flags=re.IGNORECASE)
        ],
        "missing_required": sorted(
            n for n, p in REQUIRED_INSTRUCTIONS.items() if not re.search(p, prompt_text, flags=re.IGNORECASE)
        ),
    }


def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Read the committed prompt and REFUSE it if it leaks, asks M6, or is incomplete."""
    if not path.exists():
        raise OracleBuildError(PROMPT_MISSING, {"path": str(path)})
    text = path.read_text()
    report = prompt_report(text)
    if report["forbidden"]:
        raise OracleBuildError(PROMPT_LEAKS, report["forbidden"])
    if report["m6_questions"]:
        raise OracleBuildError(PROMPT_ASKS_FORBIDDEN_QUESTION, report["m6_questions"])
    if report["missing_required"]:
        raise OracleBuildError(PROMPT_MISSING_REQUIRED_INSTRUCTION, report["missing_required"])
    return text


# --------------------------------------------------------------------- stimulus planning


@dataclass(frozen=True)
class StimulusSpec:
    """One planned stimulus, BEFORE any blind id exists.

    A28.3: selection and ranking consume the canonical identities on this object. The blind id
    is derived only after the whole realized set is settled, so nothing here may depend on it.
    """

    document_id: str
    document_sha256: str
    page_number: int
    region_ordinal: int
    frames: tuple[str, ...]
    stratum: str
    is_r1_repeat: bool = False
    is_c_audit_selected: bool = False
    control_kind: str | None = None
    control_variant: str | None = None
    source_fixture_sha256: str | None = None

    @property
    def frame_routes(self) -> tuple[str, ...]:
        """A36.4 -- the routes implied by FRAME MEMBERSHIP alone. C -> AI, D -> human.

        This is what an R1 repeat inherits (A36.6). The audit is deliberately not here: it is a
        property of the primary presentation of a base identity, not of frame membership.
        """
        routes = set()
        if C_FRAME in self.frames:
            routes.add(C_FRAME_ROUTE)
        if D_FRAME in self.frames:
            routes.add(D_FRAME_ROUTE)
        return tuple(r for r in ROUTE_ORDER if r in routes)

    @property
    def adjudication_routes(self) -> tuple[str, ...]:
        """Every route this stimulus must actually be answered on."""
        routes = set(self.frame_routes)
        if self.is_c_audit_selected:
            routes.add(ROUTE_HUMAN)
        return tuple(r for r in ROUTE_ORDER if r in routes)

    @property
    def human_answer_purposes(self) -> tuple[str, ...]:
        """What the ONE human answer is consumed for. A36.5 lets a C-audit item reuse its D answer.

        The purposes are separate because the audit denominator is defined over `cframe-audit`
        selections only: a C-and-D human answer that was NOT independently drawn must never
        enlarge the audit.
        """
        purposes = []
        if D_FRAME in self.frames:
            purposes.append(PURPOSE_D_DECISION)
        if self.is_c_audit_selected:
            purposes.append(PURPOSE_C_AUDIT)
        return tuple(purposes)

    @property
    def n_human_tasks(self) -> int:
        """A36.5 -- ONE human task, however many purposes consume it. Same blind image."""
        return 1 if ROUTE_HUMAN in self.adjudication_routes else 0

    @property
    def base_identity(self):
        if self.control_kind is not None:
            return MC.control_stimulus_identity(
                self.control_kind,
                self.source_fixture_sha256 or self.document_sha256,
                self.page_number,
                self.region_ordinal,
                self.control_variant or "",
            )
        return MC.base_stimulus_identity(self.document_sha256, self.page_number, self.region_ordinal)

    @property
    def final_identity(self):
        """The identity the blind id and the presentation order are computed from."""
        return MC.r1_repeat_identity(self.base_identity) if self.is_r1_repeat else self.base_identity

    @property
    def dpi(self) -> int:
        return MC.required_dpi(self.is_r1_repeat)


def plan_document_stimuli(frame: dict, stratum: str) -> list[StimulusSpec]:
    """ONE stimulus per region that is in either frame, carrying its membership (A36.2).

    Reads the COMMITTED frame only. It does not re-decide membership -- `build_frames` already
    settled which regions are C and which are D, and re-deriving either here would let the
    oracle layer move a frame boundary the frame layer owns.

    A region in BOTH frames yields ONE stimulus with `frames == ("C", "D")`. It is NOT emitted
    twice: A28.3's base identity has no frame component, so a second instance would be the same
    canonical identity and A30.5 would abort. A36.2 rules that this is correct -- membership is
    metadata, identity is the region.
    """
    specs = []
    for page_frame in frame["pages"]:
        for region in page_frame["regions"]:
            frames = tuple(name for flag, name in ((region["c_frame"], C_FRAME), (region["d_frame"], D_FRAME)) if flag)
            if not frames:
                continue
            specs.append(
                StimulusSpec(
                    document_id=frame["document"],
                    document_sha256=frame["document_sha256"],
                    page_number=page_frame["page_number"],
                    region_ordinal=region["region_ordinal"],
                    frames=frames,
                    stratum=stratum,
                )
            )
    return specs


C_AUDIT_SIZE = 25


def select_c_audit(primaries: list[StimulusSpec], k: int = C_AUDIT_SIZE) -> list[StimulusSpec]:
    """A36.5 -- the 25-item human audit, ranked by `cframe-audit` over C BASE identities.

    D membership may not enter this function in any way. It does not appear in the candidate
    predicate (C membership only), in the ranked item (the base identity), or in `k`. That is
    what makes the audit sample and its denominator INVARIANT under D membership, which x21
    falsifies by marking many non-audit C regions as D and requiring the selection to stay
    byte-identical.
    """
    candidates = [s for s in primaries if C_FRAME in s.frames and not s.is_r1_repeat and s.control_kind is None]
    chosen = set(map(MC.canonical, MC.select("cframe-audit", [s.base_identity for s in candidates], k)))
    return [s for s in candidates if MC.canonical(s.base_identity) in chosen]


def apply_c_audit(primaries: list[StimulusSpec], k: int = C_AUDIT_SIZE) -> list[StimulusSpec]:
    """Mark the audit-selected primaries, preserving every other field."""
    chosen = {MC.canonical(s.base_identity) for s in select_c_audit(primaries, k)}
    return [replace(s, is_c_audit_selected=True) if MC.canonical(s.base_identity) in chosen else s for s in primaries]


def plan_r1_repeats(primaries: list[StimulusSpec], fraction: float = 0.10) -> list[StimulusSpec]:
    """5.6 R1 -- 10 % of regions presented twice, ranked by CANONICAL BASE identity (A28.3).

    The repeat carries the SAME committed bbox and source region; only the raster scale differs
    (A28.4). It records its own `start_x_px` later and resolves independently, so nothing here
    copies a primary's coordinate or resolved identity.

    A36.6 -- the repeat INHERITS its primary's frame membership, and therefore its frame routes:
    C only -> AI, D only -> human, C and D -> both. There are NO route-specific R1 identities;
    one physical repeat presented to two adjudicators yields two namespaced answers, not two
    stimuli. `is_c_audit_selected` is deliberately NOT inherited: the audit is 25 items drawn
    over base identities, and auditing the repeat as well would make it 26 tasks for 25 items.
    """
    eligible = [s for s in primaries if s.control_kind is None]
    k = math.floor(len(eligible) * fraction)
    chosen = set(map(MC.canonical, MC.select("r1-repeat", [s.base_identity for s in eligible], k)))
    return [
        replace(s, is_r1_repeat=True, is_c_audit_selected=False)
        for s in eligible
        if MC.canonical(s.base_identity) in chosen
    ]


def select_answer(record: dict, purpose: str, answers: dict):
    """A36.4 -- read the answer from the route the PURPOSE mandates, never the one that exists.

    The prohibition this enforces: C metrics take the AI answer even where a human answer is
    present. Falling back to human on C-and-D regions would make C a mixed oracle whose source
    is selected by H/X discordance. So a missing mandated answer REFUSES; it never substitutes.
    """
    if purpose not in PURPOSE_ROUTE:
        raise OracleBuildError(UNKNOWN_ADJUDICATION_PURPOSE, {"purpose": purpose})
    route = PURPOSE_ROUTE[purpose]
    if route not in record.get("adjudication_routes", ()):
        raise OracleBuildError(
            ANSWER_MISSING_FOR_REQUIRED_ROUTE,
            {"purpose": purpose, "route": route, "routes": record.get("adjudication_routes")},
        )
    if route not in answers or answers[route] is None:
        raise OracleBuildError(ANSWER_MISSING_FOR_REQUIRED_ROUTE, {"purpose": purpose, "route": route})
    return answers[route]


def validate_adjudication_namespacing(adjudicated: dict) -> None:
    """A36.4 -- the adjudication artifact must namespace answers by route under one blind id.

    Frozen as a SCHEMA REQUIREMENT now so the artifact cannot later be built with one flat
    answer per id, which would silently collapse a C-and-D region's two independent answers
    into whichever was written last.
    """
    missing = [ns for ns in ADJUDICATION_NAMESPACES if ns not in adjudicated]
    if missing:
        raise OracleBuildError(ADJUDICATION_NOT_NAMESPACED, {"missing_namespaces": missing})
    for ns in ADJUDICATION_NAMESPACES:
        if not isinstance(adjudicated[ns], dict):
            raise OracleBuildError(ADJUDICATION_NOT_NAMESPACED, {"namespace": ns, "type": type(adjudicated[ns])})


def presentation_order(specs: list[StimulusSpec]) -> list[StimulusSpec]:
    """A27.7/A28.3 `blind-order` -- ranks canonical FINAL INSTANCE identities.

    NO ranking consumes a blind id. `x21` proves it by re-deriving this order under a wholly
    different blind-id scheme and requiring it not to move.
    """
    ranked = MC.order("blind-order", [s.final_identity for s in specs])
    by_identity = {MC.canonical(s.final_identity): s for s in specs}
    return [by_identity[MC.canonical(i)] for i in ranked]


# ------------------------------------------------------------------------- rendering

# A35.2 -- the adjudicator reports a 1-based printed-line index within the rendered stimulus.
# The builder maps it onto the region's committed neutral lines, which are consecutive by
# ordinal and therefore top-to-bottom in the crop. `region_line_bijection` records the map so a
# reviewer can check it rather than take it on trust.


def region_line_bijection(page_frame: dict, region_ordinal: int) -> list[list]:
    """Committed neutral-line keys of the region, in printed top-to-bottom order.

    Index i (0-based) is `start_physical_line` i+1. Ordinal ordering IS printed ordering:
    `cluster_page` assigns ordinals by descending baseline, top to bottom.
    """
    region = next((r for r in page_frame["regions"] if r["region_ordinal"] == region_ordinal), None)
    if region is None:
        raise OracleBuildError(START_LINE_OUT_OF_RANGE, {"region_ordinal": region_ordinal})
    keys = [tuple(k) for k in region["neutral_line_keys"]]
    return [list(k) for k in sorted(keys, key=lambda k: k[1])]


def resolve_start_line(bijection: list[list], start_physical_line: int) -> tuple:
    """1-based printed-line index -> committed neutral-line key. REFUSES out of range.

    A guess here would silently resolve a heading against the wrong physical line and the
    nearest-x resolver would then return a confident, wrong `start_ngid`.
    """
    if not isinstance(start_physical_line, int) or not 1 <= start_physical_line <= len(bijection):
        raise OracleBuildError(
            START_LINE_OUT_OF_RANGE, {"reported": start_physical_line, "region_lines": len(bijection)}
        )
    return tuple(bijection[start_physical_line - 1])


def render_region(page, bbox, dpi: int) -> tuple[bytes, int, int]:
    """Render exactly the committed bbox at exactly `dpi`. PDF geometry only.

    I6 -- no arm's text reaches the renderer: the only inputs are the page object, the bbox
    read from the committed frame, and the frozen DPI.
    """
    OG.check_rotation(page.rotation)
    OG.validate_region_bbox_for_page(bbox, page.rect.width, page.rect.height)
    height = page.rect.height
    # the frame's bboxes are PDF coordinates (y grows up); pymupdf Rect is top-left origin
    clip = pymupdf.Rect(bbox[0], height - bbox[3], bbox[2], height - bbox[1])
    scale = OG.scale(dpi)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
    if pix.width == 0 or pix.height == 0:
        raise OracleBuildError(EMPTY_RENDER, {"bbox": list(bbox), "dpi": dpi})
    expected = OG.expected_image_width(bbox[0], bbox[2], dpi)
    if pix.width != expected:
        raise OracleBuildError(RENDERED_WIDTH_DISAGREES, {"got": pix.width, "expected": expected, "dpi": dpi})
    return pix.tobytes("png"), pix.width, pix.height


# ------------------------------------------------------------------------ the two artifacts

# Everything the blind file is allowed to carry. An allowlist, not a denylist: a denylist
# silently passes any field added later, which is the failure mode that matters here.
BLIND_ALLOWED_KEYS = frozenset({"id", "image", "question"})

# Private-key fields whose appearance in the blind file would break blinding.
LEAKY_KEY_FIELDS = (
    "canonical_identity",
    "document",
    "document_sha256",
    "page_number",
    "region_ordinal",
    "stratum",
    "frames",
    "adjudication_routes",
    "human_answer_purposes",
    "is_c_audit_selected",
    "control_kind",
    "control_variant",
    "is_r1_repeat",
    "dpi",
    "bbox_pdf_points",
    "png_sha256",
    "architecture_output",
    "region_line_bijection",
)


@dataclass
class BuildResult:
    key: dict = field(default_factory=dict)
    blind: dict = field(default_factory=dict)
    images: dict = field(default_factory=dict)


def leakage_report(blind: dict, key: dict) -> dict:
    """Does the adjudicator-facing artifact leak anything private? DATA, not a decision.

    Two independent checks, because either alone passes for the wrong reason:
      * a STRUCTURAL check that every item carries only allowlisted keys;
      * a VALUE check that no private value appears anywhere in the blind file's serialization,
        which catches a leak smuggled inside an allowed field.
    """
    serialized = json.dumps(blind, sort_keys=True)
    unexpected = sorted({k for item in blind.get("items", []) for k in item if k not in BLIND_ALLOWED_KEYS})

    leaked_values = []
    for bid, record in key.get("stimuli", {}).items():
        for fname in LEAKY_KEY_FIELDS:
            if fname not in record:
                continue
            value = record[fname]
            for token in _leak_tokens(value):
                if token and token in serialized:
                    leaked_values.append({"blind_id": bid, "field": fname, "token": token})
    return {
        "unexpected_keys": unexpected,
        "leaked_values": leaked_values[:20],
        "n_leaked_values": len(leaked_values),
        "forbidden_text": scan_forbidden(serialized),
    }


def _leak_tokens(value) -> list[str]:
    """Serialized forms of a private value worth searching for in the blind file.

    Short numeric values (a page number, a region ordinal) are deliberately EXCLUDED: "3"
    occurs in unrelated text and would make the gate fire constantly, which is how a gate stops
    being read. Structural allowlisting is what catches those, and `x21` proves it does.
    """
    if isinstance(value, str):
        return [value] if len(value) >= 8 else []
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return []
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in _leak_tokens(v)]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _leak_tokens(v)]
    return []


def build(
    documents: list[dict],
    *,
    prompt_path: Path = PROMPT_PATH,
    r1_fraction: float = 0.10,
    c_audit_size: int = C_AUDIT_SIZE,
    controls: list[StimulusSpec] | None = None,
) -> BuildResult:
    """Build the private key and the blind file for a set of documents.

    `documents` items: {"frame", "pdf_path", "stratum", "architecture_output" (optional)}.
    `architecture_output` is the per-region H/X data the LATER join needs; it is written to the
    PRIVATE key only and never reaches the renderer or the blind file.

    Nothing is adjudicated here and nothing is scored. Refusals propagate and abort: a stimulus
    is never dropped and no denominator is ever reduced.
    """
    question = load_prompt(prompt_path)

    specs: list[StimulusSpec] = []
    for doc in documents:
        frame = doc["frame"]
        assert_not_holdout(frame["document"], doc.get("pdf_path"))
        specs.extend(plan_document_stimuli(frame, doc.get("stratum", "UNSTRATIFIED")))
    specs.extend(controls or [])
    # A36.5 -- the audit is drawn over C base identities BEFORE repeats exist, and never sees
    # D membership. Repeats are added after, and do not inherit audit selection (A36.6).
    specs = apply_c_audit(specs, c_audit_size)
    specs.extend(plan_r1_repeats(specs, r1_fraction))

    # I14 / A30.5 -- asserted over the COMPLETE realized set, controls and repeats included,
    # BEFORE anything is rendered or written. Raises on collision; never salts or re-rolls.
    MC.assert_realized_blind_ids_unique([s.final_identity for s in specs])

    ordered = presentation_order(specs)

    frames_by_doc = {d["frame"]["document"]: d for d in documents}
    result = BuildResult()
    key_stimuli: dict = {}
    blind_items: list[dict] = []

    open_docs: dict = {}
    try:
        for rank, spec in enumerate(ordered):
            doc = frames_by_doc[spec.document_id]
            frame = doc["frame"]
            page_frame = next(p for p in frame["pages"] if p["page_number"] == spec.page_number)

            # A33.1/A33.2 -- geometry from the COMMITTED frame, never re-derived from the PDF
            bbox = OG.region_bbox(page_frame, spec.region_ordinal)

            path = str(doc["pdf_path"])
            if path not in open_docs:
                open_docs[path] = pymupdf.open(path)
            page = open_docs[path][spec.page_number - 1]

            png, width, height = render_region(page, bbox, spec.dpi)
            bid = MC.blind_id(spec.final_identity)
            image_name = f"{bid}.png"

            key_stimuli[bid] = {
                "canonical_identity": MC.canonical(spec.final_identity),
                "base_identity": MC.canonical(spec.base_identity),
                "document": spec.document_id,
                "document_sha256": spec.document_sha256,
                "page_number": spec.page_number,
                "region_ordinal": spec.region_ordinal,
                "stratum": spec.stratum,
                # A36.2 -- explicit membership, deterministically ordered. NOT a single-frame
                # projection, which could not represent C-and-D without being ambiguous.
                "frames": list(spec.frames),
                "in_c_frame": C_FRAME in spec.frames,
                "in_d_frame": D_FRAME in spec.frames,
                # A36.4 -- routes are metadata about the stimulus; the answers live apart.
                "adjudication_routes": list(spec.adjudication_routes),
                "human_answer_purposes": list(spec.human_answer_purposes),
                "n_human_tasks": spec.n_human_tasks,
                "is_c_audit_selected": spec.is_c_audit_selected,
                "control_kind": spec.control_kind,
                "control_variant": spec.control_variant,
                "is_r1_repeat": spec.is_r1_repeat,
                "r1_base_identity": MC.canonical(spec.base_identity) if spec.is_r1_repeat else None,
                "presentation_rank": rank,
                "renderer": RENDERER_NAME,
                "renderer_version": str(pymupdf.version),
                "dpi": spec.dpi,
                "bbox_pdf_points": [float(v) for v in bbox],
                "image_width_px": width,
                "image_height_px": height,
                "image": image_name,
                "png_sha256": hashlib.sha256(png).hexdigest(),
                # A35.2 -- the printed-line index the adjudicator reports maps through this
                "region_line_bijection": region_line_bijection(page_frame, spec.region_ordinal),
                # the H/X data the LATER join needs. PRIVATE. Never rendered, never blinded.
                "architecture_output": (doc.get("architecture_output") or {}).get(
                    f"{spec.page_number}:{spec.region_ordinal}"
                ),
            }
            blind_items.append({"id": bid, "image": image_name, "question": question})
            result.images[image_name] = png
    finally:
        for handle in open_docs.values():
            handle.close()

    # A28.4 -- every R1 repeat shares its primary's committed bbox; only the scale differs.
    _assert_r1_matches_primary(key_stimuli)

    result.key = {
        "schema": "oracle_key/2",
        "population": "DEVELOPMENT + SYNTHETIC -- pre-execution",
        "prompt_sha256": hashlib.sha256(question.encode()).hexdigest(),
        "n_stimuli": len(key_stimuli),
        "frame_counts": frame_counts(key_stimuli),
        "stimuli": key_stimuli,
    }
    result.blind = {
        "schema": "oracle_blind/1",
        "n_items": len(blind_items),
        "items": blind_items,
    }
    return result


def frame_counts(key_stimuli: dict) -> dict:
    """A36.3 -- raw C, raw D and the overlap, reported SEPARATELY.

    `|C union D|` is never substituted for either frame's denominator. Publishing the overlap
    beside both sizes is what lets a reader see that a C-and-D region is counted once in each
    estimand, rather than having to infer it from a single pooled total.
    """
    primaries = [r for r in key_stimuli.values() if not r["is_r1_repeat"] and r["control_kind"] is None]
    c = [r for r in primaries if r["in_c_frame"]]
    d = [r for r in primaries if r["in_d_frame"]]
    both = [r for r in primaries if r["in_c_frame"] and r["in_d_frame"]]
    return {
        "c_frame": len(c),
        "d_frame": len(d),
        "c_and_d_overlap": len(both),
        "union_reported_for_information_only": len({id(r) for r in c + d}),
        "c_audit_selected": sum(1 for r in primaries if r["is_c_audit_selected"]),
        "human_tasks": sum(r["n_human_tasks"] for r in key_stimuli.values()),
        "ai_route": sum(1 for r in key_stimuli.values() if ROUTE_AI in r["adjudication_routes"]),
        "human_route": sum(1 for r in key_stimuli.values() if ROUTE_HUMAN in r["adjudication_routes"]),
    }


def _assert_r1_matches_primary(key_stimuli: dict) -> None:
    """The repeat must differ from its primary by raster scale and NOTHING else."""
    by_base = {}
    for record in key_stimuli.values():
        by_base.setdefault(record["base_identity"], []).append(record)
    for base, records in by_base.items():
        primary = next((r for r in records if not r["is_r1_repeat"]), None)
        repeat = next((r for r in records if r["is_r1_repeat"]), None)
        if primary is None or repeat is None:
            continue
        if primary["bbox_pdf_points"] != repeat["bbox_pdf_points"]:
            raise OracleBuildError(R1_BBOX_DIFFERS_FROM_PRIMARY, {"base": base})
        if primary["dpi"] != MC.PRIMARY_DPI or repeat["dpi"] != MC.R1_REPEAT_DPI:
            raise OracleBuildError(WRONG_DPI_FOR_STIMULUS, {"primary_dpi": primary["dpi"], "repeat_dpi": repeat["dpi"]})


JOIN_IMAGE_MISSING = "JOIN_IMAGE_MISSING"
JOIN_PNG_SHA_MISMATCH = "JOIN_PNG_SHA_MISMATCH"
JOIN_BLIND_ID_UNKNOWN = "JOIN_BLIND_ID_UNKNOWN"
JOIN_FIELD_MISSING = "JOIN_FIELD_MISSING"

# What a downstream join needs from the private key to bind one adjudication to one region.
REQUIRED_JOIN_FIELDS = (
    "canonical_identity",
    "document_sha256",
    "page_number",
    "region_ordinal",
    "frames",
    "adjudication_routes",
    "stratum",
    "dpi",
    "bbox_pdf_points",
    "png_sha256",
    "region_line_bijection",
)


def verify_join(result: BuildResult) -> list[dict]:
    """I7 -- is every blind id still bound to the image and region the key says it is?

    Returns the list of defects, empty when the join is sound. This is what makes the key
    LOAD-BEARING: `x21` misassociates the key and requires this to report defects, because a
    key that can be shuffled without detection is not a join, it is decoration.
    """
    defects = []
    for item in result.blind.get("items", []):
        bid = item["id"]
        record = result.key["stimuli"].get(bid)
        if record is None:
            defects.append({"reason": JOIN_BLIND_ID_UNKNOWN, "blind_id": bid})
            continue
        for fname in REQUIRED_JOIN_FIELDS:
            if record.get(fname) in (None, ""):
                defects.append({"reason": JOIN_FIELD_MISSING, "blind_id": bid, "field": fname})
        png = result.images.get(item["image"])
        if png is None:
            defects.append({"reason": JOIN_IMAGE_MISSING, "blind_id": bid, "image": item["image"]})
            continue
        if record.get("image") != item["image"] or hashlib.sha256(png).hexdigest() != record.get("png_sha256"):
            defects.append({"reason": JOIN_PNG_SHA_MISMATCH, "blind_id": bid, "image": item["image"]})
    return defects


def write_artifacts(result: BuildResult, out_dir: Path, *, key_name="oracle_key.json", blind_name="oracle_blind.json"):
    """Write both artifacts and the images. Refuses to write the CONFIRMATORY paths early."""
    out_dir = Path(out_dir)
    key_path, blind_path = out_dir / key_name, out_dir / blind_name
    assert_write_permitted(key_path)
    assert_write_permitted(blind_path)

    report = leakage_report(result.blind, result.key)
    if report["unexpected_keys"] or report["leaked_values"] or report["forbidden_text"]:
        raise OracleBuildError(BLIND_ARTIFACT_LEAKS, report)

    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    for name, png in result.images.items():
        (out_dir / "images" / name).write_bytes(png)
    key_path.write_text(json.dumps(result.key, indent=1, sort_keys=True))
    blind_path.write_text(json.dumps(result.blind, indent=1, sort_keys=True))
    return key_path, blind_path
