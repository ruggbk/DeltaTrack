"""The Pass 2 data contract: prove the schema can produce its five metrics BEFORE humans label.

`pass2-protocol.md` promises one dataset that answers candidate recall, ranking, assignment,
final diff correctness and challenge-set failure rates. The 2026-08 review called the evaluator
non-blocking because metrics come after labeling. The second review challenged that and it holds:
the risk is not that the metrics arrive late, it is that the SCHEMA cannot produce them, and the
only way to learn that is to compute them. Learning it after ~160 human rulings means re-collecting
them.

So this runs the skeletal evaluator against a synthetic fixture -- no legislation, no human
judgments -- and pins two things:

* every promised metric is computed, and is non-degenerate (the fixture contains at least one
  success and one failure of each kind, so a metric cannot pass by being vacuously 1.0 or 0.0);
* the ANTI-CIRCULARITY exclusion actually excludes. An anchor whose truth came only from the
  suggestion list must not enter the candidate-recall denominator, and the test proves that by
  flipping the field and watching the number move -- a guard that has never changed an answer
  cannot be distinguished from one that is not wired up.

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


def test_fixture_validates(schema, records):
    schema.validate_dataset(records)


def test_fixture_covers_every_shape_the_design_must_handle(records):
    """A contract fixture that omits a shape proves nothing about that shape."""
    ids = {r["anchor_id"] for r in records}
    for shape in (
        "a1-one-to-one",
        "a2-none",
        "a3-one-to-many",
        "a4-candidate-miss",
        "a5-ranking-miss",
        "a6-collision-winner",
        "a7-collision-loser",
        "a8-suggested-only",
        "a9-uncertain",
        "a10-challenge-false-keep",
    ):
        assert shape in ids, f"the contract fixture no longer covers {shape}"


def test_all_five_metrics_are_computable_and_non_degenerate(evaluator, records):
    r = evaluator.evaluate(records)

    # 1 candidate recall: 6 true counterparts over 5 eligible anchors; 2 were never retrieved.
    cr = r["candidate_recall"]
    assert (cr["counterparts_found"], cr["counterparts_total"]) == (4, 6)
    assert cr["anchors_eligible"] == 5
    assert {a for a, _ in cr["misses"]} == {"a3-one-to-many", "a4-candidate-miss"}

    # 2 ranking: 4 one-to-one anchors whose counterpart WAS retrieved; one sits at rank 3.
    assert r["ranking"]["n"] == 4
    assert r["ranking"]["top1"] == pytest.approx(0.75)
    assert r["ranking"]["mrr"] == pytest.approx((1 + 1 / 3 + 1 + 1) / 4)

    # 3 assignment: one contended target, two anchors, one resolved right.
    assert r["assignment"]["collision_groups"] == 1
    assert r["assignment"]["anchors_in_collision"] == 2
    assert r["assignment"]["accuracy"] == pytest.approx(0.5)
    assert r["assignment"]["wrong"] == ["a7-collision-loser"]

    # 4 diff correctness: a real confusion matrix, not just an accuracy.
    assert r["diff_correctness"]["n"] == 9
    assert r["diff_correctness"]["accuracy"] == pytest.approx(5 / 9)
    assert r["diff_correctness"]["matrix"]["truth=removed -> system=modified"] == 2

    # 5 failure modes: a rate inside a named stratum, explicitly not a precision.
    fm = r["failure_modes"]["high-containment-different"]
    assert (fm["mode_occurred"], fm["n"]) == (1, 1)
    assert "not a precision" in fm["NOT_a_precision"].lower() or "rigged" in fm["NOT_a_precision"]


def test_a_candidate_miss_is_counted_as_a_recall_miss_not_a_ranking_miss(evaluator, records):
    """The two failures must not double-count. a4's counterpart was never retrieved: it belongs to
    candidate recall and must be absent from the ranking population entirely."""
    r = evaluator.evaluate(records)
    assert "a4-candidate-miss" in {a for a, _ in r["candidate_recall"]["misses"]}
    # 5 one-to-one anchors exist; a4 is the one excluded from ranking.
    one_to_one = [x for x in records if x["truth"]["relation"] == "one-to-one"]
    assert len(one_to_one) == 5
    assert r["ranking"]["n"] == 4


def test_suggestion_list_truth_is_excluded_from_candidate_recall(evaluator, records):
    r = evaluator.evaluate(records)
    assert r["candidate_recall"]["anchors_excluded_circular"] == ["a8-suggested-only"]


def test_the_anti_circularity_exclusion_can_fire(evaluator, records):
    """Prove the exclusion changes the answer, by removing it.

    a8's counterpart WAS retrieved, so admitting it inflates recall -- which is precisely the
    circularity: an anchor labeled from the suggestion list can only ever agree with the
    suggestion list. If this test stops seeing a difference, the guard has become decorative.
    """
    before = evaluator.evaluate(records)["candidate_recall"]

    promoted = copy.deepcopy(records)
    for rec in promoted:
        if rec["anchor_id"] == "a8-suggested-only":
            rec["truth"]["oracle"] = "region-exhaustive"
            rec["truth"]["region_id"] = "title II"
    after = evaluator.evaluate(promoted)["candidate_recall"]

    assert before["counterparts_total"] == 6
    assert after["counterparts_total"] == 7
    assert after["counterparts_found"] == 5
    assert after["counterpart_recall"] > before["counterpart_recall"], (
        "admitting a suggestion-list-only anchor must move candidate recall upward; "
        "if it does not, the exclusion is not doing the work it is claimed to do"
    )
    assert after["anchors_excluded_circular"] == []


def test_uncertain_is_never_folded_into_none(evaluator, records):
    """`uncertain` and `none` are different claims. Collapsing them would silently convert a
    reviewer's 'I cannot tell' into evidence that no counterpart exists."""
    r = evaluator.evaluate(records)
    assert r["uncertain"] == ["a9-uncertain"]
    assert r["diff_correctness"]["n"] == len(records) - 1


@pytest.mark.parametrize(
    "mutate, expect",
    [
        (lambda rec: rec["truth"]["counterparts"][0].pop("found_via"), "found"),
        (lambda rec: rec["truth"].pop("region_id"), "region"),
        (lambda rec: rec["anchor"].pop("source_sha256"), "source_sha256"),
        (lambda rec: rec["anchor"].pop("parser_commit"), "parser_commit"),
        (lambda rec: rec["candidates"][0].pop("retrievers"), "retriever"),
        (lambda rec: rec["truth"].pop("change_type"), "change_type"),
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


def test_provenance_fields_are_present_on_every_node_reference(schema, records):
    """The 2026-08 drift finding in schema form: an observation that cannot say which XML bytes and
    which parser produced it cannot be re-quarantined when either changes."""
    for rec in records:
        for ref in [rec["anchor"], *rec["truth"]["counterparts"], *rec["candidates"]]:
            for field in ("bill", "version", "source_sha256", "parser_commit", "text_sha256"):
                assert field in ref, f"{rec['anchor_id']}: node ref missing {field}"
