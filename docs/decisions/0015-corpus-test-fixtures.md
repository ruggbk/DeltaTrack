# 15. Commit a curated corpus fixture set and collect the gates from a manifest

- Status: Accepted
- Date: 2026-07-17
- Note: the second fixture tree this record calls `test_data/` moved to `tests/data/` in
  #404, resolved through `corpus_paths.DATA_DIR`. The decision below is unchanged; only
  the path is. Paths in this record are left as they were written.

## Context

A large share of the test suite is data-driven: the correctness gates that prove
the parser reads a bill right ([0009](0009-validation-ground-truth.md)) run against
real bill XML and PDF documents. Today those gates parametrize over whatever
documents happen to be on the machine — `sorted(BILLS_DIR.glob(...))` evaluated at
collection time in `test_corpus_properties.py`, and the same shape in
`test_corpus_tree_properties.py` and `test_diff_validation.py`. The number of test
cases pytest creates therefore equals how many bill files that clone has fetched.

Two problems follow, one cosmetic and one not.

The cosmetic one: pass/skip counts are not comparable across machines. Reviewing
PRs #211 and #216 surfaced a two-environment gap of over a hundred tests that was
entirely a difference in local corpus size, not in the diff. A contributor cannot
report a count anyone else can reproduce, which weakens the "run it before you send
it" evidence the project asks for.

The real one: these gates are marked `slow`, and CI's slow job hand-picks only a
few vendored-fixture tests. So the corpus property and validation gates run *only*
locally, over whatever each developer fetched, and never in CI. A gate that runs
against an empty glob collects zero cases and passes green with no assertions — the
fail-open failure mode the project keeps hitting, the same risk
[0009](0009-validation-ground-truth.md) guards against when it insists validation
"does not silently skip."

Underneath sits an unpinned obtain step: the fetch tooling resolves a live, growing
committee listing (with an end year defaulting to the current year), so the set is
not reproducible over time. There is no committed manifest of exact bills.

This decision reverses a documented earlier stance, so the reversal is stated openly
rather than left to be rediscovered. PRs #62/#64/#66 deliberately made the corpus
fetch-scripted and gitignored — `scripts/fetch_test_assets.py` keeps its PDFs out of
git as "large binaries," `conftest.py` calls clean-clone skipping "the deliberate
design," and `AGENTS.md` recorded the intended path as *CI fetches* a curated corpus
and sets `REQUIRE_CORPUS=1` itself (tracked in [#126](https://github.com/AgoraDMV/DeltaTrack/issues/126)).
That design solved a real problem — a clean clone should not need a large download —
but it left the parser's most important gates with no CI signal and made counts
machine-dependent. The tradeoff below reweighs that.

The reweighing rests on two facts. First, bill documents are **immutable** (a
published version is frozen on govinfo) and **small** (committed subcommittee-bill
PDFs here are 240–360 KB; omnibus prints run into the low MB), so committing them is
a one-time cost with no binary churn — the usual case against committing PDFs does
not apply. Second, comparable parsers of government documents commit their fixtures
directly in plain git, no LFS: Juriscraper ships on the order of ~88 MB, PyMuPDF
~98 MB. A curated bill set is well inside that norm and far under any platform limit. US bills are public-domain government works
(17 U.S.C. 105), so committing them carries no licensing encumbrance.

## Decision

We will treat the corpus the correctness gates assert against as a **committed,
curated, versioned fixture set**, enumerated by a **committed manifest** that the
gates parametrize over — not the filesystem.

- The manifest names the exact bills (id + version) the gates run against, curated
  by structural variety — one bill per code path and document class, per
  [#126](https://github.com/AgoraDMV/DeltaTrack/issues/126) — not bulk. Its size is
  measured and recorded on the implementing PR; the target is on the order of tens of
  MB, well inside the peer norm and never the full mining corpus. `REQUIRED_CORPUS_BILLS`
  in `conftest.py` is the embryonic version of this manifest.
- Those bills are **committed to git**. A curated set is small, immutable, and gives
  CI an offline, zero-fetch, byte-identical corpus.
- The gates **parametrize over the manifest**, so the collected set is identical on
  every machine. A manifested bill absent locally becomes an explicit **skip with a
  reason**, never a vanished case, so `collected = passed + skipped` is constant and
  a partial checkout is visible, not silent.
- **CI runs the corpus gates against the committed set**, with a completeness floor
  that fails closed: it asserts that the number of manifest cases actually run equals
  the manifest length — a count *derived from the manifest*, not a hardcoded snapshot
  ([#177](https://github.com/AgoraDMV/DeltaTrack/issues/177)) — so a missing or wrong
  fixture turns green into red.
- The broad discovery sweep is **kept as an opt-in, non-CI exploratory mode**, not
  removed. Sweeping every locally-fetched bill has repeatedly caught bugs that a few
  clean bills did not ([#126](https://github.com/AgoraDMV/DeltaTrack/issues/126),
  #146); that value is real, but it is exploration, not a gate, and must not be the
  thing CI depends on.
- The large research and mining corpus (`bills_corpus/`) is **not a test input** and
  stays gitignored.

Alternatives considered:

- **Keep the test set fetched on demand, pinned by a checksummed manifest** (a
  pooch-style `filename sha256` registry). This is the right tool when the pinned set
  is too large to commit, and is retained as the prescribed approach *for the mining
  tier* should it ever need reproducibility. Rejected for the test set because that
  set is small and immutable, where committing removes the network from CI entirely
  and is simpler.
- **Git LFS / git-annex.** Rejected. Bills are re-fetchable from a durable host, so
  the need is to *pin* bytes, not *store* them off-repo; LFS pays storage, bandwidth,
  and per-run CI-quota cost to version data already hosted free, and ties the repo to
  LFS hosting.
- **Status quo — glob-discovered collection.** Rejected: the direct cause of
  non-comparable counts and of correctness gates that fail open with no CI signal.

## Consequences

- Test counts become reproducible — the collected set is the manifest, identical
  everywhere — so reviews no longer chase environment-driven count gaps.
- CI green gains meaning it lacked: the corpus correctness gates actually run there,
  against a known set, and fail closed if the set is incomplete.
- The repository grows by the committed set (tens of MB, one-time, no churn since
  bill versions are immutable). Expected-output snapshots, not the bills, are the
  churn to watch and are regenerated deliberately (as [0009](0009-validation-ground-truth.md)
  frozen expectations already are; `pytest-regressions` is the off-the-shelf form).
- A manifest and an "add a fixture" recipe must be maintained as the single source
  the collection reads; adding a fixture without the manifest, or the reverse, must
  be prevented. `AGENTS.md` guidance on the worktree fail-open and the pre-PR
  `REQUIRE_CORPUS=1` step, and `TESTING.md`, are updated; the opt-in `REQUIRE_CORPUS`
  env var is subsumed by the CI completeness floor. (Not fully, as it turned out — see
  the #220 amendment below, and #278, which finished the job.)
- CI runtime rises: the corpus gates are `slow` and PDF extraction has no CI cache,
  so the curated set is sized against a CI time budget. The PR-blocking completeness
  floor always runs on every PR; implementation may additionally run a larger slice
  on a separate (e.g. nightly) cadence, and the floor applies wherever the gates run.
- This does not displace the layered suite. Synthetic in-memory fixtures (the
  #211/#216 download tests) stay the hermetic floor; the committed corpus is the
  real-document layer, now fixed and CI-run rather than variable and local-only; the
  independent committee-report validation ([0009](0009-validation-ground-truth.md))
  remains the top layer.
- Reproducibility of the fetched corpus over time stops mattering for tests, since
  tests no longer depend on the fetch path. It remains a caveat for building research
  corpora, documented where the fetch tooling lives.
- Implementation is tracked in [#217](https://github.com/AgoraDMV/DeltaTrack/issues/217)
  (manifest-driven collection and the CI completeness floor) and
  [#126](https://github.com/AgoraDMV/DeltaTrack/issues/126) (curating which bills);
  this record is the *why*, not the build status.

## Amendment (#220, 2026-07-20)

The decision above is unchanged; this records how far it now reaches, since the body
describes a partial rollout.

- **All corpus gates are now manifest-collected**, not just the three named in #217.
  `test_node_join_corpus`, `test_xml_subsection_nodes` and `test_pdf_subsection_recall`
  were left on the fetched-glob model because they pinned larger uncommitted bills;
  their fixtures are now committed and manifested, and they carry the same fail-closed
  floor. Measured before the change on a clean checkout, those three collected 19 cases
  and finished in 0.15s (7 trivial passes, 12 skips, no document parsed); after, 32
  cases in 16.7s.
- **The predicted cost was high.** The body targets "on the order of tens of MB". The
  committed set after this change adds 13 files: 11.9 MB on disk, roughly 5.2 MB
  compressed, against a repository pack of about 7 MB. #220's own estimate for the
  first twelve (20-25 MB) was high by about 2.5x, because bill XML compresses ~4.5x
  and git stores objects compressed.
- **`REQUIRED_CORPUS_BILLS` is gone**, along with `require_corpus_or_skip`. The body
  calls it "the embryonic version of this manifest"; the manifest has now fully
  replaced it.
- **No hand-calibrated baseline needed editing, but three inert ones came alive.**
  `_XML_DROP_BUDGET` and `_KNOWN_DUPLICATE_COUNTS` already carried entries for
  `113-hr-3547/5`, `114-hr-2029/5` and `114-hr-2029/6` — dead keys, because those files
  were not manifested and so were never collected. Manifesting the files makes those
  three calibrations *live*, and they pass at their existing pinned values. The gates
  collect more cases (the added fixtures) and skip two more (113-hr-3547 v4, a shell
  amendment with no dollar amounts) with no threshold change, and three budgets that
  documented an expectation now actually enforce it.
- **The `REQUIRE_CORPUS` env var was not fully subsumed by #220, and is now gone
  ([#278](https://github.com/AgoraDMV/DeltaTrack/issues/278)).** The body predicted #220
  would subsume it, and for every corpus gate it did. Two non-manifest consumers kept it
  alive, needing different things — a network, and five uncommitted bills — under one
  name that described neither. #278 separated them:
  - The five Legislative Branch validation bills are committed (18.1 MB raw; 5.1 MB as
    git stores them today, narrowing toward the ~4 MB gzip figure once repacked). Its
    completeness floor is now an ordinary fail-closed check, asking git whether each
    file is TRACKED (#308/#327) rather than merely present. CI validates all seven of
    the fixture's bills instead of the two that happened to be committed.
  - `test_govinfo_corpus_parity` — a live BILLSTATUS fetch per bill, and the only check
    that the documented setup path still matches the code (see
    [#271](https://github.com/AgoraDMV/DeltaTrack/issues/271)) — carries
    `@pytest.mark.network`, skipped unless `--run-network` is passed. It still needs a
    marker states that requirement where an env var did not. #342 later derived its
    completeness floor from the committed manifest and put it on a weekly schedule, so it
    no longer needs a fetched corpus either.

  The general lesson, recorded because it is the reusable part: express "this test needs
  something extra" as a marker, not an environment variable. A marker is registered in
  `pyproject.toml`, discoverable via `-m`, and names one requirement, so two unrelated
  requirements cannot silently fuse behind it.

### A size bar for future additions

Committing fixtures trades repository weight for CI coverage, and git keeps blobs in
history permanently — a fixture added is a fixture the clone carries forever, even if
later removed. To keep [#126](https://github.com/AgoraDMV/DeltaTrack/issues/126)
curation from growing the pack by precedent, a fixture addition should:

- **Prefer XML over PDF** wherever the gate under test accepts either. XML compresses
  ~4.5x; the PDFs here are near-incompressible and dominate the on-disk cost.
- **Carry a stated reason in the PR** for anything above ~1 MB compressed per bill, and
  name the specific gate that needs *that* document (not a smaller or synthetic stand-in).
  The 113-hr-3547 4->5 pair clears this bar because diffing a 2.6 KB shell against a
  3 MB omnibus is the property under test; a second omnibus "for coverage" would not.
- **Prefer a single stage** over a whole version history unless adjacent-version diffing
  is the thing being gated.

This is a guideline for reviewers, not a hard cap; the point is that each addition is a
deliberate, justified choice rather than a default.

## Amendment (#308, 2026-07-24)

The decision is unchanged — fixtures are committed, curated, and enumerated by a
manifest. What changes is **where they live**, which the body deliberately left open
("it says nothing about where fixtures live"). They move from `bills/` to
`tests/corpus/`, and `bills/` becomes entirely gitignored.

The body's model was one directory holding both the committed fixtures and the
downloaded working corpus, with the fixtures re-admitted past a blanket ignore rule
file by file. That list reached 80 rules. It was a second copy of
`tests/corpus_manifest.toml` that nothing checked for agreement — it accumulated at
least one provably inert rule (`!bills/large_bills.csv`, overridden by a later
`*.csv`) without anyone noticing — and its omission was silent, because `git add` on
an ignored path is a no-op. #327 made that omission loud by asking `git ls-files`
rather than the filesystem. Splitting the trees removes the edit instead of guarding
it, which is why both changes exist and why the #327 floor is kept: it now guards an
ordinary mistake (a fixture written but never staged) rather than a footgun.

Consequences worth recording:

- **Adding a fixture is `git add` plus a manifest entry.** No ignore-file edit, and no
  need to know that `!bills/<id>/` is inert without a following `bills/<id>/*`.
- **`bills/` is genuinely disposable again.** The body's model made it part-tracked,
  which is why `TESTING.md` had to carry a bolded warning never to `rm -rf` it and why
  symlinking another checkout's corpus over it was hazardous. Both are now safe.
- **`test_data/` gets the same inversion.** It was deny-all-then-re-admit for the same
  reason and with the same effect: adding a golden required an ignore edit. It is now
  tracked by default with two local-only artifacts listed.
- **`corpus_paths.py` is the single home for the layout**, so a future move is one edit
  rather than thirty. `resolve_bill_file` is the concession to consumers whose inputs are
  mixed at the *version* level — a bill committed for the stages a gate pins and
  download-only for the rest, e.g. `115-hr-5895` (stage 3 not committed) and `115-hr-244`
  (enrolled committed, engrossed-amendment doc withheld per #11/#322). It is a deliberate
  fallback into `bills/`, and the layout guard cannot see through it, so prefer
  `fixture_path` wherever the file is committed.
- **Three new silent-failure channels open, and are closed by
  `tests/test_fixture_layout.py`**: a committed fixture addressed through `bills/`
  (resolves on a machine that downloaded it, absent in CI, where the skip-if-absent
  guard keeps the run green); a `CORPUS_SWEEP` that stops spanning both trees (nothing
  asserts its case count, so narrowing it loses coverage silently); and a fixture
  written into `tests/corpus/` but never staged (the manifest floor covers manifested
  bills, but the golden modules pin files the manifest does not name). Each rule proves
  it can fire against a synthetic bad input, except the tracking one, whose fault has to
  be injected on disk (an unstaged file) and so is verified by hand.
- **The first channel has two spellings, and the composed one is the dangerous half.**
  A bill id beside the word `bills` is greppable per bill; a download root bound once
  and combined with a bill id hundreds of lines away (`_BILLS = _ROOT / "bills"`) is not,
  because the two never appear together. `scripts/build_similarity_labels.py` came
  through the move in exactly that shape and stopped resolving — caught in review of
  #345, not by the first version of the guard. Hence a second rule: outside
  `tests/corpus_paths.py` and the fetchers, no module spells the download root at all.
- **The judgement is per version, not per bill.** A bill-level allowlist cannot express
  a partly committed bill, so exempting `115-hr-244` (for its withheld amendment doc)
  silently exempted its committed enrolled text too. The guard derives the committed set
  from the tree instead of keeping a list, which removes both the drift and the hole.
- **Repository size is unchanged.** The files move; git already stores their blobs, and
  history keeps them at the old paths regardless. The size bar for future additions
  above still applies unchanged.
- **The `.gitignore` loses its ~80-rule re-admit list**, roughly a two-thirds cut, and
  stops growing with each fixture. (Deliberately not a line count: the file keeps
  changing for unrelated reasons, and a number here would be wrong within a release
  while still reading as measured.)
