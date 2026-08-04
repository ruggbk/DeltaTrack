"""Manifest-driven committee report fixture tests (issue #295).

These tests exercise the committee report reader against ALL manifested report fixtures,
not just the Senate validation jurisdictions. This ensures the parser handles House
report formatting (which renders account tables as images) and detects any
Senate/118th-specific assumptions.

House reports are not expected to yield usable amount data (tables are images), but
they must parse without error and produce a valid document structure. This is a
parser generalization gate, not an amount-validation gate.

Every exception here is read from the manifest, never hardcoded in this file. A skip
list in test code is invisible to the vendoring script and to a reader of the data, and
it silently excuses whatever gets added to it -- which is how two govinfo error pages
came to sit in tests/data/ under fixture names while the gate stayed green (#295
review). ``text_available = false`` is the single declaration, and it is checked in
BOTH directions below: an unavailable report must have no fixture, an available one
must have a real one.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from deltatrack.parsers.committee_report import (
    extract_pre_text,
    parse_comparative_statement,
    parse_summary_blocks,
)
from scripts.report_pairing import fixture_stem
from tests.corpus_paths import DATA_DIR


def _fixture_path(src: dict) -> Path:
    """The committed fixture for a report source.

    Named after the granule when there is one: a multi-book report is one package
    holding a granule per book, so naming by package alone points both books at a
    single file.
    """
    return DATA_DIR / f"{fixture_stem(src['pkg'], src.get('granule'))}.htm"


def load_manifest() -> dict:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        return tomllib.load(f)


def _report_sources_by_version(manifest: dict) -> dict[tuple[str, str], list[dict]]:
    """Real report sources per (bill_id, stage). The "no report" sentinel is dropped."""
    result = {}
    for bill_entry in manifest.get("bill", []):
        bill_id = bill_entry["id"]
        for ver in bill_entry.get("versions", []):
            sources = [s for s in ver.get("committee_report", []) or [] if s.get("citation") != "none"]
            if sources:
                result[(bill_id, ver["stage"])] = sources
    return result


_MANIFEST = load_manifest()
_REPORT_PKGS = _report_sources_by_version(_MANIFEST)

# One entry per distinct report, keyed by citation rather than pkg: a report with no
# published text has no pkg, and keying on pkg would silently collapse every such
# report into a single unnamed case (or drop them all).
_ALL_REPORT_SOURCES: list[dict] = []
_seen_citations: set[str] = set()
for (_bill_id, _stage), _sources in _REPORT_PKGS.items():
    for _src in _sources:
        if _src["citation"] in _seen_citations:
            continue
        _seen_citations.add(_src["citation"])
        _ALL_REPORT_SOURCES.append({**_src, "bill_id": _bill_id, "stage": _stage})


def _case_id(src: dict) -> str:
    if src.get("pkg"):
        return fixture_stem(src["pkg"], src.get("granule"))
    return src["citation"].replace(" ", "")


def _declares_conference_report(raw: str) -> bool:
    """Whether the report's masthead names it a conference report.

    Matched as a whole line, not a substring: the masthead carries ``CONFERENCE
    REPORT`` on its own line where an ordinary report carries ``R E P O R T``.
    Substring matching reads the phrase out of body prose instead -- H. Rept.
    118-154 quotes "ACCOMPANYING CONFERENCE REPORTS AND JOINT EXPLANATORY
    STATEMENTS" in its boilerplate and is not a conference report.
    """
    return any(" ".join(line.split()).upper() == "CONFERENCE REPORT" for line in raw[:6000].splitlines())


# Reports govinfo publishes text for -- the ones with a fixture to parse.
_AVAILABLE = [s for s in _ALL_REPORT_SOURCES if s.get("text_available", True)]
_UNAVAILABLE = [s for s in _ALL_REPORT_SOURCES if not s.get("text_available", True)]


@pytest.mark.slow
@pytest.mark.parametrize("src", _AVAILABLE, ids=_case_id)
def test_committee_report_fixture_parses(src: dict):
    """Every manifested committee report HTML fixture must parse without error.

    The primary generalization gate for issue #295: the committee report reader
    must handle both Senate and House formatting. House reports render account
    tables as images, so they produce 0 summary blocks, but they must still parse
    into a valid document structure.

    Amount validation for House reports is NOT asserted here -- that is tracked
    separately under #5 / #289 (House extraction has no external check).
    """
    pkg = _case_id(src)
    html_path = _fixture_path(src)

    # Completeness floor: every manifested report fixture must be committed
    assert html_path.exists(), (
        f"Committee report fixture {pkg}.htm is referenced in corpus_manifest.toml "
        f"but not committed to tests/data/. Download with scripts/vendor_reports.py."
    )

    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    pre_text = extract_pre_text(html_content)

    # Basic sanity checks on extracted text
    assert len(pre_text) > 1000, f"{pkg}: extracted text too short ({len(pre_text)} chars)"
    assert "APPROPRIATIONS" in pre_text.upper(), f"{pkg}: doesn't appear to be an appropriations report"

    summary_blocks = parse_summary_blocks(pre_text)
    comparative_rows = parse_comparative_statement(pre_text)

    if src["chamber"] == "senate":
        # Senate reports carry text tables, so the reader must find something.
        total_parsed = len(summary_blocks) + len(comparative_rows)
        assert total_parsed > 0, (
            f"{pkg} (Senate): expected at least some parsed accounts, "
            f"got {len(summary_blocks)} summary blocks + {len(comparative_rows)} comparative rows"
        )
    # House: image-based tables, so 0 blocks is expected. The assertion is that the
    # two parses above completed without raising.


@pytest.mark.slow
@pytest.mark.parametrize("src", _AVAILABLE, ids=_case_id)
def test_available_report_is_a_real_rendition(src: dict):
    """A committed fixture must be report text, not a govinfo error page.

    govinfo answers an unknown package with a 302 to an error page served as HTTP
    200, so a fixture can be present, well-formed HTML, the right size, and still
    contain no report at all. Presence is not the property worth asserting; being
    the requested document is. Guards the same failure the vendoring script now
    rejects at download time.
    """
    pkg = _case_id(src)
    raw = _fixture_path(src).read_text(encoding="utf-8", errors="replace")

    assert "<pre>" in raw.lower(), f"{pkg}: no <pre> block -- this is not a govinfo text rendition"
    head = raw[:4000]
    assert "House Report" in head or "Senate Report" in head, (
        f"{pkg}: title is not a House/Senate report; got {head[:200]!r}"
    )


@pytest.mark.slow
def test_unavailable_reports_have_no_fixture():
    """A report declared text-unavailable must have no fixture and no package ID.

    The other direction of the floor, and the one that actually failed: without it,
    "unavailable" only suppresses checks, so an error page saved under the expected
    name satisfies every remaining assertion. This fails if someone re-downloads a
    placeholder, and equally if the report becomes available and the flag is not
    flipped -- so the exception cannot quietly outlive its reason.

    A loop rather than a parametrize because the corpus currently has no unavailable
    report: an empty parameter set makes pytest SKIP, and a new skip is exactly what
    the CI skip ceiling fails on. The rule itself is gated directly, without needing
    a gap in the corpus to exercise it, by test_report_pairing.py's resolve_pkgs
    cases.
    """
    for src in _UNAVAILABLE:
        _assert_unavailable_source_is_clean(src)


def _assert_unavailable_source_is_clean(src: dict) -> None:
    assert src.get("unavailable_reason"), f"{src['citation']}: text_available = false needs a reason"
    assert not src.get("pkg"), (
        f"{src['citation']}: declared text-unavailable but carries pkg={src['pkg']!r}. "
        f"A package ID that resolves to nothing reads as a vendorable fixture."
    )

    # No file may sit under any name this report would have had -- the undivided
    # package, or the granule its book number implies.
    from scripts.report_pairing import book_number, granule_id, parse_citation, predicted_pkg

    parsed = parse_citation(src["citation"])
    assert parsed, f"unparseable citation {src['citation']!r}"
    chamber, congress, number, book = parsed
    pkg = predicted_pkg(chamber, congress, number)
    candidates = [pkg]
    book_n = book_number(book)
    if book_n is not None:
        candidates.append(granule_id(pkg, book_n))

    for stem in candidates:
        stray = DATA_DIR / f"{stem}.htm"
        assert not stray.exists(), (
            f"{src['citation']} is declared text-unavailable, but {stray.name} exists. "
            f"Either it is a govinfo error page (delete it), or the report was published "
            f"(drop text_available and record its pkg/granule)."
        )


@pytest.mark.slow
def test_all_manifested_reports_are_committed():
    """Completeness floor: every available committee_report pkg must have a fixture."""
    missing = [f"{_case_id(s)} (for {s['bill_id']} {s['stage']})" for s in _AVAILABLE if not _fixture_path(s).exists()]
    assert not missing, (
        f"{len(missing)} committee report fixture(s) referenced in corpus_manifest.toml "
        f"are not committed to tests/data/:\n" + "\n".join(f"  {m}" for m in missing)
    )


@pytest.mark.slow
def test_the_gate_collected_the_expected_fixture_set():
    """The parametrized gates above must actually have cases.

    A parametrize over an empty list passes with zero assertions, so a manifest
    read that silently returned nothing would look exactly like a clean run. Floors
    rather than exact counts, so adding a fixture does not force a test edit.
    """
    assert len(_AVAILABLE) >= 20, f"expected >=20 vendorable reports, collected {len(_AVAILABLE)}"
    assert {s["chamber"] for s in _AVAILABLE} == {"house", "senate"}, (
        "the generalization gate needs both chambers represented"
    )
    # Every report in the corpus currently resolves to a real rendition, so
    # _UNAVAILABLE is empty and its gate above parametrizes over nothing. That is a
    # fact about today's corpus, not a property to assert -- requiring an unavailable
    # report would mean requiring a gap. The fail-closed machinery stays wired for
    # when one appears, and tests/test_report_pairing.py covers the rule directly.
    assert not _UNAVAILABLE or all(s.get("unavailable_reason") for s in _UNAVAILABLE), (
        "a text-unavailable report must carry the reason it is unavailable"
    )


@pytest.mark.slow
@pytest.mark.parametrize("src", [s for s in _AVAILABLE if s.get("conference")], ids=_case_id)
def test_conference_flag_is_backed_by_the_report_text(src: dict):
    """A report flagged ``conference`` must say so in its own text.

    ``mark_conference_reports`` infers the flag from report numbering, which is a
    heuristic. This is what keeps the heuristic honest: the vendored report states
    "CONFERENCE REPORT" in its header, so a wrong flag goes red here instead of
    silently attaching a conference report to pre-conference text.
    """
    raw = _fixture_path(src).read_text(encoding="utf-8", errors="replace")
    assert _declares_conference_report(raw), (
        f"{src['pkg']} is flagged conference = true, but its text does not say "
        f"CONFERENCE REPORT. The numbering heuristic in mark_conference_reports() "
        f"mis-fired for this bill."
    )


@pytest.mark.slow
@pytest.mark.parametrize("src", [s for s in _AVAILABLE if not s.get("conference")], ids=_case_id)
def test_unflagged_report_is_not_a_conference_report(src: dict):
    """The other direction: an unflagged report must not be a conference report.

    Without this, the heuristic could flag nothing at all and the test above would
    pass vacuously over an empty parameter list.
    """
    raw = _fixture_path(src).read_text(encoding="utf-8", errors="replace")
    assert not _declares_conference_report(raw), (
        f"{src['pkg']} reads as a CONFERENCE REPORT but is not flagged conference = true, "
        f"so it will be paired with pre-conference text it postdates."
    )


@pytest.mark.slow
def test_conference_report_pairs_only_with_enrolled_text():
    """A conference report explains the final agreed text, nothing earlier.

    The regression this locks: 115-hr-5895's conference report (H. Rept. 115-929)
    was paired with every House stage including ``1_reported-in-house``, which it
    postdates by months. Asserting only that the enrolled version has both reports
    could not catch that -- it was true either way -- so the load-bearing assertion
    is the negative one.
    """
    conference_citations = {s["citation"] for s in _ALL_REPORT_SOURCES if s.get("conference")}
    assert conference_citations, "no conference report in the corpus; this gate would be vacuous"

    for (bill_id, stage), sources in sorted(_REPORT_PKGS.items()):
        paired = {s["citation"] for s in sources} & conference_citations
        if "enrolled" in stage.lower():
            continue
        assert not paired, (
            f"{bill_id} {stage} is paired with conference report(s) {sorted(paired)}, "
            f"which explain the final agreed text and postdate this stage."
        )


@pytest.mark.slow
def test_senate_authored_versions_are_not_paired_with_house_reports():
    """A version's report must be the one explaining THAT text.

    The regression this locks: pairing keyed off the bill type, so every stage of an
    H.R. -- including the Senate's substitute in ``engrossed-amendment-senate`` --
    took the House report. 114-hr-2029's Senate amendment now takes S. Rept. 114-57.
    """
    from scripts.report_pairing import authoring_chamber, is_enrolled_stage

    for (bill_id, stage), sources in sorted(_REPORT_PKGS.items()):
        if is_enrolled_stage(stage):
            continue  # enrolled text is the product of both chambers
        bill_type = bill_id.split("-")[1]
        expected = authoring_chamber(stage, bill_type)
        wrong = {s["citation"] for s in sources if s["chamber"] != expected}
        assert not wrong, (
            f"{bill_id} {stage} is authored by the {expected}, but is paired with "
            f"{sorted(wrong)} from the other chamber."
        )


@pytest.mark.slow
def test_119_hr_1_books_are_distinct_source_artifacts():
    """Regression test for 119-hr-1's two-book report (issue #295).

    H. Rept. 119-106 is one package holding a granule per book, each with its own
    text rendition. The defect this locks out: both books derived the same package
    ID, so they were two citations naming one artifact -- the vendoring step
    deduplicated them to a single download and "multi-book support" was nominal.

    Two citations is therefore not the property worth asserting. Distinctness is,
    all the way down to file content: separate granule IDs, separate committed
    fixtures, and different bytes in each.
    """
    sources = _REPORT_PKGS[("119-hr-1", "1_reported-in-house")]

    books = {s.get("book") for s in sources}
    assert books == {"Book 1", "Book 2"}, f"expected both books, got {sorted(str(b) for b in books)}"

    # One parent package, two granules.
    assert {s["pkg"] for s in sources} == {"CRPT-119hrpt106"}, "both books belong to one parent package"
    granules = {s.get("book"): s.get("granule") for s in sources}
    assert granules == {"Book 1": "CRPT-119hrpt106-pt1", "Book 2": "CRPT-119hrpt106-pt2"}, (
        f"books must map to distinct granules, got {granules}"
    )

    # Two files, and genuinely different ones.
    paths = {s.get("book"): _fixture_path(s) for s in sources}
    assert len({p.name for p in paths.values()}) == 2, f"books share a fixture filename: {paths}"
    for book, path in paths.items():
        assert path.exists(), f"{book}: missing fixture {path.name}"

    contents = {book: path.read_bytes() for book, path in paths.items()}
    assert contents["Book 1"] != contents["Book 2"], (
        "the two books' fixtures are byte-identical, so they are one artifact copied twice"
    )


@pytest.mark.slow
def test_introduced_versions_carry_no_committee_report():
    """A committee report is filed at the reported stage and cannot explain earlier text.

    The regression this locks: pairing matched on authoring chamber alone, so
    118-hr-2882's introduced version took H. Rept. 118-364 -- a report that
    recommends changing that text, written after it. Asserted across the whole
    manifest rather than for the one bill, since the rule is general.
    """
    from scripts.report_pairing import PRE_COMMITTEE, stage_class

    offenders = {
        f"{bill_id} {stage}": sorted(s["citation"] for s in sources)
        for (bill_id, stage), sources in _REPORT_PKGS.items()
        if stage_class(stage) == PRE_COMMITTEE
    }
    assert not offenders, "these pre-committee versions are paired with a report filed after them:\n" + "\n".join(
        f"  {k}: {v}" for k, v in sorted(offenders.items())
    )


@pytest.mark.slow
def test_115_hr_5895_enrolled_has_conference_report():
    """The enrolled version pairs with both the House report and the conference report."""
    sources = _REPORT_PKGS[("115-hr-5895", "5_enrolled-bill")]
    citations = {s["citation"] for s in sources}

    assert "H. Rept. 115-697" in citations, "Missing House report H. Rept. 115-697"
    assert "H. Rept. 115-929" in citations, "Missing conference report H. Rept. 115-929"

    for s in sources:
        assert _fixture_path(s).exists(), f"Missing fixture for {_case_id(s)}"


@pytest.mark.slow
def test_114_hr_2029_enrolled_has_both_chambers():
    """Regression test for 114-hr-2029 enrolled having both House and Senate reports."""
    sources = _REPORT_PKGS[("114-hr-2029", "7_enrolled-bill")]
    chambers = {s["chamber"] for s in sources}

    assert "house" in chambers, "Missing House report"
    assert "senate" in chambers, "Missing Senate report"
