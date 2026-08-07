"""x04 -- audit the freeze and the execution gate. Exit non-zero if execution is forbidden.

PRE-REGISTRATION.md, "Execution gate".

TWO GATES, REPORTED SEPARATELY, because conflating them let this script print
"EXECUTION GATE OPEN" while the protocol's own gate listed two unmet prerequisites it
never checked. Freeze integrity is about whether the protocol and population are honestly
frozen; execution readiness is about whether the machinery the protocol requires exists.
Both must hold before anything may be scored.

FREEZE INTEGRITY
  F1  membership exists, is committed, and records a SHA-256 for every file
  F2  every file on disk still hashes to its recorded SHA-256
  F3  no member appears in any contamination class, or in the design-exposure list
  F4  the pre-registration's LAST-MODIFYING commit is an ancestor of the membership
      commit. First-commit is not enough: it proves only that SOME version of the
      protocol predated the population, which is exactly the hole the external review
      found -- the protocol was materially amended after selection.
  F5  nothing that would count as a confirmatory score exists yet
  F6  the answer key, if it exists, was committed BEFORE the adjudication, by git order

EXECUTION READINESS
  G1  the corrected extended-glyph adapter and reconstructor exist and are committed
  G2  their X2-a / X2-b assertion evidence exists, is committed, and PASSES -- recorded
      on DEVELOPMENT documents, never on the holdout
  G3  the adjudicator prompt exists and is committed
  G4  the design-exposure list exists and is non-empty

--self-test drives every gate that has a constructible known-bad case and requires each
to fail, because a gate that has never produced a negative cannot tell "ready" from
"blind".
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[4]

MEMBERSHIP = EV / "results" / "holdout_membership.json"
CONTAM = EV / "results" / "contamination.json"
EXPOSURE = EV / "results" / "design_exposure.json"
PREREG = EV / "PRE-REGISTRATION.md"
DOCS_DIR = EV / "holdout"
KEY = EV / "results" / "oracle_key.json"
ADJ = EV / "results" / "oracle_adjudicated.json"
SCORES = EV / "results" / "scores.json"

# Execution prerequisites named by PRE-REGISTRATION.md's execution gate.
ADAPTER = EV / "probes" / "pdfium_extended_corrected.py"
RECONSTRUCTOR = EV / "probes" / "reconstruct_extended_corrected.py"
X2_EVIDENCE = EV / "results" / "x2_contract_assertions.json"
ADJUDICATOR_PROMPT = EV / "probes" / "adjudicator_prompt.md"
AMENDMENTS = EV / "PRE-EXECUTION-AMENDMENTS.md"
# The one-way boundary. Before it: no confirmatory output may exist, and SUBSTANTIVE
# pre-execution amendments are allowed. After it: confirmatory output may exist, and a
# scoring-rule change is a DEVIATION, not an amendment.
EXECUTION_MARKER = EV / "results" / "EXECUTION-START.json"

AMENDMENT_CLASSES = {"CLERICAL", "SUBSTANTIVE", "TOOLING"}
# Paths that are outputs of running the gate itself, or scratch, and are not part of the
# frozen study surface F9 polices.
F9_IGNORE = {"results/DEVIATIONS.md"}


def marker_commit() -> str:
    """The commit that authorized confirmatory execution, or "" if none."""
    return last_commit(EXECUTION_MARKER) if EXECUTION_MARKER.exists() else ""


def amendment_commits(records: list[dict]) -> dict[str, str]:
    """Last-modifying commit of each amendment's touched files, by amendment id."""
    out = {}
    for rec in records:
        commits = [last_commit(EV / f) for f in rec.get("files_touched", []) if (EV / f).exists()]
        # `rev-list --count` returns a STRING, so an unconverted max() compares
        # lexicographically and "9" beats "1003" -- selecting the wrong commit as an
        # amendment's latest touch, which would silently misjudge the one-way boundary.
        out[rec.get("id", "?")] = max(commits, key=lambda c: int(git("rev-list", "--count", c) or 0)) if commits else ""
    return out


def parse_amendments() -> tuple[list[dict], list[str]]:
    """Amendment records from the fenced JSON blocks in PRE-EXECUTION-AMENDMENTS.md.

    Returns (records, errors). Kept in the prose file so an amendment cannot be declared
    in a machine-readable side-channel that no reviewer reads.
    """
    if not AMENDMENTS.exists():
        return [], ["PRE-EXECUTION-AMENDMENTS.md missing"]
    text = AMENDMENTS.read_text()
    records, errors = [], []
    for block in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S):
        try:
            rec = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"unparseable amendment block: {exc}")
            continue
        for key in ("id", "class", "confirmatory_output_at_time", "affects_membership", "files_touched"):
            if key not in rec:
                errors.append(f"amendment {rec.get('id', '?')} missing {key}")
        if rec.get("class") not in AMENDMENT_CLASSES:
            errors.append(f"amendment {rec.get('id', '?')} has class {rec.get('class')!r}")
        if rec.get("confirmatory_output_at_time") != "none":
            errors.append(f"amendment {rec.get('id', '?')} was made with confirmatory output in existence")
        if rec.get("affects_membership"):
            errors.append(f"amendment {rec.get('id', '?')} claims to change MEMBERSHIP -- that is a re-selection")
        if rec.get("class") == "CLERICAL" and rec.get("affects_scoring_rule"):
            errors.append(f"amendment {rec.get('id', '?')} is CLERICAL but changes a scoring rule")
        if rec.get("class") == "TOOLING" and rec.get("affects_scoring_rule"):
            errors.append(f"amendment {rec.get('id', '?')} is TOOLING but changes a scoring rule")
        records.append(rec)

    # A declared amendment is not automatically acceptable just because a path appears in
    # files_touched. The rest of these are the ways a declaration can still be a fiction.
    ids = [r.get("id") for r in records]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"duplicate amendment id {dup!r}")

    for rec in records:
        for f in rec.get("files_touched", []):
            if (EV / f).exists():
                continue
            # A path may legitimately be absent if the amendment DELETED it -- but only
            # when it is actually gone from the tree AND was present in history.
            deleted = git("log", "--diff-filter=D", "--format=%H", "-1", "--", str((EV / f).relative_to(REPO)))
            if not deleted:
                errors.append(f"amendment {rec.get('id', '?')} touches {f}, which neither exists nor was deleted")

    # A file whose change alters scoring must not be hidden under a TOOLING declaration
    # while a SUBSTANTIVE amendment quietly relies on it.
    substantive = {f for r in records if r.get("class") == "SUBSTANTIVE" for f in r.get("files_touched", [])}
    tooling_only = {f for r in records if r.get("class") == "TOOLING" for f in r.get("files_touched", [])}
    for f in sorted(substantive & tooling_only):
        errors.append(f"{f} is declared under both a SUBSTANTIVE and a TOOLING amendment")

    # ONE-WAY BOUNDARY: no SUBSTANTIVE amendment after execution was authorized.
    marker = marker_commit()
    if marker:
        commits = amendment_commits(records)
        for rec in records:
            if rec.get("class") != "SUBSTANTIVE":
                continue
            c = commits.get(rec.get("id", "?"), "")
            if c and not is_ancestor(c, marker):
                errors.append(f"SUBSTANTIVE amendment {rec.get('id', '?')} lands after the execution-start marker")
    return records, errors


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()


def committed(path: Path) -> bool:
    """Tracked by git AND identical to the committed version.

    "Tracked" alone is a PROXY: `git ls-files --error-unmatch` succeeds for a file with
    uncommitted modifications, so every gate built on it validated the WORKING TREE
    against itself rather than against the freeze. Demonstrated: deleting 7 members from
    holdout_membership.json and their PDFs, without committing, made the whole gate report
    FREEZE INTEGRITY COMPLETE over a 10-document population while the committed freeze was
    17. Frozen means frozen in git, not merely present on disk.
    """
    if not path.exists():
        return False
    rel = str(path.relative_to(REPO))
    if not git("ls-files", "--error-unmatch", rel):
        return False
    return not git("status", "--porcelain", "--", rel)


def first_commit(path: Path) -> str:
    out = git("log", "--reverse", "--format=%H", "--", str(path.relative_to(REPO)))
    return out.splitlines()[0] if out else ""


def last_commit(path: Path) -> str:
    return git("log", "-1", "--format=%H", "--", str(path.relative_to(REPO)))


def is_ancestor(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    r = subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=REPO, capture_output=True, check=False)
    return r.returncode == 0


def preselection_exposure(population_commit: str) -> tuple[dict[str, set[str]], str, list[str]]:
    """The exposure inventory as it stood IMMEDIATELY BEFORE the population was committed.

    This is the only state that can decide freshness. It is read from git at
    `<population_commit>~1`, so it is immutable, cannot be edited by any later run, and
    by construction cannot contain exposure that this study itself caused by committing
    its own holdout.

    Returns (disqualifying classes, resolved commit, errors).
    """
    errors: list[str] = []
    if not population_commit:
        return {}, "", ["no population commit"]
    pre = git("rev-parse", f"{population_commit}~1")
    if not pre:
        return {}, "", [f"cannot resolve {population_commit}~1"]

    rel_c = str(CONTAM.relative_to(REPO))
    rel_e = str(EXPOSURE.relative_to(REPO))
    raw_c = git("show", f"{pre}:{rel_c}")
    raw_e = git("show", f"{pre}:{rel_e}")
    if not raw_c:
        errors.append(f"no contamination artifact at {pre[:8]}")
    if not raw_e:
        errors.append(f"no design-exposure artifact at {pre[:8]}")
    if errors:
        return {}, pre, errors

    try:
        contam, exposure = json.loads(raw_c), json.loads(raw_e)
    except json.JSONDecodeError as exc:
        return {}, pre, [f"unparseable pre-selection artifact: {exc}"]

    # A pre-selection snapshot that already carries an own-study exemption would be one
    # written AFTER the population existed -- i.e. not a pre-selection snapshot at all.
    if "own_study_population_not_excluded" in contam.get("classes", {}):
        errors.append("pre-selection snapshot carries an own-study exemption; it is not pre-selection")

    classes = exposure_ids(contam, exposure)
    return classes, pre, errors


def f4_ok(protocol_commit: str, population_commit: str) -> bool:
    """F4's predicate: the protocol must be committed STRICTLY before the population.

    Strictly, because a commit is its own ancestor -- so without the inequality a protocol
    amended in the population's own commit would pass, which is exactly how a materially
    revised protocol was once reported as having predated its own holdout.
    """
    return (
        bool(protocol_commit)
        and bool(population_commit)
        and protocol_commit != population_commit
        and is_ancestor(protocol_commit, population_commit)
    )


def exposure_ids(contam: dict, exposure: dict) -> dict[str, set[str]]:
    """Every id a frozen member must not be. Keyed by class so a hit names its class."""
    # Only xml-only exposure is recorded-but-not-disqualifying: no PDF extractor has ever
    # run on those documents (PRE-REGISTRATION 4.3).
    #
    # There is deliberately NO own-study exemption here any more. Subtracting current
    # membership from historical exposure classes cannot distinguish
    #   (A) a document exposed BY this study, after it was frozen -- harmless, from
    #   (B) a document already exposed BEFORE selection and picked anyway -- disqualifying,
    # and it silently forgives (B). Freshness is therefore decided against the PRE-SELECTION
    # snapshot (see `preselection_exposure`), which cannot contain any exposure this study
    # later caused, so no exemption is needed at all.
    out: dict[str, set[str]] = {}
    for name, block in contam.get("classes", {}).items():
        if name in {"xml_only_not_excluded", "own_study_population_not_excluded"}:
            continue
        out[name] = set(block.get("bills", [])) | {r.upper() for r in block.get("reports", [])}
    ids = set(exposure.get("design_exposed", []))
    out["design_exposed"] = ids | {i.upper() for i in ids}
    return out


def contaminated(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, str]]:
    hits = []
    for m in members:
        mid = m["id"]
        for name, ids in lookup.items():
            if mid in ids or mid.upper() in ids:
                hits.append((mid, name))
    return hits


def check_freeze(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    n_files = sum(len(m["files"]) for m in members)
    results.append(
        (
            "F1 membership exists, committed, every file hashed",
            bool(members)
            and committed(MEMBERSHIP)
            and not [f for m in members for f in m["files"] if not f.get("sha256")],
            f"{len(members)} members, {n_files} files, committed={committed(MEMBERSHIP)}"
            if members
            else "holdout_membership.json not written",
        )
    )

    # F2/F3 are assertions OVER the members. With no members they hold vacuously, and a
    # vacuous pass is indistinguishable from a real one.
    bad = []
    for m in members:
        for f in m["files"]:
            p = DOCS_DIR / f["path"]
            if not p.exists():
                bad.append(f"{f['path']}: absent")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                bad.append(f"{f['path']}: hash mismatch")
    results.append(
        (
            "F2 every holdout file matches its recorded SHA-256",
            bool(n_files) and not bad,
            "; ".join(bad) or (f"{n_files} files match" if n_files else "VACUOUS -- no files to check"),
        )
    )

    # F3 -- FRESHNESS AT ADMISSION, decided against the pre-selection snapshot.
    #
    # Not against the current inventory: once the holdout is committed, every member
    # appears in pdf_committed and pdf_in_history by construction, and "current exposure
    # minus current membership" forgives a document that was ALREADY exposed before it was
    # picked -- the one case freshness exists to catch.
    mc_for_pre = last_commit(MEMBERSHIP) if MEMBERSHIP.exists() else ""
    pre_classes, pre_commit, pre_errors = preselection_exposure(mc_for_pre)
    hits = contaminated(members, pre_classes)
    results.append(
        (
            "F3 no member was exposed BEFORE selection",
            bool(members) and not hits and not pre_errors,
            "; ".join(pre_errors + [f"{i} in {c}" for i, c in hits])
            or (
                f"{len(members)} members absent from every disqualifying class at {pre_commit[:8]}"
                if members
                else "VACUOUS -- no members to check"
            ),
        )
    )

    # F4 -- the LAST-modifying commit of the protocol, not the first.
    #
    # And the LAST-modifying commit of the membership, not its first: the design-era
    # population was withdrawn and a confirmatory one written to the same path, so
    # `git log --reverse` on that path still reports the DESIGN commit. Comparing against
    # it would judge the current protocol against a population that no longer exists --
    # and it read FAIL for exactly that reason before this was fixed.
    pl, pf = last_commit(PREREG), first_commit(PREREG)
    mc = last_commit(MEMBERSHIP) if MEMBERSHIP.exists() else ""
    results.append(
        (
            "F4 FINAL protocol committed before the population",
            f4_ok(pl, mc),
            f"prereg last={pl[:8] or 'UNCOMMITTED'} (first={pf[:8] or '-'}) membership={mc[:8] or 'UNCOMMITTED'}",
        )
    )

    # F5 -- NARROWED, deliberately. This establishes that no canonical score ARTIFACT
    # exists. It does NOT and cannot establish that no H/X computation was ever performed:
    # git cannot prove the absence of a command. The process claim ("confirmatory
    # extraction has not been run") is an ATTESTATION recorded in the execution-start
    # marker, and is evidentially weaker than this repository fact. The two are reported
    # as different things.
    authorized = bool(marker_commit())
    results.append(
        (
            "F5 no canonical score artifact exists (repository fact, not proof of non-execution)",
            authorized or not SCORES.exists(),
            "execution authorized -- scores permitted" if authorized else f"scores.json exists: {SCORES.exists()}",
        )
    )

    if KEY.exists() and ADJ.exists():
        # LAST-modifying commits, for the same reason F4 uses them: an artifact that is
        # withdrawn and re-created at the same path keeps its original first_commit, so a
        # first-commit comparison would prove the ordering of a key that no longer exists.
        # This is the identical defect F4 carried, in the check that proves BLINDING.
        kc, ac = last_commit(KEY), last_commit(ADJ)
        results.append(
            (
                "F6 answer key committed before adjudication",
                bool(kc) and bool(ac) and is_ancestor(kc, ac) and kc != ac,
                f"key={kc[:8] or 'UNCOMMITTED'} adjudication={ac[:8] or 'UNCOMMITTED'}",
            )
        )
    else:
        results.append(("F6 answer key ordering", True, "not applicable yet -- adjudication has not run"))

    # F7 -- SET EQUALITY, not "every manifest entry exists". F1/F2 iterate the manifest, so
    # a file sitting in the population directory that the manifest never names is invisible
    # to them. One did: an HTML error page saved as CRPT-118HRPT146.pdf by a rejected
    # download that was never deleted. A manifest is not authoritative if unmanifested
    # artifacts can sit beside it unnoticed.
    on_disk = {str(p.relative_to(DOCS_DIR)) for p in DOCS_DIR.rglob("*") if p.is_file()} if DOCS_DIR.exists() else set()
    manifested = {f["path"] for m in members for f in m["files"]}
    extra, missing = sorted(on_disk - manifested), sorted(manifested - on_disk)
    results.append(
        (
            "F7 holdout/ contains exactly the manifested files",
            bool(manifested) and not extra and not missing,
            (
                "; ".join([f"EXTRA {e}" for e in extra] + [f"MISSING {m}" for m in missing])
                or (
                    f"{len(on_disk)} files == {len(manifested)} manifested"
                    if manifested
                    else "VACUOUS -- empty manifest"
                )
            ),
        )
    )

    # F8 -- type validation. govinfo answers a missing package with HTTP 200 and HTML.
    not_pdf = []
    for path in sorted(manifested):
        p = DOCS_DIR / path
        try:
            if p.open("rb").read(5) != b"%PDF-":
                not_pdf.append(path)
        except OSError:
            not_pdf.append(f"{path} (unreadable)")
    results.append(
        (
            "F8 every manifested file is really a PDF",
            bool(manifested) and not not_pdf,
            "; ".join(not_pdf) or (f"{len(manifested)} files carry a %PDF- header" if manifested else "VACUOUS"),
        )
    )

    # F10 -- the frozen artifacts must have NO uncommitted change of any kind.
    #
    # Every other invariant reads the working tree. Without this one they validate the
    # working tree against itself: a tamper that edits the manifest AND removes the
    # matching PDFs is internally consistent, so F1/F2/F3/F7/F8 all pass and the gate
    # reports COMPLETE over a population that is not the committed one. Measured: 17
    # members silently became 10 and freeze integrity still read COMPLETE.
    frozen_paths = [MEMBERSHIP, CONTAM, EXPOSURE, PREREG, AMENDMENTS, DOCS_DIR]
    dirty = []
    for p in frozen_paths:
        if not p.exists():
            continue
        st = git("status", "--porcelain", "--", str(p.relative_to(REPO)))
        if st:
            dirty.extend(line.strip() for line in st.splitlines())
    results.append(
        (
            "F10 frozen artifacts have no uncommitted changes",
            not dirty,
            "; ".join(dirty[:6]) + (f" (+{len(dirty) - 6} more)" if len(dirty) > 6 else "")
            or f"{len(frozen_paths)} frozen paths clean against HEAD",
        )
    )

    # F9 -- anything in this study modified AFTER the population was frozen must be
    # declared as an amendment. This is the general form of the defect above: code or
    # prose changing under a frozen population without a record.
    records, errors = parse_amendments()
    declared = {f for r in records for f in r.get("files_touched", [])}
    changed_after = set()
    if mc:
        out = git("diff", "--name-only", f"{mc}..HEAD", "--", str(EV.relative_to(REPO)))
        for line in out.splitlines():
            rel = str(Path(line).relative_to(EV.relative_to(REPO)))
            if rel not in F9_IGNORE:
                changed_after.add(rel)
    undeclared = sorted(changed_after - declared)
    results.append(
        (
            "F9 post-freeze changes are declared amendments",
            not errors and not undeclared,
            "; ".join(errors + [f"UNDECLARED {u}" for u in undeclared])
            or f"{len(records)} amendments, {len(changed_after)} files changed since the freeze, all declared",
        )
    )
    return results


def check_execution(members: list[dict]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    have_adapter = committed(ADAPTER) and committed(RECONSTRUCTOR)
    results.append(
        (
            "G1 corrected extended-glyph adapter committed",
            have_adapter,
            f"adapter={committed(ADAPTER)} reconstructor={committed(RECONSTRUCTOR)}",
        )
    )

    # G2 -- the X2 assertions must have RUN and PASSED, on development documents.
    #
    # `population: "DEVELOPMENT"` is a SELF-REPORTED LABEL. Believing it is the same class
    # of proxy defect as trusting a `.pdf` filename over PDF bytes: an evidence file could
    # claim DEVELOPMENT while having been produced on holdout members. So the documents it
    # names are checked against membership directly, and the label is not sufficient.
    ok, detail = False, "x2_contract_assertions.json not written"
    if X2_EVIDENCE.exists():
        try:
            ev = json.loads(X2_EVIDENCE.read_text())
            a, b = ev.get("X2a_no_u0020"), ev.get("X2b_rule_recovers_engine_spaces")
            pop = ev.get("population", "")
            docs = ev.get("documents", [])
            member_ids = {m["id"] for m in members} | {m["id"].upper() for m in members}
            leaked = sorted({d for d in docs if d in member_ids or str(d).upper() in member_ids})
            ok = bool(a) and bool(b) and pop == "DEVELOPMENT" and bool(docs) and not leaked and committed(X2_EVIDENCE)
            detail = f"X2a={a} X2b={b} population={pop!r} docs={len(docs)} committed={committed(X2_EVIDENCE)}" + (
                f" -- HOLDOUT MEMBERS PRESENT: {leaked}" if leaked else ""
            )
        except (json.JSONDecodeError, AttributeError) as exc:
            detail = f"unreadable: {exc}"
    results.append(("G2 X2-a / X2-b assertions recorded, passing, on non-holdout documents", ok, detail))

    results.append(
        (
            "G3 adjudicator prompt committed",
            committed(ADJUDICATOR_PROMPT),
            str(ADJUDICATOR_PROMPT.relative_to(EV)) if committed(ADJUDICATOR_PROMPT) else "not committed",
        )
    )

    n = 0
    if EXPOSURE.exists():
        n = len(json.loads(EXPOSURE.read_text()).get("design_exposed", []))
    results.append(
        ("G4 design-exposure list present and non-empty", bool(n) and committed(EXPOSURE), f"{n} design-exposed ids")
    )
    return results


def render(title: str, results: list[tuple[str, bool, str]]) -> list[str]:
    width = max(len(n) for n, _, _ in results)
    print(f"\n== {title} ==")
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")
    return [n for n, ok, _ in results if not ok]


def self_test(contam: dict, exposure: dict) -> int:
    """Every gate with a constructible known-bad case must fail on it."""
    checks: list[tuple[str, bool]] = []
    lookup = exposure_ids(contam, exposure)

    poisoned = [{"id": contam["excluded_bills"][0], "kind": "bill", "files": []}]
    checks.append(("F3 detects a contaminated member", bool(contaminated(poisoned, lookup))))

    exposed = [{"id": exposure["design_exposed"][0], "kind": "bill", "files": []}]
    hits = contaminated(exposed, lookup)
    checks.append(("F3 detects a design-exposed member", any(c == "design_exposed" for _, c in hits)))

    # The two controls the freshness architecture turns on. Case B must FAIL and case A
    # must PASS, and a blanket "current exposure minus current membership" cannot tell
    # them apart -- which is why F3 reads the pre-selection snapshot instead.
    real_member = json.loads(MEMBERSHIP.read_text())["members"][0]["id"] if MEMBERSHIP.exists() else "999-hr-1"

    # CASE B: exposed BEFORE selection, then selected anyway, then also in own-study.
    pre_b = {"pdf_in_history": {real_member, real_member.upper()}}
    checks.append(
        (
            "F3 case B: pre-selection contamination is NOT erased by own-study membership",
            bool(contaminated([{"id": real_member, "files": []}], pre_b)),
        )
    )

    # CASE A: clean before selection; exposed only because its frozen PDF was committed.
    pre_a: dict[str, set[str]] = {"pdf_in_history": set(), "named_in_research": set()}
    checks.append(
        (
            "F3 case A: post-freeze self-exposure does NOT retroactively fail freshness",
            not contaminated([{"id": real_member, "files": []}], pre_a),
        )
    )

    # A snapshot carrying an own-study exemption was written AFTER the population existed,
    # so it is not a pre-selection snapshot and must be refused. HEAD~1 is such a state.
    _, _, errs_pre = preselection_exposure(git("rev-parse", "HEAD"))
    checks.append(
        (
            "F3 refuses a 'pre-selection' snapshot that carries an own-study exemption",
            any("not pre-selection" in e for e in errs_pre),
        )
    )

    checks.append(
        (
            "F2/F3 refuse to pass vacuously on an empty member list",
            not any(ok for _, ok, _ in check_freeze([], lookup)[1:3]),
        )
    )

    # F4's predicate, driven directly with real commits from this repository.
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD~1")
    checks.append(("F4 accepts a strict-ancestor protocol", f4_ok(parent, head)))
    checks.append(("F4 rejects a protocol amended in the population's OWN commit", not f4_ok(head, head)))
    checks.append(("F4 rejects a protocol committed AFTER the population", not f4_ok(head, parent)))
    checks.append(("F4 rejects an uncommitted protocol", not f4_ok("", head)))

    # F7 must close the gate when an unmanifested file appears in the population directory.
    # This is the exact defect that shipped: an HTML error page named .pdf, left by a
    # rejected download, invisible to every manifest-driven check.
    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    intruder = DOCS_DIR / "_selftest_intruder" / "not_a_member.pdf"
    try:
        intruder.parent.mkdir(parents=True, exist_ok=True)
        intruder.write_bytes(b"<!DOCTYPE html>\n")
        f7 = dict((n[:2], ok) for n, ok, _ in check_freeze(members, lookup))
        checks.append(("F7 detects an unmanifested file in holdout/", not f7["F7"]))
    finally:
        intruder.unlink(missing_ok=True)
        intruder.parent.rmdir()

    # F8 must reject a manifested file that is not actually a PDF.
    victim = None
    if members:
        victim = DOCS_DIR / members[0]["files"][0]["path"]
        saved_bytes = victim.read_bytes()
        try:
            victim.write_bytes(b"<!DOCTYPE html>\n" + saved_bytes[:100])
            f8 = dict((n[:2], ok) for n, ok, _ in check_freeze(members, lookup))
            checks.append(("F8 detects a manifested file that is not a PDF", not f8["F8"]))
        finally:
            victim.write_bytes(saved_bytes)

    # F9 must reject an amendment that claims to change membership.
    saved_amend = AMENDMENTS.read_text() if AMENDMENTS.exists() else None
    try:
        AMENDMENTS.write_text(
            '```json\n{"id": "SELFTEST", "class": "CLERICAL", "confirmatory_output_at_time": "none",'
            ' "affects_membership": true, "files_touched": []}\n```\n'
        )
        _, errs = parse_amendments()
        checks.append(("F9 rejects an amendment claiming to change membership", any("MEMBERSHIP" in e for e in errs)))
        AMENDMENTS.write_text(
            '```json\n{"id": "SELFTEST", "class": "CLERICAL", "confirmatory_output_at_time": "some",'
            ' "affects_membership": false, "files_touched": []}\n```\n'
        )
        _, errs = parse_amendments()
        checks.append(
            ("F9 rejects an amendment made after confirmatory output", any("in existence" in e for e in errs))
        )
    finally:
        if saved_amend is not None:
            AMENDMENTS.write_text(saved_amend)

    # F9 hardening: a declaration must not be acceptable merely because a path is listed.
    saved_amend2 = AMENDMENTS.read_text() if AMENDMENTS.exists() else None
    try:
        base = '{"id": "%s", "class": "%s", "confirmatory_output_at_time": "none", "affects_membership": false%s}'
        AMENDMENTS.write_text(
            "```json\n" + base % ("DUP", "TOOLING", ', "files_touched": []') + "\n```\n"
            "```json\n" + base % ("DUP", "TOOLING", ', "files_touched": []') + "\n```\n"
        )
        checks.append(("F9 rejects duplicate amendment ids", any("duplicate" in e for e in parse_amendments()[1])))

        AMENDMENTS.write_text(
            "```json\n" + base % ("GHOST", "TOOLING", ', "files_touched": ["probes/does_not_exist.py"]') + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects a files_touched path that neither exists nor was deleted",
                any("neither exists nor was deleted" in e for e in parse_amendments()[1]),
            )
        )

        AMENDMENTS.write_text(
            "```json\n" + base % ("S1", "SUBSTANTIVE", ', "files_touched": ["probes/m3_boundaries.py"]') + "\n```\n"
            "```json\n" + base % ("T1", "TOOLING", ', "files_touched": ["probes/m3_boundaries.py"]') + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects a file declared under BOTH substantive and tooling",
                any("both a SUBSTANTIVE and a TOOLING" in e for e in parse_amendments()[1]),
            )
        )

        AMENDMENTS.write_text(
            "```json\n" + '{"id": "X", "class": "TOOLING", "confirmatory_output_at_time": "none",'
            ' "affects_membership": false, "affects_scoring_rule": true, "files_touched": []}' + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects TOOLING that changes a scoring rule",
                any("TOOLING but changes a scoring rule" in e for e in parse_amendments()[1]),
            )
        )
    finally:
        if saved_amend2 is not None:
            AMENDMENTS.write_text(saved_amend2)

    # F10 must fire on an uncommitted edit to a frozen artifact. This is the control for
    # the tamper that made every other invariant pass over a 10-document population.
    if MEMBERSHIP.exists():
        saved_mem = MEMBERSHIP.read_text()
        try:
            doc = json.loads(saved_mem)
            doc["members"] = doc["members"][:10]
            MEMBERSHIP.write_text(json.dumps(doc, indent=1))
            tampered = json.loads(MEMBERSHIP.read_text())["members"]
            by_id = {n.split()[0]: ok for n, ok, _ in check_freeze(tampered, lookup)}
            checks.append(("F10 detects an uncommitted edit to the frozen manifest", not by_id["F10"]))
            checks.append(("F1 no longer calls a MODIFIED manifest committed", not by_id["F1"]))
        finally:
            MEMBERSHIP.write_text(saved_mem)

    # The execution boundary must refuse to open while readiness is closed.
    rc_auth = main(["--authorize-execution"])
    checks.append(("execution authorization is REFUSED while readiness is closed", rc_auth != 0))
    checks.append(("...and no marker was written", not EXECUTION_MARKER.exists()))

    # G2 must reject evidence that passed on the HOLDOUT rather than on development.
    saved = X2_EVIDENCE.read_text() if X2_EVIDENCE.exists() else None
    try:
        X2_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        X2_EVIDENCE.write_text(
            json.dumps(
                {
                    "X2a_no_u0020": True,
                    "X2b_rule_recovers_engine_spaces": True,
                    "population": "HOLDOUT",
                    "documents_checked": 5,
                }
            )
        )
        g2 = dict((n[:2], ok) for n, ok, _ in check_execution(members))
        checks.append(("G2 rejects assertions self-labelled HOLDOUT", not g2["G2"]))

        # The proxy defect: the LABEL says DEVELOPMENT while the documents are holdout
        # members. Believing the label is the same mistake as trusting a `.pdf` filename.
        leaked_id = members[0]["id"] if members else "113-hr-933"
        X2_EVIDENCE.write_text(
            json.dumps(
                {
                    "X2a_no_u0020": True,
                    "X2b_rule_recovers_engine_spaces": True,
                    "population": "DEVELOPMENT",
                    "documents": [leaked_id],
                }
            )
        )
        g2b = dict((n[:2], ok) for n, ok, _ in check_execution(members))
        checks.append(("G2 rejects evidence LABELLED development that names a holdout member", not g2b["G2"]))
    finally:
        if saved is None:
            X2_EVIDENCE.unlink(missing_ok=True)
        else:
            X2_EVIDENCE.write_text(saved)

    width = max(len(n) for n, _ in checks)
    print("== SELF-TEST: every gate must fail on its known-bad case ==")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}")
    bad = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} gates demonstrably able to fail")
    if bad:
        print("SELF-TEST FAIL: " + "; ".join(bad))
        return 1
    print("SELF-TEST PASS")
    return 0


def main(argv: list[str]) -> int:
    if not CONTAM.exists() or not EXPOSURE.exists():
        print("FATAL: run x01_contamination.py and x05_design_exposure.py first.")
        return 2
    contam = json.loads(CONTAM.read_text())
    exposure = json.loads(EXPOSURE.read_text())

    if "--self-test" in argv:
        return self_test(contam, exposure)

    if "--authorize-execution" in argv:
        # The ONE-WAY BOUNDARY is crossed here and nowhere else. Refused unless both gates
        # are open, so execution can never be authorized while a prerequisite is missing.
        members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
        lookup = exposure_ids(contam, exposure)
        f_res, g_res = check_freeze(members, lookup), check_execution(members)
        blocked = [n for n, ok, _ in f_res + g_res if not ok]
        if blocked:
            print("REFUSED: cannot authorize execution while these are open:\n  " + "\n  ".join(blocked))
            return 1
        if EXECUTION_MARKER.exists():
            print(f"REFUSED: already authorized at {marker_commit()[:8]}")
            return 1
        EXECUTION_MARKER.write_text(
            json.dumps(
                {
                    "authorized": True,
                    "head_at_authorization": git("rev-parse", "HEAD"),
                    "repository_fact": "no canonical score artifact existed at this commit",
                    "process_attestation": (
                        "The maintainer attests that no confirmatory H/X extraction had been run "
                        "on any holdout member before this marker. This is an ATTESTATION, not a "
                        "repository proof: git cannot establish that a command was never executed."
                    ),
                    "after_this_marker": [
                        "confirmatory output may exist",
                        "no further SUBSTANTIVE pre-execution amendment is permitted",
                        "a scoring-rule change becomes a DEVIATION, not an amendment",
                    ],
                },
                indent=1,
            )
        )
        print(f"AUTHORIZED. Commit {EXECUTION_MARKER.relative_to(EV)} to make the boundary immutable.")
        return 0

    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    lookup = exposure_ids(contam, exposure)

    freeze_failed = render("FREEZE INTEGRITY", check_freeze(members, lookup))
    exec_failed = render("EXECUTION READINESS", check_execution(members))

    print()
    print(f"FREEZE INTEGRITY:    {'COMPLETE' if not freeze_failed else 'INCOMPLETE -- ' + '; '.join(freeze_failed)}")
    print(f"EXECUTION READINESS: {'OPEN' if not exec_failed else 'CLOSED -- ' + '; '.join(exec_failed)}")
    print()
    if freeze_failed or exec_failed:
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    print("EXECUTION PERMITTED.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
