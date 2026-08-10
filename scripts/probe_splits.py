"""Investigation D blocker: how many removals/additions exist ONLY because classification ran?

diff_bills splits a path-matched pair whose similarity is below SIMILARITY_THRESHOLD into a
removal plus an addition (the #368 mechanism). Those entries are CREATED BY classification.
A retrieval round moved before classification cannot see them, so its candidate population
would differ. This measures how much of the move population depends on them.

Uses production match_nodes / normalize_bill / text_similarity directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, match_nodes  # noqa: E402
from deltatrack.similarity import SIMILARITY_THRESHOLD, text_similarity  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

total_split = 0
total_unmatched_old = 0
total_unmatched_new = 0
per_pair = []

for key, old_path, new_path in baseline_pairs():
    old_tree = normalize_bill(old_path)
    new_tree = normalize_bill(new_path)
    pairs = match_nodes(old_tree, new_tree)

    split = unmatched_old = unmatched_new = 0
    for old_node, new_node in pairs:
        if old_node is not None and new_node is None:
            unmatched_old += 1
        elif old_node is None and new_node is not None:
            unmatched_new += 1
        elif old_node is not None and new_node is not None:
            o = _normalize_text(old_node.body_text)
            n = _normalize_text(new_node.body_text)
            if o != n and text_similarity(o, n) < SIMILARITY_THRESHOLD:
                split += 1

    total_split += split
    total_unmatched_old += unmatched_old
    total_unmatched_new += unmatched_new
    if split:
        per_pair.append((key, split, unmatched_old, unmatched_new))

print(f"corpus pairs: {len(baseline_pairs())}")
print(f"classification-created SPLIT pairs (one removal + one addition each): {total_split}")
print(f"structurally unmatched old nodes (removals independent of classification): {total_unmatched_old}")
print(f"structurally unmatched new nodes (additions independent of classification): {total_unmatched_new}")
print(
    f"\nsplit-derived removals are {total_split} of {total_split + total_unmatched_old} "
    f"total removals ({100.0 * total_split / max(1, total_split + total_unmatched_old):.1f}%)"
)
print("\npairs with splits (pair, splits, unmatched_old, unmatched_new):")
for row in sorted(per_pair, key=lambda r: -r[1])[:8]:
    print("  ", row)
