"""Is `normalize_raw` actually unnecessary under the hybrid contract, or only apparently?

Section 8 of `RESULTS-HYBRID.md` claims every branch of `parsers/pdf_text.normalize_raw`
repairs damage that exists only in a page-wide text blob. Read from the code that claim is
plausible; it is not evidence. Two things could make it wrong:

  * A branch might fire on documents the corpus parity table EXCLUDES. Production declines
    unnumbered layouts, and the enrolled bills it declines are exactly where the mid-line
    soft-hyphen branch exists to act (its docstring names them). So the stratum that would
    catch the failure is the stratum the headline table drops.
  * The hybrid might produce the same fused or hyphen-broken words by another route, which
    a bag-of-tokens F1 near 0.999 would not distinguish from success.

So each branch is checked where it FIRES, and the check is a token-level classification of
production-vs-hybrid differences rather than a similarity score:

  hyphen_artifact   a token on one side equals a token on the other with a hyphen added or
                    removed -- the exact damage normalize_raw's hyphen branches repair
  space_artifact    two tokens on one side are one fused token on the other
  other             everything else, sampled so it can be read

A non-zero `hyphen_artifact` on a document where the branch fires falsifies the claim.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_normalize_raw.py \
      --limit-docs 6 --out docs/research/pdf-backend-bakeoff/results/probe_normalize_raw.json
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
from score_phase1 import corpus_documents  # noqa: E402

import deltatrack.parsers.pdf_text as PT  # noqa: E402

# The branches of normalize_raw, each with the pattern that shows it fired on the raw text.
BRANCHES = {
    "crlf": re.compile(r"\r\n"),
    "hyphen_plus_margin_number": PT._HYPHEN_BREAK,
    "glued_chrome": PT._GLUED_CHROME,
    "midline_hyphen_lowercase": re.compile(r"￾[a-z]"),
    "other_soft_hyphen": re.compile(r"￾"),
    "trailing_space": re.compile(r"[^\S\n] *\n"),
}


def raw_page_texts(pdf: Path) -> list[str]:
    """PDFium's raw text per page — the input normalize_raw was written against."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    out = []
    try:
        for i in range(len(doc)):
            pg = doc[i]
            tp = pg.get_textpage()
            try:
                out.append(tp.get_text_range())
            finally:
                tp.close()
                pg.close()
    finally:
        doc.close()
    return out


def classify(prod_text: str, hy_text: str) -> dict:
    """Token-level differences between the two renderings, sorted into named kinds."""
    p, h = Counter(prod_text.split()), Counter(hy_text.split())
    only_p, only_h = p - h, h - p
    hyphen = space = 0
    samples: list[str] = []

    # A hyphen artifact: the same token appears on the other side with hyphens stripped.
    h_nohyph = {t.replace("-", ""): t for t in only_h}
    p_nohyph = {t.replace("-", ""): t for t in only_p}
    for t in list(only_p):
        k = t.replace("-", "")
        if k in h_nohyph and h_nohyph[k] != t:
            hyphen += only_p[t]
            if len(samples) < 5:
                samples.append(f"hyphen: production={t!r} hybrid={h_nohyph[k]!r}")

    # A space artifact: a token on one side is the concatenation of two on the other.
    for t in list(only_h):
        if t in p_nohyph.values():
            continue
        for i in range(2, len(t) - 1):
            if t[:i] in p and t[i:] in p:
                space += only_h[t]
                if len(samples) < 10:
                    samples.append(f"fused: hybrid={t!r} = production {t[:i]!r} + {t[i:]!r}")
                break

    return {
        "tokens_production": sum(p.values()),
        "tokens_hybrid": sum(h.values()),
        "only_production": sum(only_p.values()),
        "only_hybrid": sum(only_h.values()),
        "hyphen_artifact": hyphen,
        "space_artifact": space,
        "samples": samples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-docs", type=int, default=None)
    ap.add_argument("--only-declined", action="store_true", help="only the unnumbered layouts")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    from deltatrack.compare.pdf import _is_unnumbered_layout

    docs = corpus_documents()
    rows = []
    for i, (bill, version, pdf, _xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        # Decide membership BEFORE the expensive work: with --only-declined this skips the
        # raw-text walk and the hybrid extraction on 42 of 52 documents.
        prod_pages = PT.extract_clean_pages(pdf)
        declined = _is_unnumbered_layout(prod_pages)
        if args.only_declined and not declined:
            continue
        raws = raw_page_texts(pdf)
        fired = {name: sum(len(pat.findall(r)) for r in raws) for name, pat in BRANCHES.items()}
        hy_pages, _ = RH.reconstruct(pdfium_hybrid.extract(pdf)[0])
        entry = {
            "doc": key,
            "production_declined": declined,
            "branch_fired": fired,
            "diff": classify(PT.pdf_full_text(prod_pages)[0], PT.pdf_full_text(hy_pages)[0]),
        }
        rows.append(entry)
        d = entry["diff"]
        print(
            f"  [{len(rows)}] {key:<22} declined={str(declined):<5} "
            f"midline_hyphen_fired={fired['midline_hyphen_lowercase']:<4} "
            f"hyphen_artifacts={d['hyphen_artifact']:<4} fused={d['space_artifact']}",
            file=sys.stderr,
        )
        for s in d["samples"][:3]:
            print(f"        {s}", file=sys.stderr)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps({"documents": rows}, indent=1))
        if args.limit_docs and len(rows) >= args.limit_docs:
            break

    tot_fired = Counter()
    for r in rows:
        tot_fired.update(r["branch_fired"])
    print("\nbranch firings over the documents scored:")
    for k, v in tot_fired.items():
        print(f"  {k:28} {v:,}")
    print(f"\n  total hyphen artifacts: {sum(r['diff']['hyphen_artifact'] for r in rows)}")
    print(f"  total fused tokens    : {sum(r['diff']['space_artifact'] for r in rows)}")
    if args.out:
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
