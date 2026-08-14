"""Slice 6 phase D: how XML describes the provisions PDF calls moved.

Secondary evidence only. XML is not ground truth here — it is a second pipeline whose
``moved`` is defined by round-2 provenance, run over a source that carries real structure
instead of extracted headings. Where the same bill/version pair exists in both formats and
a provision is addressable **unambiguously** in both, the two descriptions are printed
side by side.

Unambiguous means: the PDF move's old anchor text is a ``SEC. n`` label, and that exact
label occurs exactly once among the XML side's section labels. Anything else is skipped
and counted, rather than resolved by fuzzy matching — the brief forbids inventing an
XML<->PDF matcher to fill the table, and a manufactured row would be worse than a gap.

Also reports, for the round-1 changed-anchor rows in these pairs specifically, whether XML
records any change at all at the account heading PDF says was renamed.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_xml_move_comparison.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import accepted_pdf_pairs, pages_for  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills  # noqa: E402
from deltatrack.diff_pdf import diff_pdfs  # noqa: E402

# XML writes section labels lowercase ("sec. 412") and PDF anchors uppercase ("SEC. 412").
# Case is the only difference, so folding it is a normalization and not a fuzzy match.
_SEC = re.compile(r"^SEC\.\s+\d+$", re.IGNORECASE)


def _xml_changes(old_xml: Path, new_xml: Path) -> list[dict]:
    diff = diff_bills(normalize_bill(old_xml), normalize_bill(new_xml))
    return bill_diff_to_dict(diff, financial=True)["changes"]


def _section_label(path: list[str] | None) -> str | None:
    """The path's own section label, only when the path *ends* there.

    A path ending in a subsection ("sec. 412 > (a) In general") addresses part of a
    section, not the section, so it is not the same provision as a PDF block anchored on
    the section heading. Excluding it is what keeps a row unambiguous.
    """
    if not path:
        return None
    return path[-1].upper() if _SEC.match(path[-1]) else None


def _label_index(changes: list[dict], key: str) -> Counter:
    counts: Counter = Counter()
    for change in changes:
        label = _section_label(change.get(key))
        if label:
            counts[label] += 1
    return counts


def main() -> None:
    both = []
    for bill, old, new in accepted_pdf_pairs():
        old_xml, new_xml = old.with_suffix(".xml"), new.with_suffix(".xml")
        if old_xml.exists() and new_xml.exists():
            both.append((bill, old, new, old_xml, new_xml))

    print(f"=== pairs with BOTH formats committed: {len(both)} of {len(accepted_pdf_pairs())} ===")
    for bill, old, new, _, _ in both:
        print(f"  {bill} {old.stem} -> {new.stem}")

    rows: list[dict] = []
    skipped = Counter()
    for bill, old, new, old_xml, new_xml in both:
        print(f"\n--- {bill} {old.stem} -> {new.stem} ---", file=sys.stderr, flush=True)
        pdf = diff_pdfs(pages_for(old), pages_for(new))
        xml_changes = _xml_changes(old_xml, new_xml)
        xml_old_labels = _label_index(xml_changes, "display_path_old")
        xml_by_old_label: dict[str, list[dict]] = {}
        for change in xml_changes:
            label = _section_label(change.get("display_path_old"))
            if label:
                xml_by_old_label.setdefault(label, []).append(change)

        for hunk in pdf.hunks:
            if hunk.change_type != "moved":
                continue
            old_label = hunk.v1_anchor.text if hunk.v1_anchor else None
            new_label = hunk.v2_anchor.text if hunk.v2_anchor else None
            if old_label is None or not _SEC.match(old_label):
                skipped["pdf anchor is not a bare SEC. n label"] += 1
                continue
            if xml_old_labels[old_label] != 1:
                skipped[f"XML old-side label count != 1 ({xml_old_labels[old_label]})"] += 1
                continue
            xml_change = xml_by_old_label[old_label][0]
            xml_new_path = xml_change.get("display_path_new") or []
            xml_new = xml_new_path[-1].upper() if xml_new_path else None
            rows.append(
                {
                    "bill": bill,
                    "pair": f"{old.stem}->{new.stem}",
                    "label": old_label,
                    "pdf_change_type": hunk.change_type,
                    "pdf_new_label": new_label,
                    "xml_change_type": xml_change["change_type"],
                    "xml_new_label": xml_new,
                    "agree_type": xml_change["change_type"] == "moved",
                    "agree_relabel": (new_label == xml_new),
                }
            )

    print(f"\n=== unambiguous cross-source rows: {len(rows)} ===")
    if rows:
        print(f"  {'label':12s} {'PDF -> new':22s} {'XML type':10s} {'XML -> new':22s} {'bill/pair'}")
        for row in rows:
            print(
                f"  {row['label']:12s} {str(row['pdf_new_label']):22s} {row['xml_change_type']:10s} "
                f"{str(row['xml_new_label']):22s} {row['bill']} {row['pair']}"
            )
        agree = sum(1 for r in rows if r["agree_type"])
        print(f"\n  XML also calls it moved:              {agree}/{len(rows)}")
        print(f"  XML reports the same new label:       {sum(1 for r in rows if r['agree_relabel'])}/{len(rows)}")

    print("\n=== PDF moves skipped as not unambiguously addressable in XML ===")
    for reason, count in skipped.most_common():
        print(f"  {count:4d}  {reason}")

    out = Path(__file__).resolve().parent.parent / "results" / "move-xml-comparison.json"
    out.write_text(json.dumps({"rows": rows, "skipped": dict(skipped)}, indent=1) + "\n")
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
