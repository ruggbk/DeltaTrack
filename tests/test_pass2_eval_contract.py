"""The Pass 2 data contract: prove the schema can produce VALID metrics before humans label.

`pass2-protocol.md` promises one dataset that answers candidate recall, ranking, assignment, final
diff correctness and challenge-set failure rates. Round 1 called the evaluator non-blocking because
metrics come after labeling. Round 2's challenge to that held: the risk is that the SCHEMA cannot
produce them, and the only way to learn that is to compute them — after ~160 human rulings, that
means collecting them again.

Round 3 raised the bar again, and this file follows it. v1 printed YES for all five targets while
three of them consumed truth that could not support their arithmetic:

* a **region-local NONE** ("I swept title IV and found nothing") was fed to diff correctness, where
  it certified the matcher's ``removed`` as correct on the strength of a bounded search;
* a **suggestion-list NONE** did the same, one step downstream of the guard built to stop exactly
  that;
* nodes were joined on ``(bill, version, text_sha256)``, and 33% of real documents in this corpus
  contain at least one body text shared by two or more provisions, so distinct nodes collapsed —
  always in the optimistic direction.

So the tests below pin two things. First, each metric's value on the synthetic fixture, which
contains at least one success and one failure of every shape so no metric can pass by being
vacuously 1.0. Second — and this is the part that matters — each guard is shown to CHANGE THE
ANSWER, by re-running the metric with the guard removed or with v1's join restored. A guard that
has never moved a number cannot be distinguished from one that is not wired up.

These are contract tests, not result tests. Nothing here asserts a research finding.
"""

from __future__ import annotations

import copy
import importlib.util
import json

import pytest

from tests.corpus_paths import PROJECT_ROOT

PROBES = PROJECT_ROOT / "docs" / "research" / "provision-matching" / "probes"
FIXTURE = PROBES / "fixtures" / "eval_contract_synthetic.json"


def _mod(name: str):
    spec = importlib.util.spec_from_file_location(f"_probe_{name}", PROBES / f"{name}.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def evaluator():
    return _mod("eval_pass2")


@pytest.fixture(scope="module")
def schema():
    return _mod("pass2_schema")


@pytest.fixture
def records():
    return copy.deepcopy(json.loads(FIXTURE.read_text())["records"])


# --------------------------------------------------------------------------------------------
# the fixture itself
# --------------------------------------------------------------------------------------------


def test_fixture_validates(schema, records):
    schema.validate_dataset(records)


def test_fixture_covers_every_shape_the_design_must_handle(records):
    """A contract fixture that omits a shape proves nothing about that shape."""
    ids = {r["anchor_id"] for r in records}
    for shape in (
        # rounds 1-2
        "a1-one-to-one",
        "a2-none-global",
        "a3-one-to-many-outside-region",
        "a4-candidate-miss",
        "a5-ranking-miss",
        "a6-collision-winner",
        "a7-collision-loser",
        "a8-suggested-only",
        "a9-uncertain",
        "a10-challenge-false-keep",
        # round 3 adversarial shapes
        "a11-region-only-none",
        "a12-cross-region-escape",
        "a13-suggestion-list-none",
        "a14-duplicate-text-wrong-node",
        "a15-duplicate-text-right-node",
    ):
        assert shape in ids, f"the contract fixture no longer covers {shape}"


def test_the_duplicate_text_pair_really_is_a_duplicate(records):
    """The adversarial case only tests anything if the two nodes genuinely share a content hash."""
    a14 = next(r for r in records if r["anchor_id"] == "a14-duplicate-text-wrong-node")
    a15 = next(r for r in records if r["anchor_id"] == "a15-duplicate-text-right-node")
    dup_a = a14["truth"]["counterparts"][0]
    dup_b = a15["truth"]["counterparts"][0]
    assert dup_a["text_sha256"] == dup_b["text_sha256"], "the two nodes must share body text"
    assert dup_a["element_id"] != dup_b["element_id"], "but must be distinct nodes"


# --------------------------------------------------------------------------------------------
# the five metrics
# --------------------------------------------------------------------------------------------


def test_all_five_metrics_are_computable_and_non_degenerate(evaluator, records):
    r = evaluator.evaluate(records)

    # 1 candidate recall: 9 true counterparts over 8 document-complete anchors; 4 never retrieved.
    cr = r["candidate_recall"]
    assert (cr["counterparts_found"], cr["counterparts_total"]) == (5, 9)
    assert cr["anchors_eligible"] == 8
    assert {a for a, _ in cr["misses"]} == {
        "a3-one-to-many-outside-region",
        "a4-candidate-miss",
        "a12-cross-region-escape",
        "a14-duplicate-text-wrong-node",
    }

    # 2 ranking: 5 one-to-one anchors whose counterpart WAS retrieved; two of them off rank 1.
    assert r["ranking"]["n"] == 5
    assert r["ranking"]["top1"] == pytest.approx(0.6)
    assert r["ranking"]["mrr"] == pytest.approx((1 + 1 / 3 + 1 + 1 + 1 / 2) / 5)

    # 3 assignment: three contended targets, four scorable anchors, two resolved right.
    assert r["assignment"]["collision_groups"] == 3
    assert r["assignment"]["anchors_in_collision"] == 4
    assert r["assignment"]["accuracy"] == pytest.approx(0.5)
    assert set(r["assignment"]["wrong"]) == {"a7-collision-loser", "a14-duplicate-text-wrong-node"}

    # 4 diff correctness: a real confusion matrix over document-complete anchors only.
    assert r["diff_correctness"]["n"] == 11
    assert r["diff_correctness"]["accuracy"] == pytest.approx(6 / 11)
    assert r["diff_correctness"]["matrix"]["truth=moved -> system=removed"] == 2

    # 5 failure modes: a rate inside a named stratum, explicitly not a precision.
    fm = r["failure_modes"]["strata"]["high-containment-different"]
    assert (fm["mode_occurred"], fm["n"]) == (1, 1)
    assert "rigged" in fm["NOT_a_precision"]


def test_a_candidate_miss_is_counted_as_a_recall_miss_not_a_ranking_miss(evaluator, records):
    """The two failures must not double-count: a4's counterpart was never retrieved, so it belongs
    to candidate recall and must be absent from the ranking population entirely."""
    r = evaluator.evaluate(records)
    assert "a4-candidate-miss" in {a for a, _ in r["candidate_recall"]["misses"]}
    one_to_one = [x for x in records if x["truth"]["relation"] == "one-to-one"]
    assert len(one_to_one) == 8
    assert r["ranking"]["n"] == 5


def test_uncertain_is_never_folded_into_none(evaluator, records):
    """`uncertain` and `none` are different claims. Collapsing them would silently convert a
    reviewer's 'I cannot tell' into evidence that no counterpart exists."""
    r = evaluator.evaluate(records)
    assert r["uncertain"] == ["a9-uncertain"]


# --------------------------------------------------------------------------------------------
# round 3: every guard must change an answer
# --------------------------------------------------------------------------------------------


def test_bounded_search_negatives_are_refused_by_the_completeness_metrics(evaluator, records):
    """A NONE from a region sweep or a suggestion list cannot say a counterpart does not exist."""
    r = evaluator.evaluate(records)
    for metric in ("candidate_recall", "assignment", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert refused == {"a8-suggested-only", "a11-region-only-none", "a13-suggestion-list-none"}, metric
        assert r[metric]["refused"]["requires"] == "complete-in-document"


def test_ranking_still_admits_bounded_oracles(evaluator, records):
    """The mirror of the test above, and the reason the requirement is per-metric rather than one
    global flag: where a counterpart ranked does not depend on whether another exists elsewhere, so
    refusing bounded oracles here would discard valid evidence for no gain."""
    r = evaluator.evaluate(records)
    assert r["ranking"]["refused"]["count"] == 0
    assert r["ranking"]["refused"]["requires"] == "affirmed-positive"


def test_admitting_bounded_negatives_would_inflate_diff_correctness(evaluator, records):
    """Prove the refusal changes the answer, by removing it.

    a11 (region-only NONE) and a13 (suggestion-list NONE) both carry truth ``removed`` and both sit
    opposite a system that also said ``removed``. Admitting them adds two free correct answers,
    scored on the strength of a search that never looked at most of the document. That is
    matcher-conditioned truth, and it flatters the matcher.
    """
    before = evaluator.evaluate(records)["diff_correctness"]

    promoted = copy.deepcopy(records)
    for rec in promoted:
        if rec["anchor_id"] in ("a11-region-only-none", "a13-suggestion-list-none"):
            rec["truth"]["oracles"] = ["region-exhaustive", "document-search"]
            rec["truth"].setdefault("region_id", "title IV")
    after = evaluator.evaluate(promoted)["diff_correctness"]

    assert (before["n"], after["n"]) == (11, 13)
    assert after["accuracy"] > before["accuracy"], (
        "admitting bounded-search negatives must raise measured diff correctness; if it does not, "
        "this guard is no longer doing the work it is claimed to do"
    )
    assert after["accuracy"] == pytest.approx(8 / 13)


def test_the_cross_region_escalation_is_what_prevents_a_false_none(evaluator, records):
    """a12's counterpart is in another title. With the document escalation it is a `moved` whose
    counterpart the retrievers missed. Without it, the same anchor would read `none` / `removed` —
    and would certify the matcher's `removed` as correct."""
    r = evaluator.evaluate(records)
    a12 = next(x for x in records if x["anchor_id"] == "a12-cross-region-escape")
    assert a12["truth"]["oracles"] == ["region-exhaustive", "document-search"]
    assert a12["truth"]["counterparts"][0]["found_via"] == "browse"
    assert "a12-cross-region-escape" in {a for a, _ in r["candidate_recall"]["misses"]}

    downgraded = copy.deepcopy(records)
    for rec in downgraded:
        if rec["anchor_id"] == "a12-cross-region-escape":
            rec["truth"]["oracles"] = ["region-exhaustive"]
            rec["truth"]["relation"] = "none"
            rec["truth"]["counterparts"] = []
            rec["truth"]["change_type"] = "removed"
    after = evaluator.evaluate(downgraded)
    assert after["candidate_recall"]["counterparts_total"] == 8, (
        "without the escalation the anchor leaves the recall denominator entirely — the bias is by "
        "SELECTION, not by a wrong label, which is why it is invisible in the metric itself"
    )
    assert after["candidate_recall"]["counterpart_recall"] > r["candidate_recall"]["counterpart_recall"]


@pytest.mark.parametrize(
    "metric, extract",
    [
        ("candidate_recall", lambda r: r["candidate_recall"]["counterparts_found"]),
        ("ranking", lambda r: r["ranking"]["top1"]),
        ("assignment", lambda r: r["assignment"]["accuracy"]),
    ],
)
def test_a_content_hash_join_would_corrupt_this_metric(evaluator, schema, records, metric, extract):
    """Prove the node-identity fix can fire, by restoring v1's join.

    v1 keyed nodes on ``(bill, version, text_sha256)``. The fixture's two boilerplate-identical
    target nodes then collapse, and all three of these metrics move in the OPTIMISTIC direction:
    a recall miss against the wrong node scores as a hit, a rank-2 target scores as top-1, and a
    wrong assignment scores as correct. R9 measured this shape in 33% of real documents, reaching
    every version of all four answer-key bills, so it is not a hypothetical.
    """
    real = extract(evaluator.evaluate(records))

    original = schema.observation_id
    try:
        schema.observation_id = lambda ref: (ref["bill"], ref["version"], ref["text_sha256"])
        evaluator.observation_id = schema.observation_id
        collapsed = extract(evaluator.evaluate(records))
    finally:
        schema.observation_id = original
        evaluator.observation_id = original

    assert collapsed > real, (
        f"{metric}: a content-hash join must score BETTER than an identity join on this fixture "
        "(that is the defect). If the two agree, the duplicate-text case has stopped discriminating "
        "and this guard is untested."
    )


def test_the_anti_circularity_exclusion_can_fire(evaluator, records):
    """Round 2's guard, re-pinned under v2: promoting a suggestion-list anchor to a document oracle
    must move candidate recall."""
    before = evaluator.evaluate(records)["candidate_recall"]

    promoted = copy.deepcopy(records)
    for rec in promoted:
        if rec["anchor_id"] == "a8-suggested-only":
            rec["truth"]["oracles"] = ["region-exhaustive", "document-search"]
            rec["truth"]["region_id"] = "title II"
    after = evaluator.evaluate(promoted)["candidate_recall"]

    assert before["counterparts_total"] == 9
    assert after["counterparts_total"] == 10
    assert after["counterpart_recall"] > before["counterpart_recall"]
    assert not [a for a in after["refused"]["anchors"] if a["anchor_id"] == "a8-suggested-only"]


def test_a_tainted_collision_group_disqualifies_its_members(evaluator, records):
    """An unfound competitor makes a wrong assignment look right, so one member with inadequate
    truth disqualifies the whole group rather than only itself."""
    tainted = copy.deepcopy(records)
    for rec in tainted:
        if rec["anchor_id"] == "a7-collision-loser":
            rec["truth"]["oracles"] = ["region-exhaustive"]
    after = evaluator.evaluate(tainted)["assignment"]
    assert after["collision_groups_tainted"] >= 1
    assert "a6-collision-winner" in after["anchors_disqualified_by_a_group_member"], (
        "a6 shares a contested target with a7; if a7's truth cannot enumerate competitors, a6's "
        "assignment cannot be scored either"
    )


# --------------------------------------------------------------------------------------------
# schema rejections
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, expect",
    [
        (lambda rec: rec["truth"]["counterparts"][0].pop("found_via"), "found"),
        (lambda rec: rec["truth"].pop("region_id"), "region"),
        (lambda rec: rec["anchor"].pop("source_sha256"), "source_sha256"),
        (lambda rec: rec["anchor"].pop("parser_commit"), "parser_commit"),
        (lambda rec: rec["anchor"].pop("element_id"), "element_id"),
        (lambda rec: rec["anchor"].update(element_id=""), "element_id"),
        (lambda rec: rec["candidates"][0].pop("retrievers"), "retriever"),
        (lambda rec: rec["truth"].pop("change_type"), "change_type"),
        (lambda rec: rec["truth"].pop("oracles"), "oracles"),
        (lambda rec: rec["truth"].update(oracles="region-exhaustive"), "oracles"),
        (lambda rec: rec["truth"].pop("judgment_mode"), "judgment_mode"),
        (lambda rec: rec["system"]["assigned"][0].pop("element_id"), "element_id"),
    ],
)
def test_schema_rejects_a_record_that_cannot_support_its_metrics(schema, records, mutate, expect):
    """Each removal is a field some metric needs. Dropping it must fail loudly at validation, not
    silently produce a metric computed over a smaller population than the report claims."""
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a1-one-to-one")
    mutate(target)
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert expect in str(exc.value).lower()


def test_a_challenge_record_must_declare_what_its_claim_needs(schema, records):
    """An existence claim and an absence claim need different truth; the evaluator cannot guess."""
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a10-challenge-false-keep")
    del target["challenge_requires"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "challenge_requires" in str(exc.value)


def test_observation_ids_must_identify_a_single_node(schema, records):
    """The identity design rests on element_id being unique per parse. Assert it rather than assume
    it: if a future parser stops guaranteeing it, distinct provisions collapse silently and every
    metric moves in the optimistic direction."""
    bad = copy.deepcopy(records)
    a14 = next(r for r in bad if r["anchor_id"] == "a14-duplicate-text-wrong-node")
    a15 = next(r for r in bad if r["anchor_id"] == "a15-duplicate-text-right-node")
    # give the two DIFFERENT nodes the same element_id — now one id maps to two bodies
    a15["truth"]["counterparts"][0]["element_id"] = a14["truth"]["counterparts"][0]["element_id"]
    a15["truth"]["counterparts"][0]["text_sha256"] = "f" * 64
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "observation id collision" in str(exc.value)


def test_forced_choice_cannot_establish_a_positive(schema, evaluator, records):
    """ "The best of these eight" is not "this is the same provision". A forced-choice UI therefore
    cannot support even the ranking metric, which is otherwise the most permissive."""
    assert not schema.establishes(["document-search"], "forced-choice", "affirmed-positive")
    assert schema.establishes(["document-search"], "per-candidate-binary", "affirmed-positive")

    forced = copy.deepcopy(records)
    for rec in forced:
        rec["truth"]["judgment_mode"] = "forced-choice"
    after = evaluator.evaluate(forced)
    assert after["ranking"]["n"] == 0
    assert after["candidate_recall"]["counterparts_total"] == 0


def test_provenance_fields_are_present_on_every_node_reference(schema, records):
    """The 2026-08 drift finding in schema form: an observation that cannot say which XML bytes and
    which parser produced it cannot be re-quarantined when either changes."""
    for rec in records:
        refs = [rec["anchor"], *rec["truth"]["counterparts"], *rec["candidates"], *rec["system"]["assigned"]]
        for ref in refs:
            for field in ("bill", "version", "source_sha256", "parser_commit", "text_sha256", "element_id"):
                assert field in ref, f"{rec['anchor_id']}: node ref missing {field}"
