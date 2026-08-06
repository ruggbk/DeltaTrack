# Results: confirmatory run

- Protocol: [`PRE-REGISTRATION-CONFIRMATORY.md`](PRE-REGISTRATION-CONFIRMATORY.md), frozen
  and amended **before execution**, commits `be07b71` and `37f6be8`.
- Harness corrections made before any score existed:
  [`results/HARNESS-VALIDATION.md`](results/HARNESS-VALIDATION.md).
  Deviations after the first score: [`results/DEVIATIONS.md`](results/DEVIATIONS.md).
- **This does not replace [`RESULTS.md`](RESULTS.md)**, which remains the record of the
  exploratory spike and its audit. Where this run contradicts it, both stand and the
  contradiction is named.

> **Every number here is macOS 15 / arm64.** Nothing was run on Windows, which is the
> platform the target user is on. Engine properties carry over; OS and security-stack
> properties do not.

> **A, B and C use different references and license different conclusions. They are never
> combined into a score, a table, or a verdict.** Substituting an A result for a B
> conclusion is what produced the withdrawn headline in the exploratory run.

---

# Concern A — production migration parity

**Question.** If we replace pypdfium2, does any output production currently returns to
users change? **Reference: today's native pypdfium2.** This section cannot support an
accuracy conclusion.

## A.1 Replication corpus (P1, 15 pairs)

<!-- A_P1 -->
<!-- /A_P1 -->

## A.2 Holdout (P2)

<!-- A_P2 -->
<!-- /A_P2 -->

---

# Concern B — independent document accuracy

**No metric here takes a PDFium-derived value as ground truth.** Primary mode is `strict`.
Replication and holdout are reported separately and never pooled.

## B.1 Replication corpus (P1) — controls

<!-- B_P1_B0 -->
<!-- /B_P1_B0 -->

## B.2 Replication corpus (P1) — paired cluster bootstrap

<!-- B_P1_DELTA -->
<!-- /B_P1_DELTA -->

## B.3 Holdout (P2) — controls

<!-- B_P2_B0 -->
<!-- /B_P2_B0 -->

## B.4 Holdout (P2) — paired cluster bootstrap

<!-- B_P2_DELTA -->
<!-- /B_P2_DELTA -->

---

# Concern C — security / egress

Two claims, kept apart because they support different sentences:

| Test | Claim it supports |
|---|---|
| Browser policy | "our app does not transmit through these mechanisms" |
| Environment isolation | "the process cannot reach the network at all" |

**Threat model.** This establishes strong controls for *Threat A* — DeltaTrack accidentally
or deliberately including ordinary application networking. It does **not** establish
anything about *Threat B*, arbitrary code executing in the browser: the two mechanisms
below that sit outside CSP are a standing demonstration that no page-level policy makes
exfiltration impossible.

## C.1 Per-vector egress under the corrected policy

<!-- C_EGRESS -->

Policy under test: `default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'`

Of **35 frozen mechanisms**, 29 transmitted in the no-policy control and are eligible for scoring. **27 blocked**, **0 bypass the policy**, **2 are outside what CSP governs** (webrtc, windowopen). 6 never transmitted in the control and are not scored (sw, track, svguse, link-dns-prefetch, link-preconnect, webtransport).

| vector | control | policy result |
|---|---|---|
| `fetch` | CONTROL TRANSMITTED | blocked |
| `xhr` | CONTROL TRANSMITTED | blocked |
| `beacon` | CONTROL TRANSMITTED | blocked |
| `img` | CONTROL TRANSMITTED | blocked |
| `script` | CONTROL TRANSMITTED | blocked |
| `css` | CONTROL TRANSMITTED | blocked |
| `cssimport` | CONTROL TRANSMITTED | blocked |
| `webfont` | CONTROL TRANSMITTED | blocked |
| `eventsource` | CONTROL TRANSMITTED | blocked |
| `iframe` | CONTROL TRANSMITTED | blocked |
| `dynimport` | CONTROL TRANSMITTED | blocked |
| `form` | CONTROL TRANSMITTED | blocked |
| `sw` | CONTROL UNSUPPORTED / VOID | not scored |
| `workerfetch` | CONTROL TRANSMITTED | blocked |
| `ws` | CONTROL TRANSMITTED | blocked |
| `webrtc` | CONTROL TRANSMITTED | outside CSP |
| `ping` | CONTROL TRANSMITTED | blocked |
| `speculation` | CONTROL TRANSMITTED | blocked |
| `object` | CONTROL TRANSMITTED | blocked |
| `embed` | CONTROL TRANSMITTED | blocked |
| `video` | CONTROL TRANSMITTED | blocked |
| `track` | CONTROL UNSUPPORTED / VOID | not scored |
| `svgimage` | CONTROL TRANSMITTED | blocked |
| `svguse` | CONTROL UNSUPPORTED / VOID | not scored |
| `cssbg` | CONTROL TRANSMITTED | blocked |
| `keepalive` | CONTROL TRANSMITTED | blocked |
| `importscripts` | CONTROL TRANSMITTED | blocked |
| `srcdoc` | CONTROL TRANSMITTED | blocked |
| `windowopen` | CONTROL TRANSMITTED | outside CSP |
| `metarefresh` | CONTROL TRANSMITTED | blocked |
| `link-prefetch` | CONTROL TRANSMITTED | blocked |
| `link-preload` | CONTROL TRANSMITTED | blocked |
| `link-dns-prefetch` | CONTROL UNSUPPORTED / VOID | not scored |
| `link-preconnect` | CONTROL UNSUPPORTED / VOID | not scored |
| `webtransport` | CONTROL UNSUPPORTED / VOID | not scored |

| validity condition | holds |
|---|---|
| 1_per_vector_control_assigned | yes |
| 2_known_bad_caught | yes |
| 3_all_cases_completed | yes |
| 3b_vector_count_matches | yes |
| 4_network_layer_observation | yes |

<!-- /C_EGRESS -->

**The per-vector control status is the change that matters.** Six mechanisms never
transmitted even with no policy at all. Under the exploratory rule — "the control must leak
on ≥ 12 of 35" — every one of them would have been credited as *blocked by policy*. They
are now recorded as unsupported and score nothing in either direction.

**A false negative this harness produced, and how it was caught.** The first run of this
probe scored WebRTC as **blocked** while six STUN binding requests sat in the policy run's
own log: `serve.py` labels a datagram `[stun]` when it carries the STUN magic cookie and
`[udp]` otherwise, and the detector matched only `[udp]`. That would have published "WebRTC
is closed" and silently contradicted a correct exploratory finding. It was caught because
the two runs disagreed and the disagreement was treated as the finding rather than
explained away — the comforting reading was the wrong one.

## C.2 Environment-level isolation

<!-- C_ISOLATION -->

| check | result |
|---|---|
| observer_liveness (unsandboxed beacon ARRIVED) | **PASS** |
| known_bad_inside_sandbox (beacon did NOT arrive) | **PASS** |
| external_host_unresolvable_inside_sandbox | **PASS** |
| comparison_succeeded_with_network_denied | **PASS** |
| output_identical_to_unsandboxed | **PASS** |

Verdict: **PASS**. Linux container: NOT RUN -- docker daemon unavailable at execution time.

<!-- /C_ISOLATION -->

Both controls ran in the same window, and neither alone would have been sufficient: the
known-bad beacon inside the sandbox is what attributes the silence to the sandbox, and the
unsandboxed liveness beacon is what distinguishes a working sandbox from a dead listener.

---

# Concern D — performance

<!-- D_PERF -->
<!-- /D_PERF -->

---

# Concern E — bundle size and architecture

The axis the exploratory audit identified as unmeasured and most likely to decide the
question. Its stated expectation was that **"pdfminer adds no binary at all, which is the
axis on which it could still win despite being ~8× slower."**

<!-- E_BUNDLE -->

Unit: over-the-wire bytes: gzip for raw wasm/js, published wheel size for wheels (already ZIP).

Shared Pyodide + DeltaTrack baseline: **6.43 MB** over the wire (13.84 MB raw).

| artifact | incremental backend cost | full artifact |
|---|---|---|
| pdfium-wasm | **2.19 MB** | 8.62 MB |
| pdfminer (core only) | **6.66 MB** | 13.08 MB |
| pdfminer (as micropip resolves it, with cryptography) | **9.05 MB** | 15.48 MB |

`pdfminer (core only)` is **3.03×** PDFium-WASM's incremental cost.

`pdfminer (as micropip resolves it, with cryptography)` is **4.13×** PDFium-WASM's incremental cost.

<!-- /E_BUNDLE -->

**That expectation is measured and false.** pdfminer.six's published wheel is 6.59 MB
because it bundles CJK CMap resources, and micropip resolves a further 2.20 MB wasm
`cryptography` wheel. PDFium-WASM's 4.63 MB binary gzips to 2.13 MB. The axis the audit
thought might rescue pdfminer runs the other way, and it is not close.

**What this does not measure:** a built single-file artifact, first/repeat load, Pyodide
init, comparison latency, peak memory, or the JS↔Python transfer volume. No bundler exists
to build that artifact, and writing one here would have measured the bundler.

---

# Concern F — `@embedpdf/pdfium` release readiness

Full memo: [`RELEASE-READINESS.md`](RELEASE-READINESS.md). It can gate adoption and cannot
rank a backend.

Verdict against the pre-committed requirement: **the vendoring branch is satisfiable today;
the reproduction branch is not.** npm publishes no `gitHead` for the version we ran and the
declared source path has moved, so there is no published mapping from tarball to source
commit. Vendored third-party in the shipped `.wasm` is zlib, libpng, OpenJPEG and FreeType.

---

# What this run did not settle

<!-- NOT_SETTLED -->
<!-- /NOT_SETTLED -->
