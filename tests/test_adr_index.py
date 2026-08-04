"""The ADR index in AGENTS.md is generated from docs/decisions/, and cannot drift (#481).

Seventeen accepted decision records sit in ``docs/decisions/``. Nothing loads that
directory, so before #481 a decision was reachable only if a code comment happened to
name it and the reader happened to follow the pointer. That matters more since #478 told
contributors to escalate a long rationale out of a comment and into an ADR: escalation
assumes the destination is reachable, and if it is not, the convention converts a
rationale that was verbose but present into one that is absent.

AGENTS.md is loaded every session, so the index lives there. It works because the titles
are already claims rather than topic labels ("11. Process user-provided bill content only
on the user's machine") -- a reader who sees only the title has received the decision,
which is most of what a discoverability mechanism has to deliver.

An index maintained by hand is the shape that goes stale by default. That is not a
hypothesis here: the ``Records`` table in ``docs/decisions/README.md`` had already drifted
from the file it names, describing 0004 as "Fetch discovery and text..." where the record
itself says "Fetch BILL discovery and text...". One word, invisible to review, and the
same drift in a title that states a decision would misreport what was decided. The
enumerated CI module list in CONTRIBUTING went stale three times for the same reason, and
#483 relabelled that history.

So both indexes are derived here rather than trusted, and the ADR headings they derive
from are held to a shape:

- ``test_adr_headings_are_well_formed`` -- every record's H1 is ``# N. Claim`` with no
  leading whitespace. 0009 carried a leading space before its ``#``, which drops it out
  of naive title extraction, and 0008 was the noun phrase "Deterministic Diff Engine",
  which names a topic instead of stating what was decided. Both were fixed in #481; this
  keeps the next record from reintroducing either.
- ``test_agents_md_adr_index_matches_the_records`` and
  ``test_decisions_readme_table_matches_the_records`` -- the rendered lists must equal
  what the files say, so adding, renaming or renumbering a record fails until both
  indexes are updated.

A guard that has never been shown to fire cannot distinguish "nothing drifted" from "the
check is broken", so the comparison is done against a rendering function that is directly
callable, and the failure message prints the expected block for pasting.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
DECISIONS_README = DECISIONS_DIR / "README.md"

# `# 12. Recover PDF heading levels...` -> ("12", "Recover PDF heading levels...").
# Anchored at the start of the line with no leading whitespace on purpose: that is the
# 0009 defect, and a tolerant pattern would silently accept it again.
_HEADING_RE = re.compile(r"^# (\d+)\. (.+)$")

# The generated block in AGENTS.md, delimited by its own heading and the next one.
_AGENTS_SECTION = "## Architecture decisions"


def adr_files() -> list[Path]:
    """Every accepted record, in number order. README.md and TEMPLATE.md are not records."""
    return sorted(DECISIONS_DIR.glob("0*.md"))


def adr_records() -> list[tuple[str, str, str]]:
    """``(number, title, filename)`` per record, read from each file's H1."""
    records = []
    for path in adr_files():
        first_heading = next(
            (line for line in path.read_text().splitlines() if line.lstrip().startswith("#")),
            "",
        )
        match = _HEADING_RE.match(first_heading)
        assert match, f"{path.name}: first heading is not `# N. Claim`: {first_heading!r}"
        records.append((match.group(1), match.group(2), path.name))
    return records


def render_agents_index() -> str:
    """The AGENTS.md index block, as it must appear."""
    return "\n".join(f"- [{number}. {title}](docs/decisions/{name})" for number, title, name in adr_records())


def render_readme_table() -> str:
    """The ``Records`` table rows in docs/decisions/README.md, as they must appear."""
    return "\n".join(f"| [{name[:4]}]({name}) | {title} |" for _number, title, name in adr_records())


def _agents_index_block() -> str:
    """The bullet list under the Architecture decisions heading, verbatim."""
    body = AGENTS_MD.read_text().split(_AGENTS_SECTION, 1)
    assert len(body) == 2, f"AGENTS.md has no `{_AGENTS_SECTION}` section"
    lines = [line for line in body[1].splitlines() if line.startswith("- [")]
    return "\n".join(lines)


def _readme_table_block() -> str:
    """The `| [NNNN](file.md) | Title |` rows of the Records table, verbatim."""
    rows = [line for line in DECISIONS_README.read_text().splitlines() if re.match(r"^\| \[\d{4}\]\(", line)]
    return "\n".join(rows)


def test_adr_headings_are_well_formed() -> None:
    """Every record's H1 is `# N. Claim`, unindented, so title extraction cannot miss it."""
    malformed = []
    for path in adr_files():
        first_heading = next(
            (line for line in path.read_text().splitlines() if line.lstrip().startswith("#")),
            "",
        )
        if not _HEADING_RE.match(first_heading):
            malformed.append(f"{path.name}: {first_heading!r}")
    assert not malformed, (
        "Record headings must be `# N. Claim` with no leading whitespace, and the claim "
        f"must state the decision rather than name a topic. Malformed: {malformed}"
    )


def test_adr_numbers_match_their_filenames() -> None:
    """A record's heading number matches its zero-padded filename prefix."""
    mismatched = [
        f"{name} declares itself {number}" for number, _title, name in adr_records() if int(name[:4]) != int(number)
    ]
    assert not mismatched, f"Heading number disagrees with filename: {mismatched}"


def test_agents_md_adr_index_matches_the_records() -> None:
    """AGENTS.md lists every record, with the title the record itself carries."""
    expected = render_agents_index()
    assert _agents_index_block() == expected, (
        "The ADR index in AGENTS.md has drifted from docs/decisions/. It is generated, "
        "not hand-maintained: replace the bullet list under "
        f"'{_AGENTS_SECTION}' with exactly this:\n\n{expected}\n"
    )


def test_decisions_readme_table_matches_the_records() -> None:
    """The Records table in docs/decisions/README.md says what the records say."""
    expected = render_readme_table()
    assert _readme_table_block() == expected, (
        "The Records table in docs/decisions/README.md has drifted from the records it "
        f"names. Replace its rows with exactly this:\n\n{expected}\n"
    )
