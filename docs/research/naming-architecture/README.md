# Naming architecture: authoritative vocabulary, discoverability, and rebrand resilience

A research spike on how this repository names things: whether product branding is
entangled with technical identity, and whether an unfamiliar human or agent can infer
capabilities and interfaces from the names alone.

**This is a spike, not a decision.** It records evidence and recommends what a future ADR
should and should not freeze. Nothing here is binding, no code or configuration changes
accompany it, and no ADR has been written. The report deliberately argues against several
of its own proposals (§7) rather than presenting a settled scheme.

**Status:** audit only. No code, config, or ADR written.
**Revision 3.** Revises rev. 2 rather than replacing it. Rebrand-resilience evidence (§2)
and discoverability findings (§3-§4) are preserved. New in this revision: the
vocabulary-authority analysis (§1), grounded in primary GPO source bytes in this
repository's own corpus.
**Repo state audited:** `spike/pdf-seam-external-validity` @ `df90e6e`; ADR state verified against all remote branches at the time of writing.
**Primary sources used:** the 58 committed GPO bill XML files under `tests/corpus/`; the vendored GPO render stylesheet referenced by `docs/gpo-render-conventions.md`; GAO-05-734SP as already cited by `docs/bill-structure.md:147`.

---

## 0. The governing principle

> **Do not make an agent or human learn a DeltaTrack dialect before they can reason about DeltaTrack.**

Adopted as the primary naming principle, with one correction argued in §7.1: it must read *unnecessary or undocumented* dialect, not *any* dialect. As an absolute it would indict ADR 0020, which deliberately and correctly introduced project-specific stage vocabulary.

This reframes naming as an **auditability and interface-semantics concern**. The consequence that matters most: the repository is plausibly read by someone with deep legislative expertise and no software context, or by an agent with broad training on Congress/GPO material and none on this project. Both bring vocabulary with them. Every place our identifiers mean something *different* from what those readers already know is a silent mistranslation, and silent mistranslation in a tool whose output is financial and traceability-critical is the failure mode worth spending on.

---

## 1. Vocabulary authority — findings from primary sources

### 1.1 The repository already practises the authority rule, in three places, unstated

This is the central new finding and it strengthens the ADR considerably: the rule is not novel discipline being imposed, it is **existing practice that was never written down and was never applied to identifiers**.

| Domain | Authority the repo already defers to | Evidence |
|---|---|---|
| Bill structure and typography | **GPO Bill DTD + GPO render stylesheet** | `docs/bill-structure.md:81` glossary maps every term to a Bill-DTD tag; `docs/gpo-render-conventions.md` is "distilled from the stylesheet", vendored from `govinfo.gov/bulkdata/BILLS/resources/` |
| Appropriations / budget terms | **GAO Glossary GAO-05-734SP** | Cited at `docs/bill-structure.md:147` for "appropriated by law" |
| Section-subdivision ladder | **House Office of the Legislative Counsel (HOLC)** | `AGENTS.md:115`, `docs/bill-structure.md:163` "Section subdivision ladder (HOLC)" |

Three authorities, already used, with **disjoint scopes**. That is materially different from the ranked list the brief proposes, and §7.2 argues the scoped model is the correct one.

### 1.2 Verified term collision: `bill.type` vs GPO's `bill-type`

Counted directly over the 58 committed corpus XML files:

```
bill-type="appropriations"   24
bill-type="olc"              23
bill-type="traditional"       1
```

**In GPO's own Bill DTD, `bill-type` is the drafting/DTD style.** It is not the measure type.

The canonical diff contract publishes `bill: {type, number, congress}` where `type` is `"hr"`, `"s"`, `"hjres"` — the *measure* type. So the published contract and GPO's source XML use the same term for two unrelated concepts, and the contract's meaning is the one a GPO reader would not expect.

This is the single strongest piece of evidence in the report, because it is verified from primary bytes on disk, it sits in a versioned public contract (ADR 0006), and it is exactly the mistranslation the governing principle exists to prevent.

### 1.3 Verified: GPO carries an authoritative version-stage identifier that the engine does not read

```
bill-stage="Reported-in-Senate"      14      bill-stage="Reported-in-House"      9
bill-stage="Enrolled-Bill"           10      bill-stage="Engrossed-in-House"     7
bill-stage="Introduced-in-House"      5      + 3 singletons
```

Every one of the 48 `bill`-root documents carries a `bill-stage`; the 10 `amendment-doc` roots do not. The values are exactly the vocabulary the repo's filename labels use (`1_reported-in-house.xml`).

But `grep -rn "bill-stage" src/ tools/ scripts/` finds **no reader** — one passing comment in `parsers/pdf_text.py:66` and nothing else. The label is derived from the filename stem (`version_stems.label_from_stem`) rather than from the authoritative attribute sitting in the document.

Two consequences:
- The contract's `VersionInfo.label` is an unconstrained `{"type": "string"}` (`canonical-diff.schema.json:106`) carrying what is, in fact, an authoritative closed vocabulary.
- The contract's `version_number` is the **project-specific per-bill ordinal** from ADR 0013 — explicitly "not a universal one". So the field named `version_number` is the local invention and the field named `label` is the authoritative identifier. A Congress or GPO reader would expect the reverse.

ADR 0013's ordinal is *justified* — it expresses chronological position within one bill's local sequence, which stage codes genuinely do not provide (they are stage labels and do not sort). This is a legitimate last-resort project concept. The defect is only that the naming gives the invented concept the authoritative-sounding name.

### 1.4 Verified: the corpus contains two GPO document types; the vocabulary names one

```
DOCTYPE bill            48
DOCTYPE amendment-doc   10
```

The engine **does** handle all three shapes — `bill_tree.find_bill_body` is documented as finding "the effective body element from a bill, resolution or amendment-doc root" (`bill_tree.py:142`), with the `<amendment-doc><engrossed-amendment-body><amendment><amendment-block>` path handled at line 174.

So the code makes a distinction its vocabulary erases: the entry point is `normalize_bill`, the types are `BillTree`/`BillNode`, the contract says `bill`, and 17% of the committed corpus is not a bill.

**Stated carefully:** this is a vocabulary collapse sitting on the same seam as the known `<quoted-block>` amendment defect (DeltaTrack#11, which produces a false "0 changes" on amendment bills). I have **no evidence that the naming caused the defect**, and I am not claiming it. What the co-location supports is the weaker and sufficient claim: this is the seam where a collapsed distinction is most likely to hide a real one, and it is already the seam where a real one was found.

### 1.5 A place where authoritative and project vocabulary correctly diverge

`changes[]` in the canonical contract are **observed differences between two texts**. In legislative usage, the instrument that effects a difference is an *amendment*. These are genuinely distinct: a diff is evidence of an outcome, an amendment is an act. The repository is right to keep separate words.

Nothing says so anywhere. This is the model case for the ADR's "project-specific vocabulary is last resort, and must be explicitly documented" clause — the term is justified, and the justification is missing.

### 1.6 Where authoritative sources genuinely conflict

`bill` is the umbrella term in **GPO's** vocabulary: the DTD is the Bill DTD, the root element is `<bill>`, and it covers joint resolutions. In **Congress.gov's** vocabulary, "measure" is the umbrella for bills and resolutions and "bill" is one kind of measure.

So the repo's pervasive use of `bill` is *GPO-authoritative and Congress-divergent*. Under a ranked hierarchy putting Congress first, `bill` would be wrong nearly everywhere in the codebase; under scope-based authority (structure → GPO), it is right almost everywhere. This single case is why §7.2 rejects the ranking.

*Verification limit:* the GPO facts in §1.2-§1.5 are verified from bytes in this repository. The Congress.gov "measure" usage in this section is stated from general knowledge and is **not** verified at source in this revision. It is load-bearing for the conflict claim and should be confirmed against Congress.gov's glossary before the ADR asserts it.

---

## 2. Rebrand-resilience findings (preserved from rev. 1-2)

**Branding is not materially coupled to this architecture.** 1,002 occurrences (603 `deltatrack`, 355 `DeltaTrack`, 44 `DELTATRACK`) collapse to four groups; one is structural.

By directory: `docs/research` 308 · `tests` 299 · `docs/decisions` 99 · `src` 81 · root Markdown 51 · `scripts` 46 · `web` 18 · `examples` 16 · `pyproject.toml` 10 · root wrappers 10 · `schema` 4 · `.github` 1 · `tools` 0.

| Category | Evidence | Impact | Risk |
|---|---|---|---|
| **Python namespace** | 360 imports: `tests/` 210, frozen probes 88, `src/` self 37, `scripts/` 21, `web/` 2, wrappers 2 | One grep; every failure is an ImportError or build error | Low (loud); **High (process)** for the 88 frozen |
| **Distribution identity** | `[project] name`, hatch `packages = ["src/deltatrack"]`, sdist include, `uv.lock:242` | 3 edits; mismatch is a build error by design (`pyproject.toml:9-13`) | Low — never published |
| **Serialized value** | `canonical.py:32` `GENERATOR_NAME`, emitted lines 205/473 | Regenerates examples byte-compared by `test_committed_examples.py:80` | Medium — §6 |
| **Published artifacts** | `examples/*.html` embed `{"generator":{"name":"deltatrack"}}` on GitHub Pages | `render_examples.py` + `update-examples.yml` | Low technically, public in effect |
| **Layout gates** | `test_surface_boundary.py:155-169`, `test_fixture_layout.py` (33), `test_structure_vocabulary_gate.py:35` | ~50 path strings, all fail closed | Low |
| **Deployment** | `systemctl restart deltatrack`; `deltatrack.agoradmv.org`. App is host-agnostic (`web/app.py:152-156`) | External DNS/TLS/unit | **High**, externally owned |
| **Research canaries** | `DELTATRACK_SECRET_*`, all 44 uppercase hits | Evidence of observed egress | **Immutable** |
| **UI / prose** | `web/webapp/*`, `title="DeltaTrack API"`, ADR titles, docs | Intended blast radius / editorial | Low / none |

**Already brand-independent:** zero in `.github/workflows/` (all four files); zero branded env vars (`BILLTRAX_ARTIFACTS` is the *sibling* brand, in a dev-only script); zero `[project.scripts]`; zero persistent branded paths in the engine; zero in `tools/`.

**CI detects a rename, it does not suffer one.** `uv sync` fails on a hatch package/dir mismatch; `conftest.py:41-90` aborts before collection if `deltatrack` resolves outside this checkout's `src/`; `test_engine_installs.py` builds a real wheel. Path-based config is unaffected. No partial rename produces a green run.

**No observed external consumer requires a compatibility namespace.** BillTrax's `submodules/DeltaTrack/` is not a submodule (no `.gitmodules`); it is a tracked vendored fork of the pre-#398 flat layout (last modified 2026-06-09, `ac29d7e`) doing `sys.path.insert(...)` then `from bill_tree import normalize_bill` — bare names. It emits its own shape and never reads canonical JSON. *Limit:* one checkout, one commit; absence of others in view is not proof of absence.

**Renaming during the frozen research work is unjustified.** 41 probes import `deltatrack` (88 lines) under a git-blob-hash freeze (`x04_freeze_check.py` F2) and an amendment ledger (F9); `external-validity/PRE-REGISTRATION.md:128` declares `reconstruct_hybrid.py` frozen unmodified.

**`deltatrack → bill_diff` remains architecturally misleading**, and §4.4 adds the grammatical reason.

---

## 3. Discoverability findings (preserved)

### 3.1 Three public surfaces disagree about whether input representation is a job

| Surface | Treatment | Evidence |
|---|---|---|
| Canonical contract | Property of the input | `versions.v1.source` is an `enum ["xml","pdf"]` (`schema:108`) |
| Web API | Parameter on one operation | `POST /api/compare?format=pdf\|xml&output=html\|json`, `_COMPARE` dispatch (`web/app.py:47,249-256`) |
| CLI | Selects the command | `./diff_bill.py compare A B` vs `./diff_pdf.py A B` |
| Python API | Encoded in six names | `compare_xml`, `compare_xml_html`, `compare_xml_trees_html`, `compare_xml_files_html`, `compare_pdfs`, `compare_pdfs_html` |

Two of four already do the right thing. The principle is half-adopted and undocumented, not speculative.

### 3.2 The two CLIs use different grammars for one user intent

`./diff_bill.py compare <old.xml> <new.xml>` vs `./diff_pdf.py <v1.pdf> <v2.pdf>`; descriptions read "Compare two bill XML versions" (`diff_bill.py:944`) and "Diff two PDF bill versions" (`diff_pdf.py:601`). An agent generalizing from the first invokes `diff_pdf.py compare A B` and gets an argparse error.

### 3.3 `--format` carries two meanings, and `source` carries two more

| Identifier | Surface | Meaning |
|---|---|---|
| `--format json\|html` | `diff_bill.py compare` | **Output** representation |
| `--format xml\|pdf\|both` | `fetch_bills.py download` | **Input** representation |
| `?format=pdf\|xml` | `POST /api/compare` | **Input** representation (output is a separate `output=`) |
| `--source govinfo\|api` | `fetch_bills.py` | **Provider / origin service** |
| `source: "xml"\|"pdf"` | canonical contract | **Input representation** |

**New in this revision:** `source` is a second collision, and it is worse than `--format` because the contract version is a schema `enum` — load-bearing, published, and versioned. Four concepts (input representation, output representation, provider, operation) are currently expressed by two overloaded words.

### 3.4 `parsers/` does not contain the primary parser

`parsers/` holds `pdf_text.py`, `pdf_anchors.py`, `committee_report.py`. The XML parse entry point is `bill_tree.normalize_bill` at package root, and both the code's own docs call that operation parsing:

- `compare/xml.py:7` — `normalize_bill()  (bill_tree)  — parse XML → BillTree`
- `docs/architecture.md` pipeline table — stage **Parse**, owner `bill_tree.normalize_bill`

The identifier is the only artifact that says "normalize". Under §5's technical-convention rule, `normalize` conventionally means canonicalizing a representation, not constructing a tree from a serialized document — so this is a conventional-usage violation, not only an internal inconsistency.

### 3.5 `view` is claimed twice before any `view` job exists

`formatters/view_model.py` (`DiffView`, `ChangeView`, `view_from_canonical()`) is the presentation model *of a diff*; "full-bill view" (`README.md:195`, UI) is a *panel inside a comparison report*. No standalone single-document capability ships.

### 3.6 Naming drift has already produced a measured architectural problem

ADR 0020 finds `reconcile_moves` is "a second retrieval pass, unnamed as such, running after classification", recovering **496 changes across 27 adjacent version pairs** that the first retriever structurally cannot reach — with no inspectable candidate set. It further finds one similarity ratio serving five decisions spanning retrieval, assignment, classification and presentation, including `formatters/_text.word_diff`, a renderer recomputing an identity score against the differ's cutoff.

The stage had no name, so it went unmeasured. Naming it is what made the 496 computable. This is the evidence that the exercise is load-bearing.

### 3.7 Overloaded terms

| Term | Distinct meanings |
|---|---|
| `normalize` | **4** — `normalize_bill` (parse) · `normalize_header`/`_normalize_text` (string canonicalization) · `normalize_glyphs` (`pdf_text.py:179`, Unicode mapping) · `normalize_raw` (`pdf_text.py:128`, line-ending/soft-hyphen repair) |
| `extract` | **6** — `extract_clean_pages` · `extract_text_content`/`extract_display_text` · `extract_amounts` · `extract_front_matter_nodes` · `extract_anchors` · `extract_pre_text` |
| `diff` | **4 roles** — verb (`diff_bills`) · result (`BillDiff`, `NodeDiff`, `PdfDiff`) · subsystem (`diff_bill.py`) · qualifier (`diff_html`, `xml_diff_to_canonical`) |
| `view` | **3** (§3.5) |
| `format` / `source` | **4 concepts across two words** (§3.3) |
| `tree` | **2, asymmetrically named** — `BillTree`/`BillNode` vs `TreeNode`; `build_xml_tree(bill: BillTree) -> list[TreeNode]` |

### 3.8 Consistently used, and worth protecting

`canonical` (ADR 0006), `anchor`, `level` (glossary-governed, `bill-structure.md:97`), `slug` and version ordinal (ADR 0013), and the ADR 0019/0020 stage vocabulary.

### 3.9 The `compare` / `diff` distinction the architecture already supports

`compare/` is the composition layer — `docs/architecture.md` calls it "the product surface", every entry point goes through it, its functions return finished artifacts. `*Diff` types are results; `diff_bills()` is the core algorithm. **Compare-as-operation and diff-as-result is already the architecture**; only the identifiers disagree (`diff_bill.py` exposing subcommand `compare`; `/api/compare` whose errors say "Could not diff these files").

### 3.10 Public boundary vs internal grouping — not a blanket verdict

| Name | Verdict | Reason |
|---|---|---|
| `formatters/` | **Acceptable** | Coherent output-side grouping; a caller asking "how do I get HTML?" lands correctly |
| `parsers/` | **Poor as a public boundary** | Excludes the primary parser (§3.4); includes `committee_report.py`, which is validation ground truth (ADR 0009) with **no engine consumer** — importers are two tests and `scripts/build_validation.py` |
| `formatters/_text.py` | **Correct** | Genuine utility bucket (`word_diff`, `fmt_dollar`) and **private** |
| `version_stems.py` | **Acceptable** | Filename-convention plumbing; no domain concept underlies it |

The operative distinction is **public discovery boundary vs private implementation grouping**, not domain-word vs generic-word.

---

## 4. Naming grammar — loosened, per critique

Rev. 2 proposed a five-role taxonomy. That is withdrawn: `similarity` falsified the four-role version, and a fifth role only postpones the same failure. Recommend instead:

> **Names should make their technical role apparent and follow conventional grammatical expectations where those expectations exist.**

- Operations read as verbs (`extract_anchors`, `diff_bills`, `build_pdf_tree`).
- Entities, results, measures and capabilities read as nouns (`BillTree`, `Correspondence`, `Evidence`).
- Predicates read as predicates (`_is_uppercase_heading`, `text_similarity_at_least`).
- Exceptions follow established technical convention, not a project taxonomy.

This is a *convention*, not a classification scheme, and deliberately so: an exhaustive taxonomy is itself a dialect contributors must learn, which contradicts §0.

### 4.1 Where the convention is genuinely awkward

- **Measures and cutoffs.** `text_similarity()`, `SIMILARITY_THRESHOLD`, `MOVE_THRESHOLD`, `similarity.py`. Noun-form is right; the harder question is that ADR 0020 reclassifies these as *evidence signals* and *policy parameters*, which is 0020's call to make, not 0021's.
- **Verb-first module names are sometimes right.** `diff_bill.py` reads as a verb phrase, defensible for an algorithm module. The defect is that the same token also names the result and the subsystem.
- **Private buckets stay legitimate** (§3.10).
- **Format qualifiers are correct one layer down.** `compare_xml` / `compare_pdfs` are wrong as *the public surface* and right as implementations behind a dispatcher — exactly how `_COMPARE` uses them today.

### 4.2 `bill_diff` — the ambiguity is live, not hypothetical

Within one package the token appears as subsystem (`diff_bill.py`), action (`diff_bills()`), result (`BillDiff`), and serializer over the result (`bill_diff_to_dict()`), with word order reversed between module and function. The repository already demonstrates the construction fails to separate the three roles.

---

## 5. Technical vocabulary against conventional expectation

Test: *what would an experienced external practitioner or agent expect this term to mean?*

| Term | Conventional expectation | Repo usage | Verdict |
|---|---|---|---|
| `parse` | Serialized input → structured representation per a grammar/schema | `parse_lines`, `parse_summary_blocks` ✓; but the primary XML parse is named `normalize_bill` ✗ | **Violated once, prominently** |
| `extract` | Recover information from a container or unstructured source | Six meanings, spanning genuine extraction, element reading, and tree filtering (§3.7) | **Diluted** |
| `normalize` | Canonicalize a representation without changing its information | Three uses conform; `normalize_bill` does not (§3.4) | **Violated once** |
| `serialize` | In-memory structure → transportable representation | `serialize_tree`, `build_xml_full_text` | **Conforms** |
| `render` | Structured data → presentation output | `format_diff_html`, "Render" stage | **Conforms** |
| `validate` | Check against an explicit rule, contract, schema, or evidence | `test_validate_extraction`, `build_validation.py` against committee reports (ADR 0009) | **Conforms** |
| `match` / `compare` | IR / record-linkage sense | Now governed by ADR 0020 | **Deferred to 0020** |
| `fetch` | Retrieve from a remote source | Tool named `fetch_bills.py`, primary verb `download`, plus a `fetch-index` subcommand | **Synonym drift** |

### 5.1 `parse` vs `extract` must not be collapsed — preserved and reinforced

XML parsing is schema-driven, lossless, and deterministic. PDF text recovery is lossy, engine-dependent and probabilistic — the subject of ADR 0002, ADR 0012, and the entire bake-off with its external-validity study. Collapsing both to one word would erase the distinction a research programme exists to characterize, and would misrepresent the trust boundary between the two paths to exactly the auditor §0 is written for.

**Consistency never overrides technical accuracy.** Two things share a name only when they are the same concept.

---

## 6. Rebrand rule (final form)

> **Product branding must not be a load-bearing technical identifier. Branded identity may appear in explicitly product-facing metadata and copy, but protocol, capability, dispatch, compatibility, and other technical behavior must not depend on the brand.**
>
> **Producer-side obligation.** A field carrying replaceable product identity must say so where the contract is defined. "Consumers must not depend on it" is unenforceable against a consumer never told; an unannotated free-string field in a versioned public contract is an invitation to branch on it.

| Case | Ruling | Basis |
|---|---|---|
| `schema_version` | **Load-bearing technical identity.** Consumers may and should dispatch on it | ADR 0006 versions it |
| `generator.name` | **Replaceable product identity.** May stay `"deltatrack"` or carry a successor brand; must be documented as non-dispatchable | `{"type":"string"}`, no `const`/`enum` (`schema:45-51`); no test asserts it; no observed consumer reads it |
| `from deltatrack.x import y` | **Violation** — every consumer must spell the brand | §2 |
| Docstrings; user-facing copy in `compare/` | **Fine** | Nothing spells them back |
| `DELTATRACK_SECRET_*` canaries | **Exempt and immutable** | Evidence of observed egress |
| `tempfile(prefix="deltatrack-")` | **Fine** | Ephemeral |
| `title="DeltaTrack API"` | **Fine** — product-facing OpenAPI metadata | |

**Recommended action, unchanged:** document `generator.name`'s semantics in `schema/canonical-diff.md` and add a `description` to the schema's `generator` object. **Do not change the emitted value.** Under the rule this is the producer-side obligation, not a concession; it costs a paragraph, changes no output bytes, and is the only finding that gets harder the longer it waits.

---

## 7. What I recommend rejecting or amending in the proposed policy

This section is adversarial by design: the spike was asked to falsify the naming policy it
was evaluating rather than agree with it. "The brief" and the numbered items below refer to
a review proposal that set out a candidate policy — an authority hierarchy, a naming
grammar, a set of rules to freeze. The numbering is preserved so each objection stays
traceable to what it answers.

### 7.1 Reject "No DeltaTrack dialect" as an absolute

ADR 0020 deliberately creates project-specific vocabulary: the four-stage boundary, and the `Candidate` / `Proposal` / `Retriever invocation` distinction, are this project's. The *words* are borrowed from IR and record linkage; the *specific structure* is not. It was the right call, and §3.6 shows it produced a measurement nothing else had.

Stated absolutely, item 1 is unfalsifiable-by-design and would be cited against good decisions later — which matters because ADRs are append-only and this one would be cited for years.

**Amend to:** *no unnecessary or undocumented dialect.* A project-specific term is legitimate when neither authoritative legislative nor conventional technical vocabulary is accurate; when used it must be defined in one discoverable place. §1.5 (`changes` vs `amendment`) is the model case, and it currently fails only the documentation half.

### 7.2 Reject the ranked authority hierarchy; use scoped authority

The brief ranks Congress (1) → GPO (2) → GPO Style Manual (3). The evidence contradicts the ranking for this repository's concepts.

`bill` is GPO's umbrella term — the Bill DTD, the `<bill>` root, joint resolutions included (§1.6). Congress.gov's umbrella is "measure". Under the ranked hierarchy, `bill` would be wrong across nearly the whole codebase and contract. Under scope-based authority it is right almost everywhere, and the genuine defects are narrower and actionable: `bill` as an umbrella for the 10 `amendment-doc` cases, and `bill.type` colliding with GPO's `bill-type`.

**Amend to authority scoped by concept type**, which is what the repo already does (§1.1):

| Concept type | Authority |
|---|---|
| Document structure, stages, elements, typography | **GPO** — Bill DTD, render stylesheet, Style Manual |
| Measures, chamber procedure, legislative action | **Congress** — House/Senate rules, Congress.gov |
| Appropriations and budget concepts | **GAO** — GAO-05-734SP, already cited |
| Drafting-form subdivision ladder | **HOLC**, already cited |

With the brief's own conflict rule retained: where scopes overlap and sources differ, document the conflict and state which was chosen and why. §1.6 is the first entry.

### 7.3 Amend item 10 — the freeze is right but incomplete

"Input representation, output representation, operation, and result are different concepts and should not share an ambiguous identifier" should be adopted, and extended: **provider/origin is a fourth concept**, because `source` already means provider in `fetch_bills.py --source govinfo|api` and input representation in the canonical contract's `source` enum (§3.3). A freeze naming only three concepts leaves the worse of the two collisions unaddressed — worse because the contract one is a published, versioned `enum`.

### 7.4 Amend item 14 — a glossary-membership CI gate cannot ship yet

The brief endorses deterministic vocabulary gates in CI. A gate asserting "every public identifier's head term is in the glossary" **cannot be built until the glossary exists**, and the brief correctly defers the glossary. Freezing the gate as a requirement would freeze work that is blocked.

What *can* ship immediately is narrower and purely structural: one meaning per public flag name across all surfaces (`--format`, `--source`), and a consistent CLI grammar assertion. Precedent exists — `tests/test_structure_vocabulary_gate.py` is an ADR-0018 vocabulary gate that scans by subtraction so a new module is guarded by default, and carries `TestDetectorCanFail` proving the detector still fires. That is the pattern; it should be cited, and the glossary gate should be named as a follow-on, not a same-time deliverable.

### 7.5 Sharpen item 15's "do not freeze `bill`"

Correct not to freeze it as a *namespace*, but "verify before use" understates what is already known. `bill` is verified GPO-authoritative for 48 of 58 corpus documents (§1.2-1.4). The open questions are narrower and worth stating as such: (a) the umbrella problem for `amendment-doc`, (b) the `bill.type` / `bill-type` collision, (c) whether Congress.gov's "measure" should govern any surface. Deferring the whole word obscures three specific answerable questions behind one unanswerable one.

### 7.6 Accepted without amendment

Items 4 (loosen the grammar), 5 (narrower ADRs stay authoritative in scope), 6 (rebrand rule + producer obligation), 7 (grandfather, do not freeze mechanism), 8 (do not freeze `view`), 9 (do not freeze a job taxonomy), 11 (preserve parse/extract), 12 (public boundary vs private grouping), 13 (discoverability and auditability as criteria).

---

## 8. Migration recommendation (unchanged from rev. 2)

**Do not rename now.** No architectural justification; the frozen research surface forbids it; no deadline.

- **Current finding, dated 2026-08-07.** On the consumer graph as observed today, no compatibility namespace is justified: nothing is published to any index, the one observed consumer is a vendored fork importing bare module names, and CI fails closed on every partial-rename path.
- **Deferred decision.** The migration mechanism is chosen at rename time against the graph as it stands then. **Not frozen.** A/B/C/D are analysis, not a commitment.

**Triggers to reassess:** the product is rebranded; the distribution is about to be published to an index; a consumer begins importing `deltatrack.*`; the external-validity freeze lifts; #62 is resolved and a package split is on the table architecturally.

**Do not change yet:** package name, distribution name, `GENERATOR_NAME`'s value, frozen probes, deployment names, prose, and the 37 `src/` self-imports — they are the *easiest* references to change at rename time, so converting them removes ~10% of the work while adding a style split with the other 320 sites today.

---

## 9. ADR 0021 — number, scope, and open questions

### Number: 0021, re-verified

`0019-observation-identity.md` merged on `origin/develop` (Accepted, 2026-08-07). `0020-matching-stages.md` on `origin/docs/adr-0020-matching-stages`, open as PR #562. A scan of `docs/decisions/` across **every** remote branch after a fresh fetch returns nothing above 0020. Re-check at draft time: two landed in one day.

Operational: `tests/test_adr_index.py` regenerates both the `AGENTS.md` index and the README Records table and fails if either disagrees, so a new ADR requires updating both in the same change. `docs/decisions/README.md` requires `Status: Proposed` on the PR, flipped to `Accepted` by a maintainer on merge.

### Tensions the authority rule creates with existing ADRs and code

Reported as findings for the ADR to acknowledge, **not** as work to schedule.

| Tension | Detail | Recommended handling in 0021 |
|---|---|---|
| **`bill.type` vs GPO `bill-type`** (§1.2) | Published contract term collides with GPO's own attribute, different meaning | Acknowledge as a known divergence; ADR 0006 owns the contract, so any change is 0006's to make. **Do not change the contract in 0021** |
| **`version_number` vs `label`** (§1.3) | The invented ordinal has the authoritative-sounding name; the authoritative stage label is a free string | Acknowledge; note ADR 0013 owns version identity and its ordinal is justified. Flag `label` as a candidate closed vocabulary |
| **`bill` as umbrella over `amendment-doc`** (§1.4) | 10 of 58 corpus documents are not bills; the code distinguishes them, the vocabulary does not | Acknowledge, explicitly without a causal claim about DeltaTrack#11 |
| **`normalize_bill`** (§3.4) | Violates conventional `normalize`; the docs already call it parsing | The clearest single candidate for a future rename. **Name it as an example, do not schedule it** |
| **`source` collision** (§3.3) | Provider vs input representation; the contract side is a schema `enum` | Covered by the four-concept separation; remediation is ADR 0006's and the tooling's |
| **ADR 0020's `similarity`** (§4.1) | 0020 reclassifies it as evidence signal / policy parameter | **0020 governs. 0021 must not touch it** |
| **ADR 0018's vocabulary gate** | Already enforces a different vocabulary rule over `src/deltatrack` | 0021's gate proposals must compose with it, not replace it |

### Open questions

1. Will the product be rebranded, and when? Everything in §8's triggers keys off it.
2. Congress.gov's "measure" usage — **needs source verification** before 0021 asserts the §1.6 conflict.
3. Should `label` become a closed vocabulary keyed to GPO `bill-stage`, and should the engine read the attribute rather than the filename?
4. Is `bill` the right umbrella, or should the umbrella be a distinct term with `bill` reserved for `DOCTYPE bill`?
5. Mixed-representation comparison (`compare v1.pdf v2.xml`) — nothing supports it; the web API takes one `format` for both files; ADR 0010 is silent. A unified operation forces an explicit answer, even if that answer is a specific refusal.
6. What is the canonical term for single-document presentation? Not `view` (§3.5).
7. Does anything downstream read `generator.name`? No in-repo consumer; the examples site publishes the value.
8. Will the BillTrax fork re-converge? Decides whether a compatibility layer is ever justified.
9. Who owns `deltatrack.agoradmv.org`, the certificate and the systemd unit, and what is the lead time? Critical path for any rebrand, entirely outside the repo.
10. Should `parsers/committee_report.py` be in the shipped engine at all? No engine consumer; independent of naming.
