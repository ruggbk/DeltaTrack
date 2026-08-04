"""Structure-free cross-check for PROSE: sentences the bill XML carries must be
recoverable from the PDF of the same version.

The amount cross-check (test_pdf_xml_amount_recall.py) uses the XML as an oracle for
the PDF text pipeline, but only for dollar amounts. Text extraction had no external
grounding at all on published bills -- only synthetic sentinels
(test_pdf_injection_recall.py) and one hand-built draft fixture (#7). Yet the product
reports changes in prose as well as in money, so the prose half of the pipeline was
resting on internal consistency alone.

GPO's XML is an independent transcription of the same document, which makes it the
same kind of oracle for prose that it already is for amounts, at no hand-transcription
cost. The question asked here is RECALL -- did the sentence survive extraction? -- not
fidelity: comparison is substring matching after `normalize_for_cross_format`, which
erases the accent, quote, hyphen, and punctuation-spacing conventions the two formats
disagree about. A miss means a run of words present in the official text is absent from
what the tool read, which is either:

  - a PDF extraction failure (a line dropped by page-chrome stripping, a column
    misordered, a wrap that lost a word), or
  - an XML-side artifact -- text GPO's XML renders in a form the PDF never had.

Both are worth seeing. Unlike amounts, prose does not reach 100%: the residue is real
and per-bill, so the gate is a FLOOR on recall plus a floor on the number of sentences
actually compared. The second floor matters as much as the first -- a fragment
extractor that silently yields nothing would otherwise pass this test at 100%.

Floors are calibrated on the whole fixture corpus (scripts/calibrate_prose_recall.py),
set below the measured worst case with deliberate headroom, and are not snapshots of
the current numbers: they lock the claim "essentially all prose survives extraction",
which should stay true, rather than pinning a count that legitimately moves whenever a
fixture or the extractor changes. Investigate a drop; do not re-baseline the floor to
whatever the run produced.

What the residue currently is, as of the calibration run that set these floors: of the
19 measured versions (the other 5 are shells, see `_SHELL_VERSIONS`), 16 recall 100% of
their prose, 119-hr-1 recalls 99.5% and 118-hr-8752 v2 recalls 99.8%, and the enrolled
115-hr-5895 recalls 94.1%. What holds the last three short of 100% is extraction
defects this cross-check found, not a comparison that is too strict:

  - The enrolled-bill layout carries no margin line numbers, so `extract_clean_pages`
    treats a line-initial integer as one and drops it: "not more than 25 percent"
    reads as "not more than percent". The same layout's running header ("H. R.
    5895-4") is not recognized as chrome and splices into the middle of sentences.
    Together these are the whole of 115-hr-5895's enrolled-bill residue.
  - On a line carrying a vulgar fraction, the extractor emits the margin line number
    mid-line rather than at the start, where line-number stripping would catch it, so
    a stray integer welds itself into a number: "18 3/4 percent" reads as
    "183 15 /4 percent". That is the whole of 119-hr-1's residue.
  - 118-hr-8752 v2's single miss is a lost space where a line wraps between two
    parentheticals: "$5,000,000) (reduced by" extracts as "$5,000,000)(reduced by".
    Left unnormalized deliberately -- a missing space is text the tool got wrong, and
    folding it away here would be canonicalizing a defect rather than a convention.

None of these is visible to the amount cross-check: the two figures the first two
corrupt are not dollar amounts, and the third leaves its amounts intact.

What this CANNOT see, established by injecting each fault and watching the result:
making `normalize_glyphs` a no-op leaves all 24 cases green, because the comparison
runs the same normalization over both sides, so a change there cancels out. Glyph
handling is gated by the golden prints (test_pdf_extraction_golden.py), not here.
Dropping extracted lines, extracting no fragments at all, a stale `_KNOWN_DEGRADED`
entry, and a `_SHELL_VERSIONS` entry that no longer describes a shell all do fail.

Marked @slow: parses bill XML and extracts every PDF page.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree
from pdf_corpus import cached_pages, dual_format_versions, full_text
from recall_text import normalize_for_cross_format

pytestmark = pytest.mark.slow

#: Minimum share of XML sentences recoverable from the PDF, per version. The healthy
#: population sits at 99.5-100%, so this leaves room for one unlucky sentence without
#: leaving room for a systemic failure. A version that needs a lower floor is not
#: healthy: give it an entry in `_KNOWN_DEGRADED` naming the defect, so the exception
#: is legible instead of being absorbed by a slack global floor.
RECALL_FLOOR = 0.99

#: Versions held below the floor by a known, documented extraction defect (see the
#: module docstring for both). The value is that version's own floor, still asserted:
#: a degraded version should stay where it is until the defect is fixed, and slipping
#: further is its own regression. Delete the entry when the defect is fixed rather than
#: loosening it -- and an entry going slack (the version now recalls far above its
#: floor) means the defect moved, which is worth knowing either way.
_KNOWN_DEGRADED: dict[str, float] = {
    # Line-initial integers dropped and the running header spliced into sentences,
    # both from the enrolled layout having no margin line numbers. Measured 94.1%.
    "115-hr-5895/5_enrolled-bill": 0.90,
}

#: Minimum distinct sentences a version must contribute before its recall is believed.
#: Below this the ratio is too coarse to mean anything: one miss out of two fragments
#: is a 50% recall that says nothing about the extractor.
MIN_FRAGMENTS = 20

#: Versions that genuinely carry less prose than `MIN_FRAGMENTS`, with the fragment
#: count measured at calibration. 113-hr-3547 is a two-section shell bill: a short
#: title and one amendment to title 51, and nothing else.
#:
#: Named rather than skipped, deliberately. A content-skip here would be the exact
#: fail-open the corpus content-skip ceiling in conftest.py exists to close: if a
#: regression dropped every version's fragments to zero, a skipping test would go
#: quiet and green while asserting nothing. So these versions are asserted on from
#: both sides instead -- they must still be small (a shell that grows prose is no
#: longer a shell, and its entry is wrong) and they must recall ALL of what little
#: prose they have, which is a stricter demand than the floor makes of anyone else.
_SHELL_VERSIONS = {
    "113-hr-3547/1_introduced-in-house": 2,
    "113-hr-3547/2_engrossed-in-house": 2,
    "113-hr-3547/3_received-in-senate": 2,
    "113-hr-3547/4_engrossed-amendment-senate": 4,
    "118-hr-2882/1_introduced-in-house": 4,
}

#: Words per sentence fragment. Long enough that a match cannot be coincidental, short
#: enough that most of a bill's prose qualifies.
MIN_WORDS = 8

# Elements whose text is present in the XML but legitimately absent from the PDF body,
# or present in a form no substring test can reach. Each is a structural exclusion, not
# an allow-list of failures -- nothing here is a miss that was waived.
#
#   quoted-block  Amendment inserts. Set as a block quotation with its own line
#                 numbering and indentation; the PDF's rendering of it is a different
#                 document fragment, not the same sentence.
#   toc           The table of contents repeats section headings in a dot-leadered
#                 layout, which extraction reads as a different string entirely.
_SKIPPED_ANCESTORS = frozenset({"quoted-block", "toc"})

_SENTENCE_END = ("...", ".", ";", ":")


def _local(tag: object) -> str:
    """Local name of an element tag, or "" for comments and processing instructions."""
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _split_sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation, keeping the punctuation with its sentence.

    Hand-rolled rather than regex-split so that the split points are exactly the
    characters listed in `_SENTENCE_END`. Bill prose runs to enormous semicolon-joined
    provisos, so semicolons and colons split too -- otherwise a single "sentence" would
    span a whole account paragraph, and one extraction artifact anywhere in it would
    sink the entire fragment.
    """
    out: list[str] = []
    current = ""
    for part in text.split(" "):
        current = f"{current} {part}".strip()
        if part.endswith(_SENTENCE_END):
            out.append(current)
            current = ""
    if current:
        out.append(current)
    return out


def xml_prose_fragments(xml_path: Path) -> list[str]:
    """Distinct normalized sentence fragments from a bill XML's body prose.

    Reads the raw XML rather than `normalize_bill`, for the same reason
    test_pdf_subsection_recall.py writes its own extractor: an oracle that runs through
    our own parser can only confirm the two pipelines agree, not that either matches the
    document. lxml's `itertext` is the whole extraction, so the oracle side stays
    independent of DeltaTrack code.
    """
    tree = etree.parse(str(xml_path))
    seen: set[str] = set()
    fragments: list[str] = []
    for element in tree.iter():
        if _local(element.tag) != "text":
            continue
        if any(_local(a.tag) in _SKIPPED_ANCESTORS for a in element.iterancestors()):
            continue
        for sentence in _split_sentences(" ".join(element.itertext())):
            fragment = normalize_for_cross_format(sentence)
            if len(fragment.split()) >= MIN_WORDS and fragment not in seen:
                seen.add(fragment)
                fragments.append(fragment)
    return fragments


def prose_recall(xml_path: Path, pdf_path: Path) -> tuple[list[str], list[str]]:
    """(fragments, misses) for one version -- the shared body of the test and the
    calibration script, so the number being calibrated is the number being asserted."""
    fragments = xml_prose_fragments(xml_path)
    haystack = normalize_for_cross_format(full_text(cached_pages(pdf_path)))
    return fragments, [f for f in fragments if f not in haystack]


_VERSIONS = dual_format_versions()


@pytest.mark.parametrize(
    "bill,xml_path,pdf_path",
    _VERSIONS,
    ids=[f"{name}/{xml.stem}" for name, xml, _ in _VERSIONS],
)
def test_xml_prose_appears_in_pdf(bill: str, xml_path: Path, pdf_path: Path) -> None:
    fragments, missing = prose_recall(xml_path, pdf_path)
    test_id = f"{bill}/{xml_path.stem}"

    if test_id in _SHELL_VERSIONS:
        assert len(fragments) <= _SHELL_VERSIONS[test_id], (
            f"{test_id} now yields {len(fragments)} prose fragments, more than the "
            f"{_SHELL_VERSIONS[test_id]} that made it a shell version. It should be "
            f"gated like any other version now: remove its _SHELL_VERSIONS entry."
        )
        assert not missing, (
            f"{test_id} is a shell version, so all {len(fragments)} of its prose "
            f"fragments must survive extraction. Missing: {missing}"
        )
        return

    assert len(fragments) >= MIN_FRAGMENTS, (
        f"{test_id} yields only {len(fragments)} prose fragments, too few to measure "
        f"recall against. Either the XML is a shell (add it to _SHELL_VERSIONS with "
        f"its count) or fragment extraction has regressed and is finding nothing."
    )

    floor = _KNOWN_DEGRADED.get(test_id, RECALL_FLOOR)
    recall = (len(fragments) - len(missing)) / len(fragments)
    sample = "\n    ".join(m[:160] for m in missing[:5])
    assert recall >= floor, (
        f"{test_id}: prose recall {recall:.1%} is below the "
        f"{floor:.0%} floor -- {len(missing)} of {len(fragments)} XML sentences "
        f"are absent from the extracted PDF text. This is a PDF extraction failure or "
        f"an XML-side artifact; find out which before touching the floor.\n"
        f"    {sample}"
    )

    # A degraded entry that no longer describes reality is an exemption nothing will
    # ever revisit: the version silently keeps a floor 9 points below every other one,
    # and a real regression into that gap reads as a pass. Fail when the exemption is
    # no longer earned, the same way a strict xfail does.
    assert test_id not in _KNOWN_DEGRADED or recall < RECALL_FLOOR, (
        f"{test_id} recalls {recall:.1%}, at or above the {RECALL_FLOOR:.0%} floor "
        f"every other version is held to. The defect its _KNOWN_DEGRADED entry names "
        f"appears to be fixed -- remove the entry so this version is gated normally."
    )
