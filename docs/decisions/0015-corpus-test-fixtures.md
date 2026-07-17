# 15. Commit a curated corpus fixture set and collect the gates from a manifest

- Status: Accepted
- Date: 2026-07-17

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
design," and `AGENTS.md` records the intended path as *CI fetches* a curated corpus
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
  env var is subsumed by the CI completeness floor.
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
