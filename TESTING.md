# Testing and Accuracy

This document explains, in plain terms, how we test the tool and how far the
accuracy checks actually go. The how-to-run commands are at the end; you can 
skip them if you only want to understand how accuracy is checked.

## The diff does not guess

The comparison is done by plain, rule-based code. It does not use an AI model,
and it does not call out to any service. The same two documents always produce
exactly the same comparison. There is no randomness and nothing to "get lucky"
or "get unlucky" on.

The tool does need an internet connection for one thing only: downloading bills
in the first place. By default that uses keyless govinfo bulk data (no API key);
a `CONGRESS_API_KEY` is only needed with `--source api` or year-range discovery.
That step is separate from the comparison. If you already have the documents, the
comparison needs no key and no internet connection.

## How accuracy is checked

Accuracy is checked in five ways. Each one answers a different question, and
each has limits worth being honest about. There is no single accuracy
percentage that would be truthful across all of appropriations, so we describe
what each layer does and does not establish.

### 1. Checking the numbers against an outside source

This is the strongest check. It now covers all twelve regular appropriations
subcommittees, through two kinds of independent source:

- **A separately maintained spreadsheet (Legislative Branch).** We took an
  appropriations spreadsheet kept by other people for Legislative Branch bills,
  covering both the House and Senate across several years, and confirmed that the
  dollar amounts our tool pulls out of the official bill text match the amounts in
  that spreadsheet, in the right place in the bill's structure.
- **Senate committee reports (the other eleven subcommittees).** For each of the
  remaining subcommittees we read the account-level amounts out of the Senate
  Appropriations committee report and confirmed that each amount the committee
  recommended appears in what our tool extracts from the reported bill. A committee
  report is written by different people for a different purpose than the bill, so
  it is a genuinely outside source.

Because every source was built independently of our tool, this catches mistakes
that checking the tool against itself never could. Across the committee-report
checks, the amounts we cannot recall are confirmed report-versus-bill differences
(indefinite accounts with no fixed-dollar line, totals the bill states only as
their parts, and a few report typos the report's own summary tables contradict),
not extraction errors. The per-subcommittee counts are tracked so they cannot
quietly rise.

**Limit:** the twelve subcommittees are checked to different depths. Legislative
Branch is checked structurally, meaning the right amount in the right place,
across several bills and both chambers. The other eleven are checked as
amount-recall, meaning the right amounts are present under the right agency, on a
single Senate-reported bill each, because the report and the bill name accounts
differently. Two consequences follow, and we track both on purpose: an amount that
landed on the wrong account inside the right agency would still pass the recall
check, and the House versions of those eleven subcommittees have no outside-source
check at all, because House committee reports print their account tables as images
we cannot read.

### 2. Sanity checks across every bill we have

These checks run automatically across a committed, curated set of real bills
(one per appropriations subcommittee, plus the key structural shapes) and confirm
that nothing falls through the cracks: every dollar figure in the source text
shows up somewhere in the parsed result, the same section is not accidentally
listed twice, and the tool does not silently drop large chunks of text.

**Limit:** these are broad but shallow. They confirm that the tool did not lose
or mangle content. They do not confirm that any particular comparison is
*correct*, only that nothing obvious was dropped.

### 3. Frozen expectations on specific bills

For a few real pairs of bill versions, we wrote down specific things that should
be true and turned them into automatic checks. For example: a certain set of
sections should show up as newly added rather than as edits, and a section that
was renumbered should be recognized as the same section moved, not as one
section deleted and a different one created. The tool also runs every
consecutive pair of versions through the comparison and confirms basic
soundness: it does not crash, it does not match up two sections that are
actually unrelated, and it does not report the same change twice.

The purpose of these checks is to stop the tool from getting *worse* over time.
If a future change breaks one of these expectations, a test fails.

**Limit:** these confirm the specific expectations we wrote down, plus the
section counts we recorded as a baseline. They are not a line-by-line human
review of every change in those bills. Treat them as guardrails, not as proof
that every comparison was read and signed off by a person.

### 4. Draft-bill comparisons (PDF)

Draft bills circulate as PDFs with no official machine-readable version behind
them, so they are handled and tested separately. For one draft bill, we built a
fixture by hand: a written list of the changes the comparison ought to surface,
including where each change appears (page and line) and what kind of change it
is. The tool's PDF comparison is then checked against that list.

**Limit:** this is the newest and thinnest area, and the hand-built list so far
covers a single draft bill.

### 5. Cross-checking the PDF reading against the official text

Most published bills exist in two forms: an official machine-readable version
and a PDF. For every bill we have in both forms, we confirm that every dollar
amount found in the official version also turns up when the tool reads the PDF.
Because the official version is the one checked against the outside spreadsheet
(check 1), this tells us the PDF reader is not quietly dropping or garbling
figures, even though a PDF is flat text with none of the structure the official
version carries. A second pass runs the PDF comparison across every consecutive
pair of versions and confirms it stays sound: it does not crash, it does not
report overlapping or out-of-bounds locations, and every change it reports has a
sensible type.

**Limit:** this confirms our PDF reader and our official-text reader *agree* on
the numbers, which catches reading mistakes. Agreement between our own two
readers is not the same as an outside source confirming the numbers are correct
— that is check 1, and only for Legislative Branch appropriations. (This
cross-check earlier surfaced a quirk in the official-text reader, where it
merged a dollar figure with an adjacent percentage in non-spending statutory
tables; that has since been fixed.) The soundness pass covers every bill,
including the largest omnibus in the collection.

## Known soft spots

We keep these in the open rather than papering over them:

- **"Is it the same section or a different one?"** When two sections are
  partly similar but not clearly the same and not clearly different, the tool
  has to make a judgment call, and that is where it is most likely to mislabel
  an edit. We track how often this borderline case comes up so it cannot quietly
  increase. A hand-labeled answer key (`tests/data/similarity_labels.json`, checked
  by `tests/test_similarity_labels.py`) pins the current behavior: real section
  pairs the tool gets right anchor the metric, and five human-ruled dead-zone pairs
  are recorded as `xfail` because today's word-similarity thresholds classify them
  wrong. The key is body-text-only on purpose — it is the evidence that pure text
  similarity has no skill in that band and that the fix is structural context (the
  division/agency/account breadcrumb), tracked in #170. An `xfail` flips to XPASS if
  the thresholds are improved.
- **Large combined bills.** In omnibus bills that bundle many areas together,
  section numbers repeat across areas, which makes matching harder. The tool
  handles this, but it is the trickiest case.
- **Outside-source depth varies.** As noted in check 1, all twelve subcommittees
  now have an outside-source check, but only Legislative Branch is checked for the
  right place rather than just the right amount, and only it is checked on the
  House side. The other eleven rest on a single Senate-reported bill each.

## Running the tests

The rest of this is for people running the test suite.

Tests split into two groups by a `slow` marker. The fast group runs on small
built-in examples and needs no downloads. The slow group runs against real bill
files, and nearly all of it also needs no downloads: the fixtures are committed,
and CI runs every slow module except the live-network parity gate. A download
buys you extra cases in the two suites that sweep your local `bills/`, plus the
handful of checks listed under [What still wants a download](#what-still-wants-a-download).

```bash
uv run pytest -m "not slow and not browser"   # Fast group: built-in examples, no downloads
uv run pytest                                  # Everything, including checks against real bills
uv run pytest --run-network -m slow            # ...plus the live-network parity gate (maintainer, needs a fetched corpus)
```

Three markers say what a test needs beyond a clean clone: `slow` (real bill files,
committed), `browser` (`playwright install chromium`), and `network` (a live external
fetch). `network` is the only one skipped by default -- pass `--run-network` to opt in,
or `-m "not network"` to deselect it outright. It replaced the `REQUIRE_CORPUS=1`
environment variable in #278, whose name described neither of the two unrelated things
it had come to gate.

### Test counts are not comparable between machines

A large share of the suite is data-driven, parametrized over real bill files that
live in gitignored directories (`bills/`, `bills_corpus/`). How many tests collect,
pass, or skip therefore depends on how much bill data that particular machine has
fetched — a full working checkout and a fresh clone legitimately report very
different totals for the same commit.

So an absolute count proves nothing on its own, and comparing one across machines
proves less than nothing: a reviewer who measures a contributor's reported total
against their own is reading corpus difference as a defect. The signal that does
carry is the **red-green delta on a single machine**: revert the change and
confirm the tests it added go red. Within one machine, a change in the *skip*
count is worth reading too — `-rs` prints the reasons, and a category that
quietly started skipping is coverage disappearing with no failure to show for it.

### The corpus gates run against committed fixtures

The corpus correctness gates -- listed in `CORPUS_GATE_MODULES` in
`tests/conftest.py` -- parametrize over a committed, curated fixture set named in
`tests/corpus_manifest.toml`, not over whatever bills a machine happens to have
fetched. So they run the same set on every machine and in CI, and their case
counts are reproducible. Every bill the manifest names is committed to git
(public-domain government works, 17 U.S.C. 105).

Each of those modules carries a `test_manifest_fixtures_committed` floor that
**fails closed**: if a manifested bill is missing from the checkout, the gate
goes red rather than silently collecting fewer cases. That is what CI relies on.
It replaces the old opt-in `REQUIRE_CORPUS=1` mode *for these three gates*, which
existed only because they used to parametrize over a fetched glob that was empty --
and so green, asserting nothing -- on a clean checkout (the fail-open pattern).
(#220 brought the last three modules -- `test_node_join_corpus`,
`test_xml_subsection_nodes`, `test_pdf_subsection_recall` -- onto the same manifest
and the same fail-closed floor, and deleted `require_corpus_or_skip` /
`REQUIRED_CORPUS_BILLS` with them. #278 committed the Legislative Branch validation
set and retired `REQUIRE_CORPUS` outright; the one requirement no fixture can supply
is a live network, and that is now the `network` marker.)

To sweep every bill you have fetched locally -- broader than the committed set,
and useful for finding bugs a few clean bills don't -- set `CORPUS_SWEEP=1`. It
spans both trees (the committed fixtures in `tests/corpus/` *and* `bills/`), so it
is a strict superset of what the gates collect. This is exploration, not a gate;
CI never runs it.

```bash
# The committed corpus gates (what CI runs):
uv run pytest -m slow tests/test_corpus_properties.py tests/test_corpus_tree_properties.py tests/test_diff_validation.py
# Sweep every locally-fetched bill (opt-in exploration):
CORPUS_SWEEP=1 uv run pytest -m slow tests/test_corpus_properties.py
```

### The rest of the slow suite runs in CI too

A further CI step runs the remaining slow modules (`CI_SLOW_MODULES` in
`tests/conftest.py`) against what they can already assert on from the committed
corpus. Only the live-network `test_govinfo_corpus_parity` is left out.

The distinction worth keeping straight is that committing a fixture makes a gate
**runnable**; naming its module in the workflow is what makes it **run**. Several
of these modules passed on any fresh clone for months while no CI step named
them, so they asserted nothing where it counted.

### When a skip has to be declared

A skip asserts nothing, so a suite that quietly starts skipping is
indistinguishable from one that is passing. Both watched groups therefore fail
the session on a skip that is not written down, and the failure banner names
which ceiling fired:

| Allowlist | Records | Retired by |
|---|---|---|
| `ALLOWED_CORPUS_SKIPS` | A permanent property of a document, e.g. a shell bill that genuinely carries no dollar amounts | Nothing; it is a fact about the fixture |
| `ALLOWED_CI_SLOW_SKIPS` | Mostly a bill version this repo does not commit -- a coverage gap, so the list doubles as a count of what the corpus is missing | Committing that fixture, which should delete the line |

They are kept apart on purpose: merged, a temporary gap would be
indistinguishable from a permanent fact.

Matching is on nodeid **and** reason, so an allowlisted case that starts skipping
for a *different* reason still fails. Add an entry only with a comment saying
why, and treat adding one as recording a gap rather than clearing an error.

**Sometimes the answer is not to declare it at all.** Both allowlists assume the
skip is honest: the document really has no dollar amounts, or the fixture really
is not committed. A skip caused by a *parser gap* fits neither. Declaring one
converts a known bug into documented-normal, and the ceiling then permits it
permanently — the gate goes quiet on exactly the case it exists to catch. The
honest options there are to fix the parser, or to leave the fixture out of the
corpus with a note saying why.

`115-hr-244` v5 is the worked example. It is an engrossed-amendment-house
document carrying ~1900 appropriations tags that the gates' body extraction does
not surface — the amendment-doc class tracked in #11. Committing it would have
forced an `ALLOWED_CORPUS_SKIPS` entry recording that the document had nothing
to find, which is not true of the document. It is withheld instead. Withholding
is not the same as declaring nothing: `tests/test_bill_tree.py` still names that
version, so its skip is declared in `ALLOWED_CI_SLOW_SKIPS`, where an
uncommitted fixture is an honest coverage gap that committing the file would
retire. What the withholding avoids is the *other* entry — the one that would
have asserted a false fact about the document. The manifest's `covers` note for
that bill records why, where the next person will look.

### Why a local run can collect more than CI

Most watched modules parametrize over the manifest, so their case list is
identical everywhere. Two sweep instead: `test_pdf_corpus_smoke` and
`test_pdf_xml_amount_recall` iterate whatever version pairs the bill trees hold.
Since #308 they sweep `tests/corpus/` by default, so an ordinary local run, a
worktree and CI now collect the *same* cases. Only `CORPUS_SWEEP=1` widens them to
`bills/` as well, and that mode disables the skip ceiling outright.

Cases the committed corpus cannot produce are excluded from the ceiling anyway
(`is_watched_case` in `tests/conftest.py`): no allowlist calibrated on the
committed corpus could name a case that exists only on one machine, and a case CI
cannot collect cannot regress in CI -- so watching them would turn a full local run
red while CI was green, on a branch where nothing is wrong. With both sweeping
suites now pinned to the fixture tree, that carve-out exempts nothing in practice;
it is kept so a future sweeping module inherits the right behaviour rather than
having to rediscover it.

### Adding a corpus fixture

The manifest and the committed files move together:

1. Put the bill version file(s) under `tests/corpus/<id>/` and `git add` them.
   That directory is tracked normally, so there is no `.gitignore` step: if you
   fetched the bill first, copy it across from `bills/<id>/`.
2. Add a `[[bill]]` entry to `tests/corpus_manifest.toml` naming the `id`, each
   committed version's `stage` (the filename without extension) and `formats`
   (`xml` and/or `pdf`), and a `covers` note saying what structural situation
   the bill uniquely exercises.
3. Run the gates. Any per-bill baseline a gate encodes
   (`_KNOWN_DUPLICATE_COUNTS`, `_XML_DROP_BUDGET`, ...) must be calibrated for
   the new bill or the gate fails. Commit the calibrated baseline alongside the
   fixture and manifest entry.
4. If the run names your fixture in a **skip-ceiling banner**, decide what to do
   about it. The manifest entry does not only add cases: it enrolls the bill in
   the corpus property gates, which may then legitimately content-skip on it,
   and an undeclared skip fails the session. The banner names a test you
   never touched, in a module you may not have known your fixture had joined —
   that is this step, not a pre-existing breakage. See
   [When a skip has to be declared](#when-a-skip-has-to-be-declared) for which
   allowlist applies, and for the case where the right answer is to withhold the
   fixture rather than declare its skip as a content fact.

A version committed in both `xml` and `pdf` joins more gates than the same
version committed in one format, so expect step 4 to reach further. #322 added a
single PDF and widened three modules at once.

**The two trees are separate, and only one matters to the gates** (#308).
`tests/corpus/` is committed and is what every gate reads; `bills/` is the
fetchers' working directory, entirely gitignored and entirely disposable —
delete it, or symlink another checkout's corpus over it, without touching a
fixture. `tests/corpus_paths.py` is the only place either path is spelled: use
`fixture_path(bill_id, filename)` rather than composing a path yourself, and
`tests/test_fixture_layout.py` will fail the build if a test reaches into
`bills/` for a bill that is committed.

Run a single area:

```bash
uv run pytest tests/test_bill_tree.py            # Reading and structuring the bill text
uv run pytest tests/test_diff_bill.py            # Comparing two versions
uv run pytest tests/test_financial_diff.py       # Pulling out and comparing dollar amounts
uv run pytest tests/test_reconcile.py            # Recognizing moved sections
uv run pytest tests/test_format_html.py          # The HTML report
uv run pytest tests/test_corpus_properties.py    # Sanity checks across the committed corpus (slow)
uv run pytest tests/test_validate_extraction.py  # Checking numbers against the spreadsheet (slow)
uv run pytest tests/test_pdf_diff_recall.py      # Draft-bill (PDF) comparison (slow)
uv run pytest tests/test_pdf_xml_amount_recall.py  # PDF reading vs official text, by the numbers (slow)
uv run pytest tests/test_pdf_corpus_smoke.py     # PDF comparison soundness across every bill (slow)
```

### What still wants a download

Less than the `test_pdf_*` naming suggests. Most of those suites assert against
committed fixtures and are CI gates; a download only adds cases:

| Still needs fetched bills | Why |
|---|---|
| `test_govinfo_corpus_parity` | Live BILLSTATUS fetch, so it cannot be an offline gate. Marked `network`: skipped unless you pass `--run-network`. A weekly scheduled workflow runs it against the committed fixtures (#342); a download only widens which bills it checks |
| `test_bill_tree.py::…::test_amendment_doc_115_hr_244_v5_produces_nodes` | Pinned to 115-hr-244 v5, whose fixture is deliberately withheld (#11/#322, and this file's ["When a skip has to be declared"](#when-a-skip-has-to-be-declared)). Skips without it |
| `test_pdf_text.py::TestUnbulletedFooterConsumedOutput` | Pinned to the 115-hr-5895 v3 PDF; that bill is committed at stages 1/2/4/5 only, so the class is `skipif`-gated on v3 being downloaded |

Those two are single cases pinned to a withheld version, not gates losing coverage:
they resolve through `resolve_bill_file`, which returns the `bills/` path when no
fixture exists precisely so the caller's own `.exists()` check reports on the file it
would really read.

The Legislative Branch validation set used to be on that list. #278 committed its
five remaining bills, so its completeness floor is now an ordinary fail-closed
check that runs everywhere, and CI validates all seven of the fixture's bills
instead of the two that happened to be committed.

Everything else in the slow group asserts on a clean clone, against
`tests/corpus/`. A download never changes what those gates assert, and since #308
it does not change what they *collect* either: the two sweeping suites
(`test_pdf_corpus_smoke`, `test_pdf_xml_amount_recall`) read `tests/corpus/` like
everything else. A download only widens what `CORPUS_SWEEP=1` reaches.

When you do download, the PDF suites need each bill's PDF as well as its XML;
pass `--format both`, e.g.
`uv run python tools/fetch_bills.py download 118 hr 4366 --format both`. See the
Testing section of the [README](README.md#testing).

Assets sourced directly from govinfo rather than the bill API -- such as the
reported-in-Senate watermarked PDF of S.4795 that `test_pdf_watermark_recall.py`
reads -- are committed, so a fresh clone already has them.
`scripts/fetch_test_assets.py` re-fetches one you deleted locally and records its
provenance:

```bash
uv run python scripts/fetch_test_assets.py
```

That script is not part of the validation-evidence refresh — rebuilding the
ground-truth fixtures and regenerating `docs/parser-validation.md` is a separate
procedure, written down as a runbook in
[scripts/README.md](scripts/README.md#refreshing-the-validation-evidence).

### Speeding up the PDF tests for development

The slow PDF tests read every bill PDF, and reading a large omnibus takes a
couple of minutes. Three levers keep the loop fast:

```bash
# Restrict both PDF suites to one bill (substring match on the bill name):
TEST_BILL=4366 uv run pytest tests/test_pdf_xml_amount_recall.py tests/test_pdf_corpus_smoke.py

# Run across all CPU cores:
uv run pytest -n auto

# Combine them:
TEST_BILL=4366 uv run pytest -n auto tests/test_pdf_corpus_smoke.py
```

The first run extracts each PDF and caches the result to
`tests/data/extract_cache/` (gitignored). Every later run loads from that cache
instead of re-reading the PDF, so re-running the same tests is near-instant.

An entry is reused only when nothing that produced it has changed, so the key
covers both halves: the PDF (path and modification time) and the extractor
(`src/deltatrack/parsers/pdf_text.py` and the pypdfium2 version). Editing or
replacing a PDF re-extracts it, and so does any edit to the extractor. Before
that second half was in the key (#393), an extractor change left every entry
looking current, and the golden suites reading the cache asserted against
pre-change text and stayed green on a real regression.

The rule is deliberately blunt: a comment-only edit to
`src/deltatrack/parsers/pdf_text.py` also invalidates the cache, so the next run
pays one full re-extraction.

Superseded entries are never reclaimed, so each invalidation leaves the previous
set on disk. Nothing reads them and nothing in CI restores the directory, so to
reclaim the space just delete it: `rm -rf tests/data/extract_cache`. The next run
re-extracts.

## Comparing the two pipelines by eye

The automated checks above don't diff the two pipelines against *each other*. To
eyeball the PDF-derived and XML-derived reports for the same two versions side by
side — to catch parity gaps in breadcrumbs, section grouping, financial callouts,
or change counts — serve them together:

```bash
uv run python scripts/serve_compare.py 118-hr-8752
uv run python scripts/serve_compare.py 118-hr-8752 --v1 1_reported-in-house --v2 2_engrossed-in-house
uv run python scripts/serve_compare.py path/to/bill-dir --port 8765 --no-browser
```

With no `--v1`/`--v2` it picks the two lowest-numbered versions that have both a
`.pdf` and an `.xml`. A bare bill id resolves against the committed fixtures in
`tests/corpus/`, many of which carry both formats; to view a bill you downloaded
into `bills/` instead, pass its directory path (and fetch it with `--format
both`). Rendered HTML goes to a temp dir, nothing committed. The panes reflect the current checkout, so run it on the branch whose
diff output you're inspecting. This is a manual debugging aid, not a test.

## Measuring coverage

Coverage measures how much of the comparison code the tests actually exercise.
It is reported with `pytest-cov` (already included as a development dependency).

```bash
uv run pytest --cov --cov-report=term-missing                 # Full suite (no download needed)
uv run pytest -m "not slow and not browser" --cov --cov-report=term-missing  # Fast group only
uv run pytest --cov --cov-report=html                          # Browsable report in htmlcov/
```

One caution: coverage tells you which lines of code ran during the tests, not
whether their output is correct. A high coverage number and a correct result
are different things. The five checks above are what speak to correctness.
