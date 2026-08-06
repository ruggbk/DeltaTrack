"""R9: is `(bill, version, text_sha256)` a valid identity for one parsed node?

`eval_pass2.py` joins truth counterparts, candidates and system output on that triple. The
reasoning behind rejecting `match_path` was right -- the path is the unstable key this whole
program exists because of, so joining on it would break the evaluator exactly where matching is
hardest. But the replacement assumes normalized body text is unique within a document, and nobody
checked. If two provisions in one version share a body, the evaluator silently treats them as one
node, which corrupts candidate recall, ranking, collision-group construction and assignment
accuracy at once -- and corrupts them in the direction of looking better, because a miss against
node X scores as a hit whenever some unrelated node Y happens to share its text.

This measures it on the real corpus, and prints instances rather than a count (a count cannot tell
a defect from its absence).

WHY THIS IS THE EXPECTED RESULT, not a surprise: appropriations bills are built from repeated
boilerplate. "No part of any appropriation contained in this Act shall remain available for
obligation beyond the current fiscal year unless expressly so provided herein" appears once per
division. The repo already tracks the sibling defect for match_path collisions
(`tests/test_corpus_properties.py::_KNOWN_DUPLICATE_COUNTS`, issue #1); nobody had asked the same
question of body text.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/probe_r9_node_identity.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import banner, bill_versions  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"


def main() -> None:
    print(banner())
    print()
    docs = docs_with_dupes = dup_occurrences = distinct_dup_texts = 0
    max_mult = 0
    worst_docs = []
    examples = []
    label_bills = {"114-hr-2029", "115-hr-5895", "118-hr-4366", "119-hr-1"}
    label_bill_hits = []

    for bill, versions in sorted(bill_versions().items()):
        for stem, path in sorted(versions.items()):
            try:
                tree = normalize_bill(path)
            except Exception:
                continue
            docs += 1
            counts = Counter(_normalize_text(n.body_text) for n in tree.nodes if n.body_text.strip())
            dupes = {t: k for t, k in counts.items() if k > 1}
            if not dupes:
                continue
            docs_with_dupes += 1
            distinct_dup_texts += len(dupes)
            dup_occurrences += sum(dupes.values())
            m = max(dupes.values())
            max_mult = max(max_mult, m)
            worst_docs.append((sum(dupes.values()), bill, stem, len(dupes), m))
            if bill in label_bills:
                label_bill_hits.append((bill, stem, len(dupes), m))
            if len(examples) < 6:
                worst = max(dupes, key=lambda t: dupes[t])
                # the distinct paths those identical bodies sit at -- proof they are distinct nodes
                paths = [" > ".join(n.match_path) for n in tree.nodes if _normalize_text(n.body_text) == worst]
                examples.append((bill, stem, dupes[worst], worst[:100], paths[:4]))

    print("=" * 104)
    print("1. DUPLICATE NORMALIZED BODY TEXT WITHIN A SINGLE BILL VERSION")
    print("=" * 104)
    print(f"  documents parsed                                  : {docs}")
    print(f"  documents containing at least one duplicated body : {docs_with_dupes} ({docs_with_dupes / docs:.0%})")
    print(f"  distinct body texts that occur more than once     : {distinct_dup_texts}")
    print(f"  node occurrences involved in a duplicate group    : {dup_occurrences}")
    print(f"  largest multiplicity (one text, one document)     : {max_mult}")
    print()
    print("  worst documents:")
    for total, bill, stem, n_texts, m in sorted(worst_docs, reverse=True)[:8]:
        print(f"    {bill:<14} {stem:<34} {total:>4} occurrences over {n_texts:>3} texts (max {m})")

    print()
    print("=" * 104)
    print("2. INSTANCES -- distinct nodes the evaluator's key would collapse into one")
    print("=" * 104)
    for bill, stem, mult, text, paths in examples:
        print(f"  {bill} {stem}: {mult} nodes share this body, at {len(paths)}+ distinct paths")
        print(f"    {text!r}")
        for p in paths:
            print(f"      path: {p}")
        print()

    print("=" * 104)
    print("3. DOES THIS REACH THE BILLS THE STUDY ACTUALLY USES?")
    print("=" * 104)
    if label_bill_hits:
        print("  Yes. Versions of the four answer-key bills that contain duplicate bodies:")
        for bill, stem, n_texts, m in label_bill_hits:
            print(f"    {bill:<14} {stem:<34} {n_texts:>3} duplicated texts (max multiplicity {m})")
    else:
        print("  No duplicates in the answer-key bills.")
    print()
    print("  READ THIS AS: `(bill, version, text_sha256)` is a CONTENT hash, not a node identity.")
    print("  An evaluator joining on it cannot distinguish a correct match from a match against a")
    print("  different provision that happens to be boilerplate-identical -- and it fails in the")
    print("  optimistic direction, scoring a miss as a hit. Observation identity must come from the")
    print("  parse (a deterministic node ordinal), with the text hash kept for integrity only.")


if __name__ == "__main__":
    main()
