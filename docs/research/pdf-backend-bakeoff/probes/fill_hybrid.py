"""Generate every table in RESULTS-HYBRID.md from the raw result JSON.

Same splice-between-markers discipline as fill_results.py and fill_confirmatory.py: no
number in the published document is transcribed by hand. A table that is not generated
here does not belong in the document.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_hybrid.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
BAKEOFF = REPO / "docs/research/pdf-backend-bakeoff"
RESULTS = BAKEOFF / "results"
DOC = BAKEOFF / "RESULTS-HYBRID.md"

PATHS = ("glyph", "hybrid", "pdfminer")
TARGETS = ("FAMILY HOUSING", "NAVY AND", "ARMY NATIONAL", "AMERICAN BATTLE")


def load(name: str):
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else None


def splice(text: str, marker: str, block: str) -> str:
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    if start not in text:
        return text
    head, rest = text.split(start, 1)
    tail = rest.split(end, 1)[1] if end in rest else rest
    return f"{head}{start}\n\n{block}\n\n{end}{tail}"


def missing(what: str) -> str:
    return f"_(not generated: `{what}` is absent from `results/`. Run the probe, then re-run `fill_hybrid.py`.)_"


# ---------- the four named headings -------------------------------------------


def headings_table(data: dict) -> str:
    out = [
        "| document | heading | production | glyph | **hybrid** | pdfminer |",
        "|---|---|---|---|---|---|",
    ]
    for doc, per in data.items():
        for target in TARGETS:
            cells = []
            for path in ("production", "glyph", "hybrid", "pdfminer"):
                o = per.get(target, {}).get(path)
                if o is None:
                    cells.append("—")
                    continue
                cell = f"{o['correct']} ok"
                if o["corrupted"]:
                    cell = f"**{o['correct']} ok / {o['corrupted']} malformed**"
                cells.append(cell)
            out.append(f"| `{doc}` | {target} | " + " | ".join(cells) + " |")
    tot = {p: [0, 0] for p in ("production", "glyph", "hybrid", "pdfminer")}
    for per in data.values():
        for target in TARGETS:
            for path, o in per.get(target, {}).items():
                tot[path][0] += o["correct"]
                tot[path][1] += o["corrupted"]
    out.append(
        "| **all** | **all four** | "
        + " | ".join(
            f"{v[0]} ok / {v[1]} malformed" for v in (tot[p] for p in ("production", "glyph", "hybrid", "pdfminer"))
        )
        + " |"
    )
    return "\n".join(out)


# ---------- separability ------------------------------------------------------


def separability_table(data: dict) -> str:
    out = [
        "| document | word boundaries | intra-word | boundary gap/size min | intra-word max | separable | "
        "best threshold, errors | shipped 0.25, errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for path, s in data.items():
        if s is None:
            continue
        name = "**POOLED**" if path == "__pooled__" else f"`{Path(path).name}`"
        out.append(
            f"| {name} | {s['word_boundaries']} | {s['intra_word']} | {s['boundary_ratio_min']} | "
            f"{s['intra_ratio_max']} | **{'yes' if s['separable'] else 'NO'}** | "
            f"{s['best_threshold']}, {s['best_threshold_errors']} | "
            f"{s['shipped_0.25_missed_spaces']} missed + {s['shipped_0.25_spurious_spaces']} spurious |"
        )
    return "\n".join(out)


# ---------- corpus parity -----------------------------------------------------


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 5) if vals else None


def corpus_table(data: dict) -> str:
    docs = [d for d in data["documents"] if "vs_production" in d]
    scored = [d for d in docs if not d.get("production_declined")]
    heading_docs = [d for d in scored if any(r["H2_labels_reference"] > 0 for r in d["vs_production"].values())]
    rows = []
    for path in PATHS:
        e = [d["vs_production"][path] for d in scored if path in d["vs_production"]]
        h = [d["vs_production"][path] for d in heading_docs if path in d["vs_production"]]
        rows.append(
            {
                "path": path,
                "n": len(e),
                "text_identical": sum(1 for r in e if r["H1_text_identical"]),
                "text_f1": _mean([r["H1_token_f1"] for r in e]),
                "n_head": len(h),
                "labels_exact": sum(1 for r in h if r["H2_labels_exact"]),
                "labels_absent": sum(r["H2_absent_from_reference"] for r in h),
                "labels_missed": sum(r["H2_missed_from_reference"] for r in h),
                "breadcrumb": _mean([r["H3_breadcrumb_accuracy"] for r in h]),
                "lines_identical": sum(1 for r in e if r["H4_line_numbers_identical"]),
                "lines_jaccard": _mean([r["H4_line_numbers_jaccard"] for r in e]),
                "assoc": _mean([r["H5_assoc_accuracy"] for r in h]),
            }
        )
    out = [
        f"Reference is **production** (`extract_clean_pages`) on the {len(scored)} corpus documents "
        f"production accepts. Heading metrics (H2/H3/H5) are over the {rows[0]['n_head']} of those "
        "that carry any heading; the rest cannot discriminate.",
        "",
        "| metric | " + " | ".join(f"**{p}**" if p == "hybrid" else p for p in PATHS) + " |",
        "|---|" + "---|" * len(PATHS),
    ]

    def row(label, key, fmt="{}"):
        return f"| {label} | " + " | ".join(fmt.format(r[key]) for r in rows) + " |"

    out += [
        "| H1 full text digest identical | " + " | ".join(f"{r['text_identical']}/{r['n']}" for r in rows) + " |",
        row("H1 mean token F1 vs production", "text_f1"),
        "| H2 heading-label set exact | " + " | ".join(f"{r['labels_exact']}/{r['n_head']}" for r in rows) + " |",
        row("H2 labels production does NOT produce", "labels_absent"),
        row("H2 production labels missed", "labels_missed"),
        row("H3 breadcrumb (parent) agreement", "breadcrumb"),
        "| H4 line-number set identical | " + " | ".join(f"{r['lines_identical']}/{r['n']}" for r in rows) + " |",
        row("H4 mean line-number Jaccard", "lines_jaccard"),
        row("H5 amount→heading agreement", "assoc"),
    ]
    return "\n".join(out)


def accuracy_table(data: dict) -> str:
    """The same paths against XML, so parity is not mistaken for correctness."""
    docs = [
        d for d in data["documents"] if "vs_xml" in d and not d.get("production_declined") and not d.get("quoted_block")
    ]
    out = [
        f"Reference is **XML**, over the {len(docs)} production-accepted documents WITHOUT a "
        "`<quoted-block>` (the DeltaTrack#11 parser defect drops those, and they would penalise every "
        "path equally for a reference gap). `production` is included as a fourth column here because "
        "against XML it is a candidate like any other, not the reference.",
        "",
        "| metric | production | " + " | ".join(f"**{p}**" if p == "hybrid" else p for p in PATHS) + " |",
        "|---|---|" + "---|" * len(PATHS),
    ]
    cols = ("production",) + PATHS
    for label, metric, field in (
        ("B2 heading-label F1", "B2", "f1"),
        ("B5 amount→heading F1", "B5", "f1"),
        ("B6 parent/child accuracy", "B6", "accuracy"),
    ):
        cells = []
        for path in cols:
            vals = [d["vs_xml"][path][metric].get(field) for d in docs if path in d.get("vs_xml", {})]
            cells.append(str(_mean(vals)))
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def pairs_table(data: dict) -> str:
    pairs = [p for p in data["pairs"] if "vs_production" in p]
    out = [
        f"Reference is **production**'s canonical diff over {len(pairs)} consecutive version pairs. "
        "`amounts` is the `Counter[(old, new, kind)]` of `amount_entries`; `changes` is the "
        "`Counter[(change_type, norm(old), norm(new))]` signature set.",
        "",
        "| path | amount signatures identical | change signatures identical |",
        "|---|---|---|",
    ]
    for path in PATHS:
        e = [p["vs_production"][path] for p in pairs if path in p["vs_production"]]
        if not e:
            continue
        a = sum(1 for r in e if r["H6_amounts_identical"])
        c = sum(1 for r in e if r["H6_changes_identical"])
        name = f"**{path}**" if path == "hybrid" else path
        out.append(f"| {name} | {a}/{len(e)} | {c}/{len(e)} |")
    return "\n".join(out)


def signals_table(data: dict) -> str:
    out = [
        "| document | generated chars | with a real box | with a size | with a font name | missing origin | "
        "glyph_size coverage | LineGeom coverage | margin/body font separation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for path, e in data.items():
        s1, s2, s3 = e["S1"], e["S2"], e["S3"]
        rate = f"{s1['chars_generated']}/{s1['chars_total']} ({s1['generated_rate']:.1%})"
        sep = s3["separation_rate"]
        sep_cell = f"{sep} over {s3['numbered_lines_with_both']} lines" if sep is not None else "—"
        out.append(
            f"| `{Path(path).name}` | {rate} | **{s1['generated_with_real_box']}** | "
            f"**{s1['generated_with_size']}** | **{s1['generated_with_font_name']}** | "
            f"**{s1['generated_missing_origin']}** | {s2['size_coverage']} ({s2['numbered_lines']} lines) | "
            f"{s2['geom_coverage']} | {sep_cell} |"
        )
    return "\n".join(out)


def portability_table(data: dict) -> str:
    out = [
        "| document | raw stream identical | stream diff ops | all diffs are line-trailing spaces | "
        "**page text digest identical** | line numbers identical | heading labels identical |",
        "|---|---|---|---|---|---|---|",
    ]
    for path, e in data.items():
        out.append(
            f"| `{Path(path).name}` | {e['stream_identical']} | {e['stream_diff_ops']} | "
            f"{e['stream_diffs_are_all_line_trailing_spaces']} | **{e['pages_text_identical']}** | "
            f"{e['pages_line_numbers_identical']} ({e['n_line_numbers']}) | "
            f"{e['pages_labels_identical']} ({e['n_labels']}) |"
        )
    return "\n".join(out)


def wasm_table(data: dict) -> str:
    present = data["entry_points_present"]
    out = [
        f"`@embedpdf/pdfium` **{data['wrapper_version']}**, called for real on a GPO bill page "
        f"({data['count_chars']} characters). Presence is asked of the wrapper object an adapter would "
        "call, and each function is then invoked on every character so an exported stub cannot pass.",
        "",
        "| entry point | exported | exercised |",
        "|---|---|---|",
    ]
    ex = data["exercised"]
    hits = {
        "FPDFText_GetCharBox": ex["charbox"],
        "FPDFText_GetMatrix": ex["matrix"],
        "FPDFText_GetCharOrigin": ex["origin"],
        "FPDFText_IsGenerated": ex["generated"],
        "FPDFText_IsHyphen": ex["hyphen"],
        "FPDFText_GetFontInfo": ex["fontinfo"],
        "FPDFText_HasUnicodeMapError": ex["maperror"],
    }
    for name, ok in present.items():
        n = hits.get(name)
        note = f"{n} non-trivial returns" if n is not None else "called"
        out.append(f"| `{name}` | {'yes' if ok else '**NO**'} | {note} |")
    out.append("")
    out.append(f"**All {len(present)} required entry points present: {data['all_present']}.**")
    return "\n".join(out)


def backend_spacing_table(data: dict) -> str:
    out = [
        f"Probe boundary: `{data['probe_text']}` on `{data['pdf']}` page {data['page']}. The neutral "
        f"glyph layer produces `{data['probe_text'].replace(' ', '')}` here.",
        "",
        "| backend | its own text keeps the space | produces the joined form | how a synthesised character is marked |",
        "|---|---|---|---|",
    ]
    for name, r in data["backends"].items():
        if "error" in r:
            out.append(f"| {name} | — | — | ERROR: {r['error'][:60]} |")
            continue
        out.append(
            f"| {name} | **{r['recovers_space']}** | **{r['produces_joined_form']}** | {r['generated_marker']} |"
        )
    out.append("| **the glyph seam** | **False** | **True** | n/a — the information is discarded before this point |")
    return "\n".join(out)


def main() -> None:
    text = DOC.read_text()
    jobs = [
        ("H_BACKEND_SPACING", "probe_backend_spacing.json", backend_spacing_table),
        ("H_HEADINGS", "probe_failure_headings.json", headings_table),
        ("H_SEPARABILITY", "probe_separability.json", separability_table),
        ("H_CORPUS", "hybrid_docs.json", corpus_table),
        ("H_ACCURACY", "hybrid_docs.json", accuracy_table),
        ("H_PAIRS", "hybrid_pairs.json", pairs_table),
        ("H_SIGNALS", "probe_hybrid_signals.json", signals_table),
        ("H_PORTABILITY", "hybrid_portability.json", portability_table),
        ("H_WASM", "hybrid_wasm_entrypoints.json", wasm_table),
    ]
    for marker, source, fn in jobs:
        data = load(source)
        block = fn(data) if data else missing(source)
        text = splice(text, marker, block)
    DOC.write_text(text)
    print(f"wrote {DOC}")


if __name__ == "__main__":
    main()
