"""Evidence for ADR 0019: which node fields can and cannot serve as an address.

Read-only. Writes nothing, mutates nothing, and takes no threshold.

Reports, over every bill XML under a corpus root:

- **body text** as an identity — how often two distinct nodes in one document carry the
  same body. This is the measurement ADR 0019 rests on, and the answer is "often":
  appropriations bills are assembled from repeated boilerplate, so a content-hash join
  collapses distinct provisions. It fails *optimistically*, which is why it has to be
  measured rather than assumed safe.
- **match_path** as an address — how often it is duplicated. Expected to be duplicated,
  by design: it is a blocking key, not an identity, and this prints the scale of that.
- **element_id** as an address — empty and duplicated counts. This is the field ADR 0019
  adopts, and the probe exists partly so the claim "it is unique and non-empty" is a
  measurement rather than an assumption.

Usage, from the repo root:

    PYTHONPATH=src .venv/bin/python scripts/probe_observation_identity.py tests/corpus

The default root is `tests/corpus`, the committed set (ADR 0015), so the numbers are
reproducible on a fresh clone with no downloads. Pass another root to sweep a wider
locally-fetched set; the numbers then describe that set, and ADR 0019's quoted figures
are the committed one.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from deltatrack.bill_tree import normalize_bill

DEFAULT_ROOT = Path("tests/corpus")


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else DEFAULT_ROOT
    docs = sorted(root.glob("*/*.xml"))
    if not docs:
        # A silently empty sweep is the fail-open case this probe exists to avoid
        # reproducing, so refuse rather than print a clean-looking set of zeroes.
        print(f"no bill XML under {root}", file=sys.stderr)
        return 1

    nodes_total = 0
    empty_ids = 0
    empty_by_tag: Counter[str] = Counter()
    docs_with_empty_id = 0
    docs_with_dup_id = 0
    docs_with_dup_path = 0
    nodes_in_dup_path = 0
    docs_with_dup_body = 0
    dup_body_texts = 0
    nodes_in_dup_body = 0
    max_body_multiplicity = 0
    skipped: list[str] = []

    for path in docs:
        try:
            tree = normalize_bill(path)
        except Exception as exc:  # a parse failure is not what this probe measures
            skipped.append(f"{path}: {type(exc).__name__}: {exc}")
            continue

        nodes = tree.nodes
        nodes_total += len(nodes)

        empty = [n for n in nodes if not n.element_id]
        if empty:
            docs_with_empty_id += 1
            empty_ids += len(empty)
            for node in empty:
                empty_by_tag[node.tag] += 1

        ids = Counter(n.element_id for n in nodes if n.element_id)
        if any(v > 1 for v in ids.values()):
            docs_with_dup_id += 1

        paths = Counter(n.match_path for n in nodes)
        dup_paths = [v for v in paths.values() if v > 1]
        if dup_paths:
            docs_with_dup_path += 1
            nodes_in_dup_path += sum(dup_paths)

        bodies = Counter(n.body_text for n in nodes if n.body_text.strip())
        dup_bodies = [v for v in bodies.values() if v > 1]
        if dup_bodies:
            docs_with_dup_body += 1
            dup_body_texts += len(dup_bodies)
            nodes_in_dup_body += sum(dup_bodies)
            max_body_multiplicity = max(max_body_multiplicity, max(dup_bodies))

    print(f"corpus root                                   : {root}")
    print(f"documents parsed                              : {len(docs) - len(skipped)}")
    print(f"nodes total                                   : {nodes_total}")
    for row in skipped:
        print(f"  SKIPPED {row}")

    print("\n--- element_id as an address (ADR 0019 adopts this) ---")
    print(f"nodes with an EMPTY element_id                : {empty_ids}")
    print(f"documents containing at least one             : {docs_with_empty_id}")
    for tag, count in empty_by_tag.most_common():
        print(f"    tag={tag!r:32} {count}")
    print(f"documents with a DUPLICATED element_id        : {docs_with_dup_id}")

    print("\n--- match_path as an address (a blocking key, not an identity) ---")
    print(f"documents with a duplicated match_path        : {docs_with_dup_path}")
    print(f"nodes involved in a match_path collision      : {nodes_in_dup_path}")

    print("\n--- body text as an identity (the finding ADR 0019 rests on) ---")
    print(f"documents with at least one duplicated body   : {docs_with_dup_body}")
    print(f"distinct body texts occurring more than once  : {dup_body_texts}")
    print(f"node occurrences in a duplicate group         : {nodes_in_dup_body}")
    print(f"largest multiplicity (one text, one document) : {max_body_multiplicity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
