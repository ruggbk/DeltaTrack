# Naming architecture: authoritative vocabulary, discoverability, and rebrand resilience

A research spike on how this repository names things: whether product branding is
entangled with technical identity, and whether an unfamiliar human or agent can infer
capabilities and interfaces from the names alone.

**This is a spike, not a decision.** It records evidence and recommends what a future ADR
should and should not freeze. Nothing here is binding, no code or configuration changes
accompany it, and no ADR has been written. The report deliberately argues against several
of its own proposals (§7) rather than presenting a settled scheme.

**Status:** audit only. No code, config, or ADR written.
**Revision 4.** Rev. 3 over-read the committed corpus, treating observed occurrence as
normative definition and corpus proportions as population facts. §1 is rebuilt around an
explicit evidence hierarchy (§1.0), and every claim it could not support has been
downgraded or withdrawn (§1.8 lists them). Rebrand-resilience evidence (§2) and
discoverability findings (§3-§4) are otherwise preserved.
**Repo state audited:** `spike/pdf-seam-external-validity` @ `df90e6e`; ADR state verified against all remote branches at the time of writing.

---

## 0. The governing principle

> **Do not make an agent or human learn a DeltaTrack dialect before they can reason about DeltaTrack.**

Adopted as the primary naming principle, with one correction argued in §7.1: it must read
*unnecessary or undocumented* dialect, not *any* dialect. As an absolute it would indict
ADR 0020, which deliberately and correctly introduced project-specific stage vocabulary.

This reframes naming as an **auditability and interface-semantics concern**. The
consequence that matters most: the repository is plausibly read by someone with deep
legislative expertise and no software context, or by an agent with broad training on
Congress/GPO material and none on this project. Both bring vocabulary with them. Every
place our identifiers mean something *different* from what those readers already know is a
silent mistranslation, and silent mistranslation in a tool whose output is financial and
traceability-critical is the failure mode worth spending on.

**The report is bound by the discipline it recommends.** An official but purposively
selected corpus may establish that something exists. It may not quietly become a model of
congressional publishing. §1.0 is the mechanism for holding this document to that.

---

## 1. Vocabulary authority

### 1.0 Three classes of evidence, and what each can support

Rev. 3 conflated these. They are kept apart throughout this revision, and every claim
below is labelled with the class it rests on.

| Class | What it is | What it can establish | What it cannot |
|---|---|---|---|
| **A — Normative semantic authority** | The specification, DTD, data dictionary, glossary, rule, or official documentation that *defines* a term | What a term or attribute officially means | — |
| **B — Observed official examples** | Values and structures occurring in official documents in this repository's committed corpus | That a value or shape **exists**, and that the engine must handle it | Prevalence across congressional measures; the *meaning* of a term where a class-A source exists |
| **C — Repository behaviour** | How this codebase names, interprets, or processes a concept | What DeltaTrack currently does | Anything about what is correct |

#### What the committed corpus is, and is not

`tests/corpus/` holds 58 XML documents across 26 bill directories. They are genuine GPO
artifacts, byte-identical to what govinfo published (ADR 0015).

They are also a **purposive, appropriations-heavy sample**, assembled for this project's
historical research and regression-testing needs — the money-diff work came first, and the
corpus was selected to exercise it. It is not statistically or structurally representative
of congressional measures, and it does not contain every measure type or every GPO XML
shape. Every bill directory is `hr` or `s`; no joint, concurrent, or simple resolution is
present, though the repository's own `BILL_TYPES` (§1.3) enumerates all eight.

Two worked consequences, stated because rev. 3 got both wrong:

> `bill-type="appropriations"` on 24 of 58 documents establishes that the value **occurs**
> and that the engine encounters it. It does **not** establish that ~41% of congressional
> measures carry it. On an appropriations-selected corpus, that proportion is close to a
> restatement of the selection criterion.

> 10 of 58 documents being `DOCTYPE amendment-doc` proves this corpus **contains amendment
> documents**, and therefore that the code must handle them. It says nothing about how
> common amendment documents are in congressional publishing generally.

#### What this revision did not do

**No class-A source was read for this revision.** The `bill.dtd` and `amend.dtd` that the
corpus documents declare are not vendored in this checkout (`reference/` is gitignored and
absent), and no external specification, GovInfo user guide, or Congress.gov glossary was
consulted. Every semantic claim below is therefore an **inference from class-B
observation**, explicitly marked, and each needs class-A confirmation before an ADR
asserts it. §1.8 lists what that costs.

### 1.1 The repository already practises scoped authority, in three places, unstated

*Class C, with class-A sources cited by the repo itself.*

This is the central structural finding and it strengthens the ADR: the authority rule is
not new discipline being imposed, it is **existing practice never written down and never
applied to identifiers**.

| Concept scope | Authority the repo defers to | Evidence |
|---|---|---|
| Bill structure and elements | The congressional bill DTD | `docs/bill-structure.md:81` glossary maps every term to a Bill-DTD tag |
| Publishing and typography | GPO render stylesheet | `docs/gpo-render-conventions.md`, distilled from the stylesheet vendored from `govinfo.gov/bulkdata/BILLS/resources/` |
| Appropriations and budget terms | GAO Glossary **GAO-05-734SP** | Cited at `docs/bill-structure.md:147` |
| Drafting-form subdivision ladder | House Office of the Legislative Counsel | `AGENTS.md:115`; `docs/bill-structure.md:163` |

Four authorities, already used, with **disjoint scopes**. That is materially different from
a ranked institutional list, and §7.2 argues the scoped model is correct.

### 1.2 "Bill type" is a cross-surface collision among official vocabularies

*Class B for the values; class C for the repository's usage; class A not consulted.*

Rev. 3 framed this as DeltaTrack diverging from GPO. That framing was wrong, and the
correction makes the finding more useful rather than less.

**Two official surfaces use "bill type" for different concepts.**

*Surface 1 — the document XML.* Every `bill`-root document in the corpus declares
`<!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN" "bill.dtd">` and carries a
`bill-type` attribute. Observed values across the 58 files:

```
bill-type="appropriations"   24
bill-type="olc"              23
bill-type="traditional"       1
```

These are drafting-form or document-class values, not `hr`/`s`/`hjres`. **That reading is
an inference from the observed value set, not a definition** — `bill.dtd` was not read, and
its data dictionary is the class-A source that would settle what the attribute means.

*Surface 2 — GovInfo packaging and Congress.gov addressing.* The same phrase means the
measure type. `tools/fetch_govinfo.py:229-244` builds govinfo bulk-data paths as
`BILLS/{congress}/{session}/{bill_type}/BILLS-{congress}{bill_type}{number}{ver}.xml`,
where `bill_type` is `hr`/`s`/`hjres`. `tools/shared/bill_types.py` enumerates all eight
values with their Congress.gov URL slugs.

*Surface 3 — this repository's published contract.* The canonical diff publishes
`bill: {type, number, congress}` with `type` in the measure sense — i.e. aligned with
surface 2, not surface 1.

**So DeltaTrack did not invent a meaning.** It adopted one official vocabulary (GovInfo /
Congress.gov packaging) for a term that a different official vocabulary (the document DTD)
uses for something else. The hazard is the **unqualified identifier**: `type` inside an
object named `bill`, with no indication of which surface's vocabulary governs.

This is the strongest available argument for ADR 0021's central rule, and it is stronger
than rev. 3's version:

> Authoritative vocabulary is scoped to a concept *and a representation*. Where official
> vocabularies themselves differ by scope, an unqualified identifier does not merely risk
> ambiguity — it guarantees that some correct reader will resolve it wrongly.

### 1.3 Version identity: at least four distinct notions, three of them official

*Class B and C. No class-A source consulted for any of them.*

Rev. 3 called `bill-stage` "the authoritative version identifier." **Withdrawn** — nothing
consulted supports singling it out as canonical.

What can be stated:

| Notion | Where it appears | Class |
|---|---|---|
| `bill-stage="Reported-in-House"` | Attribute on every `bill` root in the corpus; title-case | B |
| GovInfo **version code** (`ih`, `rh`, `eh`, `eas`, `enr`, `renr`, …) | Filenames and bulk-data URLs; enumerated at `tools/fetch_govinfo.py:82` `VERSION_CODES` | B/C |
| BILLSTATUS `textVersions <type>` spelling | A **third** spelling that diverges from the codes' canonical names — the repo documents "Reported to Senate" vs "Reported in Senate" at `fetch_govinfo.py:164-174` and patches it explicitly | C documenting B |
| DeltaTrack per-bill chronological ordinal | ADR 0013; the contract's `version_number` | C |

Three official surfaces disagree on how to name a version, and the repository already
carries a hand-maintained reconciliation between two of them. That is independent support
for §7.2's scoped-authority model, arrived at from a different direction.

Two observations that survive:

- **`bill-stage` is present in every corpus `bill` document and is read nowhere.**
  `grep -rn "bill-stage" src/ tools/ scripts/` finds one passing comment in
  `parsers/pdf_text.py:66` and no reader. The label is derived from the filename stem
  (`version_stems.label_from_stem`).
- **The contract's `VersionInfo.label` is an unconstrained `{"type": "string"}`**
  (`canonical-diff.schema.json:106`) carrying values drawn from what is evidently a closed
  official vocabulary.

**What does not follow:** that `bill-stage` should replace `version_number`. ADR 0013's
ordinal expresses chronological position within one bill's local sequence, which stage
labels do not provide. Whether any official identifier should back `label`, and which one,
is ADR 0013/0006 research, not this spike's to answer.

### 1.4 The corpus contains a second document type with a parallel attribute vocabulary

*Class B for existence; class C for handling.*

```
DOCTYPE bill            48
DOCTYPE amendment-doc   10
```

The amendment documents declare a **different DTD** — `-//US Congress//DTDs/amend.dtd//EN`
— and carry a different attribute set: `amend-type="engrossed-amendment"`,
`amend-degree="first"`, with no `bill-type` and no `bill-stage`. All 10 in this corpus
share those same two values, so the corpus establishes that the shape exists and exercises
exactly one variant of it.

The engine **does** handle these: `bill_tree.find_bill_body` is documented as finding "the
effective body element from a bill, resolution or amendment-doc root" (`bill_tree.py:142`),
with the `<amendment-doc><engrossed-amendment-body><amendment><amendment-block>` path at
line 174.

So the code makes a distinction its vocabulary erases: the entry point is `normalize_bill`,
the types are `BillTree`/`BillNode`, and the contract says `bill`.

Independent of corpus composition, the repository's own `tools/shared/bill_types.py`
enumerates `hres`, `sres`, `hconres`, `sconres` — simple and concurrent resolutions, which
are not bills — so the umbrella problem is visible in class-C evidence alone and does not
depend on the sample.

**Stated carefully:** this vocabulary collapse sits on the same seam as the known
`<quoted-block>` amendment defect (DeltaTrack#11). I have **no evidence that naming caused
that defect** and do not claim it. The supportable claim is weaker and sufficient: this is
where a collapsed distinction would be most likely to hide a real one, and it is already
where a real one was found.

### 1.5 Legislative and technical vocabularies coexisting correctly

*Class C.*

`changes[]` in the canonical contract are observed differences between two texts. An
*amendment* is the legislative instrument that effects a difference. These are different
concepts, and the repository is right to keep separate words.

Rev. 3 offered this as its model case of justified invented dialect. **Reclassified:**
`change` and `diff` are established technical vocabulary, not project inventions. The
correct lesson is the more useful one — *legislative and technical vocabularies coexist
correctly when they name genuinely different concepts*. Neither has to yield. What is
missing is only that nothing states the distinction.

### 1.6 A vocabulary conflict this revision can point at but not resolve

`bill` is the umbrella in the document-XML surface: the DTD is `bill.dtd`, the root element
is `<bill>`, and joint resolutions are published under it. Elsewhere in official usage,
"measure" is the umbrella for bills and resolutions and "bill" is one kind of measure.

*Class-A status:* **unverified.** The first half is inference from class-B observation; the
second half was stated in rev. 3 from general knowledge and is **not** confirmed against
Congress.gov's glossary or any other normative source. It is load-bearing for the conflict
claim and must be checked before an ADR asserts it.

What the case is good for regardless: it is the clearest illustration of why a *ranked*
institutional hierarchy fails (§7.2). Under "Congress outranks GPO," `bill` would be wrong
across nearly the whole codebase. Under scoped authority the question becomes tractable and
narrow.

### 1.7 New primary sources used in this revision

| Source | Class | What it gave |
|---|---|---|
| DOCTYPE declarations in corpus XML | B | The **names** of the governing specs: `-//US Congress//DTDs/bill.dtd//EN`, `-//US Congress//DTDs/amend.dtd//EN`. Identifies the class-A sources; does not substitute for them |
| `amend-type` / `amend-degree` attribute values | B | Amendment documents carry a parallel, distinct attribute vocabulary |
| `tools/fetch_govinfo.py:82,229-244` | C documenting B | GovInfo's own path vocabulary uses "bill type" in the measure sense, and maintains version **codes** as a separate identifier space |
| `tools/shared/bill_types.py` | C documenting B | All eight measure types with Congress.gov slugs, six of which are not bills |
| `tools/fetch_govinfo.py:164-174` | C documenting B | Three official spellings of version identity, with a hand-maintained patch between two |

### 1.8 Claims downgraded or withdrawn in this revision

| Rev. 3 claim | Disposition |
|---|---|
| "the corpus is the authoritative source" | **Withdrawn.** Reclassified as class-B observation from a purposive sample (§1.0) |
| "GPO's `bill-type` **is** the drafting style" | **Downgraded** to an inference from observed values, pending `bill.dtd` (§1.2) |
| "DeltaTrack's `bill.type` collides with GPO's" | **Reframed.** A collision between two *official* surfaces; DeltaTrack adopted one of them (§1.2) |
| "`bill-stage` is the authoritative version identifier" | **Withdrawn.** One of at least three official notions, none shown canonical (§1.3) |
| Corpus proportions read as population facts | **Withdrawn** throughout; occurrence only (§1.0) |
| "`normalize_bill` is a misnamed parser" | **Withdrawn and replaced** with a more accurate and more damaging reading (§3.4) |
| XML parsing is "lossless" | **Withdrawn** (§5.1) |
| PDF recovery is "probabilistic" | **Withdrawn** — contradicts ADR 0008 (§5.1) |
| "the stage had no name, so it went unmeasured" | **Downgraded** from causal to associative (§3.6) |
| `changes` vs `amendment` as justified invented dialect | **Reclassified** (§1.5) |

---

## 2. Rebrand-resilience findings (preserved)

*Class C throughout; these are facts about this repository.*

**Branding is not materially coupled to this architecture.** 1,002 occurrences (603
`deltatrack`, 355 `DeltaTrack`, 44 `DELTATRACK`) collapse to four groups; one is structural.

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

**CI detects a rename, it does not suffer one.** `uv sync` fails on a hatch package/dir
mismatch; `conftest.py:41-90` aborts before collection if `deltatrack` resolves outside this
checkout's `src/`; `test_engine_installs.py` builds a real wheel. Path-based config is
unaffected. No partial rename produces a green run.

**No observed external consumer requires a compatibility namespace.** BillTrax's
`submodules/DeltaTrack/` is not a submodule (no `.gitmodules`); it is a tracked vendored
fork of the pre-#398 flat layout (last modified 2026-06-09, `ac29d7e`) doing
`sys.path.insert(...)` then `from bill_tree import normalize_bill` — bare names. It emits
its own shape and never reads canonical JSON. *Limit:* one checkout, one commit.

**Renaming during the frozen research work is unjustified.** 41 probes import `deltatrack`
(88 lines) under a git-blob-hash freeze (`x04_freeze_check.py` F2) and an amendment ledger
(F9); `external-validity/PRE-REGISTRATION.md:128` declares `reconstruct_hybrid.py` frozen
unmodified.

**`deltatrack → bill_diff` remains architecturally misleading**, and §4.2 adds the
grammatical reason.

---

## 3. Discoverability findings (preserved)

### 3.1 Three public surfaces disagree about whether input representation is a job

| Surface | Treatment | Evidence |
|---|---|---|
| Canonical contract | Property of the input | `versions.v1.source` is an `enum ["xml","pdf"]` (`schema:108`) |
| Web API | Parameter on one operation | `POST /api/compare?format=pdf\|xml&output=html\|json`, `_COMPARE` dispatch (`web/app.py:47,249-256`) |
| CLI | Selects the command | `./diff_bill.py compare A B` vs `./diff_pdf.py A B` |
| Python API | Encoded in six names | `compare_xml`, `compare_xml_html`, `compare_xml_trees_html`, `compare_xml_files_html`, `compare_pdfs`, `compare_pdfs_html` |

Two of four already do the right thing. The principle is half-adopted and undocumented.

### 3.2 The two CLIs use different grammars for one user intent

`./diff_bill.py compare <old.xml> <new.xml>` vs `./diff_pdf.py <v1.pdf> <v2.pdf>`;
descriptions read "Compare two bill XML versions" (`diff_bill.py:944`) and "Diff two PDF
bill versions" (`diff_pdf.py:601`). An agent generalizing from the first invokes
`diff_pdf.py compare A B` and gets an argparse error.

### 3.3 `--format` carries two meanings, and `source` carries two more

| Identifier | Surface | Meaning |
|---|---|---|
| `--format json\|html` | `diff_bill.py compare` | **Output** representation |
| `--format xml\|pdf\|both` | `fetch_bills.py download` | **Input** representation |
| `?format=pdf\|xml` | `POST /api/compare` | **Input** representation (output is a separate `output=`) |
| `--source govinfo\|api` | `fetch_bills.py` | **Provider / origin service** |
| `source: "xml"\|"pdf"` | canonical contract | **Input representation** |

`source` is the worse of the two, because the contract version is a schema `enum` — published, versioned, load-bearing. Four concepts are currently expressed by two overloaded words.

### 3.4 `parsers/` does not contain the primary XML entry point, and `normalize_bill` is not simply a misnamed parser

Rev. 3 called `normalize_bill` a parser wearing the wrong name. Reading the implementation
(`bill_tree.py:1470-1499`) shows that was too simple, and the accurate reading is worse for
the name rather than better.

```
serialized XML
  → ET.parse(xml_path)                     the actual XML parse (stdlib)
  → find_bill_bodies(root)                 source interpretation: which element(s) are the body
  → _extract_metadata(root, xml_path)      extraction: congress, type, number, version, title
  → extract_front_matter_nodes(...)        selection: form block + enacting clause
  → _walk_one_body(body) per body          structural transformation to BillNode
  → BillTree                               the project's representation
```

So `normalize_bill` **contains** a parse but is not one, and it is not a normalization
either. Conventionally, *normalize* means canonicalizing a representation while preserving
its information; this selects and discards. `BillNode` (`bill_tree.py:31-60`) is a flat
record of extracted strings that retains no XML, and `<quoted-block>` content is known to
be dropped (DeltaTrack#11).

The precise defect: **the name states one step of a five-step composite, and the step it
names is the one the function does not conventionally perform.** That is the same failure
mode ADR 0020 documented for `reconcile_moves` — an identifier that understates a
multi-stage responsibility — which makes it the better example, not the weaker one.

Separately, `parsers/` holds `pdf_text.py`, `pdf_anchors.py`, `committee_report.py`; the XML
entry point sits at package root. Both `compare/xml.py:7` and the `docs/architecture.md`
pipeline table label that stage **Parse** — so the docs also compress the composite into its
first step.

### 3.5 `view` is claimed twice before any `view` job exists

`formatters/view_model.py` (`DiffView`, `ChangeView`, `view_from_canonical()`) is the
presentation model *of a diff*; "full-bill view" (`README.md:195`, UI) is a *panel inside a
comparison report*. No standalone single-document capability ships.

### 3.6 Naming an implicit stage made a responsibility measurable

ADR 0020 identifies `reconcile_moves` as "a second retrieval pass, unnamed as such, running
after classification." Recognizing and naming that behaviour as a distinct retrieval stage
made the responsibility possible to reason about and measure independently; the resulting
probe found **496 recovered changes across 27 adjacent version pairs** of the committed
corpus, with no inspectable candidate set behind them.

*Rev. 3 wrote "the stage had no name, so it went unmeasured." That asserts causation the
evidence does not carry, and it is withdrawn.* The association is strong enough on its own:
the measurement arrived with the decomposition.

ADR 0020 also finds one similarity ratio serving five decisions spanning retrieval,
assignment, classification and presentation — including `formatters/_text.word_diff`, a
renderer recomputing an identity score against the differ's cutoff.

### 3.7 Overloaded terms

| Term | Distinct meanings |
|---|---|
| `normalize` | **4** — `normalize_bill` (a five-step composite, §3.4) · `normalize_header`/`_normalize_text` (string canonicalization) · `normalize_glyphs` (`pdf_text.py:179`, Unicode mapping) · `normalize_raw` (`pdf_text.py:128`, line-ending/soft-hyphen repair) |
| `extract` | **6** — `extract_clean_pages` · `extract_text_content`/`extract_display_text` · `extract_amounts` · `extract_front_matter_nodes` · `extract_anchors` · `extract_pre_text` |
| `diff` | **4 roles** — verb (`diff_bills`) · result (`BillDiff`, `NodeDiff`, `PdfDiff`) · subsystem (`diff_bill.py`) · qualifier (`diff_html`, `xml_diff_to_canonical`) |
| `view` | **3** (§3.5) |
| `format` / `source` | **4 concepts across two words** (§3.3) |
| `tree` | **2, asymmetrically named** — `BillTree`/`BillNode` vs `TreeNode`; `build_xml_tree(bill: BillTree) -> list[TreeNode]` |
| "bill type" | **2 across official surfaces**, before this repository names anything (§1.2) |

### 3.8 Consistently used, and worth protecting

`canonical` (ADR 0006), `anchor`, `level` (glossary-governed, `bill-structure.md:97`),
`slug` and version ordinal (ADR 0013), and the ADR 0019/0020 stage vocabulary.

### 3.9 The `compare` / `diff` distinction the architecture already supports

`compare/` is the composition layer — `docs/architecture.md` calls it "the product
surface", every entry point goes through it, its functions return finished artifacts.
`*Diff` types are results; `diff_bills()` is the core algorithm. **Compare-as-operation and
diff-as-result is already the architecture**; only the identifiers disagree (`diff_bill.py`
exposing subcommand `compare`; `/api/compare` whose errors say "Could not diff these
files").

### 3.10 Public boundary vs internal grouping — not a blanket verdict

| Name | Verdict | Reason |
|---|---|---|
| `formatters/` | **Acceptable** | Coherent output-side grouping; a caller asking "how do I get HTML?" lands correctly |
| `parsers/` | **Poor as a public boundary** | Excludes the XML entry point (§3.4); includes `committee_report.py`, validation ground truth (ADR 0009) with **no engine consumer** — importers are two tests and `scripts/build_validation.py` |
| `formatters/_text.py` | **Correct** | Genuine utility bucket (`word_diff`, `fmt_dollar`) and **private** |
| `version_stems.py` | **Acceptable** | Filename-convention plumbing; no domain concept underlies it |

The operative distinction is **public discovery boundary vs private implementation
grouping**, not domain-word vs generic-word.

---

## 4. Naming grammar — a convention, not a taxonomy

An exhaustive role taxonomy is withdrawn: `similarity` falsified the four-role version, and
a fifth role only postpones the same failure. A taxonomy is itself a dialect contributors
must learn, which contradicts §0. Recommend instead:

> **Names should make their technical role apparent and follow conventional grammatical
> expectations where those expectations exist.**

Operations read as verbs; entities, results, measures and capabilities read as nouns;
predicates read as predicates (`_is_uppercase_heading`, `text_similarity_at_least`);
exceptions follow established technical convention rather than a project scheme.

### 4.1 Where the convention is genuinely awkward

- **Measures and cutoffs.** `text_similarity()`, `SIMILARITY_THRESHOLD`, `MOVE_THRESHOLD`. Noun form is right; ADR 0020 reclassifies these as evidence signals and policy parameters, which is 0020's call, not 0021's.
- **Verb-first module names are sometimes right.** `diff_bill.py` reads as a verb phrase, defensible for an algorithm module. The defect is that the same token also names the result and the subsystem.
- **Private buckets stay legitimate** (§3.10).
- **Representation qualifiers are correct one layer down.** `compare_xml` / `compare_pdfs` are wrong as *the public surface* and right as implementations behind a dispatcher — exactly how `_COMPARE` uses them.

### 4.2 `bill_diff` — the ambiguity is live, not hypothetical

Within one package the token appears as subsystem (`diff_bill.py`), action (`diff_bills()`),
result (`BillDiff`), and serializer over the result (`bill_diff_to_dict()`), with word order
reversed between module and function. The repository already demonstrates the construction
fails to separate the three roles.

---

## 5. Technical vocabulary against conventional expectation

Test: *what would an experienced external practitioner or agent expect this term to mean?*

| Term | Conventional expectation | Repo usage | Verdict |
|---|---|---|---|
| `parse` | Serialized input → structured representation per a grammar/schema | `parse_lines`, `parse_summary_blocks` ✓; `ET.parse` inside `normalize_bill` ✓ — but the composite around it is labelled "Parse" in the docs | **Docs compress a composite** |
| `normalize` | Canonicalize a representation, preserving information | Three uses conform; `normalize_bill` neither preserves nor is a single step (§3.4) | **Violated once, prominently** |
| `extract` | Recover information from a container or unstructured source | Six meanings, spanning genuine extraction, element reading, and tree filtering | **Diluted** |
| `serialize` | In-memory structure → transportable representation | `serialize_tree`, `build_xml_full_text` | **Conforms** |
| `render` | Structured data → presentation output | `format_diff_html`, "Render" stage | **Conforms** |
| `validate` | Check against an explicit rule, contract, schema, or evidence | `test_validate_extraction`, `build_validation.py` against committee reports (ADR 0009) | **Conforms** |
| `match` / `compare` | IR / record-linkage sense | Governed by ADR 0020 | **Deferred to 0020** |
| `fetch` | Retrieve from a remote source | Tool named `fetch_bills.py`, primary verb `download`, plus a `fetch-index` subcommand | **Synonym drift** |

### 5.1 XML and PDF differ, and neither difference is what rev. 3 said it was

Two corrections, both mattering because ADR 0021 is about precise technical terminology.

**PDF recovery is not probabilistic.** ADR 0008 requires that "the same inputs always yield
byte-identical output" and states that the hard problems are "solved with deterministic
heuristics (#56), not by trading away reproducibility." Calling the PDF path probabilistic
contradicts a standing decision. The accurate distinction:

> XML arrives with explicit structural markup governed by a DTD and is transformed
> deterministically into the internal representation. PDF arrives as presentation-oriented
> content from which textual and structural information must be **recovered** using
> deterministic heuristics.

PDF is more inferential, more lossy, engine-sensitive and structurally ambiguous — all
without being nondeterministic.

**XML → BillTree is not lossless either.** `BillNode` retains no XML, the walk selects
rather than preserves, and `<quoted-block>` content is known to be dropped (DeltaTrack#11).
Rev. 3's "lossless" is withdrawn. Both paths lose information; they differ in *how much is
inferred* and *how much the source told you explicitly*.

**Consistency never overrides technical accuracy.** `parse` and `extract` must stay
distinct — collapsing them would erase the distinction ADR 0002, ADR 0012 and the
external-validity study exist to characterize, and would misrepresent the trust boundary
between the two paths to exactly the auditor §0 is written for. Two things share a name only
when they are the same concept.

---

## 6. Rebrand rule (final form)

> **Product branding must not be a load-bearing technical identifier. Branded identity may
> appear in explicitly product-facing metadata and copy, but protocol, capability,
> dispatch, compatibility, and other technical behavior must not depend on the brand.**
>
> **Producer-side obligation.** A field carrying replaceable product identity must say so
> where the contract is defined. "Consumers must not depend on it" is unenforceable against
> a consumer never told; an unannotated free-string field in a versioned public contract is
> an invitation to branch on it.

| Case | Ruling | Basis |
|---|---|---|
| `schema_version` | **Load-bearing technical identity.** Consumers may and should dispatch on it | ADR 0006 versions it |
| `generator.name` | **Replaceable product identity.** May stay `"deltatrack"` or carry a successor brand; must be documented as non-dispatchable | `{"type":"string"}`, no `const`/`enum` (`schema:45-51`); no test asserts it; no observed consumer reads it |
| `from deltatrack.x import y` | **Violation** — every consumer must spell the brand | §2 |
| Docstrings; user-facing copy in `compare/` | **Fine** | Nothing spells them back |
| `DELTATRACK_SECRET_*` canaries | **Exempt and immutable** | Evidence of observed egress |
| `tempfile(prefix="deltatrack-")` | **Fine** | Ephemeral |
| `title="DeltaTrack API"` | **Fine** — product-facing OpenAPI metadata | |

**Recommended action:** document `generator.name`'s semantics in `schema/canonical-diff.md`
and add a `description` to the schema's `generator` object. **Do not change the emitted
value.** Under the rule this is the producer-side obligation, not a concession; it costs a
paragraph, changes no output bytes, and is the only finding that gets harder the longer it
waits.

---

## 7. What I recommend rejecting or amending in the proposed policy

This section is adversarial by design: the spike was asked to falsify the naming policy it
was evaluating rather than agree with it. "The brief" and the numbered items refer to a
review proposal that set out a candidate policy — an authority model, a naming grammar, a
set of rules to freeze. The numbering is preserved so each objection stays traceable.

### 7.1 Reject "No DeltaTrack dialect" as an absolute

ADR 0020 deliberately creates project-specific vocabulary: the four-stage boundary and the
`Candidate` / `Proposal` / `Retriever invocation` distinction are this project's. The
*words* are borrowed from IR and record linkage; the *specific structure* is not. It was the
right call, and §3.6 shows the decomposition arrived with a measurement.

Stated absolutely, the principle is unfalsifiable-by-design and would be cited against good
decisions later — which matters because ADRs are append-only.

**Amend to:** *no unnecessary or undocumented dialect.* A project-specific term is
legitimate when neither authoritative legislative nor conventional technical vocabulary is
accurate, and when used it must be defined in one discoverable place.

### 7.2 Reject ranked institutional authority; scope authority to concept *and representation*

A ranking of Congress → GPO → Style Manual fails on the evidence. `bill` is the umbrella in
the document-XML surface (§1.6); under "Congress outranks GPO" it would be wrong across
nearly the whole codebase.

But rev. 3's replacement — assigning broad concepts to institutions — is also too coarse,
because §1.2 and §1.3 show **the same institution using one term for different concepts on
different surfaces**. GovInfo's packaging vocabulary and the congressional DTD's attribute
vocabulary both have official standing and disagree.

**Amend to:** *use the normative authority governing the specific concept **and its
representation***.

| Concept and representation | Normative authority |
|---|---|
| Bill/amendment XML attribute and element semantics | The applicable congressional XML specification — `bill.dtd`, `amend.dtd`, and their data dictionaries |
| Package, path and metadata terminology | GovInfo documentation |
| Legislative procedure and forms of legislative business | Congress / House / Senate authorities |
| Publishing and typography | GPO stylesheet and GPO Style Manual |
| Budget and appropriations terminology | GAO, statutory, or congressional authority as applicable |
| Deliberately-defined project architecture concepts | The narrower ADR that defined them |

With the conflict rule retained: where scopes overlap and sources differ, document the
conflict and record which was chosen and why. §1.2 and §1.3 are the first two entries, and
neither is resolvable without class-A sources.

### 7.3 Amend the representation freeze — provider is a fourth concept

"Input representation, output representation, operation, and result are different concepts"
should be adopted and extended: **provider/origin is a fourth**, because `source` means
provider in `fetch_bills.py --source govinfo|api` and input representation in the contract's
`source` enum (§3.3). A freeze naming only three leaves the worse collision unaddressed.

Also amend the absolute form. "Input format is never a job selector" is too strong. Prefer:

> Input representation should not create a separate user-facing operation when user intent
> and the operation's contract are otherwise the same. It may remain visible where it
> implies different guarantees, different supported operations, different failure modes, or
> materially different semantics.

### 7.4 A glossary-membership CI gate cannot ship yet

A gate asserting "every public identifier's head term is in the glossary" cannot be built
until the glossary exists, and the glossary depends on class-A research this spike did not
do. Freezing it as a requirement would freeze blocked work.

What can ship now is narrower and purely structural: one meaning per public flag name across
all surfaces, and a CLI-grammar assertion. Precedent exists —
`tests/test_structure_vocabulary_gate.py` is an ADR-0018 vocabulary gate that scans by
subtraction so a new module is guarded by default, and carries `TestDetectorCanFail` proving
the detector still fires.

### 7.5 "Do not freeze `bill`" is right, and understates what is known

Correct not to freeze it as a namespace. But the open questions are narrower and answerable
rather than one unanswerable one: (a) the umbrella problem, visible in class-C evidence
alone via `BILL_TYPES`'s four non-bill entries (§1.4); (b) the "bill type" cross-surface
collision (§1.2); (c) whether an umbrella term other than `bill` has official standing —
which needs class-A confirmation (§1.6).

### 7.6 Accepted without amendment

Loosening the grammar; narrower ADRs staying authoritative in scope; the rebrand rule plus
producer obligation; grandfathering without freezing a mechanism; not freezing `view`; not
freezing a job taxonomy; preserving parse/extract; public boundary vs private grouping;
discoverability and auditability as criteria.

---

## 8. Migration recommendation

**Do not rename now.** No architectural justification; the frozen research surface forbids
it; no deadline.

- **Current finding, dated 2026-08-07.** On the consumer graph as observed today, no compatibility namespace is justified: nothing is published to any index, the one observed consumer is a vendored fork importing bare module names, and CI fails closed on every partial-rename path.
- **Deferred decision.** The migration mechanism is chosen at rename time against the graph as it stands then. **Not frozen.**

**Triggers to reassess:** the product is rebranded; the distribution is about to be
published to an index; a consumer begins importing `deltatrack.*`; the external-validity
freeze lifts; #62 is resolved and a package split is on the table architecturally.

**Do not change yet:** package name, distribution name, `GENERATOR_NAME`'s value, frozen
probes, deployment names, prose, and the 37 `src/` self-imports — they are the *easiest*
references to change at rename time, so converting them removes ~10% of the work while
adding a style split with the other 320 sites today.

---

## 9. ADR 0021 — number, scope, and open questions

### Number: 0021

`0019-observation-identity.md` merged on `origin/develop` (Accepted, 2026-08-07).
`0020-matching-stages.md` on `origin/docs/adr-0020-matching-stages`, open as PR #562. A scan
of `docs/decisions/` across every remote branch returns nothing above 0020. Re-check at
draft time: two landed in one day.

Operational: `tests/test_adr_index.py` regenerates both the `AGENTS.md` index and the README
Records table and fails if either disagrees, so a new ADR requires updating both in the same
change. `docs/decisions/README.md` requires `Status: Proposed` on the PR, flipped to
`Accepted` by a maintainer on merge.

### Tensions with existing ADRs and code

Findings for the ADR to acknowledge, **not** work to schedule. None is remediable without
class-A sources, and each belongs to a narrower ADR.

| Tension | Owner | Handling in 0021 |
|---|---|---|
| "Bill type" collision across official surfaces (§1.2) | ADR 0006 owns the contract | Acknowledge as the motivating example. **Do not change the contract** |
| Version identity: three official notions plus one local (§1.3) | ADR 0013 / 0006 | Acknowledge; ADR 0013's ordinal is justified; `label`'s backing is open research |
| `bill` as umbrella over `amendment-doc` and resolutions (§1.4) | ADR 0006 / 0013 | Acknowledge, explicitly without a causal claim about DeltaTrack#11 |
| `normalize_bill` names one step of a composite (§3.4) | — | Name as an example. **Do not schedule a rename** |
| `source` collision (§3.3) | ADR 0006 and the tooling | Covered by the four-concept separation |
| ADR 0020's `similarity` reclassification (§4.1) | ADR 0020 | **0020 governs. 0021 must not touch it** |
| ADR 0018's vocabulary gate | ADR 0018 | 0021's gate proposals must compose with it, not replace it |

### Open questions

1. **The class-A sources this spike did not read** — `bill.dtd`, `amend.dtd` and their data dictionaries, GovInfo documentation, Congress.gov's glossary. Every semantic claim in §1 depends on them. This is the single largest gap.
2. Will the product be rebranded, and when? Everything in §8's triggers keys off it.
3. Should `VersionInfo.label` be backed by an official vocabulary, and which of the three?
4. Is `bill` the right umbrella, or does another term have official standing (§1.6)?
5. Mixed-representation comparison (`compare v1.pdf v2.xml`) — nothing supports it; the web API takes one `format` for both files; ADR 0010 is silent.
6. What is the canonical term for single-document presentation? Not `view` (§3.5).
7. Does anything downstream read `generator.name`?
8. Will the BillTrax fork re-converge? Decides whether a compatibility layer is ever justified.
9. Who owns `deltatrack.agoradmv.org`, the certificate and the systemd unit, and what is the lead time?
10. Should `parsers/committee_report.py` be in the shipped engine at all? No engine consumer; independent of naming.
