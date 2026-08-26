# 5. Keep DeltaTrack a contained two-version tool; support other tools beyond this scope

- Status: Accepted
- Date: 2026-06-27
- Revised: 2026-08-26 — the safety contract is about bill *content*, not all state.

## Context

Two kinds of work share this problem space. DeltaTrack compares two versions of a
bill. Other tools analyze bills and their diffs. The two are easy to confuse, and
that confusion produces a recurring question: where does a given feature belong?
The pressure usually arrives as "let's also support more than two versions," "let's
track a bill across its whole lifecycle," or "let's add storage so the user doesn't
redo work each time."

DeltaTrack's audience is congressional staffers working under strict IT rules, often
offline. For that audience, one property of the tool does a lot of quiet work: it
runs locally, leaves no bill text behind, and is self-contained. "This tool touches
nothing and is safe to run" is not a nicety; it is part of why a staffer can use it
at all.

Without an explicit boundary, every new request gets relitigated from scratch, and
each "just add storage" suggestion quietly erodes that property. This record draws
the line and says why.

## Decision

DeltaTrack is the ephemeral, local tool that compares **two** versions of a bill.
Its principles are simplicity, accuracy, speed, offline operation, and a safety
contract: **no bill content accumulates on the user's machine.** No cache of
extracted text, no index of prior comparisons, no temporary copy the user did not
ask for. The user supplies the two versions; the tool writes its report where the
user directs it and retains nothing of what it read.

Program state and user preferences are not bill content, and are permitted. Which
version of DeltaTrack is installed, or that a user prefers a money-only view,
carries no bill text and threatens nothing this contract protects. The contract is
about content, not about memory in general.

Everything that spans more than a single two-version comparison sits outside this
scope: multi-version and full-lifecycle tracking, comparison over time, and trends
across many bills. Those consumers read DeltaTrack's canonical JSON
([0006](0006-canonical-diff-contract.md)) and build on it. DeltaTrack also serves as
a diff engine for them, but that is a by-product of being a clean, trustworthy
engine, not its main purpose. DeltaTrack stands on its own as a staffer tool first.

The test for where a feature belongs is not processing power. It is whether the
feature needs **persistent bill content or comparison history, or automated input
gathering**. If it does, it is outside DeltaTrack's scope. Three reasons hold the
line, in order of weight:

1. **The safety contract.** Bill text that never accumulates is a security property
   the staffer audience relies on. Adding a content cache or a store of prior
   comparisons breaks it, and a DeltaTrack that breaks it is no longer DeltaTrack.
2. **Input burden.** Because the tool holds no bill content, the user supplies the
   inputs each session. Two versions is reasonable to ask for; five versions, or a
   bill's full lifecycle, forces the user to gather and manage every version and
   every pairwise comparison by hand. Removing that burden requires the storage and
   automation DeltaTrack deliberately lacks.
3. **Focus.** Speed and accuracy on the two-version case are easier to guarantee in
   a tool that does only that.

Bill acquisition falls on the far side of the same line even though the tooling
ships in this repository: `tools/` writes public bill versions to disk by design,
and [0016](0016-product-tooling-surface-split.md) places it outside the product
surface. The safety contract binds the product.

Alternatives:

- **Store bill content and prior comparisons so users do not redo work each
  session.** Rejected: it breaks the safety contract above, which is the core reason
  the staffer audience can run the tool. The need it addresses is real, but it
  belongs to a tool built to hold content.
- **Fold the comparison tool and the analysis tool into one product.** Rejected as a
  scope decision: a tool that holds no bill content and a platform built on stored
  content have incompatible core contracts, so one set of responsibilities cannot be
  both. (Whether the two are ever *packaged* together — for example as layers in one
  codebase — is a separate, still-open question. Even layered, the DeltaTrack layer
  keeps this contract.)

## Consequences

- Every "where does this go?" question has a default answer: if it needs persistent
  bill content, comparison history, or automated input gathering, it is outside
  DeltaTrack. Settled questions stop being reopened per feature.
- DeltaTrack's offline, self-contained design (and the self-contained HTML report and
  canonical-JSON handoff in [0006](0006-canonical-diff-contract.md)) is justified
  rather than incidental — it is the safety contract expressed in the architecture.
- The accepted cost: the user supplies both versions every session, because **the
  tool keeps no bill text between runs.** That repetition is the price of the safety
  contract, not a defect to fix by adding a content store. Reducing it by remembering
  the user's *settings* is fair game; reducing it by remembering their *documents* is
  not.
- N-way comparison, which the schema notes as a possible v2.0 change, is unlikely to
  be DeltaTrack's job; cross-version work points outside this scope. This record does
  not decide the format question, only where the responsibility sits.
- The scope is not frozen forever. DeltaTrack may expand, but only on demonstrated
  user demand, and never into territory that requires persistent bill content or
  otherwise breaks the safety contract. That demand, not internal convenience, is the
  trigger to revisit.
- Stated for users as Product Principle 5, "Leave Nothing Behind", in
  [docs/PRODUCT.md](../PRODUCT.md).
