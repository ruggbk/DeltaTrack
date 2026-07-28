# 16. Separate the product, the acquisition tooling, and the delivery channel in the layout

- Status: Accepted
- Date: 2026-07-28

## Context

About 2,600 lines of this repo's Python was bill acquisition, not the diff engine, and
nothing in the layout or the packaging said so. Four fetch scripts, `bill_index/`, and the
`shared/` helpers only they used sat beside `bill_tree.py`, `diff_bill.py`, and
`diff_pdf.py` at the repo root, so a newcomer could not tell the product from the tooling
and the repo read as larger and less focused than the tool it ships.

Packaging carried the same fusion. `[project.dependencies]` listed `fastapi`, `uvicorn`,
`python-multipart`, and `slowapi` alongside the engine's own requirement, so anyone
installing DeltaTrack to compare two bill versions installed a web server. Of the seven
core dependencies, exactly one — `pypdfium2` — was the engine's.

The layout also worked against [ADR 0005](0005-deltatrack-billtrax-boundary.md), which
puts automated input gathering on BillTrax's side of the line. The acquisition tooling sat
in the product tree, blurring the boundary that record exists to protect.

Two facts made the split cheaper than it looked. The fetch cluster is **closed**: it
imports only itself, and no product module imports any of it. And of the three modules
under `server/`, only `app.py` used FastAPI — `pdf_compare.py` and `xml_compare.py` are the
in-memory "two versions in, HTML out" pipeline, which the `diff_bill.py` and `diff_pdf.py`
CLIs both reached into for their own HTML output.

## Decision

We will separate the three surfaces by directory and by dependency group, **inside this
repository**:

- **The product** stays at the repo root: the engine modules, `parsers/`, `formatters/`,
  and `compare/` — the last extracted from `server/`, where it was misfiled.
- **`tools/`** holds bill acquisition: the fetch scripts, `bill_index/`, and `shared/`.
- **`web/`** holds the delivery channel: the FastAPI app and the static front-end.
- **`[project.dependencies]`** is reduced to `pypdfium2`. The web and fetch stacks become
  `web` and `fetch` dependency groups.

`tools/` is a second import root rather than a package, listed in pytest's `pythonpath` and
ruff's `src`. The fetch scripts are run directly (`./tools/fetch_bills.py`), which puts only
their own directory on `sys.path`, so they must resolve each other by bare name; making
`tools/` a package would have forced `python -m tools.fetch_bills` on every documented
command for no gain. The cost is that both roots share one flat module namespace, so a
`tools/x.py` may not be added beside a root `x.py` — a test enforces this.

Groups rather than extras, and all three install by default. The separation that matters is
what a *consumer* of the engine gets, which is `[project.dependencies]`; groups are
development-time only and never published. Making `web` opt-in was rejected as worse than
doing nothing: two test modules guard their imports with `pytest.importorskip("fastapi")`,
so a default sync without it would convert them into silent skips — the fail-open pattern
[#288](https://github.com/AgoraDMV/DeltaTrack/issues/288) exists to close.

Alternatives considered and rejected for now:

- **Moving the engine into a `deltatrack/` package.** The orthodox layout, and wanted — but
  it changes every documented command and roughly eighty test files, which would have
  buried this diff. Deferred to its own issue; nothing here blocks it.
- **Moving `server/` out as one unit.** Would have left the product CLIs importing across
  the very boundary being drawn. Splitting it instead removed two reach-arounds that
  [#62](https://github.com/AgoraDMV/DeltaTrack/issues/62) tracks.
- **Moving the tooling to a separate repository or to BillTrax.** Still an open question.
  This split deliberately does not foreclose it.

## Consequences

The engine installs with one dependency instead of seven, and the layout now states which
code is the product. Two product-to-web reach-arounds are gone. `scripts/` and
`docs/research/` are untouched, and `shared/` now holds only tooling.

Costs and new constraints:

- **Documented commands changed.** `./fetch_bills.py …` is now `./tools/fetch_bills.py …`.
  Anything outside this repo that invoked the old paths breaks.
- **The deployed site needs a matching change.** It launches `uvicorn server.app:app`,
  which is now `web.app:app`. That command lives on the host, not in this repo, so the
  repository and the deployment must be updated together.
- **The flat two-root namespace is a standing constraint**, not a one-off. It is why
  duplicate command names are now a test failure.
- **Earlier records keep their original paths.** ADRs are append-only, so
  [0004](0004-govinfo-bulk-data.md) and [0013](0013-bill-storage-and-version-identity.md)
  still name `fetch_bills.py`, `fetch_govinfo.py`, and `shared/version_stems.py` at their
  old locations. They now live at `tools/fetch_bills.py`, `tools/fetch_govinfo.py`, and
  `version_stems.py`.
- **Nothing enforces the boundary except a test.** `tools/` being on the import path means
  a product module *could* import the tooling and every other gate would stay green, so
  `tests/test_surface_boundary.py` asserts the direction directly and derives its forbidden
  roster from the trees rather than a hardcoded list.

References: [#367](https://github.com/AgoraDMV/DeltaTrack/issues/367),
[ADR 0005](0005-deltatrack-billtrax-boundary.md),
[ADR 0011](0011-local-only-processing.md),
[#62](https://github.com/AgoraDMV/DeltaTrack/issues/62),
[#112](https://github.com/AgoraDMV/DeltaTrack/issues/112).
