"""Property-based tests that run against the full bill XML corpus.

These are diagnostic tests, not TDD-driven. They check invariants that should
hold across all bill versions and surface issues mechanically. Failures here
indicate parser gaps, not test bugs.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from deltatrack.bill_tree import (
    _extract_appropriations_text,
    extract_text_content,
    find_bill_body,
    normalize_bill,
)
from tests.conftest import assert_manifest_committed, manifest_xml_files

pytestmark = pytest.mark.slow

# The gate parametrizes over the COMMITTED corpus manifest (tests/corpus_manifest.toml),
# not a `bills/*` glob, so the collected set is identical on every machine and in CI
# (fail closed if a fixture is uncommitted) rather than whatever a machine fetched
# (fail open on an empty glob). CORPUS_SWEEP=1 swaps in the broad local glob for
# opt-in, non-CI exploration. See docs/decisions/0015-corpus-test-fixtures.md.
ALL_XML_FILES = manifest_xml_files()
DOLLAR_RE = re.compile(r"\$[\d,]+")

# Tags whose subtrees should be excluded from raw text collection.
# <quote> contains cited text, not appropriations content.
# <header> text is stored in header_text, not body_text.
_SKIP_TAGS = {"quote", "header"}

# Amounts that reach no node, each traced to a filed defect rather than absorbed into a
# tolerance. Keyed by fixture id, then by the amount's SOURCE spelling.
#
# The point of naming them individually is that the gate stays exact for everything else:
# a new hole cannot hide behind slack left for an old one, which is what a ratio allows.
# test_every_dollar_amount_appears_in_a_node also fails if an entry here stops being
# missing, so a fix removes its entry rather than leaving dead tolerance behind.
KNOWN_UNCOVERED_AMOUNTS: dict[str, dict[str, str]] = {
    # Division U (the LIBOR Act folded into the FY2022 omnibus) is one of 13 divisions in
    # this bill whose sections are not wrapped in a <title>, so the division walk reaches
    # none of them. This is the only amount in the corpus that the defect hides, because
    # the divisions it drops are policy text rather than appropriations.
    "117-hr-2471/6_enrolled-bill.xml": {
        "$200,000,000,000,000": "#465 division without a <title> child is dropped from the tree",
    },
}


def _collect_body_text_excluding(body: ET.Element, skip_tags: set[str]) -> str:
    """Walk the element tree, collecting text but skipping subtrees with tags in skip_tags."""
    parts: list[str] = []

    def _walk(el: ET.Element) -> None:
        if el.tag in skip_tags:
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            _walk(child)
            if child.tail:
                parts.append(child.tail)

    _walk(body)
    return " ".join(parts)


def _extract_dollar_matches(text: str) -> list[tuple[int, str]]:
    """Find all non-zero dollar amounts as ``(value, literal)`` pairs.

    The literal is the source spelling. Callers that ask "did this amount reach a
    node" must search for the literal rather than for a re-formatted ``f"${value:,}"``,
    because the round trip through ``int`` is lossy on malformed source: 118-s-4797
    carries ``$60,00,000``, which reformats to ``$6,000,000`` and is then findable in
    no node, though the section holding it is present and intact. Comparing literals
    removes that class of false positive; measured across the committed corpus it
    drops the reported misses from 2 to 1 and introduces none.
    """
    matches = []
    for m in DOLLAR_RE.finditer(text):
        value = int(m.group().replace("$", "").replace(",", ""))
        if value > 0:
            matches.append((value, m.group()))
    return matches


def _extract_dollar_amounts(text: str) -> list[int]:
    """Find all non-zero dollar amounts in text."""
    return [value for value, _literal in _extract_dollar_matches(text)]


def _xml_id(xml_path: Path) -> str:
    """Create a readable test ID from a bill XML path."""
    return f"{xml_path.parent.name}/{xml_path.name}"


def _skip_if_absent(xml_path: Path) -> None:
    """Skip (not error) a manifest case whose fixture is absent from a partial local
    checkout, keeping collected = passed + skipped constant. The completeness floor
    (test_manifest_fixtures_committed) turns any such absence red in CI."""
    if not xml_path.exists():
        pytest.skip(f"manifest fixture not present locally: {_xml_id(xml_path)}")


def test_manifest_fixtures_committed() -> None:
    """Fail-closed completeness floor for the corpus property gates (#217, ADR 0015).

    These gates parametrize over the committed manifest (ALL_XML_FILES). This guard —
    which always runs, no env var — fails (not skips) if any manifested fixture is
    absent from the checkout, so a fresh CI checkout missing a committed bill goes red
    instead of silently collecting fewer cases. Under CORPUS_SWEEP it still validates
    that the committed manifest subset is present (the local glob is a superset).
    """
    assert_manifest_committed(ALL_XML_FILES, "corpus-properties")


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_every_dollar_amount_appears_in_a_node(xml_path: Path) -> None:
    """Every dollar amount in the raw XML body appears in at least one node's body_text.

    Excludes amounts inside <quote> and <header> elements (stored separately).

    The cap is absolute, not a ratio, because a ratio cannot express this property on
    documents of this size. A percentage tolerance scales with the bill: at the 0.98 it
    replaces, 117-hr-2471 could lose 67 of its 3,385 amounts and stay green, and the
    slack was widest on the largest bills, which is where the money is. It also cannot
    see loss that is large in sections but small in dollars -- 13 divisions of that bill
    reach no node at all (#465) and it still scored 0.9997, because the missing divisions
    are policy text carrying one dollar amount between them.

    Anything genuinely uncovered belongs in ``KNOWN_UNCOVERED_AMOUNTS`` against a filed
    defect, not inside a tolerance that also silently absorbs the next regression.
    """
    _skip_if_absent(xml_path)
    test_id = _xml_id(xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    # Collect dollar amounts from raw XML, excluding quote/header subtrees
    raw_text = _collect_body_text_excluding(body, _SKIP_TAGS)
    raw_matches = _extract_dollar_matches(raw_text)

    if not raw_matches:
        pytest.skip("No dollar amounts in bill body")

    if len(raw_matches) < 3:
        # Shell bills (procedural placeholders later replaced with full text)
        # have 1-2 amounts. Missing 1 of 1 gives 0% coverage, which is noise.
        pytest.skip(f"Shell bill: only {len(raw_matches)} amounts, too few for meaningful coverage")

    # Parse with the actual parser
    bill_tree = normalize_bill(xml_path)
    all_body_text = " ".join(node.body_text for node in bill_tree.nodes)

    # Search for the source spelling, not a re-formatted f"${value:,}" -- see
    # _extract_dollar_matches for why the round trip invents misses on malformed source.
    missing = sorted({literal for _value, literal in raw_matches if literal not in all_body_text})
    allowed = KNOWN_UNCOVERED_AMOUNTS.get(test_id, {})

    unexpected = [literal for literal in missing if literal not in allowed]
    assert not unexpected, (
        f"{test_id}: {len(unexpected)} of {len(raw_matches)} amounts appear in no node: {unexpected[:5]}. "
        f"If this is a known defect, file it and add it to KNOWN_UNCOVERED_AMOUNTS with the issue."
    )

    # The allowlist is self-cleaning: an entry that stops being missing is a fixed defect,
    # and leaving it behind would let the gate keep tolerating a hole that has closed.
    # Without this, the allowlist decays into exactly the open-ended tolerance the ratio
    # was, one entry at a time.
    stale = [literal for literal in allowed if literal not in missing]
    assert not stale, (
        f"{test_id}: {stale} now reach a node, so their KNOWN_UNCOVERED_AMOUNTS entries "
        f"are obsolete. Remove them (and close the issue they name if nothing else blocks it)."
    )


def test_no_section_sibling_is_dropped_from_every_node() -> None:
    """A section with appropriations children keeps its other children too (#459).

    The ratio gate above is a whole-bill coverage floor, so a handful of dropped amounts
    hides inside its tolerance no matter how the tolerance is set. This one is exact and
    scoped to the shape that produced the loss: when a section carries ``appropriations-*``
    children (the elements holding an account and its amount), its other children -- a
    <list>, a <continuation-text>, a <quoted-block> -- must still reach some node.

    They used to reach none, because that branch built the section's node from the opening
    <text> alone. The money vanished from both renderings, which is why no comparison
    between two views could detect it, and why the loss had to be measured against the
    source XML instead.

    Swept across the whole corpus in ONE case rather than parametrized per fixture, and
    that is deliberate. Most fixtures contain no section of this shape, so a per-fixture
    gate would content-skip roughly 35 of 41 cases, and every one of those skips would
    have to be declared in ALLOWED_CORPUS_SKIPS (#220) to say nothing at all. A single
    sweep carries its own fail-closed floor instead: it asserts that the corpus actually
    presented instances to check, so "nothing dropped" can never mean "nothing looked at".
    """
    checked = 0
    dropped = []
    for xml_path in ALL_XML_FILES:
        if not xml_path.exists():
            continue
        root = ET.parse(xml_path).getroot()
        try:
            find_bill_body(root)
        except ValueError:
            continue

        sections = [s for s in root.iter("section") if any(c.tag.startswith("appropriations-") for c in s)]
        if not sections:
            continue

        tree = normalize_bill(xml_path)
        all_text = " ".join(f"{n.body_text} {n.display_text}" for n in tree.nodes)

        for section in sections:
            for child in section:
                if child.tag in ("enum", "header", "text") or child.tag.startswith("appropriations-"):
                    continue
                amounts = _extract_dollar_amounts(extract_text_content(child))
                if not amounts:
                    continue
                checked += 1
                missing = [a for a in amounts if f"${a:,}" not in all_text]
                if missing:
                    enum = section.find("enum")
                    label = (enum.text or "").strip() if enum is not None else "?"
                    dropped.append(f"{_xml_id(xml_path)} sec.{label} <{child.tag}> {[f'${a:,}' for a in missing[:3]]}")

    # The floor. 19 money-bearing siblings exist across the committed fixtures, 8 of which
    # were dropped before #459. Requiring most of them keeps the gate honest if a fixture
    # is retired, while still going red if the corpus stops exercising this shape at all.
    assert checked >= 15, (
        f"only {checked} money-bearing siblings found corpus-wide; this gate is not exercising anything"
    )
    assert dropped == [], f"{len(dropped)} of {checked} money-bearing siblings appear in no node: {dropped[:3]}"


# Files known to have duplicate match_paths (cross-division collisions, issue #1).
# Values are the current duplicate counts. Files not listed must have zero duplicates.
_KNOWN_DUPLICATE_COUNTS: dict[str, int] = {
    # #188 note: subsection nodes inherit their section's match_path as a prefix, so
    # a cross-division duplicated section duplicates its subsection paths one level
    # deeper. Every #188 count increase was verified to be exactly that class (new
    # duplicate keys are all subsection nodes under already-colliding sections) —
    # the same collision-group matching (#1) covers them.
    "113-hr-3547/5_engrossed-amendment-house.xml": 168,
    # Enrolled has 12 divisions whose later titles spill out as orphan <title>
    # siblings. Walking them (#146) surfaces genuine cross-division collisions
    # (general provisions, same-named bureaus across divisions) on division-stripped
    # match_paths — now matching the engrossed-amendment version's 150 (was 73 when
    # the orphan titles were silently dropped). Real source structure, not a bug.
    "113-hr-3547/6_enrolled-bill.xml": 168,
    "113-hr-83/6_engrossed-amendment-house.xml": 128,
    "113-hr-83/7_enrolled-bill.xml": 128,
    "114-hr-2029/6_engrossed-amendment-house.xml": 176,
    "114-hr-2029/7_enrolled-bill.xml": 176,
    "115-hr-1625/6_enrolled-bill.xml": 177,
    "115-hr-244/6_enrolled-bill.xml": 159,
    "115-hr-5895/2_engrossed-in-house.xml": 20,
    "115-hr-5895/3_placed-on-calendar-senate.xml": 20,
    "115-hr-5895/4_engrossed-amendment-senate.xml": 6,
    # Enrolled version places Division C's TITLE II-V at <legis-body> level beside the
    # divisions (not nested). Walking them (#146) surfaces genuine cross-division
    # collisions: the orphaned "TITLE V—General provisions" (sec. 501-505) shares a
    # division-stripped match_path with Division A's "TITLE V—General provisions".
    # Real source structure, not a parser error (cf. 119-hr-1's twin Sec. 10012).
    "115-hr-5895/5_enrolled-bill.xml": 8,
    "116-hr-1865/5_engrossed-amendment-house.xml": 55,
    "116-hr-1865/6_enrolled-bill.xml": 55,
    "118-hr-2882/5_engrossed-amendment-house.xml": 55,
    "118-hr-2882/6_enrolled-bill.xml": 55,
    "118-hr-4366/4_engrossed-amendment-senate.xml": 7,
    "118-hr-4366/5_engrossed-amendment-house.xml": 33,
    "118-hr-4366/6_enrolled-bill.xml": 33,
    # Fresh bills added for overfitting smoke test (2026-04-15)
    "117-hr-4432/1_reported-in-house.xml": 1,
    "117-hr-4502/1_reported-in-house.xml": 1,
    "117-hr-4502/2_engrossed-in-house.xml": 39,
    "117-hr-4502/3_received-in-senate.xml": 39,
    "118-hr-4820/1_reported-in-house.xml": 7,
    # Fresh bills added for Part C smoke test (2026-04-15)
    "116-hr-133/6_engrossed-amendment-house.xml": 160,
    "116-hr-133/7_enrolled-bill.xml": 160,
    "117-hr-2471/6_enrolled-bill.xml": 151,
    # Committee-report external-validation bills (#8/#44). All duplicates are benign
    # cross-section heading collisions (a heading repeated across the appropriation, a
    # limitation/administrative-provisions section, and general provisions), not parser
    # errors. These Senate prints are committed (tests/corpus/118-s-*) and named in
    # the corpus manifest, so the gate runs them in CI; these counts are its baselines.
    "118-s-4795/1_reported-in-senate.xml": 2,  # CJS: DOJ general-provisions + NASA pair
    "118-s-4796/1_reported-in-senate.xml": 7,  # Transportation-HUD: FAA/FHWA/NHTSA/HUD repeats
    "118-s-4797/1_reported-in-senate.xml": 1,  # State-Foreign Ops: callable-capital limitation
    "118-s-4802/1_reported-in-senate.xml": 3,  # Interior-Environment: Forest Service repeats
    "118-s-4928/1_reported-in-senate.xml": 5,  # Financial Services: Treasury/OPM salaries, DC funds
    "118-s-4942/1_reported-in-senate.xml": 2,  # Labor-HHS: VETS employment-and-training lines
    "118-s-4927/1_reported-in-senate.xml": 4,  # Energy-Water: Corps of Engineers heading repeats
    "118-s-2321/1_reported-in-senate.xml": 1,  # CJS FY2024 (out-of-corpus guard): NASA pair
    # 119-hr-1 (reconciliation): two genuinely-distinct Sec. 10012 in the reported version
    # (Alien SNAP eligibility + Emergency food assistance), one renumbered to 10013 later.
    # Real source duplicate, not a parser error; exposes the matcher's reliance on body
    # similarity over header (tracked in DeltaTrack#8). Committed + in the manifest, so CI runs it.
    "119-hr-1/1_reported-in-house.xml": 1,
}


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_no_duplicate_match_paths(xml_path: Path) -> None:
    """Each node's match_path should be unique within a bill.

    Duplicates indicate cross-division path collisions (issue #1).
    Files with known duplicates assert the count hasn't increased.
    Files with no known duplicates assert zero.
    """
    _skip_if_absent(xml_path)
    test_id = _xml_id(xml_path)
    bill_tree = normalize_bill(xml_path)

    if not bill_tree.nodes:
        pytest.skip("No nodes parsed")

    counts = Counter(node.match_path for node in bill_tree.nodes)
    dupes = {k: v for k, v in counts.items() if v > 1}
    total_dupes = sum(v - 1 for v in dupes.values())

    known = _KNOWN_DUPLICATE_COUNTS.get(test_id, 0)

    if known == 0:
        assert total_dupes == 0, (
            f"{test_id}: unexpected {total_dupes} duplicate match_paths. Sample: {list(dupes.items())[:3]}"
        )
    else:
        assert total_dupes <= known, (
            f"{test_id}: duplicate count increased from {known} to {total_dupes}. Sample: {list(dupes.items())[:3]}"
        )


_APPRO_TAGS = {"appropriations-major", "appropriations-intermediate", "appropriations-small"}

# Files with known missing appropriations elements (parser doesn't reach them).
# Typically caused by elements nested inside divisions/titles the parser skips.
_KNOWN_MISSING_APPRO: dict[str, int] = {
    "113-hr-3547/6_enrolled-bill.xml": 310,
    # 115-hr-5895 enrolled previously missed 33 appropriations elements — exactly the
    # top-level titles normalize_bill dropped (#146). Now fully walked; baseline is 0
    # (entry removed) so any future regression trips the assertion.
    # Fresh bills added for Part C smoke test (2026-04-15)
    "116-hr-133/6_engrossed-amendment-house.xml": 1,
    "116-hr-133/7_enrolled-bill.xml": 1,
}


def _normalize_ws(text: str) -> str:
    """Collapse whitespace for comparison."""
    return " ".join(text.split())


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_every_appropriations_element_with_text_produces_node(xml_path: Path) -> None:
    """Every appropriations-* element with text content should map to a parsed node.

    Extracts text using the same function the parser uses, then checks that
    the normalized text appears in at least one node's body_text.
    """
    _skip_if_absent(xml_path)
    test_id = _xml_id(xml_path)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    # Find all appropriations elements with text content
    appro_elements = []
    for el in body.iter():
        if el.tag in _APPRO_TAGS:
            text = _extract_appropriations_text(el)
            if text.strip():
                appro_elements.append((el, text))

    if not appro_elements:
        pytest.skip("No appropriations elements with text")

    # Parse and collect all node body texts (normalized)
    bill_tree = normalize_bill(xml_path)
    node_texts = [_normalize_ws(node.body_text) for node in bill_tree.nodes]

    # Check each appropriations element's text appears in some node
    missing = []
    for el, text in appro_elements:
        normalized = _normalize_ws(text)
        if not any(normalized in nt for nt in node_texts):
            preview = normalized[:80]
            missing.append((el.tag, el.attrib.get("id", "?"), preview))

    total = len(appro_elements)
    total - len(missing)

    known_missing = _KNOWN_MISSING_APPRO.get(test_id, 0)

    if known_missing == 0:
        assert len(missing) == 0, (
            f"{test_id}: {len(missing)}/{total} appropriations elements not found in nodes. Sample: {missing[:3]}"
        )
    else:
        assert len(missing) <= known_missing, (
            f"{test_id}: missing count increased from {known_missing} to {len(missing)}. Sample: {missing[:3]}"
        )


# Tags excluded from character coverage: parser stores these in separate fields,
# not in body_text.
_CHAR_SKIP_TAGS = {"quote", "header", "enum"}


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_character_coverage_ratio(xml_path: Path) -> None:
    """Parser should capture a high ratio of the bill body's text content.

    Compares total characters in the body (excluding quote/header/enum subtrees)
    against total characters across all node body_text fields.
    """
    _skip_if_absent(xml_path)
    test_id = _xml_id(xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    raw_text = _collect_body_text_excluding(body, _CHAR_SKIP_TAGS)
    raw_chars = len(raw_text.strip())

    if raw_chars == 0:
        pytest.skip("No text content in bill body")

    bill_tree = normalize_bill(xml_path)
    node_chars = sum(len(node.body_text) for node in bill_tree.nodes)

    ratio = node_chars / raw_chars if raw_chars > 0 else 0.0

    # Low floor catches only catastrophic failures. Actual ratios range from
    # ~0.12 (amendment docs) to ~1.0+ (full bills). Shell bills and early
    # versions with little appropriations text have legitimately low ratios.
    assert ratio >= 0.10, f"{test_id}: character coverage ratio {ratio:.3f} ({node_chars}/{raw_chars} chars)"
