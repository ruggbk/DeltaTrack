"""The product may not import the tooling or the delivery channel (#367).

`tools/` is a second import root on pytest's `pythonpath`, not a package, so
`import fetch_bills` resolves from anywhere in the suite. That is what let the fetch
cluster move without touching a single test import -- and it is also why the boundary
this issue draws has no natural enforcement: a product module could import the fetch
tooling tomorrow and every gate would stay green. The surfaces would re-fuse silently,
which is the failure the reorganization exists to prevent.

So assert it directly. The forbidden roster is derived from what is actually in
`tools/` and `web/` rather than listed here: a hardcoded list guards a shrinking subset
as those trees grow, and reads green the whole time.

Direction matters. Tooling importing the product is fine and expected -- `web/app.py`
calls `compare/`, `scripts/` reach into the engine. Only the reverse is a defect,
because it is what would make the engine un-installable without a web server or a
bill downloader.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Trees whose modules the product must not import.
NON_PRODUCT_TREES = ("tools", "web")


def _product_packages() -> list[Path]:
    """Every package on the product side, by subtraction rather than by roster.

    A listed roster is the failure this file argues against for the forbidden names, and
    it applies just as much here: `("parsers", "formatters", "compare")` describes the
    engine as it is today, and a package added tomorrow -- which is exactly what #398
    does when it finally gives the engine a directory -- would be silently unscanned
    while the gate stayed green.

    Subtracting instead makes the two failure directions asymmetric in the safe way. A
    forgotten NON_PRODUCT_TREES entry over-scans, which surfaces as a loud failure
    someone then resolves deliberately; a forgotten roster entry under-scans, which is
    invisible.

    Keys on `__init__.py` rather than "holds a .py somewhere": `bills_corpus/` and
    `bills_bulk_text/` are symlinks into a corpus of thousands of files, and a recursive
    search would walk all of it on every run to learn nothing.
    """
    return sorted(
        entry
        for entry in ROOT.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in NON_PRODUCT_TREES
        and (entry / "__init__.py").is_file()
    )


def _product_files() -> list[Path]:
    """Every source file on the product side of the boundary."""
    files = sorted(p for p in ROOT.glob("*.py"))
    for package in _product_packages():
        files.extend(sorted(package.rglob("*.py")))
    return files


def _forbidden_names() -> set[str]:
    """Top-level module names the product may not import, derived from the trees.

    `tools/` contributes each of its modules and packages by bare name, because that is
    how they resolve -- there is no `tools.` prefix to look for. `web/` contributes its
    own package name, since it *is* a package and is imported as `web.app`.
    """
    names = {"web"}
    for entry in (ROOT / "tools").iterdir():
        if entry.name.startswith((".", "_")):
            continue
        if entry.suffix == ".py":
            names.add(entry.stem)
        elif entry.is_dir():
            names.add(entry.name)
    return names


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by one file, including function-local imports.

    Walks the whole AST rather than reading only module-level imports: both engine
    reach-arounds this issue removed (`diff_bill.py` and `diff_pdf.py` into the old
    `server/`) were deliberately deferred imports inside a function, which a
    top-level-only scan would not have seen.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_product_modules_do_not_import_tooling_or_the_web_channel():
    """The boundary itself. A violation here means the surfaces have re-fused."""
    forbidden = _forbidden_names()

    violations = [
        f"{path.relative_to(ROOT).as_posix()} imports {sorted(bad)}"
        for path in _product_files()
        if (bad := _imported_roots(path) & forbidden)
    ]

    assert not violations, (
        "product code imports a non-product surface:\n"
        + "\n".join(violations)
        + f"\n\n{list(NON_PRODUCT_TREES)} are consumers of the engine, not part of it. "
        "Move the shared code into the product tree instead of importing across the boundary."
    )


def test_the_boundary_scan_actually_looked_at_something():
    """Completeness floor for both halves of the check above.

    Each half is discovery, and discovery that finds nothing passes green over an
    entirely re-fused repo: an empty forbidden roster intersects nothing, and an empty
    file list has nothing to intersect it with. Names the load-bearing members rather
    than pinning counts, so a new module joins without editing this.
    """
    scanned = {p.relative_to(ROOT).as_posix() for p in _product_files()}
    for expected in ("diff_bill.py", "diff_pdf.py", "bill_tree.py", "compare/pdf.py", "formatters/diff_html.py"):
        assert expected in scanned, f"product scan missed {expected!r} -- discovery is broken, not the code"

    packages = {p.name for p in _product_packages()}
    assert {"parsers", "formatters", "compare"} <= packages, (
        f"package derivation missed one of the engine's own packages: found {sorted(packages)}"
    )
    assert not packages & set(NON_PRODUCT_TREES), (
        f"package derivation swept in a non-product tree: {sorted(packages & set(NON_PRODUCT_TREES))}"
    )

    forbidden = _forbidden_names()
    for expected in ("fetch_bills", "bill_index", "shared", "web"):
        assert expected in forbidden, f"forbidden roster missed {expected!r} -- derivation is broken, not the code"


#: Trees that consume the engine rather than being part of it. Only used by the guard
#: below, which needs to tell "not product" from "product the scan cannot see".
CONSUMER_TREES = frozenset(NON_PRODUCT_TREES) | {"tests", "scripts"}


def test_a_namespace_package_cannot_hide_from_the_product_scan():
    """The narrower under-scan that keying on `__init__.py` leaves behind.

    A product directory added WITHOUT an `__init__.py` still imports fine as a namespace
    package, and would be invisible to `_product_packages` for the same reason the old
    hardcoded roster was -- the gate would read green over a real violation inside it.

    Keying on `__init__.py` is still the right call (see `_product_packages`: the corpus
    symlinks make a recursive search ruinous), so the gap is closed from the other side,
    with a roster of CONSUMERS. That roster fails in the loud direction: a new directory
    that is neither a discovered package nor a listed consumer stops the suite and gets
    classified deliberately, instead of being silently assumed to be neither.
    """
    discovered = {p.name for p in _product_packages()}

    unaccounted = sorted(
        entry.name
        for entry in ROOT.iterdir()
        if entry.is_dir()
        and not entry.is_symlink()  # bills_corpus/ and bills_bulk_text/ point at the corpus
        and not entry.name.startswith((".", "_"))
        and entry.name not in CONSUMER_TREES
        and entry.name not in discovered
        and any(entry.glob("*.py"))
    )

    assert not unaccounted, (
        f"top-level directories hold Python but are neither a discovered product package "
        f"nor a listed consumer tree: {unaccounted}. If one is part of the engine, give it "
        "an __init__.py so the boundary scan covers it; if it consumes the engine, add it "
        "to CONSUMER_TREES. Leaving it unclassified means the boundary is not checked there."
    )


def test_a_new_product_package_is_scanned_without_being_listed(tmp_path, monkeypatch):
    """The gap the roster left: a package the engine grows later.

    With `PRODUCT_PACKAGES` hardcoded, adding `engine/` and importing the fetch tooling
    from it passed this whole file green -- the violation was real and simply outside
    what discovery looked at. That is the shape #398 will produce, so pin it against a
    fake root rather than waiting for the real one.
    """
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "__init__.py").write_text("")
    (tmp_path / "engine" / "core.py").write_text("import fetch_bills\n")
    # A non-package directory alongside it must stay out, or the boundary would be
    # asserted over docs and fixtures too.
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "scratch.py").write_text("import fetch_bills\n")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert [p.name for p in _product_packages()] == ["engine"]
    scanned = {p.relative_to(tmp_path).as_posix() for p in _product_files()}
    assert "engine/core.py" in scanned
    assert "notes/scratch.py" not in scanned


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import fetch_bills", {"fetch_bills"}),
        ("from web.app import app", {"web"}),
        ("def f():\n    from shared.http import api_get\n", {"shared"}),
        ("from . import sibling", set()),
    ],
    ids=["plain-import", "from-import", "function-local", "relative-import-ignored"],
)
def test_import_extraction_sees_the_forms_that_matter(source, expected, tmp_path):
    """`_imported_roots` is the only step with no completeness floor above.

    It is exercised solely through real source files where no violation exists, so a
    version that returned nothing at all -- or that skipped function-local imports, the
    exact shape both removed reach-arounds used -- would pass the whole suite while the
    gate checked nothing. Pinned on literals so that cannot happen quietly.
    """
    path = tmp_path / "sample.py"
    path.write_text(source)

    assert _imported_roots(path) == expected
