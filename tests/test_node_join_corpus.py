"""Corpus behavioral gates for the own-span containment join (#172).

Behavioral, not geometric: these assert "change X files under node Y" as
observable in the view/rendered output on stable corpus pairs — deliberately
NOT a corpus-wide span-geometry property test (the extent investigation on
#172 concluded that would only pin incidental overlap counts) and NOT
full-page snapshots (#170 will later change which pairs the cards show).

XML ground truth: the change's structural ``path`` (display_path) and the tree
derive from the same serializer, so the joined breadcrumb must match the
structural path exactly — except the leading short-title/definitions sections,
which the tree groups under the synthesized Front Matter node (#161) where the
flat path says just "Sec. 1"; there the join is deeper, and pinning it proves
deepest-wins live (a naive bisect files these under "Front Matter" itself).

PDF ground truth: the anchor breadcrumb (``path``), resolved structurally from
the same anchor stream that builds the tree.

``bills/`` is gitignored (fetched via ``fetch_bills.py``), so every case skips
cleanly on a clean clone; ``test_corpus_present_when_required`` fails loud in
REQUIRE_CORPUS mode instead (#167).
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

import pytest

from diff_pdf import diff_pdfs
from formatters.canonical import view_from_canonical
from formatters.diff_html import format_diff_html
from server.pdf_compare import _build_canonical
from server.xml_compare import compare_xml
from tests.conftest import require_corpus_or_skip
from tests.pdf_corpus import cached_pages

pytestmark = pytest.mark.slow

BILLS = Path(__file__).parent.parent / "bills"

# (bill, v1 stem, v2 stem) — stable fixtures named on #172/#175.
XML_PAIRS = [
    ("113-hr-3547", "5_engrossed-amendment-house", "6_enrolled-bill"),
    ("113-hr-3547", "4_engrossed-amendment-senate", "5_engrossed-amendment-house"),
    ("114-hr-2029", "5_engrossed-amendment-senate", "6_engrossed-amendment-house"),
]


def _xml_paths(bill: str, v1: str, v2: str) -> tuple[Path, Path]:
    return BILLS / bill / f"{v1}.xml", BILLS / bill / f"{v2}.xml"


def _available(pairs, suffix: str) -> list:
    out = []
    for bill, v1, v2 in pairs:
        a, b = BILLS / bill / f"{v1}{suffix}", BILLS / bill / f"{v2}{suffix}"
        if a.exists() and b.exists():
            out.append((bill, v1, v2))
    return out


@lru_cache(maxsize=None)
def _xml_view(bill: str, v1: str, v2: str):
    a, b = _xml_paths(bill, v1, v2)
    canonical = compare_xml(a.read_bytes(), b.read_bytes())
    return canonical, view_from_canonical(canonical)


@lru_cache(maxsize=None)
def _pdf_view(bill: str, v1: str, v2: str):
    a = BILLS / bill / f"{v1}.pdf"
    b = BILLS / bill / f"{v2}.pdf"
    diff = diff_pdfs(cached_pages(a), cached_pages(b))
    canonical = _build_canonical(diff, cached_pages(a), cached_pages(b), "v1", "v2", congress="")
    return canonical, view_from_canonical(canonical)


def test_corpus_present_when_required():
    require_corpus_or_skip(_available(XML_PAIRS, ".xml"), "node-join")


# ---------- XML: join agrees with the structural path ---------------------------


@pytest.mark.parametrize(("bill", "v1", "v2"), _available(XML_PAIRS, ".xml"))
def test_xml_join_matches_structural_path(bill, v1, v2):
    canonical, view = _xml_view(bill, v1, v2)
    checked = mismatched = 0
    examples = []
    for change, cv in zip(canonical["changes"], view.changes):
        if cv.change_type == "removed" or not cv.node_path:
            continue
        path = (change.get("path") or {}).get("v2") or []
        if not path:
            continue
        checked += 1
        joined = [label.casefold() for label, _level in cv.node_path]
        if joined == [seg.casefold() for seg in path]:
            continue
        # The one sanctioned divergence: leading sections the tree groups
        # under Front Matter (#161) — the join lands DEEPER than the flat
        # path, under the Front Matter child named for the section.
        if cv.node_path[0][0] == "Front Matter" and len(cv.node_path) > 1:
            continue
        mismatched += 1
        if len(examples) < 3:
            examples.append((path, [label for label, _ in cv.node_path]))
    assert checked > 0, "gate ran on zero placeable changes (fail-open, #167)"
    assert mismatched == 0, f"join disagrees with structural path: {examples}"


@pytest.mark.parametrize(("bill", "v1", "v2"), _available([XML_PAIRS[1]], ".xml"))
def test_xml_front_matter_changes_file_under_children_not_the_hull(bill, v1, v2):
    # 113-hr-3547 4->5 changes its leading sections. Their positions sit inside
    # BOTH the Front Matter hull span and its children's own spans, and the
    # hull shares its exact start offset with the first child — the two
    # position classes a naive sorted-starts bisect misfiles (to the hull /
    # the preceding leaf). Deepest-wins must land them on the children.
    _, view = _xml_view(bill, v1, v2)
    fm_leaves = {
        cv.node_path[-1][0]
        for cv in view.changes
        if cv.node_path and cv.node_path[0][0] == "Front Matter" and len(cv.node_path) > 1
    }
    assert {"Short title", "Table of contents"} <= fm_leaves, fm_leaves


@pytest.mark.parametrize(("bill", "v1", "v2"), _available([XML_PAIRS[2]], ".xml"))
def test_xml_removed_changes_place_into_v2_groups(bill, v1, v2):
    # 114-hr-2029 5->6 removes whole sections. Every removal with a v1 span
    # must file somewhere (v2 remap or v1-derived group), never drop to
    # Uncategorized silently.
    canonical, view = _xml_view(bill, v1, v2)
    removed = [
        cv
        for change, cv in zip(canonical["changes"], view.changes)
        if cv.change_type == "removed" and (change.get("full_text_span") or {}).get("v1")
    ]
    assert len(removed) > 0, "gate ran on zero removals (fail-open, #167)"
    unplaced = [cv.nav_label_html for cv in removed if not cv.node_path]
    assert not unplaced, f"{len(unplaced)} removals unplaced: {unplaced[:3]}"


@pytest.mark.parametrize(("bill", "v1", "v2"), _available([XML_PAIRS[0]], ".xml"))
def test_xml_rendered_report_neither_drops_nor_duplicates_cards(bill, v1, v2):
    canonical, view = _xml_view(bill, v1, v2)
    html = format_diff_html(view, canonical=canonical)
    assert len(view.changes) > 0
    for i in range(len(view.changes)):
        assert html.count(f'id="change-{i}"') == 1, f"change-{i} dropped or duplicated"


# ---------- PDF ------------------------------------------------------------------

PDF_AGREEMENT_PAIR = [("114-hr-2029", "3_referred-in-senate", "4_reported-to-senate")]
PDF_SECTION_ONLY_PAIR = [("113-hr-3547", "3_received-in-senate", "4_engrossed-amendment-senate")]
PDF_NULL_SPAN_PAIR = [("113-hr-3547", "1_introduced-in-house", "2_engrossed-in-house")]


@pytest.mark.parametrize(("bill", "v1", "v2"), _available(PDF_AGREEMENT_PAIR, ".pdf"))
def test_pdf_join_consistent_with_anchor_breadcrumb(bill, v1, v2):
    # Change spans and anchor blocks derive from the same line-offset table,
    # so every placed change's joined ancestry must contain its structural
    # anchor breadcrumb — all-agree, not a pinned count.
    canonical, view = _pdf_view(bill, v1, v2)
    checked = disagreed = 0
    for change, cv in zip(canonical["changes"], view.changes):
        if cv.change_type == "removed" or not cv.node_path:
            continue
        path = (change.get("path") or {}).get("v2") or []
        if not path:
            continue
        checked += 1
        joined = {label.casefold() for label, _level in cv.node_path}
        if not all(seg.casefold() in joined for seg in path):
            disagreed += 1
    assert checked > 0, "gate ran on zero placeable changes (fail-open, #167)"
    assert disagreed == 0


@pytest.mark.parametrize(("bill", "v1", "v2"), _available(PDF_SECTION_ONLY_PAIR, ".pdf"))
def test_pdf_without_account_level_lands_at_section_level(bill, v1, v2):
    # ADR 0012: early/simple PDFs surface no agency/account anchors. The join
    # landing at SECTION level is the correct degraded outcome, not a failure.
    canonical, view = _pdf_view(bill, v1, v2)
    tree_levels = set()

    def walk(nodes):
        for n in nodes:
            tree_levels.add(n["level"])
            walk(n.get("children") or [])

    walk(canonical["tree"]["v2"])
    assert "account" not in tree_levels and "agency" not in tree_levels, (
        f"fixture no longer account-absent ({sorted(tree_levels)}); pick another pair"
    )
    # All change types: on this pair the only placeable changes are removals
    # (v1 tree, same section-only shape); the level property is type-agnostic.
    placed = [cv for cv in view.changes if cv.node_path]
    assert len(placed) > 0, "gate ran on zero placed changes (fail-open, #167)"
    assert {cv.node_path[-1][1] for cv in placed} == {"section"}


@pytest.mark.parametrize(("bill", "v1", "v2"), _available(PDF_NULL_SPAN_PAIR, ".pdf"))
def test_pdf_null_span_changes_degrade_to_group_label(bill, v1, v2):
    # Small early versions resolve no usable v2 offsets for their changes:
    # node_path stays empty and the card keeps its group_label — degrade,
    # never a crash or a misfile.
    canonical, view = _pdf_view(bill, v1, v2)
    assert len(view.changes) > 0
    checked = 0
    for change, cv in zip(canonical["changes"], view.changes):
        span = (change.get("full_text_span") or {}).get("v2")
        if span is None and cv.change_type != "removed":
            checked += 1
            assert cv.node_path == ()
    # Completeness floor (#167): if this fixture ever starts resolving spans,
    # the loop above asserts nothing — fail loud so the fixture gets replaced.
    assert checked > 0, "fixture no longer has null-span changes; pick another pair"


# ---------- perf smoke ------------------------------------------------------------

OMNIBUS_PAIR = [("114-hr-2029", "5_engrossed-amendment-senate", "6_engrossed-amendment-house")]


@pytest.mark.parametrize(("bill", "v1", "v2"), _available(OMNIBUS_PAIR, ".xml"))
def test_join_at_omnibus_scale_stays_fast(bill, v1, v2):
    # ~2.2k changes x ~2.4k tree nodes. The index is built once per side and
    # each lookup is O(log N); an accidental O(changes x nodes) regression
    # blows straight through this generous ceiling.
    canonical, _ = _xml_view(bill, v1, v2)
    start = time.perf_counter()
    view = view_from_canonical(canonical)
    elapsed = time.perf_counter() - start
    assert len(view.changes) > 1000
    assert elapsed < 20, f"view_from_canonical took {elapsed:.1f}s at omnibus scale"
