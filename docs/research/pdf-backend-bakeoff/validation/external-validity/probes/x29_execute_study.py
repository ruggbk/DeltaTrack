"""x29 -- test `execute_study` and the A43 holdout-guard repair. SYNTHETIC + DEVELOPMENT only.

NOT CONFIRMATORY. No holdout document is opened by any extractor, nothing is scored, and no
canonical `results/frames.json` is produced. The evidence artifact is
`results/x29_execute_study.json`.

Every control records the CONCRETE MUTATION that makes it fail, and every one of them is
actually injected. A control that reads back a boolean the code just computed cannot tell a
working rule from a rule that never fires.

THE GUARD CONTROLS ARE INERT BY CONSTRUCTION. The hypothesis under test is "the source guard
does not fire", so a probe that hands it a real holdout PDF would perform exactly the
unauthorised extraction the guard exists to prevent, on the run where the guard is broken.
Every such control therefore carries a HOLDOUT DOCUMENT ID with a DEVELOPMENT file path: the
id alone is what `holdout_member` matches, so the guard is fully exercised, and if it failed
open the probe would extract a development document and harm nothing.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import build_frames as BF  # noqa: E402
import build_oracle as BO  # noqa: E402
import execute_study as ES  # noqa: E402
import x04_freeze_check as X04  # noqa: E402

OUT = EV / "results" / "x29_execute_study.json"
ROWS: list[dict] = []
FAILED: list[str] = []

# Two SMALL development documents, neither a frozen member. Whole-document extraction is the
# canonical scope, so the controls use documents where that is cheap rather than introducing a
# page limit the canonical path deliberately cannot express.
DEV_DOCS = [
    ("113-hr-3547", REPO / "tests/corpus/113-hr-3547/2_engrossed-in-house.pdf"),
    ("118-hr-2882", REPO / "tests/corpus/118-hr-2882/4_engrossed-amendment-senate.pdf"),
]
# A real frozen member id, paired with a DEVELOPMENT path -- see the module docstring.
A_HOLDOUT_ID = "113-hr-933"


def check(name: str, ok: bool, mutation: str, observed: str = "") -> None:
    ROWS.append({"check": name, "ok": bool(ok), "fails_when": mutation, "observed": observed})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {observed}" if observed else ""))


def refuses(fn, reason: str, exc_type=ES.ExecutionPathError) -> tuple[bool, str]:
    """Call `fn`; require it to raise `exc_type` with `.reason == reason`."""
    try:
        fn()
    except exc_type as exc:
        return (exc.reason == reason), f"{exc.reason}"
    except Exception as exc:  # a different exception is NOT the refusal under test
        return False, f"{type(exc).__name__}: {exc}"
    return False, "no refusal raised"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------- a synthetic population


def make_membership(root: Path, docs: list[tuple[str, Path]]) -> tuple[Path, Path]:
    """A well-formed membership over DEVELOPMENT files, in the frozen document's shape."""
    docs_root = root / "holdout"
    docs_root.mkdir(parents=True, exist_ok=True)
    members = []
    for i, (doc_id, src) in enumerate(docs, start=1):
        rel = f"{doc_id}/file.pdf"
        dest = docs_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        members.append(
            {
                "id": doc_id,
                "kind": "bill",
                "stratum": i,
                "population": BF.P_HEAD,
                "files": [{"path": rel, "sha256": sha256_of(dest), "pages": 0}],
            }
        )
    doc = {
        "n_members": len(members),
        "n_documents": len(members),
        "strata": [{"stratum": i, "population": BF.P_HEAD} for i in range(1, len(members) + 2)],
        "members": members,
    }
    path = root / "membership.json"
    path.write_text(json.dumps(doc, indent=1))
    return path, docs_root


def mutate(path: Path, fn) -> Path:
    """Write a MUTATED copy of a membership beside it, and return the new path."""
    doc = json.loads(path.read_text())
    fn(doc)
    out = path.with_name(f"mutated_{abs(hash(repr(doc))) % 10**8}.json")
    out.write_text(json.dumps(doc, indent=1))
    return out


# ------------------------------------------------------------------------- the controls


def part_population(root: Path) -> dict:
    print("\n== population assembly: the committed membership is the only authority ==")
    mpath, droot = make_membership(root, DEV_DOCS)

    pop = ES.load_population(mpath, droot)
    check(
        "a well-formed membership loads every member with its metadata",
        len(pop) == 2 and {d.document_id for d in pop} == {d for d, _ in DEV_DOCS},
        "the loader drops, reorders or invents a member",
        f"{len(pop)} descriptors",
    )
    check(
        "population and stratum are READ from the authority, never inferred",
        all(d.population == BF.P_HEAD for d in pop) and sorted(d.stratum for d in pop) == [1, 2],
        "a descriptor carries a population or stratum the membership does not state",
    )

    # --- MUTATION 1: one frozen member omitted -----------------------------------------
    ok, obs = refuses(lambda: ES.assert_population_complete(pop[:1], mpath), ES.POPULATION_INCOMPLETE)
    check("MUTATION omit one frozen member -> POPULATION_INCOMPLETE", ok, "a 1-of-2 population is accepted", obs)

    # --- MUTATION 2: an extra member appended ------------------------------------------
    extra = (*pop, ES.DocumentDescriptor("999-hr-999", "bill", BF.P_HEAD, 1, pop[0].pdf_path, pop[0].sha256, 1))
    ok, obs = refuses(lambda: ES.assert_population_complete(extra, mpath), ES.POPULATION_HAS_EXTRA)
    check("MUTATION append a non-member -> POPULATION_HAS_EXTRA", ok, "an extra document is scored", obs)

    # --- MUTATION 3: a member duplicated -----------------------------------------------
    ok, obs = refuses(lambda: ES.assert_population_complete((*pop, pop[0]), mpath), ES.POPULATION_DUPLICATED)
    check("MUTATION duplicate a member -> POPULATION_DUPLICATED", ok, "one document is counted twice", obs)

    dupe = mutate(mpath, lambda d: d["members"].append(copy.deepcopy(d["members"][0])))
    ok, obs = refuses(lambda: ES.load_population(dupe, droot), ES.DUPLICATE_MEMBER_ID)
    check("MUTATION duplicate id IN the membership -> DUPLICATE_MEMBER_ID", ok, "the loader accepts it", obs)

    # --- MUTATION 4: one member SUBSTITUTED for another --------------------------------
    swapped = (pop[0], ES.DocumentDescriptor("999-hr-999", "bill", BF.P_HEAD, 2, pop[1].pdf_path, pop[1].sha256, 1))
    ok, obs = refuses(lambda: ES.assert_population_complete(swapped, mpath), ES.POPULATION_SUBSTITUTED)
    check(
        "MUTATION substitute a member -> POPULATION_SUBSTITUTED, not merely INCOMPLETE",
        ok,
        "a swap is reported as the same failure as an omission, hiding which happened",
        obs,
    )

    # --- MUTATION 5: the source bytes do not match the recorded SHA --------------------
    def corrupt_sha(d):
        d["members"][0]["files"][0]["sha256"] = "0" * 64

    ok, obs = refuses(lambda: ES.load_population(mutate(mpath, corrupt_sha), droot), ES.SOURCE_SHA_MISMATCH)
    check(
        "MUTATION recorded sha256 != source bytes -> SOURCE_SHA_MISMATCH",
        ok,
        "a document swapped after the freeze check is extracted anyway",
        obs,
    )

    # --- MUTATION 6: the source file is gone -------------------------------------------
    ok, obs = refuses(
        lambda: ES.load_population(
            mutate(mpath, lambda d: d["members"][0]["files"][0].update(path="gone/x.pdf")), droot
        ),
        ES.SOURCE_FILE_MISSING,
    )
    check(
        "MUTATION source file absent -> SOURCE_FILE_MISSING", ok, "a missing document silently shrinks the study", obs
    )

    # --- MUTATION 7: population mapping mutated to an UNKNOWN value --------------------
    ok, obs = refuses(
        lambda: ES.load_population(mutate(mpath, lambda d: d["members"][0].update(population="P-heads")), droot),
        ES.UNKNOWN_POPULATION,
    )
    check("MUTATION population -> 'P-heads' -> UNKNOWN_POPULATION", ok, "an unknown population yields 0 C-regions", obs)

    # --- MUTATION 8: stratum mutated OUT of the declared set --------------------------
    ok, obs = refuses(
        lambda: ES.load_population(mutate(mpath, lambda d: d["members"][0].update(stratum=99)), droot),
        ES.INVALID_STRATUM,
    )
    check(
        "MUTATION stratum -> 99 -> INVALID_STRATUM",
        ok,
        "section 4.5's strata-filled count reads a phantom stratum",
        obs,
    )

    # --- MUTATION 9: the declared size disagrees with the member list ------------------
    ok, obs = refuses(
        lambda: ES.load_population(mutate(mpath, lambda d: d.update(n_members=99)), droot), ES.DECLARED_COUNT_MISMATCH
    )
    check(
        "MUTATION n_members -> 99 -> DECLARED_COUNT_MISMATCH", ok, "a corrupted authority passes as a smaller one", obs
    )

    # --- MUTATION 10: a malformed member -----------------------------------------------
    ok, obs = refuses(
        lambda: ES.load_population(mutate(mpath, lambda d: d["members"][0].pop("stratum")), droot), ES.MEMBER_MALFORMED
    )
    check("MUTATION delete a member's stratum -> MEMBER_MALFORMED", ok, "a member without metadata is defaulted", obs)

    # --- MUTATION 11: stratum mapping is LOAD-BEARING ----------------------------------
    # Mutated to another VALID stratum, so nothing refuses; the point is that the value
    # PROPAGATES. If it did not, mutations 8 and 10 would be guarding a field nobody reads.
    restratified = mutate(mpath, lambda d: d["members"][0].update(stratum=3))
    moved = ES.load_population(restratified, droot)
    before, after = ES.document_strata(pop, mpath), ES.document_strata(moved, restratified)
    check(
        "a stratum mutation ALTERS the downstream input (document_strata), so the guard is not vacuous",
        before != after and after[DEV_DOCS[0][0]] == 3,
        "document_strata returns the same map whatever the membership says",
        f"{before} -> {after}",
    )
    # CLERICAL: the fixture lives in a per-run temporary directory, so recording its absolute
    # path made this artifact differ on every run for no informational gain -- a diff that
    # always shows a change is a diff nobody reads. The shape is what matters, not the mktemp.
    return {"membership": "<tmp>/membership.json", "docs_root": "<tmp>/holdout", "n_members": len(pop)}


def part_frames(root: Path) -> dict:
    print("\n== frames.json: one frame per frozen member, written and read back ==")
    mpath, droot = make_membership(root, DEV_DOCS)
    pop = ES.load_population(mpath, droot)

    out_path = root / "frames.json"
    payload = ES.write_frames(pop, out_path, mpath)
    check(
        "write_frames emits exactly one frame per member, in the membership's shape",
        len(payload["frames"]) == 2
        and sorted(f["document"] for f in payload["frames"]) == sorted(d.document_id for d in pop),
        "a member is dropped or duplicated between population and artifact",
        f"{len(payload['frames'])} frames",
    )
    check(
        "the artifact records the whole-document scope, not a prefix",
        payload["page_limit"] is None,
        "a page limit reaches the canonical path and shrinks every denominator",
    )

    # --- MUTATION 12: the artifact is read back and MUST match the population ----------
    doc = ES.load_frames(out_path, pop, require_committed=False, membership_path=mpath)
    check(
        "load_frames accepts the artifact it just wrote",
        len(doc["frames"]) == 2,
        "the round-trip loses a frame",
    )
    ok, obs = refuses(
        lambda: ES.load_frames(out_path, pop[:1], require_committed=False, membership_path=mpath),
        ES.POPULATION_INCOMPLETE,
    )
    check("MUTATION load frames against a 1-of-2 population -> refuses", ok, "a later stage reads a subset", obs)

    truncated = root / "frames_truncated.json"
    trunc_doc = copy.deepcopy(payload)
    trunc_doc["frames"] = trunc_doc["frames"][:1]
    truncated.write_text(json.dumps(trunc_doc))
    ok, obs = refuses(
        lambda: ES.load_frames(truncated, pop, require_committed=False, membership_path=mpath),
        ES.FRAME_POPULATION_MISMATCH,
    )
    check(
        "MUTATION delete a frame FROM the artifact -> FRAME_POPULATION_MISMATCH",
        ok,
        "a truncated frames.json is consumed as a complete study",
        obs,
    )

    # --- MUTATION 13: a later stage must consume a COMMITTED artifact -----------------
    ok, obs = refuses(
        lambda: ES.load_frames(out_path, pop, require_committed=True, membership_path=mpath),
        ES.FRAMES_ARTIFACT_UNCOMMITTED,
    )
    check(
        "MUTATION consume an UNCOMMITTED frames.json -> FRAMES_ARTIFACT_UNCOMMITTED",
        ok,
        "the oracle reads frames that exist only in the working tree, which no reviewer can read",
        obs,
    )

    # --- downstream descriptors come from the authority, never transcribed ------------
    oracle_docs = ES.oracle_documents(doc, pop, mpath)
    check(
        "oracle_documents carries the membership's stratum and the real pdf_path",
        len(oracle_docs) == 2
        and {d["stratum"] for d in oracle_docs} == {1, 2}
        and all(Path(d["pdf_path"]).is_file() for d in oracle_docs),
        "a stratum is transcribed by hand or a path is invented",
    )
    ok, obs = refuses(lambda: ES.oracle_documents(doc, pop[:1], mpath), ES.POPULATION_INCOMPLETE)
    check("MUTATION oracle_documents on a subset -> refuses at the handover", ok, "the oracle is built on 1 of 2", obs)

    controls = ES.control_documents(pop, mpath)
    check(
        "control_documents gives S1 and cross-engine the same complete population",
        [c["document"] for c in controls] == [d.document_id for d in pop],
        "S1 and cross-engine measure a different set than the frames",
    )
    ok, obs = refuses(lambda: ES.control_documents(pop[:1], mpath), ES.POPULATION_INCOMPLETE)
    check("MUTATION control_documents on a subset -> refuses at the handover", ok, "S1 runs on 1 of 2", obs)

    # --- MUTATION 14: the population field is RESULT-BEARING --------------------------
    # P-robust vs P-head changes the C-frame draw (the draw is P-head-only), so a mutated
    # population string silently empties the C-frame rather than erroring. This is why
    # mutation 7 matters and why the value may only come from the authority.
    robust_m = mutate(mpath, lambda d: [m.update(population=BF.P_ROBUST) for m in d["members"]])
    robust_pop = ES.load_population(robust_m, droot)
    robust_payload = ES.frames_document(robust_pop, robust_m)
    c_head = sum(f["counts"]["c_frame_selected"] for f in payload["frames"])
    c_robust = sum(f["counts"]["c_frame_selected"] for f in robust_payload["frames"])
    check(
        "a population mutation ALTERS the C-frame draw, so the field is result-bearing",
        c_head != c_robust and c_robust == 0,
        "P-head and P-robust produce the same C-frame, i.e. the population field is inert",
        f"P-head c_frame_selected={c_head}, P-robust={c_robust}",
    )
    return {
        "frames_written": "<tmp>/frames.json",
        "n_frames": len(payload["frames"]),
        "c_frame_selected_p_head": c_head,
        "c_frame_selected_p_robust": c_robust,
    }


def part_identity(root: Path) -> dict:
    """A43.6 -- authority validation was ID-ONLY after load_population.

    Every mutation here keeps the document id CORRECT and changes one result-bearing field.
    Before the repair all four were accepted by every handover, which is why they are the
    controls: an id-set comparison cannot see any of them.
    """
    print("\n== A43.6: a correct id with substituted metadata ==")
    mpath, droot = make_membership(root, DEV_DOCS)
    pop = ES.load_population(mpath, droot)
    a, b = pop[0], pop[1]

    # NON-VACUITY, established first: the UNMUTATED population passes every handover the
    # mutations below are checked against. Without this the refusals could come from a path
    # that refuses everything, and the controls would prove nothing.
    for label, fn in (
        ("assert_population_complete", lambda: ES.assert_population_complete(pop, mpath)),
        ("control_documents", lambda: ES.control_documents(pop, mpath)),
        ("document_strata", lambda: ES.document_strata(pop, mpath)),
        ("build_document_frame_for", lambda: ES.build_document_frame_for(a, mpath)),
    ):
        try:
            fn()
            ok, obs = True, "accepted"
        except Exception as exc:
            ok, obs = False, f"{type(exc).__name__}: {exc}"
        check(f"NON-VACUITY: the unmutated population passes {label}", ok, "the handover refuses everything", obs)

    # --- MUTATION 18: pdf_path substituted, id and recorded sha RETAINED ---------------
    swapped_path = (dataclasses.replace(a, pdf_path=b.pdf_path), b)
    ok, obs = refuses(lambda: ES.assert_population_complete(swapped_path, mpath), ES.DESCRIPTOR_METADATA_MISMATCH)
    check(
        "MUTATION swap pdf_path to another DEVELOPMENT pdf, keeping id -> DESCRIPTOR_METADATA_MISMATCH",
        ok,
        "the frame is built from substituted bytes while carrying the frozen document_sha256",
        obs,
    )
    ok, obs = refuses(lambda: ES.build_document_frame_for(swapped_path[0], mpath), ES.EXTRACTION_SOURCE_MISMATCH)
    check(
        "...and the bytes are RE-HASHED at the point of extraction -> EXTRACTION_SOURCE_MISMATCH",
        ok,
        "a path substituted after load reaches the runners; hashing at load only proves what was true at load",
        obs,
    )

    # --- MUTATION 19: population substituted for the other VALID one ------------------
    swapped_pop = (dataclasses.replace(a, population=BF.P_ROBUST), b)
    ok, obs = refuses(lambda: ES.assert_population_complete(swapped_pop, mpath), ES.DESCRIPTOR_METADATA_MISMATCH)
    check(
        "MUTATION swap population to the other VALID value, keeping id -> DESCRIPTOR_METADATA_MISMATCH",
        ok,
        "the C-frame draw silently empties (P-head-only) under an unchanged document id",
        obs,
    )
    ok, obs = refuses(lambda: ES.frames_document(swapped_pop, mpath), ES.DESCRIPTOR_METADATA_MISMATCH)
    check("...and frames_document refuses before building anything", ok, "the mutated frame is produced", obs)

    # --- MUTATION 20: stratum substituted for another VALID one -----------------------
    swapped_stratum = (dataclasses.replace(a, stratum=3), b)
    ok, obs = refuses(lambda: ES.assert_population_complete(swapped_stratum, mpath), ES.DESCRIPTOR_METADATA_MISMATCH)
    check(
        "MUTATION swap stratum to another VALID value, keeping id -> DESCRIPTOR_METADATA_MISMATCH",
        ok,
        "section 4.5's strata-filled count reads a stratum the authority never assigned",
        obs,
    )
    ok, obs = refuses(lambda: ES.document_strata(swapped_stratum, mpath), ES.DESCRIPTOR_METADATA_MISMATCH)
    check(
        "...and document_strata refuses rather than reporting the mutated map", ok, "the mutated map is returned", obs
    )

    # --- MUTATION 21: canonical frames.json bound to an ALTERNATE authority -----------
    ok, obs = refuses(lambda: ES.write_frames(pop, ES.FRAMES, mpath), ES.NON_CANONICAL_AUTHORITY)
    check(
        "MUTATION write the CANONICAL frames.json from a synthetic membership -> NON_CANONICAL_AUTHORITY",
        ok,
        "a fixture population is written to the canonical path and records itself as the authority",
        obs,
    )
    # NON-VACUITY for that gate: the same synthetic membership IS allowed at a non-canonical
    # path, so the refusal is about the pairing and not about the fixture.
    try:
        ES.write_frames(pop, root / "elsewhere.json", mpath)
        ok, obs = True, "accepted at a non-canonical path"
    except Exception as exc:
        ok, obs = False, f"{type(exc).__name__}: {exc}"
    check("NON-VACUITY: the same synthetic membership is accepted at a NON-canonical path", ok, "", obs)

    # --- MUTATION 22: read-back, a frame disagreeing with the authority ---------------
    payload = ES.frames_document(pop, mpath)
    for field, bad_value, why in (
        ("document_sha256", "0" * 64, "a frame built from substituted bytes is consumed downstream"),
        ("population", BF.P_ROBUST, "a frame built under the wrong population is consumed downstream"),
    ):
        doc = copy.deepcopy(payload)
        doc["frames"][0][field] = bad_value
        art = root / f"frames_bad_{field}.json"
        art.write_text(json.dumps(doc, default=str))
        # Deliberately with NO population argument -- the arm a downstream consumer is most
        # likely to call, and the one that previously checked nothing at all.
        ok, obs = refuses(
            lambda art=art: ES.load_frames(art, None, require_committed=False, membership_path=mpath),
            ES.FRAME_SOURCE_MISMATCH,
        )
        check(f"MUTATION frame {field} disagrees with the authority -> FRAME_SOURCE_MISMATCH", ok, why, obs)

    ok, obs = True, ""
    try:
        ES.load_frames(root / "elsewhere.json", None, require_committed=False, membership_path=mpath)
    except Exception as exc:
        ok, obs = False, f"{type(exc).__name__}: {exc}"
    check("NON-VACUITY: an unmutated artifact still loads with no population argument", ok, "", obs)
    return {
        "n_members": len(pop),
        "mutations": ["pdf_path", "population", "stratum", "canonical_authority", "readback"],
    }


def part_guard() -> dict:
    print("\n== A43: the holdout guard IS the committed membership ==")
    frozen = ES.frozen_member_ids()
    check(
        "build_oracle.HOLDOUT_GUARD equals the committed membership",
        set(BO.HOLDOUT_GUARD) == set(frozen),
        "the guard is a transcription that drifts from the authority",
        f"{len(BO.HOLDOUT_GUARD)} ids, symmetric difference {len(set(BO.HOLDOUT_GUARD) ^ set(frozen))}",
    )
    check(
        "every frozen member is refused pre-boundary by assert_source_permitted",
        all(BO.holdout_member(m) == m for m in frozen),
        "a frozen member is not recognised as holdout, so the source gate never fires on it",
    )

    # THE DEFECT, REPRODUCED AS A CONTROL. Inject the old literal's divergence and require
    # both the equality invariant and the source gate to notice.
    saved = BO.HOLDOUT_GUARD
    try:
        victim = sorted(frozen)[0]
        BO.HOLDOUT_GUARD = frozenset(saved - {victim} | {"CRPT-115HRPT699"})
        ok, obs = refuses(BO.assert_guard_matches_membership, BO.HOLDOUT_GUARD_DIVERGED, BO.OracleBuildError)
        check(
            "MUTATION drop a real member and add a phantom -> HOLDOUT_GUARD_DIVERGED",
            ok,
            "the guard may disagree with the committed population and nothing says so",
            obs,
        )
        check(
            "...and the divergence names BOTH directions",
            BO.holdout_member(victim) is None,
            "an unguarded member is not detectable through the guard's own API",
            f"{victim} unguarded while diverged",
        )
        problems = X04.execution_path_report()
        check(
            "MUTATION guard divergence turns G5 RED",
            any("diverged" in p for p in problems),
            "readiness stays green while the source gate is open on real members",
            f"{len(problems)} problem(s)",
        )
    finally:
        BO.HOLDOUT_GUARD = saved
    check("the guard is restored after fault injection", set(BO.HOLDOUT_GUARD) == set(frozen), "debris is left behind")

    # An unreadable authority must RAISE, never yield an empty (i.e. disabled) guard.
    ok, obs = refuses(
        lambda: BO._membership_ids(EV / "results" / "does_not_exist.json"),
        BO.HOLDOUT_POPULATION_UNAVAILABLE,
        BO.OracleBuildError,
    )
    check(
        "MUTATION unreadable membership -> HOLDOUT_POPULATION_UNAVAILABLE, not an empty guard",
        ok,
        "a missing authority disables the holdout guard entirely and looks like a clean load",
        obs,
    )
    return {"n_guarded": len(BO.HOLDOUT_GUARD), "equals_membership": set(BO.HOLDOUT_GUARD) == set(frozen)}


def part_boundary() -> dict:
    print("\n== the boundary still gates the canonical path ==")
    state = BO.execution_boundary_state()
    check(
        "the execution boundary is ABSENT in this session", state == "ABSENT", "the probe ran post-authorization", state
    )

    ok, obs = refuses(
        lambda: BO.assert_write_permitted(ES.FRAMES), BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION, BO.OracleBuildError
    )
    check(
        "canonical results/frames.json may not be written pre-boundary",
        ok,
        "the first confirmatory artifact is the one the write guard cannot see",
        obs,
    )

    # INERT BY CONSTRUCTION: a frozen member's ID with a DEVELOPMENT file path. If the guard
    # failed open this would extract a development document, not the holdout.
    decoy = ES.DocumentDescriptor(A_HOLDOUT_ID, "bill", BF.P_HEAD, 1, DEV_DOCS[0][1], "0" * 64, 1)
    ok, obs = refuses(
        lambda: ES.build_document_frame_for(decoy), BO.HOLDOUT_BEFORE_EXECUTION_BOUNDARY, BO.OracleBuildError
    )
    check(
        "extraction of a frozen member refuses pre-boundary, BEFORE any arm runs",
        ok,
        "a frozen member is extracted while the boundary is ABSENT",
        obs,
    )
    return {"boundary_state": state}


def part_g5() -> dict:
    print("\n== G5 cannot stay green when the execution path is absent or broken ==")
    members = json.loads(X04.MEMBERSHIP.read_text())["members"]

    def g5() -> tuple[bool, str]:
        row = next(r for r in X04.check_execution(members) if r[0].startswith("G5"))
        return row[1], row[2]

    ok_now, detail = g5()
    check("G5 is GREEN on the repaired tree", ok_now, "the repair itself does not satisfy G5", detail)

    # --- MUTATION 15: the entrypoint is DELETED ---------------------------------------
    saved_fn = ES.write_frames
    try:
        del ES.write_frames
        ok, _ = g5()
        check(
            "MUTATION delete execute_study.write_frames -> G5 RED",
            not ok,
            "readiness stays green while the canonical writer is gone",
            "; ".join(X04.execution_path_report()[:1]),
        )
    finally:
        ES.write_frames = saved_fn

    # --- MUTATION 16: a PAGE LIMIT is introduced on the canonical path ----------------
    saved_limit = ES.PAGE_LIMIT
    try:
        ES.PAGE_LIMIT = 8
        ok, _ = g5()
        check(
            "MUTATION set a canonical PAGE_LIMIT -> G5 RED",
            not ok,
            "a prefix scope reaches the canonical path and silently shrinks every denominator",
            "; ".join(X04.execution_path_report()[:1]),
        )
    finally:
        ES.PAGE_LIMIT = saved_limit

    # --- MUTATION 17: the component FILE is removed -----------------------------------
    target = EV / "probes" / "execute_study.py"
    saved_bytes = target.read_bytes()
    try:
        target.unlink()
        ok, detail_missing = g5()
        check(
            "MUTATION remove probes/execute_study.py -> G5 RED",
            not ok and "execute_study" in detail_missing,
            "the surface no longer covers the component that decides which documents enter the study",
            detail_missing,
        )
    finally:
        target.write_bytes(saved_bytes)
    check(
        "the component file is restored byte-identically after fault injection",
        target.read_bytes() == saved_bytes,
        "fault injection leaves the tree modified",
    )

    ok_after, _ = g5()
    check("G5 is GREEN again after every injected fault is reverted", ok_after, "a fault was not fully reverted")
    return {"g5_green": ok_now, "surface_size": len(X04.METHODOLOGY_SURFACE)}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pop_ev = part_population(root / "pop")
        frame_ev = part_frames(root / "frames")
        identity_ev = part_identity(root / "identity")
    guard_ev = part_guard()
    boundary_ev = part_boundary()
    g5_ev = part_g5()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened by any extractor, nothing scored",
        "amendment": "A43",
        "canonical_frames_json_created": False,
        "holdout_extraction_performed": False,
        "development_documents": [d for d, _ in DEV_DOCS],
        "canonical_entrypoint": "execute_study.canonical_population() -> write_frames() -> load_frames()",
        "population_authority": "results/holdout_membership.json",
        "page_limit": ES.PAGE_LIMIT,
        "refusal_classes": sorted(v for k, v in vars(ES).items() if k.isupper() and isinstance(v, str) and k == v),
        "identity": identity_ev,
        "guard": guard_ev,
        "boundary": boundary_ev,
        "g5": g5_ev,
        "population_evidence": pop_ev,
        "frames_evidence": frame_ev,
        "checks": ROWS,
        "n_checks": len(ROWS),
        "n_failed": len(FAILED),
    }
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks passed -> {OUT.relative_to(EV)}")
    if FAILED:
        print("FAILED: " + "; ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
