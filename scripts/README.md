# Developer scripts

Maintenance and investigation tooling, not part of the product CLI (for that, see the
[Command reference](../README.md#command-reference)). These are run by contributors, not
end users. Unless noted, run them with `uv run python scripts/<name>.py` from the project
root.

## Validation and accuracy

| Script | What it does |
|--------|--------------|
| `build_validation.py` | Build `test_data/validation_<slug>.json` for each committee-report jurisdiction (the ground-truth fixtures). `--fetch` downloads the upstream sources first. |
| `generate_validation_report.py` | Generate `docs/parser-validation.md`, the team-facing parser-accuracy report, from those fixtures. |
| `fetch_test_assets.py` | Re-fetch a bill-print PDF the slow suite needs that `tools/fetch_bills.py` cannot produce (it defaults to XML). Every asset it lists is committed, so this is a provenance record plus a way to restore one you deleted, not a setup step. Committee-report PDFs are **not** fetched here — the ones the gates read are committed fixtures ([ADR 0015](../docs/decisions/0015-corpus-test-fixtures.md)). |
| `compare_differs.py <a> <b>` | Compare DeltaTrack against off-the-shelf differs on the same bill pair (evidence for [ADR 0001](../docs/decisions/0001-structured-money-diff.md)). |

## PDF / rendering

| Script | What it does |
|--------|--------------|
| `serve_compare.py <bill> [--v1 V --v2 V] [--port N] [--no-browser]` | Render a bill's PDF-derived and XML-derived diffs side by side and serve them locally — the main PDF↔XML parity debugging aid. |
| `heading_precision.py` | Measure PDF heading-anchor recovery against the XML hierarchy (DeltaTrack#89). |
| `parity_table.py` | Print the PDF↔XML change-parity table for the four evidence bills — the snapshot [ADR 0014](../docs/decisions/0014-leveled-heading-tree-scope.md) records. Reporting only; `tests/test_pipeline_parity.py` is the gate that asserts the bands. |
| `ugly_money_table.py <old.xml> <new.xml> -o <out>` | Emit a deliberately unstyled money-diff table for staffer validation (fidelity stripped so only the money diff is under test). |
| `../render_examples.py` | Regenerate the committed example HTML diffs and landing page under `examples/`. The only renderer of the published examples; CI deploys what it wrote, and `tests/test_committed_examples.py` fails if they're stale. |

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
