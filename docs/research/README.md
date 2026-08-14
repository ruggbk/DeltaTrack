# Research directories

Studies that investigated a question about the engine, one directory each.

## Retention policy

Research artifacts are working material, not automatically permanent repository material. At
closure, retain only artifacts needed to reproduce a consequential result, enforce an invariant,
document a durable decision, or serve as a frozen input. Git history preserves the investigative
record.

In practice:

- **Generated outputs are not committed by default.** Probe results, censuses and sweeps are
  regenerable; gitignore them. A result that becomes a genuinely frozen input or oracle is the
  explicit exception — `git add -f` it, and say in the retaining document why it is frozen.
- **Permanent regression behaviour belongs in `tests/`.** A probe that has become a thing which
  must keep being true is a test, not a probe; move it and delete the probe.
- **Condense a study when it closes.** A chronological diary is what git history is for. What
  survives is the design it explains and the questions it left open.
- **A probe survives only if it reproduces a consequential result that no permanent test owns.**
  Usually that means an *unresolved* finding. Once a question is settled and gated, its probe is
  history.
- **Do not keep a file because it was useful during the investigation.** That is the whole point
  of the rule, and the case where it is hardest to apply.

The corollary worth stating: deleting a probe does not delete the evidence. Both stay in history,
addressable by the commit that added them, and the closing document should say so.

Each directory's own README states its question and status. No index here, deliberately: a
hand-maintained list of directories and statuses goes stale the moment a study closes, and `ls`
already answers the first half.

[`pdf-matching-convergence/`](pdf-matching-convergence/README.md) is the worked example of a
closed study: three probes retained because they reproduce a finding no test owns, everything
else removed from HEAD, and one document each for the settled design and the open question.
