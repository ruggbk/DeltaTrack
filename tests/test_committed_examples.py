"""The committed reference reports must match what the renderer produces today (#284).

Three rendered HTML files are checked into the repo: the two under `examples/` and the
sample the web app serves from its landing page. All three are produced by hand, by
running `render_examples.py` and copying one of its outputs over the sample, so they fall
behind silently whenever the renderer changes and nobody re-runs it. They had drifted a
month behind before #285 regenerated them, and the full suite stayed green throughout.

These tests close that gap: they re-render from the committed corpus and compare. The
render is deterministic and takes under two seconds, so it runs in the default CI job
rather than behind the `slow` marker. That choice is load-bearing. CI invokes `slow`
tests only by explicit path (`.github/workflows/ci.yml`), so marking these `slow` would
quietly drop them from CI and rebuild the fail-open gap they exist to close.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import render_examples
from corpus_paths import FIXTURES_DIR

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
SERVED_SAMPLE = ROOT / "webapp" / "sample" / "example.html"
PDF_EXAMPLE = EXAMPLES / "hr8752_pdf_diff.html"

REGENERATE = "Run `uv run python render_examples.py` and commit the result."


def _corpus_files() -> list[Path]:
    """Every bill file `render_examples.py` reads, derived from its own spec list."""
    files = []
    for spec in render_examples.EXAMPLES_TO_RENDER:
        for stem in (spec.v1_filename_stem, spec.v2_filename_stem):
            for suffix in ("xml", "pdf"):
                files.append(FIXTURES_DIR / spec.bill_dir / f"{stem}.{suffix}")
    return files


def _describe_mismatch(committed: Path, fresh: Path) -> str:
    """Point at the first differing line instead of dumping ~900 KB into the report."""
    old = committed.read_text().splitlines()
    new = fresh.read_text().splitlines()
    for n, (a, b) in enumerate(zip(old, new), start=1):
        if a != b:
            return f"first differs at line {n}:\n  committed: {a[:160]}\n  fresh:     {b[:160]}"
    return f"identical for {min(len(old), len(new))} lines, then lengths differ ({len(old)} vs {len(new)})"


def test_example_corpus_files_are_committed():
    """Fail closed if a source bill goes missing, rather than skipping the comparison.

    Without this, deleting a corpus file would turn the render below into an error or a
    skip, and the drift guard would stop guarding without anyone being told.
    """
    missing = [p.relative_to(ROOT) for p in _corpus_files() if not p.exists()]
    assert not missing, f"corpus files render_examples.py needs are missing: {missing}"


def test_committed_examples_match_a_fresh_render(tmp_path, monkeypatch):
    """The files under `examples/` are what the current renderer emits."""
    monkeypatch.setattr(render_examples, "EXAMPLES", tmp_path)
    render_examples.main()

    fresh_files = sorted(tmp_path.glob("*.html"))
    assert fresh_files, "render_examples.main() wrote nothing; the comparison below would vacuously pass"

    for fresh in fresh_files:
        committed = EXAMPLES / fresh.name
        assert committed.exists(), f"{fresh.name} is rendered but not committed. {REGENERATE}"
        if committed.read_bytes() != fresh.read_bytes():
            pytest.fail(f"examples/{fresh.name} is stale. {REGENERATE}\n{_describe_mismatch(committed, fresh)}")


def test_served_sample_matches_the_pdf_example():
    """The sample the web app serves is a copy of the committed PDF example.

    `webapp/index.html` offers "View a sample report", so this file is the first thing a
    visitor opens. `docs/web-compare.md` documents it as a copy of `examples/*_pdf_diff.html`;
    this pins that, so the sample cannot lag the example it is copied from.
    """
    served = hashlib.sha256(SERVED_SAMPLE.read_bytes()).hexdigest()
    example = hashlib.sha256(PDF_EXAMPLE.read_bytes()).hexdigest()
    assert served == example, (
        f"{SERVED_SAMPLE.relative_to(ROOT)} does not match {PDF_EXAMPLE.relative_to(ROOT)} "
        f"({served[:12]} vs {example[:12]}). {REGENERATE} Then copy it over the sample:\n"
        f"  cp {PDF_EXAMPLE.relative_to(ROOT)} {SERVED_SAMPLE.relative_to(ROOT)}"
    )
