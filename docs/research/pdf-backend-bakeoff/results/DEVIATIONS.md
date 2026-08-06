# Deviations from the frozen confirmatory protocol

Rows are appended when the change happens, never reconstructed afterwards. Pre-scoring
harness corrections are not deviations and live in
[`HARNESS-VALIDATION.md`](HARNESS-VALIDATION.md).

| Change | When | Results already visible? | Reason | Could move |
|---|---|---|---|---|
| **P3a's required real conference report was not obtained.** The protocol froze P3a as "the existing 12, plus one real conference report (`CRPT-*`) and one real committee print (`CPRT-*`), both required". The committee print was obtained (`CPRT-119HPRT63305`, a full-committee markup — closer to the chair's-mark class than expected). No conference report was found. | After A, B, C, E, F results were visible; before P3 was scored | **Yes** — A/B/C/E/F were complete | 800 `CRPT` records from 2015 onward were checked through the govinfo API and **none** carries "conference report" or "conference committee" in its title. Modern practice resolves differences by amendments between the houses rather than by conference, so the class is close to extinct in the period the corpus covers. | Nothing in A, B, C, D, E or F. P3 is a robustness and safe-failure probe only and produces no ranking. The unvalidated-source-class list gains "conference-report layouts" permanently rather than provisionally. |
