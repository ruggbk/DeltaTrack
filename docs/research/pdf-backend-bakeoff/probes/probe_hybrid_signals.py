"""Does the hybrid contract still carry every geometry/style signal DeltaTrack needs?

The hybrid stream adds characters that carry no geometry. That is a real cost and this
probe prices it, rather than letting the heading-recovery win stand in for the answer.

Three questions:

  S1  How much of the stream is generated, and is the "generated chars have no usable
      geometry" claim exactly true or merely mostly true? Reported as rates over every
      generated char, because a single generated char with a REAL box would mean the
      contract's `None` fields are throwing away information.

  S2  Do the signals the engine actually consumes survive? `glyph_size` (ADR 0012 heading
      levels) and `LineGeom` (the major detector's line-fullness split) are computed only
      from non-generated characters, so the test is whether enough non-generated
      characters remain on each printed line to compute them.

  S3  Does FONT ROLE separation survive? `docs/source-signal-inventory.md` records font
      name as the highest-value unadopted PDF signal -- margin line numbers are a
      different font from the body on 99.9% of numbered lines. Scored as role separation
      (margin vs body vs chrome), never as name-string equality, since names are
      print-class dependent. The empty-font-name rate is reported per stream because the
      inventory's guard depends on it.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_hybrid_signals.py \
      tests/corpus/114-hr-2029/4_reported-in-senate.pdf --limit 40
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid as RH  # noqa: E402
from contract_hybrid import CP, FONT, GEN, SIZE, X0, X1  # noqa: E402

_NUMBERED = re.compile(r"^(\d{1,2}) (.*)$")


def s1_generated(pages) -> dict:
    tot = gen = 0
    no_origin = real_box = non_identity_size = named_font = 0
    for pg in pages:
        for c in pg.chars:
            tot += 1
            if not c[GEN]:
                continue
            gen += 1
            if c[2] is None:  # baseline / origin
                no_origin += 1
            if c[X0] is not None and c[X1] is not None and c[X1] - c[X0] > 0:
                real_box += 1
            if c[SIZE] is not None:
                non_identity_size += 1
            if c[FONT]:
                named_font += 1
    return {
        "chars_total": tot,
        "chars_generated": gen,
        "generated_rate": round(gen / tot, 5) if tot else None,
        "generated_missing_origin": no_origin,
        "generated_with_real_box": real_box,
        "generated_with_size": non_identity_size,
        "generated_with_font_name": named_font,
        "claim_generated_carry_only_origin": (no_origin == 0 and real_box == 0 and non_identity_size == 0),
    }


def s2_signals(pages) -> dict:
    """Every numbered printed line must still yield a size and a full LineGeom."""
    lines = with_size = with_geom = 0
    for pg in pages:
        for row in RH.cluster_lines(pg):
            text = RH._line_text(row)
            m = _NUMBERED.match(text)
            if not m:
                continue
            lines += 1
            ink = [c for c in row if chr(c[CP]) not in ("\r", "\n")]
            content = ink[len(m.group(1)) :]
            printed = [c for c in content if c[CP] != 32 and c[X0] is not None]
            if printed and [c[SIZE] for c in printed if c[SIZE] is not None]:
                with_size += 1
            if printed and RH._first_word_right(content) is not None:
                with_geom += 1
    return {
        "numbered_lines": lines,
        "with_glyph_size": with_size,
        "with_line_geom": with_geom,
        "size_coverage": round(with_size / lines, 5) if lines else None,
        "geom_coverage": round(with_geom / lines, 5) if lines else None,
    }


def s3_font_roles(pages) -> dict:
    """Margin-number font vs body font, over numbered printed lines.

    Keyed on role, not on a literal name: the margin font is whatever font the margin
    digits are set in on this document, and the test is whether it DIFFERS from the font
    of the body text on the same line.
    """
    margin_fonts: Counter = Counter()
    body_fonts: Counter = Counter()
    separated = lines = 0
    empty_named = named_total = 0
    for pg in pages:
        for row in RH.cluster_lines(pg):
            text = RH._line_text(row)
            m = _NUMBERED.match(text)
            if not m:
                continue
            ink = [c for c in row if chr(c[CP]) not in ("\r", "\n")]
            n_margin = len(m.group(1))
            mf = {c[FONT] for c in ink[:n_margin] if not c[GEN]}
            bf = {c[FONT] for c in ink[n_margin:] if not c[GEN] and c[CP] != 32}
            for c in ink:
                if c[GEN]:
                    continue
                named_total += 1
                if not c[FONT]:
                    empty_named += 1
            if not mf or not bf:
                continue
            lines += 1
            margin_fonts.update(mf)
            body_fonts.update(bf)
            if not (mf & bf):
                separated += 1
    return {
        "numbered_lines_with_both": lines,
        "margin_font_differs_from_body": separated,
        "separation_rate": round(separated / lines, 5) if lines else None,
        "margin_fonts": margin_fonts.most_common(4),
        "body_fonts": body_fonts.most_common(4),
        "non_generated_chars": named_total,
        "non_generated_empty_font_name": empty_named,
        "empty_font_name_rate": round(empty_named / named_total, 6) if named_total else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = {}
    for path in args.pdfs:
        pages, summary = pdfium_hybrid.extract(Path(path), args.limit)
        entry = {"summary": summary, "S1": s1_generated(pages), "S2": s2_signals(pages), "S3": s3_font_roles(pages)}
        out[path] = entry
        print(f"\n## {path}")
        s1, s2, s3 = entry["S1"], entry["S2"], entry["S3"]
        print(f"  S1 generated {s1['chars_generated']}/{s1['chars_total']} ({s1['generated_rate']:.1%})")
        print(
            f"     of those: missing origin={s1['generated_missing_origin']}  real box={s1['generated_with_real_box']}"
            f"  size={s1['generated_with_size']}  font name={s1['generated_with_font_name']}"
        )
        print(f"     'generated chars carry origin ONLY' holds exactly: {s1['claim_generated_carry_only_origin']}")
        print(f"  S2 numbered lines {s2['numbered_lines']}: size {s2['size_coverage']}, geom {s2['geom_coverage']}")
        print(f"  S3 margin/body font separation {s3['separation_rate']} over {s3['numbered_lines_with_both']} lines")
        print(f"     margin={s3['margin_fonts']}  body={s3['body_fonts']}")
        print(f"     empty font-name rate on real chars: {s3['empty_font_name_rate']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=1))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
