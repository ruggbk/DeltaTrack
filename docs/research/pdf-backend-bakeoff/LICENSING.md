# Phase 6: licensing and distribution memo

Recorded **separately from the technical score**, per the spec's instruction, so a
licensing conclusion can never be mistaken for a measurement and vice versa.

Every license below was read from the **installed artifact** (package metadata and the
bundled `LICENSE` files), not from documentation or memory. Versions are the ones the
bake-off actually ran.

> This is a project distribution-policy analysis, not legal advice. How licenses combine
> in a given distribution is a nuanced question this memo does not attempt to resolve.
> The operative project rule is the one the spec fixed before the bake-off ran:
> **DeltaTrack will not ship dependencies requiring AGPL compliance, absent a separate
> explicit licensing decision.**

## The artifacts as measured

| Component | Version | License (read from artifact) | Verified at |
|---|---|---|---|
| **DeltaTrack** | this tree | Apache-2.0 | `LICENSE` |
| **PDF.js** (`pdfjs-dist`) | 6.2.108 | Apache-2.0 | `package.json`, `LICENSE` |
| **PDFium-WASM** (`@embedpdf/pdfium`) | 2.15.0 | MIT (wrapper) | `package.json`, `LICENSE` |
| ⮑ bundled PDFium engine | — | BSD-3-Clause (PDFium Authors) | `LICENSE.pdfium` |
| **pdfminer.six** | 20260107 | MIT | package metadata |
| **pypdf** | 6.14.2 | BSD-3-Clause | package metadata |
| **pypdfium2** (incumbent) | 5.12.1 | BSD-3-Clause, Apache-2.0 | package metadata |
| **PyMuPDF** | 1.28.0 | *"Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"* | package metadata |

## What this means for distributing a WASM binary

The question the spec asks is specifically about **distribution**, because a client-side
tool triggers distribution obligations even where it triggers no network-service ones.

**The permissive candidates (PDF.js, PDFium-WASM, pdfminer.six, pypdf) are all
compatible with shipping inside an Apache-2.0 project**, and all four impose the same
shape of obligation: retain the copyright notice and license text in the distributed
artifact. For a single-file HTML build that means the license texts must be embedded in
the bundle (a comment block or an about panel), not merely present in the source repo.
That is a build-step requirement, and it is cheap, but it is a real one and a single-file
artifact makes it easy to forget.

Two specifics worth naming rather than glossing:

- **PDFium-WASM is two licenses, not one.** The `@embedpdf` wrapper is MIT; the engine
  inside the `.wasm` is BSD-3-Clause from the PDFium Authors. Both notices travel with
  the binary. The shipped package carries them as separate files, which is the correct
  signal that both apply.
- **PDFium vendors third-party code** (font, image and compression libraries) that this
  memo did not enumerate, because the bundled `LICENSE.pdfium` covers only PDFium itself.
  Before shipping a PDFium-WASM build, that transitive set needs an actual audit. Flagged
  as an **open item**, not cleared. The incumbent `pypdfium2` already carries the same
  question and its metadata hints at it ("dependency licenses"), so this is a
  pre-existing obligation being inherited rather than a new one being taken on.

### PyMuPDF, and why it never enters the decision tree

PyMuPDF's own metadata states the dual license outright. Under the project rule it is a
**ceiling reference only**, and its score in the results must not be read as a
recommendation.

On the AGPL §13 question the spec raises: a purely client-side tool that a staffer runs
locally arguably does not engage the network-interaction clause at all, since there is no
remote user interacting with it over a network. **But that argument is irrelevant to this
decision**, because §13 is not the binding constraint — **distribution** is. Shipping the
WASM binary to a congressional office is conveying the work, and the AGPL's source-
provision obligations attach to conveyance regardless of §13. Reaching for the §13
argument would be answering a question nobody asked.

The obligation would also **pass downstream to BillTrax** (ADR 0005), which is the more
consequential half: a licensing choice made here for DeltaTrack's convenience becomes a
constraint on a separate product's distribution. That is exactly the kind of decision
that should be made deliberately by the maintainer rather than absorbed as a side effect
of a backend choice.

Revisiting stays possible and stays cheap to state: an explicit licensing decision, or a
commercial license from Artifex. Neither is in scope here.

## The number that prices a PDFium-WASM effort

The spec's main reason for running PyMuPDF at all is to price the gap between the best
achievable score and the best *shippable* one. **The measured gap is essentially zero**,
and that is the finding: see [`RESULTS.md`](RESULTS.md) for the figures. PyMuPDF does not
outperform the permissive candidates on this corpus by a margin that would justify an
AGPL-compliance obligation or a commercial-license purchase.

That result also dissolves the question the spec expected to be hardest. It had assumed a
PDFium-WASM effort might need funding and that PyMuPDF's score would tell us what it was
worth. In fact a credible PDFium-WASM build **already exists, is MIT/BSD-3, and already
exposes the FFI the engine needs** — so there is no engineering effort to price.

## Recommendation

**On licensing grounds alone, three of the four permissive candidates are shippable
today**, and the choice between them should be made on the technical results rather than
on license risk. PyMuPDF is excluded by project policy, not by any measured deficiency.

Two build-time obligations to carry into whichever is chosen:

1. Embed the required notices **in the distributed artifact**, not just the repo.
2. Audit PDFium's vendored third-party licenses **before** shipping a PDFium-WASM build.
