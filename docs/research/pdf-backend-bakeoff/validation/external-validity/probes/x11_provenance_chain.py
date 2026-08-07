"""x11 -- carry `source_char_index` end-to-end on the DEVELOPMENT hybrid path.

NOT CONFIRMATORY. DEVELOPMENT documents only (hybrid arm only). No holdout document is
opened, no scoring is performed.

WHAT A21 LEFT OPEN. The neutral identity is `(document_sha256, page_number,
source_char_index)`, and A21 measured that **neither adapter stores it**: both `continue`
past rejected characters, so a list position is not the index. The identity was therefore
validated as a DESIGN and not carried by anything.

WHY THIS IS A WRAPPER AND NOT AN EDIT TO THE ADAPTERS. `probes/backends/pdfium_hybrid.py`,
`probes/contract_hybrid.py` and `probes/reconstruct_hybrid.py` are byte-pinned in
`validation/PRESERVED-MANIFEST.txt` under the tag `pdf-bakeoff-prevalidation`, and every
`.py` in that manifest verifies clean today. Those are the exact bytes that produced the
prior spike's confirmatory results, so changing them would retire that claim to buy a
field this probe can obtain without it. The production/research adapters are therefore
untouched, and G1's checklist (A22) states exactly where the field must land when the
harness is built.

THE DRIFT THIS PROBE GUARDS AGAINST. Instrumenting a frozen implementation means
duplicating it, and a duplicate drifts -- a skipped edge case, a filter that moved -- so it
measures a DIFFERENT population while reporting agreement. Both duplications here are
therefore gated by an equality assertion against the frozen original:

    chars     every field of every character, element by element, against
              `pdfium_hybrid.extract`
    lines     every emitted printed line's text, in order, against
              `reconstruct_hybrid.reconstruct_page(...).print_lines`

If either duplicate drifts, this probe fails loudly instead of quietly comparing two
different things.

THE CHAIN PROVED
    PDFium char i -> extracted char record -> reconstruction row -> emitted printed line
    -> neutral projection
"""

from __future__ import annotations

import ctypes
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import pdfium_hybrid  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
import pypdfium2.raw as pdfium_raw  # noqa: E402
import reconstruct_hybrid  # noqa: E402
from contract_hybrid import BASELINE, CP, GEN, SIZE, UPRIGHT, VBOX, X0, X1  # noqa: E402
from neutral_identity import (  # noqa: E402
    EmittedLine,
    SourceGlyph,
    build_owner,
    cluster,
    eligible,
    reconstruction_signature,
)

OUT = EV / "results" / "x11_provenance_chain.json"
ROWS: list[dict] = []
FAILED: list[str] = []

_FONT_BUF = 256
_UPRIGHT_EPS = 1e-6
_SOFT_HYPHEN_CP = 0x00AD
_SOFT_HYPHEN = "­"
_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")


def check(name: str, expected, observed, implication: str = "") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


# ------------------------------------------------------------------ 1. extraction + gid


def extract_with_gids(pdf_path: Path, limit: int | None = None) -> list[tuple[int, list]]:
    """`pdfium_hybrid.extract`, with the PDFium char index recorded beside each record.

    A LINE-FOR-LINE mirror of the frozen adapter's per-character loop. It records `i` and
    changes no decision: the same characters are kept, rejected and flagged, with the same
    values. `verify_extraction` proves that claim rather than resting on this comment.
    """
    doc = pdfium.PdfDocument(str(pdf_path))
    pages: list[tuple[int, list]] = []
    buf = (ctypes.c_char * _FONT_BUF)()
    flags = ctypes.c_int()
    try:
        n_pages = len(doc) if limit is None else min(limit, len(doc))
        for p in range(n_pages):
            page_obj = doc[p]
            textpage = page_obj.get_textpage()
            try:
                raw = textpage.raw
                n = pdfium_raw.FPDFText_CountChars(raw)
                out: list = []
                for i in range(max(n, 0)):
                    cp = pdfium_raw.FPDFText_GetUnicode(raw, i)
                    generated = pdfium_raw.FPDFText_IsGenerated(raw, i) == 1
                    hyphen = pdfium_raw.FPDFText_IsHyphen(raw, i) == 1
                    if hyphen:
                        cp = _SOFT_HYPHEN_CP
                    elif cp < 0x20 and not generated:
                        cp = 0xFFFD

                    ox, oy = ctypes.c_double(), ctypes.c_double()
                    has_origin = bool(pdfium_raw.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)))
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    has_box = bool(
                        pdfium_raw.FPDFText_GetCharBox(
                            raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
                        )
                    )
                    mat = pdfium_raw.FS_MATRIX()
                    has_matrix = bool(pdfium_raw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)))

                    if generated:
                        out.append(
                            (
                                i,
                                (
                                    cp,
                                    True,
                                    oy.value if has_origin else None,
                                    ox.value if has_origin else None,
                                    None,
                                    None,
                                    None,
                                    "",
                                    True,
                                ),
                            )
                        )
                        continue
                    if not (has_box and has_matrix and has_origin):
                        continue
                    size = pdfium_raw.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    nfont = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
                    font = "" if nfont <= 0 else bytes(buf[: max(nfont - 1, 0)]).decode("utf-8", "replace")
                    out.append(
                        (
                            i,
                            (
                                cp,
                                False,
                                oy.value,
                                left.value,
                                right.value,
                                round(size, 4),
                                (bottom.value, top.value),
                                font,
                                abs(mat.b) < _UPRIGHT_EPS and mat.a > 0,
                            ),
                        )
                    )
            finally:
                textpage.close()
                page_obj.close()
            pages.append((p + 1, out))
    finally:
        doc.close()
    return pages


def verify_extraction(name: str, frozen_pages, gid_pages) -> None:
    """THE ANTI-DRIFT GATE: the instrumented copy must reproduce the frozen adapter exactly."""
    mismatches = []
    if len(frozen_pages) != len(gid_pages):
        mismatches.append(f"page count {len(frozen_pages)} != {len(gid_pages)}")
    for fp, (pno, gp) in zip(frozen_pages, gid_pages):
        if fp.page_number != pno or len(fp.chars) != len(gp):
            mismatches.append(f"page {pno}: {len(fp.chars)} chars vs {len(gp)}")
            continue
        for pos, (fc, (_gid, gc)) in enumerate(zip(fp.chars, gp)):
            if fc != gc:
                mismatches.append(f"page {pno} pos {pos}: {fc!r} != {gc!r}")
                if len(mismatches) > 5:
                    break
    check(
        f"{name}: instrumented extraction reproduces the frozen adapter field-for-field",
        [],
        mismatches,
        "a drifted copy would measure a different population while reporting agreement",
    )


# --------------------------------------------------------- 2. reconstruction + gid


def _cells_for_row(row: list[tuple[int, tuple]]) -> list[tuple[int | None, str]]:
    """`reconstruct_hybrid._line_text`, cell by cell, so each character keeps its gid.

    Mirrors the frozen transformation exactly: drop CR/LF, render the soft hyphen as an
    ASCII hyphen, collapse each run of spaces to its FIRST cell, then strip the ends.
    """
    cells: list[tuple[int | None, str]] = []
    for gid, c in row:
        ch = chr(c[CP])
        if ch in ("\r", "\n"):
            continue
        cells.append((None if c[GEN] else gid, "-" if ch == _SOFT_HYPHEN else ch))
    collapsed: list[tuple[int | None, str]] = []
    for cell in cells:
        if cell[1] == " " and collapsed and collapsed[-1][1] == " ":
            continue
        collapsed.append(cell)
    while collapsed and collapsed[0][1] == " ":
        collapsed.pop(0)
    while collapsed and collapsed[-1][1] == " ":
        collapsed.pop()
    return collapsed


def emitted_lines(page_number: int, chars_with_gids: list[tuple[int, tuple]]) -> list[EmittedLine]:
    """The architecture's EMITTED PRINTED LINES, carrying source-glyph provenance.

    The unit is one element of `Page.print_lines` -- production documents it as "one entry
    per line the GPO actually printed". `Page.lines` is NOT the unit: it is the later
    `_merge_print_lines` soft-hyphen recombination, shared by both arms, which spans
    several physical lines by design.
    """
    kept = [
        (pos, gid, c)
        for pos, (gid, c) in enumerate(chars_with_gids)
        if c[BASELINE] is not None
        and (c[GEN] or (c[SIZE] is not None and c[SIZE] > reconstruct_hybrid._SIZE_FLOOR and c[UPRIGHT]))
    ]
    if not kept:
        return []
    rows: list[list] = []
    current: list = []
    anchor: float | None = None
    for item in sorted(kept, key=lambda t: (-t[2][BASELINE], t[0])):
        c = item[2]
        if anchor is None or abs(c[BASELINE] - anchor) <= reconstruct_hybrid._BASELINE_TOL:
            current.append(item)
            if anchor is None:
                anchor = c[BASELINE]
        else:
            rows.append(current)
            current = [item]
            anchor = c[BASELINE]
    if current:
        rows.append(current)
    rows = [sorted(row, key=lambda t: t[0]) for row in rows]

    body_size = reconstruct_hybrid._dominant_size([[c for _p, _g, c in row] for row in rows])
    out: list[EmittedLine] = []
    for row in rows:
        pairs = [(g, c) for _p, g, c in row]
        cells = _cells_for_row(pairs)
        text = "".join(ch for _, ch in cells)
        if reconstruct_hybrid.is_chrome(text, [c for _g, c in pairs], body_size):
            continue
        m = _NUMBERED_LINE.match(text)
        if m:
            cells = cells[len(m.group(1)) + 1 :]
        out.append(EmittedLine(cells=cells, lid=(page_number, len(out))))
    return out


def verify_reconstruction(name: str, frozen_page, emitted: list[EmittedLine]) -> None:
    """THE ANTI-DRIFT GATE: same emitted printed lines, in the same order, as the frozen module."""
    want = [ln.text for ln in frozen_page.print_lines]
    got = [el.text() for el in emitted]
    diffs = [f"[{i}] {w!r} != {g!r}" for i, (w, g) in enumerate(zip(want, got)) if w != g][:5]
    check(
        f"{name}: provenance-carrying reconstruction reproduces print_lines exactly",
        (len(want), []),
        (len(got), diffs),
        "the emitted-line unit is Page.print_lines, and this copy of it is the same one",
    )


# ------------------------------------------------------------------ 3. the neutral skeleton


def neutral_for_page(page_number: int, chars_with_gids: list[tuple[int, tuple]]):
    glyphs = []
    for gid, c in chars_with_gids:
        box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
        g = None if c[GEN] else gid
        if eligible(g, box, bool(c[UPRIGHT])):
            glyphs.append(SourceGlyph(gid, c[BASELINE], box[0], box[1], box[2], box[3]))
    return cluster(glyphs, page_number)


def main(limit: int = 12) -> int:
    docs = [
        ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
        ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ]
    report = []
    for name, path in docs:
        if not path.exists():
            print(f"  SKIP {name} (absent)")
            continue
        print(f"\n== {name} ==")
        frozen_pages, _ = pdfium_hybrid.extract(path, limit=limit)
        gid_pages = extract_with_gids(path, limit=limit)
        verify_extraction(name, frozen_pages, gid_pages)

        chain_ok = 0
        n_neutral = n_emitted = 0
        shape = Counter()
        cross = 0
        gid_max = 0
        unknown_gids: list[str] = []
        for frozen_page, (pno, chars) in zip(frozen_pages, gid_pages):
            fp, _diag = reconstruct_hybrid.reconstruct_page(frozen_page)
            emitted = emitted_lines(pno, chars)
            if pno == 1:
                verify_reconstruction(name, fp, emitted)
            elif [ln.text for ln in fp.print_lines] == [e.text() for e in emitted]:
                chain_ok += 1

            lines = neutral_for_page(pno, chars)
            owner = build_owner(lines)
            n_neutral += len(lines)
            n_emitted += len(emitted)
            gid_max = max([gid_max] + [max(nl.gids) for nl in lines if nl.gids])
            # Every gid anywhere downstream must name a character the extraction actually
            # produced. A list position dressed up as a char index would fail here.
            known = {gid for gid, _c in chars}
            for nl in lines:
                unknown_gids += [f"p{pno} skeleton {g}" for g in nl.gids - known]
            for e in emitted:
                unknown_gids += [f"p{pno} emitted {g}" for g in e.gids - known]
            for ln in lines:
                sig = reconstruction_signature(emitted, ln, owner)
                shape[len(sig)] += 1
                if any(others for _owned, others in sig):
                    cross += 1

        check(
            f"{name}: the chain holds on every remaining page",
            len(frozen_pages) - 1,
            chain_ok,
            "PDFium char i -> record -> row -> emitted printed line -> neutral projection",
        )
        check(
            f"{name}: every skeleton and emitted gid names a real extracted character",
            [],
            unknown_gids[:5],
            "a list position dressed up as a source_char_index would fail this",
        )
        # every emitted gid must be a real PDFium char index, i.e. within the page's count
        rec = {
            "document": name,
            "pages": len(frozen_pages),
            "neutral_lines": n_neutral,
            "emitted_printed_lines": n_emitted,
            "signature_shape_counts": {str(k): v for k, v in sorted(shape.items())},
            "neutral_lines_with_a_cross_line_merge": cross,
            "max_source_char_index_seen": gid_max,
        }
        report.append(rec)
        print(
            f"  neutral_lines={n_neutral} emitted_printed_lines={n_emitted} "
            f"shape={dict(sorted(shape.items()))} cross_line_merges={cross}"
        )

    doc = {
        "population": "DEVELOPMENT (hybrid only) -- no holdout opened, no scoring",
        "chain": "PDFium char i -> extracted record -> reconstruction row -> emitted printed line"
        " -> neutral projection",
        "emitted_line_unit": "one element of Page.print_lines (production: 'one entry per line"
        " the GPO actually printed')",
        "adapters_modified": False,
        "why_not": (
            "pdfium_hybrid.py, contract_hybrid.py and reconstruct_hybrid.py are byte-pinned in "
            "validation/PRESERVED-MANIFEST.txt (tag pdf-bakeoff-prevalidation) and verify clean today; "
            "they are the exact bytes that produced the prior spike's confirmatory results"
        ),
        "signature_shape_key": "0 = neutral line no emitted line carries (chrome/margin/dropped); "
        "1 = emitted as a single printed line; 2+ = split across that many emitted printed lines",
        "documents": report,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
