"""cross_engine_control -- A39.2: the CONFIRMATORY cross-engine qualification producer.

    frozen rule   PRE-REGISTRATION red-team #2 / A27.6 -- re-run the neutral skeleton through a
                  second engine on a 10 % page subsample; document >= 0.95 and every sampled
                  page >= 0.75, else label results PDFIUM-CONDITIONED FRAME. NEVER
                  decision-blocking.
    executable    `cross_engine_result(document, pdf_path)` and `write_cross_engine_control(...)`
    test          `x22_score_input_contract.py`

WHY THIS EXISTS SEPARATELY FROM x09. `x09` is the DEVELOPMENT proof that the mechanism works
and that its faults are detectable; its artifact is explicitly development-only and may not be
consumed as the confirmatory qualification. This module produces the distinct canonical
artifact for the confirmatory population, behind the same VALID execution boundary as every
other confirmatory writer.

NO SECOND GEOMETRY COMPARATOR IS INVENTED. The matching rule, the tolerances and both
thresholds are x09's, imported and reused. The only thing added here is A39.2's frozen page
sample, which x09 never needed because it measured whole documents.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import methodology_contracts as MC  # noqa: E402
import x09_skeleton_cross_engine as X09  # noqa: E402


def cross_engine_result(document: str, document_sha256: str, pdf_path: Path, limit: int | None = None) -> dict:
    """One document's cross-engine agreement, measured on the A39.2 sampled pages.

    The sample is drawn from the document's OWN page numbers, so it is reproducible from
    committed facts and independent of the order pages are listed in.
    """
    pdfium_pages = X09.pdfium_lines(Path(pdf_path), limit)
    pymupdf_pages = X09.pymupdf_lines(Path(pdf_path), limit)
    measured = X09.measure(pdfium_pages, pymupdf_pages)

    all_pages = [row["page"] for row in measured]
    sampled = set(MC.cross_engine_pages(document_sha256, all_pages))
    sampled_rows = [row for row in measured if row["page"] in sampled]

    matched = sum(row["matched"] for row in sampled_rows)
    total = sum(row["pdfium_lines"] for row in sampled_rows)
    document_agreement = (matched / total) if total else 0.0
    page_agreements = {
        row["page"]: (row["matched"] / row["pdfium_lines"] if row["pdfium_lines"] else 0.0) for row in sampled_rows
    }

    qualification = MC.cross_engine_qualification(document_agreement, page_agreements)
    return {
        "document": document,
        "document_sha256": document_sha256,
        "page_count": len(all_pages),
        "sampled_pages": sorted(sampled),
        "n_sampled": len(sampled),
        "matched_lines": matched,
        "pdfium_lines": total,
        **qualification,
    }


def write_cross_engine_control(documents: list[dict], out_path: Path | None = None) -> dict:
    """A39.2 -- the CANONICAL execution-time artifact. Refuses before a VALID boundary.

    `documents` items: {"document", "document_sha256", "pdf_path"}. Guarded exactly as the
    oracle key and the S1 artifact are, so no confirmatory artifact can be written under a
    weaker condition than the material it describes.
    """
    import build_oracle as BO

    out_path = Path(out_path) if out_path else (HERE.parents[1] / "results" / "cross_engine_control.json")
    BO.assert_write_permitted(out_path)

    rows = []
    for doc in documents:
        BO.assert_source_permitted(doc["document"], doc.get("pdf_path"))
        rows.append(cross_engine_result(doc["document"], doc["document_sha256"], Path(doc["pdf_path"])))

    artifact = {
        "schema": "cross_engine_control/1",
        "population": BO.realized_population(
            [{"frame": {"document": d["document"]}, "pdf_path": d.get("pdf_path")} for d in documents]
        ),
        "execution_boundary_state": BO.execution_boundary_state(),
        "namespace": MC.CROSS_ENGINE_NAMESPACE,
        "fraction": MC.CROSS_ENGINE_FRACTION,
        "document_min": MC.CROSS_ENGINE_DOC_MIN,
        "page_min": MC.CROSS_ENGINE_PAGE_MIN,
        "comparator": "x09 matching rule and tolerances, reused -- no second geometry comparator",
        "per_document": rows,
        "n_documents": len(rows),
        "n_qualified": sum(1 for r in rows if not r["passed"]),
        # A27.6 -- reporting qualification only. It labels results and blocks nothing.
        "decision_blocking": False,
        "qualification_applies": any(not r["passed"] for r in rows),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1, default=str))
    return artifact
