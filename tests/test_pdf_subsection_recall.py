"""Precision/recall parity gate for run-in subsection anchors (DeltaTrack#96).

A regex-INDEPENDENT oracle: a raw-XML extractor over ``<section>/<subsection enum>``,
written fresh here because ``bill_tree`` collapses subsections into the section's text
and exposes no per-subsection node/enum. From it:

- **Precision** (``test_precision_no_false_subsections``): every PDF-detected
  ``(section, enum)`` must be a real, NON-quoted XML subsection. Precision-first —
  measured 0 false positives on the appropriations fixtures, 2 on the messy 119-hr-1
  (documented residue below).
- **Recall** (``test_recall_floor``): the denominator is the true catchline-bearing
  subsection set — a subsection with a non-empty ``<header>`` OR whose ``<text>`` opens
  with the run-in pattern — built WITH the same roman-reject the PDF uses, and with
  quoted-block subsections EXCLUDED (they self-exclude on the PDF side too). Recall =
  PDF-detected / that denominator, over catchline-bearing subsections only.
- **Quoted-block leak** (``test_no_quoted_block_leak``): the PDF must detect ZERO
  subsections that live inside a ``<quoted-block>`` amendment (they render with GPO's
  ``‘‘`` and self-exclude). Measured 0 on 119-hr-1 (numbered, quote-heavy: 177 quoted
  subsections). The `<header>` element is inconsistently applied across bills, so it is
  NOT a usable denominator on its own — hence the header-OR-inline union above.

Floors sit UNDER the measured values (regression floors, not targets; per
feedback_validate_against_hard_fixture the clean fixtures are exact and the messy one
carries documented residue):

    fixture      precision  recall   (measured 2026-07-09)
    118-hr-8752    1.000     1.000
    117-hr-4502    1.000     1.000
    119-hr-1       0.998     0.995

Documented residue (on 119-hr-1, NOT chased — each needs the leveled tree / a wider
window, both out of #96 scope):
- Precision: doubled two-letter enumerators ``(aa)``/``(bb)`` that are a DEEPER-level
  (paragraph/clause) run-in, mis-emitted at subsection level (2 of 931). The two-letter
  doubled-enum rule can't tell a 27th subsection from a deep-list continuation without
  the leveled tree (#54/#108). The precision test pins that every false positive is such
  a two-letter enum — a single-letter FP would be a NEW class and fails loud.
- Recall: a subsection whose catchline wraps beyond the 2-line window (a very long
  ``<header>``; 5 of 934). Bounded look-ahead is the deliberate precision-first tradeoff.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import pytest

from parsers.pdf_anchors import (
    _match_runin_subsection,
    _valid_subsection_enum,
    breadcrumb_for,
    extract_anchors,
)
from tests.conftest import assert_manifest_committed
from tests.pdf_corpus import cached_pages

pytestmark = pytest.mark.slow

ROOT = Path(__file__).parent.parent
BILLS = ROOT / "bills"

# (bill, pdf rel path, xml rel path) under bills/.
FIXTURES = [
    ("118-hr-8752", "118-hr-8752/1_reported-in-house.pdf", "118-hr-8752/1_reported-in-house.xml"),
    ("117-hr-4502", "117-hr-4502/1_reported-in-house.pdf", "117-hr-4502/1_reported-in-house.xml"),
    ("119-hr-1", "119-hr-1/1_reported-in-house.pdf", "119-hr-1/1_reported-in-house.xml"),
]

PRECISION_FLOOR = 0.99
RECALL_FLOOR = 0.98
# Denominator sanity so a broken extractor can't make the ratios vacuously pass (#167).
MIN_CATCHLINES = 3


def _norm_sec(text: str | None) -> str | None:
    m = re.search(r"(\d+[A-Za-z]?)", text or "")
    return m.group(1) if m else None


def _norm_enum(text: str | None) -> str | None:
    m = re.match(r"\(([A-Za-z]{1,2})\)", (text or "").strip())
    return m.group(1) if m else None


@lru_cache(maxsize=None)
def _xml_index(xml_path: str) -> tuple[frozenset, frozenset, frozenset]:
    """``(all_pairs, catchline_pairs, quoted_pairs)`` of ``(section, enum)`` for one XML.

    ``all_pairs`` — every non-quoted ``<section>/<subsection>`` pair (the precision
    oracle). ``catchline_pairs`` — the subset that bears a run-in catchline: a non-empty
    ``<header>`` OR a ``<text>`` opening that matches the run-in pattern, roman-reject
    applied (the recall denominator). ``quoted_pairs`` — subsections inside a
    ``<quoted-block>`` amendment, which the PDF must NOT detect (the leak oracle).
    """
    root = ET.parse(BILLS / xml_path).getroot()
    quoted_elems = {e for qb in root.iter("quoted-block") for e in qb.iter()}
    all_pairs: set[tuple[str, str]] = set()
    catchline_pairs: set[tuple[str, str]] = set()
    quoted_pairs: set[tuple[str, str]] = set()
    for sec in root.iter("section"):
        secn = _norm_sec(sec.findtext("enum"))
        if secn is None:
            continue
        for sub in sec.findall("subsection"):
            enum = _norm_enum(sub.findtext("enum"))
            if enum is None:
                continue
            if sec in quoted_elems:
                quoted_pairs.add((secn, enum))
                continue
            all_pairs.add((secn, enum))
            if not _valid_subsection_enum(enum.lower()):
                continue
            header = (sub.findtext("header") or "").strip()
            text_el = sub.find("text")
            text = "".join(text_el.itertext()).strip() if text_el is not None else ""
            if header or _match_runin_subsection(f"({enum}) {text}", []) is not None:
                catchline_pairs.add((secn, enum))
    return frozenset(all_pairs), frozenset(catchline_pairs), frozenset(quoted_pairs)


@lru_cache(maxsize=None)
def _pdf_pairs(pdf_path: str) -> frozenset:
    """Every PDF-detected ``(section, enum)`` subsection pair, section resolved from the
    anchor's breadcrumb (the nearest enclosing ``SEC.``)."""
    anchors = extract_anchors(cached_pages(BILLS / pdf_path))
    pairs: set[tuple[str | None, str | None]] = set()
    for a in anchors:
        if a.kind != "subsection":
            continue
        secn = None
        for seg in breadcrumb_for(a, anchors):
            m = re.match(r"SEC(?:TION)?\.?\s+(\d+[A-Za-z]?)", seg)
            if m:
                secn = m.group(1)
        pairs.add((secn, _norm_enum(a.text)))
    return frozenset(pairs)


def test_manifest_fixtures_committed():
    """Fail-closed floor (#220, ADR 0015): always collects and runs with no env var, so
    an uncommitted fixture fails here instead of emptying the parametrization."""
    assert_manifest_committed(FIXTURES, "pdf-subsection-parity")


@pytest.mark.parametrize(("bill", "pdf_rel", "xml_rel"), FIXTURES, ids=[f[0] for f in FIXTURES])
def test_precision_no_false_subsections(bill, pdf_rel, xml_rel):
    all_pairs, _catch, _quoted = _xml_index(xml_rel)
    pp = _pdf_pairs(pdf_rel)
    assert len(pp) > 0, f"{bill}: zero subsections detected (fail-open)"
    fp = pp - all_pairs
    precision = len(pp & all_pairs) / len(pp)
    assert precision >= PRECISION_FLOOR, f"{bill} precision {precision:.3f}, FPs {sorted(fp)}"
    # Residue characterization: any false positive must be a doubled two-letter enum
    # (a deeper-level (aa)/(bb) run-in). A single-letter FP is a NEW class — fail loud.
    assert all(enum is not None and len(enum) == 2 for _sec, enum in fp), (
        f"{bill}: unexpected non-doubled-enum false positive: {sorted(fp)}"
    )


@pytest.mark.parametrize(("bill", "pdf_rel", "xml_rel"), FIXTURES, ids=[f[0] for f in FIXTURES])
def test_recall_floor(bill, pdf_rel, xml_rel):
    _all, catchlines, _quoted = _xml_index(xml_rel)
    assert len(catchlines) >= MIN_CATCHLINES, f"{bill}: catchline denominator {len(catchlines)} too small (fail-open)"
    pp = _pdf_pairs(pdf_rel)
    hit = pp & catchlines
    recall = len(hit) / len(catchlines)
    missed = sorted(catchlines - pp)
    assert recall >= RECALL_FLOOR, f"{bill} recall {recall:.3f}, missed {missed[:10]}"


@pytest.mark.parametrize(("bill", "pdf_rel", "xml_rel"), FIXTURES, ids=[f[0] for f in FIXTURES])
def test_no_quoted_block_leak(bill, pdf_rel, xml_rel):
    # The PDF must detect ZERO subsections living inside a <quoted-block> amendment.
    # 119-hr-1 is the meaningful case (177 quoted subsections); the appropriations
    # fixtures have few or none, so guard the completeness with the count.
    _all, _catch, quoted = _xml_index(xml_rel)
    pp = _pdf_pairs(pdf_rel)
    leak = pp & quoted
    assert not leak, f"{bill}: quoted-block subsections leaked as anchors: {sorted(leak)}"
    if bill == "119-hr-1":
        assert len(quoted) > 50, f"quoted oracle shrank to {len(quoted)} — leak gate went vacuous"
