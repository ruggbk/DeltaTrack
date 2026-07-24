"""Where bill documents live.

Two trees, deliberately separate (#308, ADR 0015):

``tests/corpus/`` (:data:`FIXTURES_DIR`)
    The curated, committed fixture set. Every file here is tracked in git and named in
    ``tests/corpus_manifest.toml`` or pinned by a golden module, so the correctness
    gates collect a byte-identical set on every machine and in CI.

``bills/`` (:data:`DOWNLOADS_DIR`)
    The working directory ``fetch_bills.py`` and ``fetch_bill_text_archives.py``
    download into. Entirely gitignored, entirely disposable, and not a test input.

They used to be one directory, which meant a committed fixture needed a hand-written
``.gitignore`` re-admit line: a second copy of the manifest that nothing checked for
agreement, and whose omission was silent (``git add`` no-ops on an ignored path, so the
fixture stayed on the author's disk and vanished only on a fresh CI checkout). Splitting
the trees removes that edit rather than guarding it.

Import from here rather than spelling either path again — one home for the layout means
a future move is one edit, and a test that reaches into ``bills/`` for a *fixture* is
reaching into disposable scratch, which ``tests/test_fixture_layout.py`` now rejects.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

#: Committed test fixtures. Tracked in git; safe to depend on in CI.
FIXTURES_DIR = PROJECT_ROOT / "tests" / "corpus"

#: Downloaded working corpus. Gitignored; present only where someone has fetched it.
DOWNLOADS_DIR = PROJECT_ROOT / "bills"


def fixture_path(bill_id: str, filename: str) -> Path:
    """Path to a committed fixture, whether or not it exists.

    Does not fall back to :data:`DOWNLOADS_DIR`: a gate that pins a fixture should fail
    loudly when it is missing, not quietly read a downloaded copy that only one machine
    has. Use :func:`resolve_bill_file` for the genuinely mixed case.
    """
    return FIXTURES_DIR / bill_id / filename


def resolve_bill_file(bill_id: str, filename: str) -> Path:
    """The committed fixture if there is one, else the downloaded copy.

    For the one consumer whose inputs are legitimately mixed: the committee-report
    validation fixtures reference nineteen bill versions, fourteen committed and five
    still download-only (#278). Returns the ``bills/`` path when no fixture exists, so
    the caller's own ``.exists()`` check reports on the file it would actually read.
    """
    committed = fixture_path(bill_id, filename)
    return committed if committed.exists() else DOWNLOADS_DIR / bill_id / filename


def sweep_bill_dirs() -> list[Path]:
    """Every bill directory in either tree, fixtures first, one entry per bill id.

    Backs ``CORPUS_SWEEP=1`` (the opt-in, non-CI exploratory mode). It must span both
    trees: sweeping only ``bills/`` after the split would silently drop the committed
    fixtures from the broad sweep, narrowing exploratory coverage with nothing turning
    red — locked by ``tests/test_fixture_layout.py``. A bill present in both trees is
    yielded once, from ``tests/corpus/``, so a downloaded copy cannot shadow the
    committed bytes.
    """
    by_id: dict[str, Path] = {}
    for root in (FIXTURES_DIR, DOWNLOADS_DIR):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name not in by_id:
                by_id[d.name] = d
    return [by_id[k] for k in sorted(by_id)]
