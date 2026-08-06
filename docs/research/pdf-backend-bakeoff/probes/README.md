# Bake-off probes

Frozen reproduction artifacts for [`../RESULTS.md`](../RESULTS.md) and
[`../RED-TEAM.md`](../RED-TEAM.md). Not maintained source: they exist to reproduce those
documents' numbers. Excluded from lint by the `docs/research/**/probes` rule in
`pyproject.toml`.

**Production code is not modified by any of these.** The engine is imported from
`src/deltatrack` unchanged. Where the browser path needs `pypdfium2` importable under
WASM, a stub is written into the Pyodide filesystem that **raises** on any real PDFium
call, so a silent fallback to the incumbent is impossible rather than merely unlikely.

## Setup

The spike's dependencies are **not** in `pyproject.toml`, deliberately: they are
benchmark-only and three of them (PyMuPDF especially) should never reach the product's
dependency set. Install them into the worktree venv explicitly.

```bash
uv pip install --python .venv/bin/python -r docs/research/pdf-backend-bakeoff/probes/requirements.txt
```

```bash
cd docs/research/pdf-backend-bakeoff/probes/js && npm install
```

`node_modules/`, `package-lock.json` and the generated `egress-fixtures/` are gitignored;
the WASM runtimes are not committed, per the spec's "commit the builder, not the binary"
rule. Node 22 and a Playwright Chromium (`.venv/bin/python -m playwright install chromium`)
are assumed.

**Versions the published numbers were produced with** — record these when re-running,
because several results are version-sensitive:

| Component | Version |
|---|---|
| pypdfium2 (incumbent) | 5.12.1, bundling PDFium **152.0.7947.0** |
| `@embedpdf/pdfium` | 2.15.0, engine from the `embedpdf/runtime` fork @ `608d50ef` |
| pdfjs-dist | 6.2.108 |
| pdfminer.six / pypdf / PyMuPDF | 20260107 / 6.14.2 / 1.28.0 |
| pyodide | 314.0.3 (Python 3.14) |
| Playwright / Chromium | 1.60.0 |

All measurements are macOS 15 / arm64. **Nothing was run on Windows.**

## Reproducing each published number

Run from the repo root. Long runs write incrementally, so they can be inspected mid-flight.

| # | Command | Produces | Wall time |
|---|---|---|---|
| 0 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase0_speed.py 25` | pdfminer-vs-incumbent speed gate | ~1 min |
| 0 | `node docs/research/pdf-backend-bakeoff/probes/js/phase0_pdfjs.mjs tests/corpus/118-hr-4366/1_reported-in-house.pdf` | PDF.js whole-document + font-resolution cost | ~2 s |
| 1 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase1.py --out docs/research/pdf-backend-bakeoff/results/phase1.json --cross-check-lcs` | `phase1.json` (52 docs × 6 backends) | **~25 min** |
| 1 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/report_phase1.py --results docs/research/pdf-backend-bakeoff/results/phase1.json` | the Phase 1 tables | seconds |
| 2 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase2.py --out docs/research/pdf-backend-bakeoff/results/phase2.json` | `phase2.json` (15 pairs × 6 × 2 modes) | **~60 min** |
| 2 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/report_phase2.py --results docs/research/pdf-backend-bakeoff/results/phase2.json` | T4 / T2 / per-bill tables | seconds |
| 3 | `node docs/research/pdf-backend-bakeoff/probes/js/phase3_pyodide.mjs tests/corpus/118-hr-4366/1_reported-in-house.pdf --pages 20` | `phase3_pyodide.json`, browser-vs-native parity | ~1 min |
| 4 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_egress.py --out docs/research/pdf-backend-bakeoff/results/phase4.json` | `phase4.json`, the 4-part egress proof | ~2 min |
| 4 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_webrtc.py --out docs/research/pdf-backend-bakeoff/results/phase4_webrtc.json` | WebRTC mitigation matrix | ~1 min |
| 5 | `node docs/research/pdf-backend-bakeoff/probes/js/phase5_perf.mjs --pages 60` | `phase5_perf.json`, 60-page sample | ~5 min |
| 5 | `node docs/research/pdf-backend-bakeoff/probes/js/phase5_fulldoc.mjs` | `phase5_fulldoc.json` — **the gate-9 decision** | ~3 min |
| B | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_tierb.py --out docs/research/pdf-backend-bakeoff/results/tierb.json` | `tierb.json`, 12 non-corpus documents | ~10 min |
| — | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_results.py` | regenerates RESULTS.md's tables from raw JSON | seconds |

### Red-team probes

These back [`../RED-TEAM.md`](../RED-TEAM.md) and the audit section of `RESULTS.md`.

| Command | Produces |
|---|---|
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_ablation.py` | `redteam_ablation.json` — **the result that withdrew the headline**: 8 ablations × 6 backends on XML-referenced metrics only |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_unguarded.py` | `redteam_unguarded.json` — the 2 declined pairs scored anyway (the 15/15) |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_validate_amounts.py` | `redteam_amount_validation.json` — 43 amounts vs an independent extractor |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_egress2.py` | `redteam_egress2.json` — 19 further vectors; finds the two policy bypasses |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_csp_mitigation.py` | `redteam_csp_mitigation.json` — proves removing `'unsafe-inline'` closes Speculation Rules |

## Things that will bite a re-runner

- **Phase 1 and Phase 2 are the long poles** (~25 and ~60 min). Both write their JSON after
  every document/pair, so progress is inspectable and a killed run is not wasted.
- **Do not run a timing probe concurrently with anything else.** Phase 5's numbers were
  taken on an idle machine; running them alongside Phase 2 would silently inflate them.
- **`score_phase2.py` applies production's unnumbered-layout guard** and marks two pairs
  declined. That is deliberate — see the correction note in `RESULTS.md`. To see the
  unguarded numbers, use `redteam_unguarded.py`, not a modified `score_phase2.py`.
- **Egress probes bind 127.0.0.1:8973 over both TCP and UDP.** A stale `serve.py` from a
  killed run will make the next one look like it observed nothing.
- **The CSP mitigation probe deliberately includes a VOID variant** that runs zero vectors.
  That is not a bug: it demonstrates the false pass that an inline bootstrap produces under
  `script-src 'self'`, which is how the first version of this measurement went wrong.
- **Node backends stream JSONL over stdout.** A 1000-page bill is ~130 MB of JSON; the
  harness reads it page-by-page rather than buffering, and passes
  `--max-old-space-size=8192`.
- **`.venv/bin/python`, not `python`.** From a worktree, `uv sync` or `PYTHONPATH=$PWD/src`;
  never `uv pip install -e .`, which clobbers the shared venv.
