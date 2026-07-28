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
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The product surface: the engine's own modules. Root `.py` files plus the packages
#: they are built from. `tests/`, `scripts/`, `tools/`, and `web/` are all consumers of
#: this code, not part of it.
PRODUCT_PACKAGES = ("parsers", "formatters", "compare")

#: Trees whose modules the product must not import.
NON_PRODUCT_TREES = ("tools", "web")


def _product_files() -> list[Path]:
    """Every source file on the product side of the boundary."""
    files = sorted(p for p in ROOT.glob("*.py"))
    for package in PRODUCT_PACKAGES:
        files.extend(sorted((ROOT / package).rglob("*.py")))
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

    forbidden = _forbidden_names()
    for expected in ("fetch_bills", "bill_index", "shared", "web"):
        assert expected in forbidden, f"forbidden roster missed {expected!r} -- derivation is broken, not the code"


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
