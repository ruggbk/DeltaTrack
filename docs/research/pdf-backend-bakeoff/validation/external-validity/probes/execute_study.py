"""execute_study -- the canonical execution path. A43, made executable.

RESULT-BEARING. This is the component that decides WHICH DOCUMENTS ENTER THE STUDY, so it can
move every realized result. It introduces NO new methodological rule: the population is the
one frozen in `results/holdout_membership.json`, the arms are the frozen runners, the frame is
built by the frozen `build_frames.build_document_frame`, and the extraction scope is the whole
document, which is what section 6 already means by "100 % of the holdout" and what
`cross_engine_control` already documents as "what the canonical writer uses".

THE DEFECT THIS REPAIRS. Every result-bearing API below this one takes a CALLER-SUPPLIED list
of documents -- `build_oracle.build(documents)`, `s1_control.write_s1_control(documents)`,
`cross_engine_control.write_cross_engine_control(documents)`, `score_metrics.ScoreInputs(frames)`.
Each of them is correct in isolation and none of them can tell whether the list it received is
the frozen population, a subset of it, or a different population entirely. There was no
component whose job was to produce that list from the committed authority, and no writer for
the `results/frames.json` those stages consume. A study can therefore have been run on 16 of
17 members with every downstream gate green, because nothing downstream knows what 17 is.

    THE POPULATION AUTHORITY IS THE COMMITTED MEMBERSHIP, AND THERE IS NO OTHER.

Every descriptor this module hands to a later stage is re-checked against that authority at
the moment it is handed over -- not once at load, because a list can be filtered after it is
loaded and the filtering is exactly the failure mode. `assert_population_complete` therefore
runs inside `write_frames`, `oracle_documents` and `control_documents`, and a subset, a
superset, a duplicate or a substituted member refuses there rather than scoring quietly.

WHAT THIS COMPONENT MAY NOT DECIDE. The membership; the extraction scope (whole document);
which population or stratum a member carries (both are read from the authority, never
inferred); the frame contents; any metric, threshold, route or decision rule. Its only
permitted freedom is the JSON layout of the `frames.json` wrapper, which `score_metrics`
deliberately does not read -- it consumes the document frames themselves.

WHY THE WRITER IS HERE AND NOT IN `build_frames`. No frozen source requires a location.
HARNESS-PLAN section 2 lists `results/frames.json` under `build_frames`' "outputs" but is
explicitly "not frozen protocol"; `score_metrics` says only that "the `frames.json` wrapper
belongs to whatever writes it". `build_frames` is deliberately pure -- it has no file I/O at
all -- and keeping it that way preserves the property its controls rely on, that a frame is a
value with no ambient state. The wrapper lives with the population assembler that knows what a
complete population is, because the bijection assertion is the only thing the wrapper is for.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import build_frames as BF
import build_oracle as BO
import run_extended
import run_hybrid

HERE = Path(__file__).resolve()
EV = HERE.parents[1]

MEMBERSHIP = EV / "results" / "holdout_membership.json"
DOCS_DIR = EV / "holdout"
FRAMES = EV / "results" / "frames.json"

FRAMES_SCHEMA = "frames/1"

# THE EXTRACTION SCOPE IS THE WHOLE DOCUMENT. Not a parameter, deliberately. Every x-probe
# carries its own PAGE_LIMIT and every one of them labels it "a machinery demonstration
# window, NOT a census"; a limit reaching this path would silently shrink the M0/M7/M9
# denominators section 6 defines over "100 % of the holdout", and would shrink the D-frame
# census that decides whether Rule 1 may run at all. There is no spelling of a prefix here.
PAGE_LIMIT = None

# refusal classes -- every one deterministic, none a value
MEMBERSHIP_MISSING = "MEMBERSHIP_MISSING"
MEMBERSHIP_MALFORMED = "MEMBERSHIP_MALFORMED"
MEMBER_MALFORMED = "MEMBER_MALFORMED"
DUPLICATE_MEMBER_ID = "DUPLICATE_MEMBER_ID"
DECLARED_COUNT_MISMATCH = "DECLARED_COUNT_MISMATCH"
UNKNOWN_POPULATION = "UNKNOWN_POPULATION"
INVALID_STRATUM = "INVALID_STRATUM"
SOURCE_FILE_MISSING = "SOURCE_FILE_MISSING"
SOURCE_SHA_MISMATCH = "SOURCE_SHA_MISMATCH"
POPULATION_INCOMPLETE = "POPULATION_INCOMPLETE"
POPULATION_HAS_EXTRA = "POPULATION_HAS_EXTRA"
POPULATION_DUPLICATED = "POPULATION_DUPLICATED"
POPULATION_SUBSTITUTED = "POPULATION_SUBSTITUTED"
FRAMES_ARTIFACT_MISSING = "FRAMES_ARTIFACT_MISSING"
FRAMES_ARTIFACT_MALFORMED = "FRAMES_ARTIFACT_MALFORMED"
FRAMES_ARTIFACT_UNCOMMITTED = "FRAMES_ARTIFACT_UNCOMMITTED"
FRAME_POPULATION_MISMATCH = "FRAME_POPULATION_MISMATCH"
FRAME_METADATA_MISMATCH = "FRAME_METADATA_MISMATCH"
# A43.6 -- the ID-ONLY hole. A descriptor carrying the right id and the wrong result-bearing
# metadata passed every handover, because completeness was a set comparison over ids.
DESCRIPTOR_METADATA_MISMATCH = "DESCRIPTOR_METADATA_MISMATCH"
EXTRACTION_SOURCE_MISMATCH = "EXTRACTION_SOURCE_MISMATCH"
NON_CANONICAL_AUTHORITY = "NON_CANONICAL_AUTHORITY"
FRAME_SOURCE_MISMATCH = "FRAME_SOURCE_MISMATCH"
DUPLICATE_FRAME = "DUPLICATE_FRAME"
# A43.8 -- the authority was read from the WORKING TREE and never proven to still be the
# committed frozen artifact at the moment it was trusted.
CANONICAL_AUTHORITY_UNCOMMITTED = "CANONICAL_AUTHORITY_UNCOMMITTED"
CANONICAL_AUTHORITY_NOT_FROZEN = "CANONICAL_AUTHORITY_NOT_FROZEN"


class ExecutionPathError(Exception):
    """The canonical path is NOT EXECUTABLE on this input. Never a value, never a skip.

    Every condition below is one where continuing would produce a study over a population
    that is not the frozen one, which is indistinguishable downstream from a valid run.
    """

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


@dataclass(frozen=True)
class DocumentDescriptor:
    """One frozen member, resolved to everything the later stages need.

    Frozen so a stage cannot mutate a descriptor it was handed and change its own input.
    """

    document_id: str
    kind: str
    population: str
    stratum: int
    pdf_path: Path
    sha256: str
    pages: int


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _known_strata(doc: dict) -> frozenset[int]:
    """The stratum ids the membership itself declares. Not a literal in this file.

    A hardcoded 1..8 here would be a second authority for a fact the membership already
    carries, which is the exact defect A43 repairs in `build_oracle.HOLDOUT_GUARD`.
    """
    strata = doc.get("strata")
    if not isinstance(strata, list) or not strata:
        raise ExecutionPathError(MEMBERSHIP_MALFORMED, {"why": "no strata block"})
    out = set()
    for s in strata:
        if not isinstance(s, dict) or not isinstance(s.get("stratum"), int):
            raise ExecutionPathError(MEMBERSHIP_MALFORMED, {"why": "malformed stratum record", "record": s})
        out.add(s["stratum"])
    return frozenset(out)


def load_population(membership_path: Path = MEMBERSHIP, docs_root: Path = DOCS_DIR) -> tuple[DocumentDescriptor, ...]:
    """Every frozen member, resolved and verified. The ONLY way a descriptor is created.

    Validation is not a courtesy here: each check below is a way the population could differ
    from the frozen one while every downstream gate stayed green.

    The parameters exist for SYNTHETIC and DEVELOPMENT controls only. `canonical_population()`
    takes none, and is what the canonical path and G5 use -- a caller-supplied membership path
    is not evidence about the frozen population, the same reason `score_metrics` refuses a
    caller-supplied R1 scalar.
    """
    membership_path, docs_root = Path(membership_path), Path(docs_root)
    if not membership_path.is_file():
        raise ExecutionPathError(MEMBERSHIP_MISSING, {"path": str(membership_path)})
    try:
        doc = json.loads(membership_path.read_text())
    except json.JSONDecodeError as exc:
        raise ExecutionPathError(MEMBERSHIP_MALFORMED, {"error": str(exc)}) from exc

    members = doc.get("members")
    if not isinstance(members, list) or not members:
        raise ExecutionPathError(MEMBERSHIP_MALFORMED, {"why": "no members"})

    known_strata = _known_strata(doc)
    seen: set[str] = set()
    out: list[DocumentDescriptor] = []
    for m in members:
        if not isinstance(m, dict):
            raise ExecutionPathError(MEMBER_MALFORMED, {"member": m})
        mid = m.get("id")
        for field in ("id", "kind", "population", "stratum", "files"):
            if m.get(field) in (None, "", []):
                raise ExecutionPathError(MEMBER_MALFORMED, {"member": mid, "missing": field})
        if mid in seen:
            raise ExecutionPathError(DUPLICATE_MEMBER_ID, {"member": mid})
        seen.add(mid)

        if m["population"] not in BF.KNOWN_POPULATIONS:
            raise ExecutionPathError(UNKNOWN_POPULATION, {"member": mid, "population": m["population"]})
        if m["stratum"] not in known_strata:
            raise ExecutionPathError(
                INVALID_STRATUM, {"member": mid, "stratum": m["stratum"], "known": sorted(known_strata)}
            )

        files = m["files"]
        if not isinstance(files, list) or len(files) != 1:
            # The frozen population is one file per member. More than one would make
            # "the document" ambiguous for every per-document metric and denominator.
            raise ExecutionPathError(
                MEMBER_MALFORMED, {"member": mid, "why": "expected exactly 1 file", "n": len(files or [])}
            )
        f = files[0]
        for field in ("path", "sha256", "pages"):
            if f.get(field) in (None, ""):
                raise ExecutionPathError(MEMBER_MALFORMED, {"member": mid, "missing": f"files[0].{field}"})

        pdf_path = docs_root / f["path"]
        if not pdf_path.is_file():
            raise ExecutionPathError(SOURCE_FILE_MISSING, {"member": mid, "path": str(pdf_path)})
        # THE SOURCE IS HASHED, not trusted by name. F2 checks this at gate time; checking it
        # again HERE is what stops a file swapped between the gate and the run from being
        # extracted, and it is the only check that sees the bytes the runners will actually read.
        actual = sha256_of(pdf_path)
        if actual != f["sha256"]:
            raise ExecutionPathError(SOURCE_SHA_MISMATCH, {"member": mid, "recorded": f["sha256"], "actual": actual})

        out.append(
            DocumentDescriptor(
                document_id=mid,
                kind=m["kind"],
                population=m["population"],
                stratum=m["stratum"],
                pdf_path=pdf_path,
                sha256=actual,
                pages=f["pages"],
            )
        )

    # The membership declares its own size. A member silently dropped from `members` while
    # `n_members` still reads 17 is a corrupted authority, not a smaller population.
    for field, value in (("n_members", len(out)), ("n_documents", len(out))):
        declared = doc.get(field)
        if declared is not None and declared != value:
            raise ExecutionPathError(DECLARED_COUNT_MISMATCH, {"field": field, "declared": declared, "actual": value})
    return tuple(out)


def canonical_population() -> tuple[DocumentDescriptor, ...]:
    """THE population. No parameters, so there is no channel through which it can be steered."""
    assert_canonical_authority()
    return load_population()


def frozen_member_ids(membership_path: Path = MEMBERSHIP) -> frozenset[str]:
    """The frozen id set, read from the authority. `build_oracle`'s guard is derived from this."""
    doc = json.loads(Path(membership_path).read_text())
    return frozenset(m["id"] for m in doc.get("members", []))


def is_canonical_authority(membership_path: Path = MEMBERSHIP) -> bool:
    """Is this THE committed membership, as opposed to a SYNTHETIC/DEVELOPMENT fixture?"""
    try:
        return Path(membership_path).resolve() == MEMBERSHIP.resolve()
    except OSError:
        return False


def assert_canonical_authority(membership_path: Path = MEMBERSHIP) -> None:
    """A43.8 -- the canonical authority must still BE the frozen artifact when it is trusted.

    THE DEFECT THIS CLOSES. Every check in this module reads `holdout_membership.json` from
    the WORKING TREE. x04's F1/F10/F11 prove it is committed, clean and identical to the
    population freeze -- but they prove it AT GATE TIME. Execution happens afterwards, and
    nothing re-established it. Measured, with a simulated VALID boundary and the canonical
    membership edited so member A pointed at member B's path and SHA:

        canonical_population()      ACCEPTED -- 116-hr-7611 resolved to 115-hr-5961/rh.pdf
        assert_population_complete  ACCEPTED
        control_documents           ACCEPTED
        document_strata             ACCEPTED
        assert_source_permitted     ACCEPTED   (the last guard before extraction)

    A43.6's descriptor checks cannot see this and are not weakened by it: they compare the
    descriptor against the authority, and here THE AUTHORITY ITSELF MOVED, so the two agree --
    both wrong. Re-hashing the source cannot see it either, because the mutated authority
    records the hash of the file it now points at. An authority is only worth comparing
    against while it is the frozen one, which is a fact about git and not about its contents.

    NOT IMPOSED ON FIXTURES. A SYNTHETIC or DEVELOPMENT membership is untracked by design, so
    requiring it to be committed would refuse every control while proving nothing about the
    canonical run. The restriction attaches to the canonical PATH, not to the concept.

    x04 IS THE SINGLE DEFINITION of both "committed" and "the frozen population", reused here
    rather than restated. A second spelling would be a second thing to keep in agreement --
    the defect A43.2 already repaired for the holdout guard.
    """
    if not is_canonical_authority(membership_path):
        return
    from x04_freeze_check import POPULATION_FREEZE_COMMIT, blob_sha, committed

    if not committed(MEMBERSHIP):
        raise ExecutionPathError(
            CANONICAL_AUTHORITY_UNCOMMITTED,
            {"path": str(MEMBERSHIP), "why": "untracked, or modified against HEAD"},
        )
    have = blob_sha(MEMBERSHIP)
    want = blob_sha(MEMBERSHIP, POPULATION_FREEZE_COMMIT)
    if not want or have != want:
        raise ExecutionPathError(
            CANONICAL_AUTHORITY_NOT_FROZEN,
            {"blob": have, "frozen_blob": want, "population_freeze_commit": POPULATION_FREEZE_COMMIT},
        )


def authority_index(membership_path: Path = MEMBERSHIP) -> dict[str, dict]:
    """id -> the authority's own record of that member. The comparison target for A43.6."""
    doc = json.loads(Path(membership_path).read_text())
    out = {}
    for m in doc.get("members", []):
        f = (m.get("files") or [{}])[0]
        out[m["id"]] = {
            "kind": m.get("kind"),
            "population": m.get("population"),
            "stratum": m.get("stratum"),
            "path": f.get("path"),
            "sha256": f.get("sha256"),
        }
    return out


def assert_population_complete(population: tuple[DocumentDescriptor, ...], membership_path: Path = MEMBERSHIP) -> None:
    """The population handed to a stage IS the frozen one -- BY ID AND BY METADATA.

    Checked at the handover and not only at load, because `load_population` returns a tuple
    that any caller can slice. Omission and substitution are reported as DIFFERENT refusals:
    a 16-of-17 run and a 17-with-one-swapped run are different failures, and collapsing them
    would hide which one happened.

    A43.6 -- THE ID SET WAS NOT ENOUGH, and the hole was real rather than theoretical.
    Completeness compared `{d.document_id}` against the frozen ids and nothing else, so a
    descriptor could carry the correct id with a substituted `pdf_path`, `population` or
    `stratum` and pass every handover. Measured on DEVELOPMENT material, all three were
    accepted, and all three are result-bearing:

        pdf_path   -> the frame was built from the OTHER document's bytes while still carrying
                      the frozen document_sha256 -- a frame that misdescribes its own
                      provenance, which is the key every downstream join uses
        population -> c_frame_selected 3 -> 0 (the C-frame draw is P-head-only)
        stratum    -> document_strata changed, which section 4.5's adequacy count reads

    Every result-bearing field is therefore compared against the authority's own record.
    `pages` deliberately is not: no rule reads it, and the SOURCE BYTES it would only proxy for
    are verified directly at the point of extraction.
    """
    frozen_records = authority_index(membership_path)
    frozen = frozenset(frozen_records)
    ids = [d.document_id for d in population]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ExecutionPathError(POPULATION_DUPLICATED, {"duplicated": dupes})
    got = set(ids)
    missing, extra = sorted(frozen - got), sorted(got - frozen)
    if missing and extra:
        raise ExecutionPathError(POPULATION_SUBSTITUTED, {"missing": missing, "extra": extra})
    if missing:
        raise ExecutionPathError(POPULATION_INCOMPLETE, {"missing": missing, "n": len(got), "frozen": len(frozen)})
    if extra:
        raise ExecutionPathError(POPULATION_HAS_EXTRA, {"extra": extra})

    for d in population:
        want = frozen_records[d.document_id]
        mismatches = {
            field: (value, want[field])
            for field, value in (
                ("kind", d.kind),
                ("population", d.population),
                ("stratum", d.stratum),
                ("sha256", d.sha256),
            )
            if value != want[field]
        }
        # The path is compared by its RECORDED SUFFIX, not absolutely: `docs_root` is a
        # SYNTHETIC/DEVELOPMENT seam, so an absolute comparison would refuse every control
        # while proving nothing more about the canonical run, whose docs_root is the default.
        if want["path"] and not str(d.pdf_path).endswith(str(want["path"])):
            mismatches["path"] = (str(d.pdf_path), want["path"])
        if mismatches:
            raise ExecutionPathError(DESCRIPTOR_METADATA_MISMATCH, {"member": d.document_id, "fields": mismatches})


# ------------------------------------------------------------------ stage 1: the frames


def build_document_frame_for(descriptor: DocumentDescriptor, membership_path: Path = MEMBERSHIP) -> dict:
    """Run both frozen arms over the WHOLE document and build the frozen frame.

    `assert_source_permitted` is called first and is the frozen gate: a confirmatory member
    may not be opened while the execution boundary is not VALID. It is deliberately called
    here, at the point of extraction, rather than once by the caller.

    A43.6 -- THE BYTES ABOUT TO BE EXTRACTED ARE RE-HASHED HERE, against the authority and not
    against the descriptor. Hashing at load proves what was true at load; this is the only
    check that sees the file the runners are about to open, and it is what closes the
    substituted-path channel at the exact moment it would do damage. Comparing to the
    descriptor's own `sha256` would be circular -- a substituted descriptor carries whatever
    hash it likes.

    ORDER MATTERS, and the first spelling of this had it wrong. The re-hash READS THE FILE, so
    running it first meant a confirmatory member's bytes were read before the gate that decides
    whether it may be opened at all, and a pre-boundary holdout reported a hash mismatch instead
    of `HOLDOUT_BEFORE_EXECUTION_BOUNDARY`. Authorization is the more fundamental question and
    is asked first; the substitution check then runs on material we are permitted to open.
    """
    # A43.8 first: it reads git and the manifest, never the PDF, so it does not reintroduce
    # the ordering defect above -- and an authority worth consulting is a precondition for
    # both of the checks that follow.
    assert_canonical_authority(membership_path)
    BO.assert_source_permitted(descriptor.document_id, descriptor.pdf_path)
    recorded = authority_index(membership_path).get(descriptor.document_id, {}).get("sha256")
    actual = sha256_of(descriptor.pdf_path)
    if recorded is None or actual != recorded:
        raise ExecutionPathError(
            EXTRACTION_SOURCE_MISMATCH,
            {
                "member": descriptor.document_id,
                "path": str(descriptor.pdf_path),
                "recorded": recorded,
                "actual": actual,
            },
        )
    h_pages = run_hybrid.run(descriptor.pdf_path, limit=PAGE_LIMIT)
    x_pages, _summary = run_extended.run(descriptor.pdf_path, limit=PAGE_LIMIT)
    return BF.build_document_frame(descriptor.sha256, descriptor.document_id, descriptor.population, h_pages, x_pages)


def _authority_label(membership_path: Path) -> str:
    """Study-relative when the authority is the committed one, absolute otherwise.

    A SYNTHETIC control's membership lives outside the study tree, and `relative_to` raises
    on it. The canonical artifact still records the plain committed path, so a reviewer can
    see at a glance whether a frames.json was built from the authority or from a fixture.
    """
    path = Path(membership_path)
    try:
        return str(path.relative_to(EV))
    except ValueError:
        return str(path)


def frames_document(population: tuple[DocumentDescriptor, ...], membership_path: Path = MEMBERSHIP) -> dict:
    """The `frames.json` payload: one frame per frozen member, and the bijection asserted.

    THE BIJECTION IS THE POINT. `build_frames` cannot see the population -- it takes one
    document at a time -- so "every frozen member has exactly one frame" is not a property any
    existing component could hold. It is asserted here before the artifact exists, and again
    in `load_frames` after it is read back.
    """
    assert_population_complete(population, membership_path)
    frames = [build_document_frame_for(d, membership_path) for d in population]

    built = [f["document"] for f in frames]
    expected = [d.document_id for d in population]
    if sorted(built) != sorted(expected):
        raise ExecutionPathError(FRAME_POPULATION_MISMATCH, {"built": sorted(built), "expected": sorted(expected)})

    return {
        "schema": FRAMES_SCHEMA,
        "population_authority": _authority_label(membership_path),
        "n_documents": len(frames),
        "page_limit": PAGE_LIMIT,
        "page_limit_note": "None means the WHOLE document -- section 6's '100 % of the holdout'",
        "execution_boundary_state": BO.execution_boundary_state(),
        "documents": [
            {"document": d.document_id, "population": d.population, "stratum": d.stratum, "sha256": d.sha256}
            for d in population
        ],
        "frames": frames,
    }


def write_frames(
    population: tuple[DocumentDescriptor, ...],
    out_path: Path | None = None,
    membership_path: Path = MEMBERSHIP,
) -> dict:
    """Write the canonical `results/frames.json`. Refuses before a VALID boundary.

    A43.6 -- THE CANONICAL ARTIFACT MAY ONLY BE BOUND TO THE CANONICAL AUTHORITY. The
    `membership_path` seam exists for SYNTHETIC and DEVELOPMENT controls, and nothing stopped
    it being combined with the canonical `out_path`: a frames.json at the canonical location,
    built from a fixture population, recording that fixture as its own `population_authority`.
    The two seams are independently reasonable and their combination is not.
    """
    out_path = Path(out_path) if out_path else FRAMES
    if out_path.resolve() == FRAMES.resolve() and Path(membership_path).resolve() != MEMBERSHIP.resolve():
        raise ExecutionPathError(
            NON_CANONICAL_AUTHORITY,
            {"out_path": str(out_path), "membership_path": str(membership_path), "required": str(MEMBERSHIP)},
        )
    assert_canonical_authority(membership_path)
    BO.assert_write_permitted(out_path)
    payload = frames_document(population, membership_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, default=str))
    return payload


# ------------------------------------------- stage 2+: consume the COMMITTED upstream artifact


def load_frames(
    path: Path | None = None,
    population: tuple[DocumentDescriptor, ...] | None = None,
    *,
    require_committed: bool = True,
    membership_path: Path = MEMBERSHIP,
) -> dict:
    """Read `frames.json` BACK FROM DISK, so a later stage consumes a committed artifact.

    HARNESS-PLAN section 1: "Each stage's output is a committed JSON artifact, so a later
    stage never re-derives an earlier stage's decisions." Passing the in-memory payload
    straight from `write_frames` into the oracle would satisfy the types and break that rule
    silently -- the frames the oracle used would be the ones in RAM, not the ones a reviewer
    can read. `require_committed` makes the rule executable rather than advisory.
    """
    path = Path(path) if path else FRAMES
    # A43.8 -- a canonical artifact may not be CONSUMED against a drifted authority either.
    # Every check below compares the artifact to the manifest, so the manifest must first be
    # the frozen one for those comparisons to mean anything.
    assert_canonical_authority(membership_path)
    if not path.is_file():
        raise ExecutionPathError(FRAMES_ARTIFACT_MISSING, {"path": str(path)})
    if require_committed:
        from x04_freeze_check import committed

        try:
            is_committed = committed(path)
        except ValueError:
            # Outside the repository entirely, so it cannot be committed. Reported as the
            # same refusal rather than a ValueError escaping as an unhandled crash.
            is_committed = False
        if not is_committed:
            raise ExecutionPathError(FRAMES_ARTIFACT_UNCOMMITTED, {"path": str(path)})
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ExecutionPathError(FRAMES_ARTIFACT_MALFORMED, {"error": str(exc)}) from exc
    if doc.get("schema") != FRAMES_SCHEMA or not isinstance(doc.get("frames"), list):
        raise ExecutionPathError(FRAMES_ARTIFACT_MALFORMED, {"schema": doc.get("schema")})

    # A43.6 -- EVERY FRAME IS CHECKED AGAINST THE AUTHORITY, unconditionally and before any
    # consumer can read it. This does not need the `population` argument: the artifact claims
    # a document identity per frame, and that claim is checkable on its own. A frame built
    # from substituted bytes, or under the wrong population, is refused here even if the
    # caller passes no population at all -- the arm of load_frames a downstream stage is most
    # likely to use.
    records = authority_index(membership_path)
    for f in doc["frames"]:
        did = f.get("document")
        want = records.get(did)
        if want is None:
            raise ExecutionPathError(FRAME_POPULATION_MISMATCH, {"frame_document_not_a_member": did})
        bad = {
            field: (f.get(key), want[field])
            for field, key in (("sha256", "document_sha256"), ("population", "population"))
            if f.get(key) != want[field]
        }
        if bad:
            raise ExecutionPathError(FRAME_SOURCE_MISMATCH, {"member": did, "fields": bad})

    # A43.7 -- THE FRAME SET IS A PROPERTY OF THE ARTIFACT, not of the caller's argument.
    #
    # The bijection used to sit inside `if population is not None`, so an artifact whose every
    # surviving frame was individually valid passed when no population was supplied. Measured:
    # a truncated artifact loaded with 1 frame, and a duplicated one with 3 frames, against a
    # 2-member authority. Per-frame validity cannot see either -- deleting a frame leaves the
    # rest correct, and a duplicate IS correct, twice.
    #
    # The artifact must therefore carry EXACTLY ONE frame per member of the authority, checked
    # unconditionally. `population` now adds only its descriptor checks, and the old
    # artifact-vs-population comparison is dropped as redundant: artifact == authority holds
    # here and population == authority holds in assert_population_complete, so the two agree
    # by transitivity rather than by a third comparison.
    ids = [f.get("document") for f in doc["frames"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ExecutionPathError(DUPLICATE_FRAME, {"duplicated": dupes, "n_frames": len(ids)})
    missing, extra = sorted(set(records) - set(ids)), sorted(set(ids) - set(records))
    if missing or extra:
        raise ExecutionPathError(
            FRAME_POPULATION_MISMATCH,
            {"missing": missing, "extra": extra, "n_frames": len(ids), "n_authority": len(records)},
        )

    if population is not None:
        assert_population_complete(population, membership_path)
    return doc


def oracle_documents(
    frames_doc: dict, population: tuple[DocumentDescriptor, ...], membership_path: Path = MEMBERSHIP
) -> list[dict]:
    """`build_oracle.build`'s `documents`, assembled from the authority -- never transcribed.

    The stratum comes from the committed membership, not from the frame and not from a
    caller. A stratum handed in by hand is a second authority for a fact the population
    already carries, and section 4.5's "strata filled" count reads it.
    """
    assert_population_complete(population, membership_path)
    by_id = {f["document"]: f for f in frames_doc["frames"]}
    missing = sorted(d.document_id for d in population if d.document_id not in by_id)
    if missing:
        raise ExecutionPathError(FRAME_POPULATION_MISMATCH, {"missing_frames": missing})

    out = []
    for d in population:
        frame = by_id[d.document_id]
        # The frame carries the document's own identity; if it disagrees with the authority
        # the join is against a different document than the one the population names.
        if frame.get("document_sha256") not in (None, d.sha256):
            raise ExecutionPathError(
                FRAME_METADATA_MISMATCH,
                {"member": d.document_id, "frame_sha": frame.get("document_sha256"), "membership_sha": d.sha256},
            )
        out.append({"frame": frame, "pdf_path": d.pdf_path, "stratum": d.stratum})
    return out


def _control_record(descriptor: DocumentDescriptor) -> dict:
    """ONE control-stage record, derived entirely from an authority-checked descriptor.

    Factored out of `control_documents` so the record's SHAPE has a single executable owner.
    `handoff_report` runs this exact function into the consumer's own reader, so a field
    dropped here is refused by the readiness gate rather than at execution time.

    A45 -- `document_sha256` IS RESULT-BEARING and is not decoration. A39.2 ranks the
    cross-engine page sample over `(document_sha256, page_number)`, so the value chosen here
    selects WHICH PAGES are measured, and `cross_engine_control.verified_sha256` then checks it
    against the source bytes. It comes from `DocumentDescriptor.sha256`, which
    `load_population` computed from the file it resolved and `assert_population_complete`
    (called by every caller of this function) has just compared against the authority's own
    record -- so it is the canonical membership SHA, not a second opinion about the document.
    """
    return {
        "document": descriptor.document_id,
        "document_sha256": descriptor.sha256,
        "pdf_path": descriptor.pdf_path,
    }


def control_documents(population: tuple[DocumentDescriptor, ...], membership_path: Path = MEMBERSHIP) -> list[dict]:
    """The `documents` list `write_s1_control` and `write_cross_engine_control` both take.

    A45 -- THE RECORD WAS INCOMPLETE FOR ONE OF ITS TWO CONSUMERS. It carried `document` and
    `pdf_path`, which is exactly what `write_s1_control` reads, and `write_cross_engine_control`
    additionally reads `document_sha256`. The canonical call
    `write_cross_engine_control(control_documents(population))` therefore failed closed with
    `KeyError('document_sha256')` and no `cross_engine_control.json` was written -- a MANDATORY
    `score_metrics` input, and the sole source of the PDFIUM-CONDITIONED FRAME qualification.

    The repair is not a longer list at the caller. A43 removed caller-supplied population and
    descriptor freedom on purpose, so the missing field is read from the SAME authority-checked
    descriptor as every other field: a result-bearing producer may not depend on a caller
    remembering which metadata its consumer happens to need.
    """
    assert_population_complete(population, membership_path)
    return [_control_record(d) for d in population]


def document_strata(population: tuple[DocumentDescriptor, ...], membership_path: Path = MEMBERSHIP) -> dict[str, int]:
    """`ScoreInputs.document_strata`, read from the committed membership by this module."""
    assert_population_complete(population, membership_path)
    return {d.document_id: d.stratum for d in population}


# ---------------------------------------------------------------- G5's liveness introspection

# The public surface G5 requires. Named here so the gate checks a CONTRACT rather than a
# file's existence: a module that imports but has lost `write_frames` is a broken execution
# path, and readiness must not stay green on it.
REQUIRED_CALLABLES = (
    "canonical_population",
    "assert_population_complete",
    "build_document_frame_for",
    "frames_document",
    "write_frames",
    "load_frames",
    "oracle_documents",
    "control_documents",
    "document_strata",
    # A45 -- the handoff check is part of the surface. Deleting it must turn G5 RED rather than
    # silently restoring the state in which readiness could not see an unusable handoff.
    "handoff_report",
)


def _handoff_probe() -> DocumentDescriptor:
    """A descriptor-shaped stand-in, used ONLY to exercise the record mapping.

    It never enters a population -- `assert_population_complete` refuses it on sight -- and no
    file is named that exists. Its only job is to be a legal input to `_control_record`, so the
    shape check below needs neither the frozen population nor a single byte of the holdout.
    """
    return DocumentDescriptor(
        document_id="HANDOFF-PROBE-NOT-A-MEMBER",
        kind="bill",
        population=sorted(BF.KNOWN_POPULATIONS)[0],
        stratum=0,
        pdf_path=Path("handoff-probe-not-a-file.pdf"),
        sha256="0" * 64,
        pages=0,
    )


def handoff_report() -> list[str]:
    """A45 -- is the record this module hands the control stages one its CONSUMER can read?

    THE DEFECT THIS CLOSES. G5 asked whether each result-bearing component existed and whether
    this module still had its entrypoints. Both were true, and the canonical call
    `write_cross_engine_control(control_documents(population))` still could not run: the
    producer emitted `{"document", "pdf_path"}` and the consumer reads `document_sha256`.
    Existence and callability are properties of each side alone; COMPATIBILITY is a property of
    the pair, and nothing held it. Readiness read green and execution failed closed on the
    first confirmatory artifact it tried to write.

    THIS IS NOT A FIELD-NAME COMPARISON. `_control_record` is the same function the canonical
    handoff maps over the population, and `document_inputs` is the same function
    `write_cross_engine_control` calls on every record it processes. Neither side reads a shared
    declaration, so the two can only agree by actually agreeing. Dropping `document_sha256` from
    `_control_record` turns this report -- and therefore G5 -- RED.

    NOTHING IS MEASURED AND NOTHING IS OPENED. `execution_path_report`'s standing property that
    it never opens a PDF or reads the holdout is preserved: the probe descriptor names a file
    that does not exist, and `document_inputs` only reads keys.
    """
    try:
        import cross_engine_control as CE
    except Exception as exc:
        return [f"cross_engine_control does not import, so the handoff cannot be checked: {exc}"]
    try:
        CE.document_inputs(_control_record(_handoff_probe()))
    except Exception as exc:
        return [
            "control_documents' record is REFUSED by its own consumer "
            f"(cross_engine_control.document_inputs): {type(exc).__name__}: {exc}"
        ]
    return []


def contract_report() -> list[str]:
    """Problems with this module's own contract. Empty means the path is live."""
    problems = [
        f"execute_study.{name} is missing or not callable"
        for name in REQUIRED_CALLABLES
        if not callable(globals().get(name))
    ]
    if PAGE_LIMIT is not None:
        problems.append(f"PAGE_LIMIT is {PAGE_LIMIT!r}; the canonical scope is the whole document")
    # Called through `globals()` for the same reason it is in REQUIRED_CALLABLES: a deleted
    # entrypoint must be REPORTED as a broken execution path, not raise a NameError out of the
    # gate that was asking whether the path is broken.
    fn = globals().get("handoff_report")
    if callable(fn):
        problems.extend(fn())
    return problems
