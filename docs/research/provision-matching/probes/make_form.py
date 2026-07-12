"""Generate a self-contained HTML labeling form per reviewer (no server, no install).

The reviewer opens `form_<name>.html` in any browser, labels one card at a time, and clicks
"Download my labels" to get `labels_<name>.json` to send back. State autosaves to the
browser's localStorage so they can close and resume. Nothing leaves their machine until they
export — fits the local-only constraint (ADR 0011).

Anti-priming (protocol §5): the card shows only the two texts + structural breadcrumbs + a
NEUTRALLY phrased question. It never shows the mining stratum name, the scores under test, or
the matcher's decision. Rationale is required whenever confidence is medium/low.

The HTML/CSS/JS lives in `form_template.html` (edit it there); this script only injects the
reviewer's assigned, blinded candidates as JSON.

Run (per reviewer; the reviewer must exist in assignments.json):
    PYTHONPATH=docs/research/provision-matching/probes .venv/bin/python \
        docs/research/provision-matching/probes/make_form.py will
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_TEMPLATE = _HERE / "form_template.html"

# fields that must never reach a card — the scores under test + mining artifacts (§5)
_FORBIDDEN = {"measures", "containment", "cosine", "word_overlap", "stratum", "change_type", "extra"}

# neutral question + option labels per stratum (never the mining stratum name)
_QUESTION = {
    "high-containment-different": (
        "Are these the same provision carried across versions, or two different provisions?",
        [("same", "Same provision"), ("different", "Different provisions")],
    ),
    "financial-line": (
        "Are these the same account/line (an amount edit of one line), or two different lines?",
        [("same", "Same line (amount edit)"), ("different", "Different lines")],
    ),
    "consolidation": (
        "Is the OLD provision genuinely absorbed into the NEW section, or only coincidentally sharing a citation?",
        [("genuinely-absorbed", "Genuinely absorbed"), ("coincidentally-contained", "Coincidentally contained")],
    ),
}

_STANDARD = [
    (
        "Same",
        "Same subject, same statutory target, same account/authority — continued or edited "
        "across versions, no matter how much text was added or removed.",
    ),
    ("Different", "Distinct provisions that merely share boilerplate, a citation, or a reused section number."),
    (
        "Genuinely absorbed",
        "The old provision's statutory target actually appears, substantively, inside the new section.",
    ),
    (
        "Coincidentally contained",
        "The overlap is just a shared boilerplate citation, with no substantive continuation.",
    ),
]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: make_form.py <reviewer>")
    reviewer = sys.argv[1]
    entries = {e["id"]: e for e in json.loads((_HERE / "worklist.json").read_text(encoding="utf-8"))["entries"]}
    assign = json.loads((_HERE / "assignments.json").read_text(encoding="utf-8"))["assignments"]
    mine = [cid for cid, a in assign.items() if reviewer in a["reviewers"]]
    if not mine:
        sys.exit(f"no candidates assigned to {reviewer!r} (run make_assignments.py with them)")

    # order by id hash, not raw id, so strata stay interleaved (raw id groups by the
    # cons-/fina-/hcd- prefix and would re-block the anti-priming order from make_worklist)
    payload = []
    for cid in sorted(mine, key=lambda c: hashlib.sha256(c.encode()).hexdigest()):
        if cid not in entries:
            continue  # assignments referenced an id no longer in a regenerated worklist
        e = entries[cid]
        if e["stratum"] not in _QUESTION:
            sys.exit(f"unknown stratum {e['stratum']!r} for {cid} — no neutral question defined (§5)")
        q, opts = _QUESTION[e["stratum"]]
        payload.append(
            {
                "id": cid,
                "question": q,
                "options": opts,
                "bill_old": e["bill_old"],
                "bill_new": e["bill_new"],
                "version_old": e["version_old"],
                "version_new": e["version_new"],
                "bc_old": e.get("display_path_old") or [],
                "bc_new": e.get("display_path_new") or [],
                "text_old": e["text_old"],
                "text_new": e["text_new"],
            }
        )
    leaked = {k for card in payload for k in card if k in _FORBIDDEN}
    if leaked:
        sys.exit(f"score/mining fields leaked into the form: {leaked} — refusing to write (§5)")
    data = {"reviewer": reviewer, "standard": _STANDARD, "entries": payload}
    # </ breaks out of <script>; U+2028/U+2029 are legal JSON but JS line terminators that
    # would make the whole embedded blob fail to parse — escape all three.
    injected = (
        json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace(" ", "\\u2028").replace(" ", "\\u2029")
    )
    html = _TEMPLATE.read_text(encoding="utf-8").replace("__REVIEWER__", reviewer).replace("__DATA__", injected)
    out = _HERE / f"form_{reviewer}.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {len(payload)} cards -> {out.name}  (open in a browser; export labels_{reviewer}.json)")


if __name__ == "__main__":
    main()
