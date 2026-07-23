# Contributing to DeltaTrack

Thanks for your interest in contributing! This project compares versions of U.S. appropriations bills to make the legislative process more transparent. Contributions of all kinds are welcome: bug fixes, new features, documentation improvements, and bug reports.

New to the codebase or to congressional bills? Two things are worth reading first:

- **[docs/bill-structure.md](docs/bill-structure.md)** -- the data model the whole project rests on: what a division, account, or section is, and how the XML and PDF paths reconstruct the bill's hierarchy. Read this before touching parsing or diff code.
- **[docs/decisions/](docs/decisions/)** -- short records of the non-obvious choices and why they were made.

## Community

DeltaTrack is built by the Congressional Tech team at [Civic Tech DC](https://luma.com/civic-tech-dc). The work focuses on diffing draft versions of bills for congressional staffers, across two repos: **BillTrax** (online) and **DeltaTrack** (local). The fastest way to get oriented and find people to pair with:

- **Join the Slack** -- the [`#congressional-tech` channel](https://civictechdc.slack.com/archives/C0AT13U25V2) in the Civic Tech DC workspace. Day-to-day questions and coordination happen here.
- **Come to the biweekly meetup** -- in person, via [Civic Tech DC on Luma](https://luma.com/civic-tech-dc). The single best way to get started: come, say hello, and pick up a first issue with someone alongside you.

You don't need either to send a pull request, but both make the on-ramp much shorter.

## Getting started

### Prerequisites

- **Python 3.12+** -- check with `python3 --version`
- **uv** (Python package manager) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git** -- for version control

### Setup

```bash
# Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/DeltaTrack.git
cd DeltaTrack

# Install dependencies (including dev tools)
uv sync

# Install pre-commit hooks (runs linting/formatting automatically on commit)
uv run pre-commit install

# Run the fast test suite to verify everything works
uv run pytest -m "not slow and not browser"
```

### Optional: download bill files for full test suite

The fast tests use inline XML and mocked data. Integration tests need real bill files: XML for the diff tests and PDF for the PDF comparison tests (`test_pdf_*`):

```bash
# No API key needed: fetch_bills.py downloads from keyless govinfo bulk data by
# default. (A key is only needed for --source api or download-all year-range
# discovery — get a free one at https://api.congress.gov/sign-up/, put it in .env
# via `cp .env.example .env`, and fetch_bills.py loads .env automatically.)

# Download the primary test bill (--format both gets XML + PDF; default is XML only)
uv run python fetch_bills.py download 118 hr 4366 --format both

# Run the suite; tests whose bill isn't downloaded yet skip automatically
uv run pytest
```

See the README for the full list of bills used by the test suite.

## Finding work to do

Work is tracked in [GitHub Issues](https://github.com/AgoraDMV/DeltaTrack/issues) and on the [project board](https://github.com/orgs/AgoraDMV/projects/1). An issue moves across the board left to right:

| Column | Meaning |
|--------|---------|
| **Backlog** | Captured, but not yet groomed or ready to start. |
| **Ready** | Groomed and safe to pick up -- **start here**. |
| **In progress** | Someone is actively working it. |
| **In review** | A pull request is open and awaiting review. |
| **Done** | Merged and complete. (Pull requests land on `develop`; `main` is the protected release branch.) |

To pick up work:

1. Choose an issue from **Ready**, or one labeled [`good first issue`](https://github.com/AgoraDMV/DeltaTrack/labels/good%20first%20issue) if you're new.
2. **Claim it** so two people don't start the same thing: comment on the issue to call it. If you have write access, also assign yourself and move the card to **In progress**; otherwise a maintainer will. We're a small team and work mostly async between syncs, so visible ownership matters.

The board handles the later transitions for you: opening a pull request with `Closes #<n>` moves the issue to **In review**, and merging it moves the issue to **Done** and closes it. The only card you move by hand is **In progress**, when you start work.

Not sure whether an issue is a good fit? Ask in a comment or at the regular sync (see [Community](#community)).

## Making changes

### Branch workflow

`develop` is the integration branch; `main` is the protected release branch. Day-to-day
work targets `develop`, not `main`.

1. Create a branch from `develop` for your work
2. Make your changes in small, focused commits
3. Push your branch and open a pull request against `develop`

**Branch from `develop`, not from another feature branch.** Even when one piece
of work logically follows another, don't stack pull requests. GitHub retargets a
stacked pull request at `develop` only when its parent branch is *deleted* on
merge, and this repo has "Automatically delete head branches" turned off
([#88](https://github.com/AgoraDMV/DeltaTrack/issues/88)). Without that
retargeting, "merged" means merged into the parent branch: the child pull request
shows **MERGED** in the UI while its content sits in a now-stale branch and never
reaches `develop`. The badge cannot tell you the difference. If you do stack one,
confirm the content actually landed rather than trusting the badge:

```bash
git fetch origin develop
git cat-file -e origin/develop:path/to/changed/file && echo "reached develop"
```

### Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting. If you installed the pre-commit hooks, this runs automatically on each commit. You can also run it manually:

```bash
uv run ruff check .          # Lint
uv run ruff check --fix .    # Lint and auto-fix
uv run ruff format .         # Format
```

### Adding a CLI command

A command is an **executable `.py` file in the project root**. That is the whole
definition, and it is what the documentation gate keys on, so a new command is
discovered automatically and is required to be documented. To add one:

1. Create `<name>.py` in the project root with a shebang. `#!/usr/bin/env python3` is
   the common form; the two bulk fetchers use `#!/usr/bin/env -S uv run --quiet python`,
   which resolves the environment itself rather than relying on `source ./init`.
2. `chmod +x <name>.py`, and commit the bit (`git update-index --chmod=+x <name>.py`
   if it did not survive). Without it the file reads as a module and is not a command.
3. Expose the argument parser as `build_parser()` returning an `argparse.ArgumentParser`.
   The gate calls it to enumerate subcommands, so each subcommand is documented
   individually rather than the script as a whole.
4. Add a row to the README's **Command reference** table for the script (or one per
   subcommand), spelled exactly as a user types it: `./<name>.py <subcommand>`.
5. Add `<name>` to the completeness floor in `tests/test_docs_consistency.py`
   (`test_the_command_gate_actually_found_commands`). The floor names every command
   rather than counting them, so an unnamed command that later loses its executable
   bit drops out of discovery with the suite still green. The step-2 check catches
   that only for a script carrying a `__main__` block; for one that parses at module
   level, this floor is the only thing standing between it and a silent exit.

`tests/test_docs_consistency.py` names what is missing where it can: skip step 4 and it
fails with the exact row to add, skip step 2 and it fails with `Root scripts look
runnable but are not executable`. Steps 1, 3 and 5 it cannot check for you:

- A shebang is never required on its own. Paired with a `__main__` block on a file
  that lacks the executable bit, it is what raises that step-2 failure.
- A command with no `build_parser` is documented under its bare script name rather
  than rejected (`fetch_bill_archives.py`, [#10](https://github.com/AgoraDMV/DeltaTrack/issues/10)).
- Nothing ties the floor's list back to what discovery found, which is why step 5 is
  a step and not an assertion.

Root `.py` files that are *not* commands (`fetch_govinfo.py`, `bill_tree.py`) simply
carry no executable bit.

Root scripts once shipped a bare-name symlink beside them (`fetch_bills` pointing at
`fetch_bills.py`) so the `.py` could be dropped from the invocation. Those are gone
([#319](https://github.com/AgoraDMV/DeltaTrack/issues/319)): the symlink was cosmetic,
and making "is a root symlink" the definition of a command meant anything else linked
into the root, such as a corpus directory linked in from another checkout, was reported
as an undocumented command.

### Testing

Tests are split into groups by speed and dependencies:

- **Fast tests** (`uv run pytest -m "not slow and not browser"`) -- unit tests on inline XML and mocked data; no bill files needed.
- **Browser tests** (`uv run pytest -m browser`) -- Playwright/Chromium front-end tests. One-time setup: `uv run playwright install chromium`.
- **Slow tests** (`uv run pytest -m slow`) -- integration and external-validation tests against real bill files. The corpus correctness gates (`test_corpus_properties`, `test_corpus_tree_properties`, `test_diff_validation`) run against a committed fixture set named in `tests/corpus_manifest.toml`, so they run in CI and their counts are reproducible; each fails closed if a manifested bill is uncommitted. `CORPUS_SWEEP=1` opts into sweeping every locally-fetched bill (non-CI exploration). A few other slow suites (the PDF recall tests, the Legislative Branch spreadsheet validation, and the live-network govinfo parity gate) still read larger fetched bills and skip when absent, or fail loudly under `REQUIRE_CORPUS=1` (see [TESTING.md](TESTING.md)). 

Adding or renaming a CLI subcommand? Add its row to the README "Command reference" table in the same change -- `tests/test_docs_consistency.py` introspects each root command script's parser and fails if a command has no row. Adding a whole new command? See ["Adding a CLI command"](#adding-a-cli-command) above for the convention the gate enforces.

When adding code, write tests for it. Test files live in `tests/`; mark tests that need real XML files with `@pytest.mark.slow` and front-end tests with `@pytest.mark.browser`. Shared helpers are in `tests/conftest.py`. [TESTING.md](TESTING.md) is the home for the full command catalog and what each validation layer proves.

### What CI checks

Every pull request runs these gates (defined in `.github/workflows/ci.yml`). Run them locally before pushing to avoid a surprise red CI:

```bash
uv run ruff check .                          # 1. Lint
uv run ruff format --check .                 # 2. Formatting (run `ruff format .` to fix)
uv run pytest -m "not slow and not browser"  # 3. Fast tests
uv run pytest -m browser                     # 4. Browser tests (needs `playwright install chromium`)
uv run pytest -m slow \
  tests/test_committee_report.py \
  tests/test_validate_extraction.py::test_report_amounts_recalled \
  tests/test_validate_extraction.py::test_fixture_is_senate_reported_bill  # 5. External validation
uv run pytest -m slow \
  tests/test_corpus_properties.py \
  tests/test_corpus_tree_properties.py \
  tests/test_diff_validation.py                # 6. Corpus correctness gates (committed manifest)
```

The pre-commit hooks cover gates 1 and 2 on each commit, but `ruff format --check` still fails CI if you committed without them. Gates 5 and 6 run against vendored/committed fixtures, so they need no downloads or API key.

## Submitting a pull request

1. Run the CI gates locally (above) and make sure they pass.
2. Open a pull request against `develop`.
3. In the description, link the issue it addresses ("Closes #123") and say what changed and why.
4. For a behavior change, note how you verified it -- not just "tests pass," but what you ran or eyeballed (see [Reviewing a pull request](#reviewing-a-pull-request)).
5. For a bug fix, show the test failing without the fix. A test that passes with or without your change doesn't prove the bug is gone.
6. If you used an AI coding assistant, say so (see below).

A maintainer reviews and merges. CI must be green.

### AI-assisted contributions

They're welcome, and we ask you to disclose them: one line in the pull request
description naming the tool is enough. Disclosure tells a reviewer where to look
harder; it isn't held against the change. The bar is the same either way, and
it's the bar this project already had:

- **You're the author.** Be ready to explain why the change is written the way it
  is and to answer review comments yourself. "That's what the model produced"
  isn't an answer, and a change nobody can defend can't be merged.
- **Run it before you send it.** Generated evidence isn't evidence. A test result
  or benchmark quoted in a description that nobody actually ran costs a reviewer
  more than claiming nothing at all, because it looks like proof.
- **One concern per pull request.** A model will happily fix six things at once,
  and a reviewer can't verify that.

A change that clears these is welcome however it was written. One that doesn't
gets closed, also however it was written.

## Reviewing a pull request

Review is how a small team shares context and catches the bugs tests miss. New teammates are encouraged to review early -- it's one of the fastest ways to learn the codebase.

What to look at, roughly in priority order:

- **Correctness of the diff itself.** This is the product. Passing tests are necessary, not sufficient: a diff can be green and still wrong. For any change that affects diff output, **run the tool on a real bill and eyeball the report** rather than trusting the suite alone. `scripts/serve_compare.py` gives a side-by-side view (see [TESTING.md](TESTING.md)).
- **The risk hotspots**, where a bug does the most damage:
  - **Parser accuracy** (`bill_tree.py`, `parsers/`) -- does the bill's structure come through intact? A missing or mis-nested section corrupts everything downstream. See [docs/parser-validation.md](docs/parser-validation.md).
  - **Financial diff** (`diff_bill.py` and its financial filtering) -- dollar amounts and their changes must be exact.
  - **The canonical schema contract** (`formatters/canonical.py`) -- both pipelines and the renderer depend on it, so a breaking change there ripples everywhere.
- **Tests for the change.** New behavior should come with a test that would fail without the fix. Judge that by the red-green delta on your own machine, not by the totals the author reported — test counts legitimately differ between machines here, and [TESTING.md](TESTING.md#test-counts-are-not-comparable-between-machines) explains why.
- **Docs and decisions.** A non-obvious choice belongs in a code comment or a [decision record](docs/decisions/); a user-facing change belongs in the README.

Leave specific comments, then approve or request changes. A maintainer does the actual merge.

## Filing an issue

Keep it light. Pick the matching template (bug, feature, or task) and fill in
what you know — you don't need to scope, size, or solve it. The most useful thing
you can provide for a bug is a way to reproduce it.

For bug reports, include:
- What you expected to happen
- What actually happened
- Steps to reproduce (bill number, versions compared, command you ran)
- Any error output

That's enough. The team fleshes out the rest when grooming the issue for pickup.

### Filing from the command line

`gh issue create --body-file` and `--body` **bypass the templates above entirely**,
along with the `type:` they set. Templates apply only in the web UI or when you
pass `--template <file>`. So an issue filed from the CLI silently matches none of
the repo's structure and carries no issue type.

If you file from the CLI (or have an AI assistant do it), read the template file
in `.github/ISSUE_TEMPLATE/` and fill its sections yourself, then set the type
explicitly with `--type Bug` / `--type Feature` / `--type Task`.

For a defect you found from inside the codebase, or anything you've already
analyzed, use the fill-in skeleton in
**[docs/issue-analysis-template.md](docs/issue-analysis-template.md)**. It covers
what's wrong / how it surfaced / why it matters / what to do, plus the evidence
rules, and trims down for tasks and features.

### Writing an issue others can read

Whatever you file and however you file it, two habits do most of the work. Both
are about the reader who wasn't there when you found the problem:

- **Open with the observable problem, not the artifact that surfaced it.** State
  what's wrong before naming a file, test, or function. Someone without the repo
  open should finish your first sentence knowing what's broken and why it matters.
- **Make cross-references self-describing.** `#141 (enrolled PDFs yield no anchors)`,
  not a bare `#141`. If a sentence stops making sense when you delete the number,
  the number was doing the explaining. Same for decision records and for jargon:
  define project terms inline the first time you use them.

[docs/issue-analysis-template.md](docs/issue-analysis-template.md) has the full
shape and the reasoning behind it.

## Grooming an issue for pickup

Reporting and picking-up are two different jobs. Filing should be low-friction;
making an issue *ready to pick up* is the team's job, done during triage (the
**Backlog → Ready** move on the board, usually at the biweekly sync). An issue is
**Ready** when it answers:

- **Problem / why** — what's wrong or missing, and why it matters.
- **Acceptance criteria** — a short checklist of what "done" looks like.
- **Scope** — one line on what's in and out, so the work doesn't sprawl.
- **Where to start** — entry file(s) or the relevant doc.
- **Priority** — set the org-level Priority field: Urgent / High / Medium / Low (see below).
- **Effort** *(optional)* — set the org-level Effort field if useful; not a focus right now.

This keeps the bar to *report* low while still giving a newcomer everything they
need to *start*.

### Priority

Priority lives in the **org-level Priority issue field** (defined once for the
AgoraDMV org, so it's consistent across DeltaTrack and BillTrax), set during
grooming. Its values are **Urgent / High / Medium / Low**:

- **Urgent** — broken or trust-critical: wrong/lost diff output, silent data
  corruption. Drop other work for these.
- **High** — important correctness or coverage to do soon; cheap unblockers.
- **Medium** — coverage, fidelity, structure, contributor on-ramp. Most work.
- **Low** — cleanups, cosmetics, deferred decisions, nice-to-haves.

Priority is "the next-couple-weeks tier," not a permanent ranking — the **Ready**
column holds the current Urgent/High items, and we re-look at each sync. We track
priority in one place (the field), not also as labels, to avoid two competing
sources of truth.

Sizing is available via the org-level **Effort** field (High / Medium / Low) if a
piece of work needs it, but it isn't a focus right now — don't block grooming on
it.

### Sprints

The biweekly sync doubles as sprint planning. The **`Sprint` iteration field**
(two-week, Wednesday-aligned blocks) is the sprint container, and the current
iteration's title holds that cycle's **theme** ("this sprint: get the demo out").
Committing an issue to the sprint = set its `Sprint` to the current iteration and
move it to **Ready**. We don't freeze the sprint or size by points — critical
items are chosen by judgment, and other **Ready** work is fair game. Track the
active sprint on the **Current sprint** board view (`iteration:@current`).

## Epics

A larger effort that spans several pull requests is tracked as an **epic**: an
issue with the **`epic` label** that is broken into **sub-issues** (the smaller,
discrete pieces of work). Pick up the *sub-issues*, not the epic itself.

- The epic's progress is the **sub-issues progress bar** on the parent — it isn't
  dragged through the board columns like a normal issue.
- Each **sub-issue** flows the board normally and closes via its own
  `Closes #<n>` pull request. When all sub-issues are done, a maintainer closes
  the epic.
- Epics live on the **Roadmap** view; the working board filters them out, so the
  day-to-day columns show only discrete, pickup-ready work.

Reach for an epic only when work genuinely needs decomposing — most features are a
single issue.

## Questions?

Open an issue, ask in [Slack](https://civictechdc.slack.com/archives/C0AT13U25V2), or bring it to the [meetup](https://luma.com/civic-tech-dc). There are no dumb questions. See [Community](#community) for how to join.
