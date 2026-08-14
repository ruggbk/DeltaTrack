"""cross_engine_control -- A39.2: the CONFIRMATORY cross-engine qualification producer.

    frozen rule   PRE-REGISTRATION red-team #2 / A27.6 -- re-run the neutral skeleton through a
                  second engine on a 10 % page subsample; document >= 0.95 and every sampled
                  page >= 0.75, else label results PDFIUM-CONDITIONED FRAME. NEVER
                  decision-blocking.
    executable    `cross_engine_result(...)` and `write_cross_engine_control(...)`
    test          `x22_score_input_contract.py`

WHY THIS EXISTS SEPARATELY FROM x09. `x09` is the DEVELOPMENT proof that the mechanism works
and that its faults are detectable; its artifact is explicitly development-only and may not be
consumed as the confirmatory qualification. This module produces the distinct canonical
artifact for the confirmatory population, behind the same VALID execution boundary as every
other confirmatory writer.

THE RULE HAS EXACTLY ONE OWNER, AND IT IS `X09.gate`. This module selects A39.2's sampled rows
and then CALLS that function; it does not recompute the denominator or the thresholds. An
earlier version did recompute them and got both wrong -- it read a `pdfium_lines` key that does
not exist, and scored `matched / pdfium` instead of the frozen `matched / max(pdfium, pymupdf)`.
The larger-count denominator is load-bearing: it makes over-segmentation by EITHER engine lower
agreement, so scoring against PDFium alone made PyMuPDF over-segmentation invisible. Keeping
0.95 / 0.75 / `max(...)` in two independently executable places is what allowed that drift, so
they now live in one place only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import methodology_contracts as MC  # noqa: E402
import x09_skeleton_cross_engine as X09  # noqa: E402

SOURCE_SHA256_MISMATCH = "SOURCE_SHA256_MISMATCH"
DOCUMENT_RECORD_INCOMPLETE = "DOCUMENT_RECORD_INCOMPLETE"
# A45.6 -- the record's three fields must JOINTLY describe one member of the authority.
DOCUMENT_NOT_A_MEMBER = "DOCUMENT_NOT_A_MEMBER"
RECORD_AUTHORITY_MISMATCH = "RECORD_AUTHORITY_MISMATCH"
NON_CANONICAL_AUTHORITY = "NON_CANONICAL_AUTHORITY"


class CrossEngineError(Exception):
    """The measurement cannot be produced as frozen. Deterministic, never a value."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def verified_sha256(pdf_path: Path, expected_sha256: str) -> str:
    """A39.2 -- the document SHA is RESULT-BEARING input, so it is verified, not trusted.

    The page sample is ranked over `(document_sha256, page_number)`. A caller-supplied string
    that does not match the bytes would therefore select a different sample for the same
    document -- silently, and reproducibly, so nothing downstream could notice. Verifying
    closes that freedom: the pure A39.2 contract will happily rank any SHA, but the
    result-bearing producer cannot reach that freedom.
    """
    actual = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise CrossEngineError(
            SOURCE_SHA256_MISMATCH,
            {"path": str(pdf_path), "expected": expected_sha256, "actual": actual},
        )
    return actual


def document_inputs(record: dict) -> tuple[str, str, Path]:
    """THIS PRODUCER'S OWN READ of one caller document record. The requirement, executable.

    A45. `write_cross_engine_control` used to index the record inline, so "what this consumer
    requires" existed only as three subscript expressions inside a loop body -- unreachable
    without running the loop, which means running the measurement, which pre-boundary means not
    at all. The canonical producer `execute_study.control_documents` emitted a record without
    `document_sha256`, nothing compared the two shapes, and the mismatch surfaced as a raw
    `KeyError` at execution time with no artifact written.

    Naming the read here makes the requirement callable without measuring anything, which is
    what lets a readiness gate exercise the real handoff on a real descriptor and go RED
    instead of discovering the gap after authorization.

    THIS IS THE ONLY PLACE THE WRITER READS THE MEASUREMENT ARGUMENTS from a record, so the
    requirement cannot drift from the use: a fourth field would have to be read here to reach
    `cross_engine_result`, and `handoff_report` would then exercise that too.

    Deliberately NOT a shared constant imported by both sides. A field-name set that the
    producer, the consumer and the test all read from one declaration agrees with itself by
    construction and proves nothing about the boundary.
    """
    missing = [f for f in ("document", "document_sha256", "pdf_path") if record.get(f) in (None, "")]
    if missing:
        raise CrossEngineError(
            DOCUMENT_RECORD_INCOMPLETE,
            {"missing": missing, "record_keys": sorted(record) if isinstance(record, dict) else None},
        )
    # ORDERED AS `cross_engine_result`'s OWN PARAMETERS, so `cross_engine_result(*inputs)` is
    # the only spelling and a silently transposed pair is not reachable.
    return record["document"], record["document_sha256"], Path(record["pdf_path"])


def assert_records_from_authority(documents: list[dict], membership_path=None) -> list[str]:
    """A45.6 -- every record's id, PATH and SHA must JOINTLY describe ONE member. Returns ids.

    THE DEFECT THIS CLOSES, measured before the repair on SYNTHETIC/DEVELOPMENT material. A
    record carrying member A's id with member B's VALID path and B's VALID SHA was ACCEPTED:

        row['document']        113-hr-3547        <- A
        row['document_sha256'] 3824ac79f11f       <- B's, and it really is B's bytes
        sampled_pages          [2]                <- ranked over B's SHA
        A's OWN measurement    sampled [1], pass=False
        the substituted row    sampled [2], pass=True

    So the artifact reported a PASS for a document whose own measurement FAILS the frozen gate,
    which WITHHOLDS AN EARNED `PDFIUM-CONDITIONED FRAME` qualification. Nothing downstream could
    see it: `verified_sha256` passes because B's SHA genuinely is B's bytes, and `score_metrics`'
    exact set-equality check passes because A's id IS present, so
    `CROSS_ENGINE_DOCUMENT_MISSING`, `_EXTRA` and `_DUPLICATE` all stay silent.

    WHY THE OTHER TWO CHECKS CANNOT COVER THIS, and why this is not a third authority.
    `verified_sha256` compares the record to the SOURCE BYTES; this compares the record to the
    COMMITTED AUTHORITY. Neither implies the other, and the pair above is exactly the case that
    satisfies the first and violates the second. The authority is not re-defined here: the id ->
    record mapping is `execute_study.authority_index`, the same function
    `assert_population_complete` and `load_frames` already compare against. There is one
    population authority and this reads it.

    NOT A SUBSTITUTE FOR `control_documents` EITHER. That the canonical caller derives its
    records from the authority is a CALLER OBLIGATION; this is a GATE on the writer, so a
    hand-assembled tuple cannot reach a measurement whatever the caller intended.

    NO FILE IS READ and no page is measured, so this can refuse before any extraction and can be
    called on the canonical composition pre-boundary as a positive control.

    The path is compared by its RECORDED SUFFIX, for the reason `assert_population_complete`
    records: `docs_root` is a SYNTHETIC/DEVELOPMENT seam, so an absolute comparison would refuse
    every fixture while proving nothing more about the canonical run.
    """
    import execute_study as ES

    membership_path = Path(membership_path) if membership_path else ES.MEMBERSHIP
    # A43.8, reused rather than restated: an authority is only worth comparing against while it
    # is still the frozen artifact. A no-op for SYNTHETIC/DEVELOPMENT fixtures by construction.
    ES.assert_canonical_authority(membership_path)
    records = ES.authority_index(membership_path)

    seen = []
    for doc in documents:
        document, sha, pdf_path = document_inputs(doc)
        want = records.get(document)
        if want is None:
            raise CrossEngineError(
                DOCUMENT_NOT_A_MEMBER,
                {"document": document, "authority": str(membership_path), "n_members": len(records)},
            )
        mismatches = {}
        if sha != want["sha256"]:
            mismatches["document_sha256"] = (sha, want["sha256"])
        if want["path"] and not str(pdf_path).endswith(str(want["path"])):
            mismatches["pdf_path"] = (str(pdf_path), want["path"])
        if mismatches:
            raise CrossEngineError(
                RECORD_AUTHORITY_MISMATCH,
                {"document": document, "fields": mismatches, "authority": str(membership_path)},
            )
        seen.append(document)
    return seen


def _page_count(pdf_path: Path) -> int:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def cross_engine_result(document: str, document_sha256: str, pdf_path: Path, limit: int | None = None) -> dict:
    """One document's cross-engine qualification, measured on the A39.2 sampled pages.

    `limit=None` means THE WHOLE DOCUMENT, which is what the canonical writer uses. It is
    resolved to the real page count rather than passed through: `X09.pymupdf_lines` computes
    `min(limit, page_count)` and would raise on None. It is never reinterpreted as zero or as
    some prefix -- a silently truncated confirmatory measurement would qualify a frame on a
    fraction of its pages and report it as the whole.
    """
    pdf_path = Path(pdf_path)
    sha = verified_sha256(pdf_path, document_sha256)
    effective_limit = _page_count(pdf_path) if limit is None else limit

    pdfium_pages = X09.pdfium_lines(pdf_path, effective_limit)
    pymupdf_pages = X09.pymupdf_lines(pdf_path, effective_limit)
    measured = X09.measure(pdfium_pages, pymupdf_pages)

    sampled_pages = MC.cross_engine_pages(sha, [row["page"] for row in measured])
    sampled_rows = [row for row in measured if row["page"] in set(sampled_pages)]

    # THE FROZEN RULE, called rather than reimplemented.
    verdict = X09.gate(sampled_rows)

    return {
        "document": document,
        "document_sha256": sha,
        "page_count": len(measured),
        "pages_measured": [row["page"] for row in measured],
        "sampled_pages": sampled_pages,
        "n_sampled": len(sampled_pages),
        "matched": sum(row["matched"] for row in sampled_rows),
        # the frozen denominator, reported so a reader can see WHICH one was used
        "denominator": sum(max(row["pdfium"], row["pymupdf"]) for row in sampled_rows),
        "denominator_rule": "sum(max(pdfium, pymupdf)) over sampled pages -- X09.gate's own",
        "gate": verdict,
        "passed": verdict["pass"],
        "qualification": None if verdict["pass"] else "PDFIUM-CONDITIONED FRAME",
        "decision_blocking": False,  # A27.6 -- qualifies reporting, blocks nothing
    }


CANONICAL_ARTIFACT = HERE.parents[1] / "results" / "cross_engine_control.json"


def write_cross_engine_control(documents: list[dict], out_path: Path | None = None, membership_path=None) -> dict:
    """A39.2 -- the CANONICAL execution-time artifact. Refuses before a VALID boundary.

    `documents` items: {"document", "document_sha256", "pdf_path"}, and on the canonical path
    they come from `execute_study.control_documents`. Guarded exactly as the oracle key and the
    S1 artifact are, so no confirmatory artifact can be written under a weaker condition than
    the material it describes.

    A45.6 -- EVERY RECORD IS CHECKED AGAINST THE POPULATION AUTHORITY, and that check is a GATE
    here rather than an obligation on the caller. "The canonical caller happens to use
    `control_documents`" is not a property this writer can verify, and a hand-assembled record
    carrying one member's id with another's valid path and valid SHA was accepted, producing a
    row that reported the wrong document's verdict under the right document's name.

    ALL RECORDS ARE VALIDATED BEFORE ANY IS MEASURED. Validating inside the measurement loop
    would let a valid record ahead of a substituted one be extracted first, so "refused before
    any measurement" would be true of the artifact and false of the run.

    `membership_path` is the SYNTHETIC/DEVELOPMENT seam, and it is the same seam
    `execute_study.load_population` and `write_frames` carry. It may NOT be combined with the
    canonical `out_path`: the two are independently reasonable and their combination is a
    canonical artifact vouched for by a fixture, which is the A43.6 defect.
    """
    import build_oracle as BO

    out_path = Path(out_path) if out_path else CANONICAL_ARTIFACT
    # The pairing rule runs FIRST, before the boundary gate, exactly as `write_frames` orders it
    # -- so it is testable pre-boundary rather than hidden behind an authorization refusal.
    if out_path.resolve() == CANONICAL_ARTIFACT.resolve():
        import execute_study as ES

        if membership_path is not None and Path(membership_path).resolve() != ES.MEMBERSHIP.resolve():
            raise CrossEngineError(
                NON_CANONICAL_AUTHORITY,
                {"out_path": str(out_path), "membership_path": str(membership_path), "required": str(ES.MEMBERSHIP)},
            )
    BO.assert_write_permitted(out_path)
    # NO MEASUREMENT HAS HAPPENED YET, and none may until every record is proven to describe a
    # member. `verified_sha256` is deliberately NOT duplicated here: it compares the record to
    # the BYTES and still runs inside `cross_engine_result`, where it catches the one case this
    # cannot see -- bytes that changed while the recorded SHA did not.
    assert_records_from_authority(documents, membership_path)

    rows = []
    for doc in documents:
        # ORDER UNCHANGED BY A45. Authorization is the more fundamental question and is still
        # asked first, on the same fields. `document_inputs` opens no file, so it could safely
        # run earlier; it is left second so that a MALFORMED HOLDOUT record keeps reporting
        # HOLDOUT_BEFORE_EXECUTION_BOUNDARY rather than a shape complaint, which is the same
        # ordering ruling `execute_study.build_document_frame_for` records.
        BO.assert_source_permitted(doc["document"], doc.get("pdf_path"))
        rows.append(cross_engine_result(*document_inputs(doc)))

    artifact = {
        "schema": "cross_engine_control/1",
        "population": BO.realized_population(
            [{"frame": {"document": d["document"]}, "pdf_path": d.get("pdf_path")} for d in documents]
        ),
        "execution_boundary_state": BO.execution_boundary_state(),
        "namespace": MC.CROSS_ENGINE_NAMESPACE,
        "fraction": MC.CROSS_ENGINE_FRACTION,
        "document_threshold": X09.DOC_MIN,
        "page_threshold": X09.PAGE_MIN,
        "rule_owner": "x09_skeleton_cross_engine.gate -- called, never reimplemented",
        "development_evidence_is_not_this": "results/x09_skeleton_cross_engine.json is DEVELOPMENT "
        "mechanism evidence only and is never a confirmatory scorer input",
        "per_document": rows,
        "n_documents": len(rows),
        "n_qualified": sum(1 for r in rows if not r["passed"]),
        "decision_blocking": False,
        "qualification_applies": any(not r["passed"] for r in rows),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1, default=str))
    return artifact
