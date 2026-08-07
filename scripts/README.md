# Developer scripts

Maintenance and investigation tooling, not part of the product CLI (for that, see the
[Command reference](../README.md#command-reference)). These are run by contributors, not
end users. Unless noted, run them with `uv run python scripts/<name>.py` from the project
root.

## Validation and accuracy

| Script | What it does |
|--------|--------------|
| `build_validation.py` | Build `tests/data/validation_<slug>.json` for each committee-report jurisdiction (the ground-truth fixtures). `--fetch` downloads the upstream sources first; passing slugs (e.g. `cjs`) restricts the rebuild to those jurisdictions. |
| `generate_validation_report.py` | Generate `docs/parser-validation.md`, the team-facing parser-accuracy report, from those fixtures. |
| `fetch_test_assets.py` | Re-fetch a bill-print PDF the slow suite needs that `tools/fetch_bills.py` cannot produce (it defaults to XML). Every asset it lists is committed, so this is a provenance record plus a way to restore one you deleted, not a setup step. Committee-report PDFs are **not** fetched here — the ones the gates read are committed fixtures ([ADR 0015](../docs/decisions/0015-corpus-test-fixtures.md)). |
| `compare_differs.py <a> <b>` | Compare DeltaTrack against off-the-shelf differs on the same bill pair (evidence for [ADR 0001](../docs/decisions/0001-structured-money-diff.md)). |
| `probe_observation_identity.py [root]` | Measure which node fields can serve as an address: duplicated body texts, duplicated `match_path`s, and empty or duplicated `element_id`s. Read-only; the evidence behind [ADR 0019](../docs/decisions/0019-observation-identity.md). Defaults to the committed `tests/corpus`, so it needs no downloads. Needs `PYTHONPATH=src`. |

### Refreshing the validation evidence

[docs/parser-validation.md](../docs/parser-validation.md) is the home for *why* this
validation is shaped the way it is. This is *what to run* to refresh it, in order.
Every step runs from the project root.

```sh
# 1. Fetch the upstream govinfo sources and rebuild the ground-truth fixtures.
#    Optional slugs restrict it to those jurisdictions (default: all).
uv run python scripts/build_validation.py --fetch        # -> wrote <absolute path>/tests/data/validation_<slug>.json (N accounts)

# 2. Regenerate the team-facing report from those fixtures.
uv run python scripts/generate_validation_report.py      # -> wrote docs/parser-validation.md (val/tot recalled, N%); skipped: none

# 3. Verify with the gate that actually reads this evidence.
uv run pytest -m slow tests/test_committee_report.py tests/test_validate_extraction.py
```

Things worth knowing before running any of it:

- **Run steps 1 and 2 together, or neither.** Step 1 without step 2 leaves the published
  figures in `docs/parser-validation.md` describing the previous fixtures.
- **These scripts write into the repository.** `build_validation.py` overwrites the
  committed fixtures under `tests/data/`; `generate_validation_report.py` overwrites the
  committed `docs/parser-validation.md`. Review `git diff` before committing; a
  legitimately changed account count needs its `min_accounts` floor refreshed in
  [tests/validation_sources.py](../tests/validation_sources.py) (the field comment there
  explains the floor).
- **`fetch_test_assets.py` is not part of this loop.** It restores committed bill-print
  PDFs you deleted locally and records their provenance; it touches neither the
  validation fixtures nor the report.
- **Step 1 currently produces a nine-fixture diff you should not commit.** Six
  committee-report fixtures have drifted from their sources and are never rebuilt
  from them ([#293](https://github.com/AgoraDMV/DeltaTrack/issues/293)); on the
  current tree the rebuild regenerates `match_path` values as `null`, quietly
  dropping those accounts to the agency-scoped fallback. Committing that diff
  degrades the ground truth while looking like a refresh.
- **Adding a jurisdiction** is documented in
  [tests/validation_sources.py](../tests/validation_sources.py) — follow it, then run
  this loop.

The commands run unattended; the `git diff` review before committing is the part that
waits on a person.

## Committee report pairing

Which committee report explains a given bill version, recorded per version in
[tests/corpus_manifest.toml](../tests/corpus_manifest.toml) as `committee_report`
(DeltaTrack#295).

| Script | What it does |
|--------|--------------|
| `report_pairing.py` | Not a runnable script — the shared pairing rules both of the others import. Defines a stage's authoring chamber, where it sits in the bill's life, and which reports are conference reports. Change a rule here, then re-run the updater. |
| `update_manifest_with_reports.py [--refresh]` | Rewrite the manifest's `committee_report` entries. Default is offline: re-applies the pairing rules to the report sources already recorded. `--refresh` re-fetches BILLSTATUS and re-confirms each package and granule against govinfo. Edits via tomlkit so the manifest's documentation comments survive. |
| `vendor_reports.py` | Download the committed report HTML fixtures named by the manifest, and re-validate the ones already present. Rejects govinfo's error page, which it serves as HTTP 200 for an unknown package. |

Which report explains a version turns on three things: the chamber that **authored**
that text, **when** the text exists, and which **lineage** it belongs to.

- A committee report is filed at the reported stage, so it explains text from there
  on, never the introduced text it recommends changing.
- It propagates forward only through its own lineage: the reported text, the
  engrossment derived from it, and transit to the other chamber (which amends
  nothing). Once the other chamber amends, the lineage ends — and it does not
  resume when the first chamber later amends *that*. Such a version gets no report
  unless one explaining it is recorded deliberately.
- A conference report explains only the enrolled result.

The lineage rule is what stops an unrelated report re-attaching to a repurposed
shell bill. Four corpus bills are that shape: an omnibus carried by a House
amendment onto a reported bill about something else entirely (H. Rept. 118-364
accompanies the Udall Foundation Reauthorization Act; the House amendment to
H.R. 2882 is the Further Consolidated Appropriations Act, 2024).

The round is read from the stage NAME, not by counting authoring runs over the
manifest's versions: the manifest holds committed fixtures, not every version a bill
had. 113-hr-83 commits only its House amendment, which a run-count would read as
that chamber's first text when it is its second.

A report is published either as one undivided document or as a package holding one
granule per book, which is how `H. Rept. 119-106` Books 1 and 2 are separately
addressable:

```
pkg     = "CRPT-119hrpt106"        # parent package
granule = "CRPT-119hrpt106-pt1"    # Book 1; -pt2 is Book 2
```

Granules are addressed inside the parent's path
(`/content/pkg/CRPT-119hrpt106/html/CRPT-119hrpt106-pt1.htm`); there is no standalone
`CRPT-119hrpt106-pt1` package. Fixtures are named after the granule when there is one,
so each book is its own committed file.

A report govinfo publishes no text for is recorded as `text_available = false` with a
reason and **no** `pkg`, and must have no fixture — `tests/test_manifest_report_fixtures.py`
asserts both directions, so the exception cannot outlive its reason. Nothing is
predicted: a package or granule is recorded only after govinfo is asked and answers.

## PDF / rendering

| Script | What it does |
|--------|--------------|
| `serve_compare.py <bill> [--v1 V --v2 V] [--port N] [--no-browser]` | Render a bill's PDF-derived and XML-derived diffs side by side and serve them locally — the main PDF↔XML parity debugging aid. |
| `heading_precision.py` | Measure PDF heading-anchor recovery against the XML hierarchy (DeltaTrack#89). |
| `parity_table.py` | Print the PDF↔XML change-parity table for the four evidence bills — the snapshot [ADR 0014](../docs/decisions/0014-leveled-heading-tree-scope.md) records. Reporting only; `tests/test_pipeline_parity.py` is the gate that asserts the bands. |
| `ugly_money_table.py <old.xml> <new.xml> -o <out>` | Emit a deliberately unstyled money-diff table for staffer validation (fidelity stripped so only the money diff is under test). |
| `render_examples.py` | Regenerate the committed example HTML diffs and landing page under `examples/`. The only renderer of the published examples; CI deploys what it wrote, and `tests/test_committed_examples.py` fails if they're stale. |

## Similarity-threshold audit prototypes

One-off prototypes from the similarity-function investigation; kept for reproducibility.

| Script | What it does |
|--------|--------------|
| `p1_similarity_fixtures.py` | P.1 — synthetic stress fixtures for the similarity function. |
| `p2_catalog_survey.py` | P.2 — real-bill cliff survey. Requires BillTrax data (MySQL/container). |
| `p3_prototypes.py` | P.3 — alternative similarity-function prototypes (normalize / Levenshtein / Jaccard). |

## Smoke test

| Script | What it does |
|--------|--------------|
| `../tests/smoke_test_matching.py` | Division-aware matching on fresh bills outside the dev corpus; a manual sanity check, not part of the pytest suite. |
