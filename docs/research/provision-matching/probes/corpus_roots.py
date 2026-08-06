"""Where the bill XML actually lives, for probes written after the #308 fixture split.

Study 1's probes all read `bills/` alone. That was correct when they were written; it is not
correct now. #308 ("move committed fixtures to tests/corpus/, ignore bills/ wholly") split the
corpus in two, and `bills/` became the disposable working tree that a fresh clone does not have
at all. Measured 2026-08-06 on develop:

    bills/          20 bills,  71 xml versions, 13 with >= 2 versions
    tests/corpus/   31 bills,  58 xml versions, 12 with >= 2 versions
    union           34 bills, 106 xml versions, 18 with >= 2 versions

paper.md §5 reports its corpus as 31 bills / 17 multi-version (102 versions per the source-signal
audit). So the union is a slight superset of what Study 1 measured, while `bills/` alone is about
a third smaller in the multi-version bills that every adjacent-pair number depends on. A probe
that reads `bills/` today silently measures a different, smaller corpus than the one Study 1
reports -- the numbers do not merely drift, they are computed over different inputs.

New probes read the UNION. Where a bill appears in both roots, versions are merged by filename and
`bills/` wins on a collision (it is the fetched original; tests/corpus/ is the curated copy).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ROOTS = (REPO / "bills", REPO / "tests" / "corpus")


def bill_versions() -> dict[str, dict[str, Path]]:
    """{bill_id: {version_stem: xml_path}} across every corpus root."""
    out: dict[str, dict[str, Path]] = {}
    for root in ROOTS:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            for xml in sorted(d.glob("*.xml")):
                out.setdefault(d.name, {}).setdefault(xml.stem, xml)
    return out


def multi_version_bills() -> dict[str, list[Path]]:
    """{bill_id: [xml_path, ...]} for bills with >= 2 versions, sorted by version stem."""
    return {b: [v[k] for k in sorted(v)] for b, v in bill_versions().items() if len(v) >= 2}


def adjacent_pairs() -> list[tuple[str, Path, Path]]:
    """(bill_id, older_xml, newer_xml) for every adjacent version pair in the union corpus.

    Adjacency is by the numeric prefix on the version stem (`1_reported-in-house`), and a pair is
    emitted only when the two prefixes are consecutive -- a gap means the corpus is missing the
    version between them, and diffing across the gap would measure a two-step change as one.
    """
    pairs = []
    for bill, paths in multi_version_bills().items():
        numbered = []
        for p in paths:
            head = p.stem.split("_", 1)[0]
            if head.isdigit():
                numbered.append((int(head), p))
        numbered.sort()
        for (na, pa), (nb, pb) in zip(numbered, numbered[1:]):
            if nb == na + 1:
                pairs.append((bill, pa, pb))
    return pairs


def merged_root() -> Path:
    """A single directory that looks like the old `bills/` but holds the UNION of both roots.

    Built out of symlinks under the system temp dir, so it adds nothing to the repo and needs no
    .gitignore entry. Rebuilt on each call (a few hundred symlinks, milliseconds) so it cannot go
    stale against a corpus that just changed.

    This exists so Study 1's probes can read the whole corpus again by changing ONE line
    (`BILLS = REPO / "bills"` -> `BILLS = merged_root()`) rather than being rewritten. Their
    `d.glob("*.xml")` / `BILLS / bill / f"{v}.xml"` access patterns both work unchanged.
    """
    import tempfile

    root = Path(tempfile.gettempdir()) / "deltatrack-merged-corpus"
    for bill, versions in bill_versions().items():
        d = root / bill
        d.mkdir(parents=True, exist_ok=True)
        for stem, src in versions.items():
            link = d / f"{stem}.xml"
            if link.is_symlink() or link.exists():
                continue
            link.symlink_to(src)
    return root


if __name__ == "__main__":
    bv = bill_versions()
    print(f"bills: {len(bv)}   versions: {sum(len(v) for v in bv.values())}")
    print(f"multi-version bills: {len(multi_version_bills())}   adjacent pairs: {len(adjacent_pairs())}")
