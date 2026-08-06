"""The Pass 2 data contract: prove the schema can produce VALID metrics before humans label.

`pass2-protocol.md` promises one dataset that answers candidate recall, ranking, assignment, final
diff correctness and challenge-set failure rates. Four review rounds have each moved the bar for
what "can produce" means:

* **R1** called the evaluator non-blocking. **R2** showed the risk is that the SCHEMA cannot produce
  the metrics, which is only discoverable by computing them.
* **R3** showed that computing them is not computing them VALIDLY: a region-local NONE and a
  suggestion-list NONE were both certifying the matcher's ``removed`` as correct, and nodes were
  joined on body text, which 33% of real documents share between two provisions.
* **R4** showed that even the fixed oracle could be satisfied by EFFORT rather than COVERAGE — a
  reviewer who searched a document and found nothing was granted "the counterpart set is complete",
  which a transformed counterpart survives.

So the tests below pin two things. First, each metric's value on the synthetic fixture, which
contains at least one success and one failure of every shape so no metric can pass by being
vacuously 1.0. Second — the part that matters — each guard is shown to CHANGE THE ANSWER, by
re-running the metric with the guard removed or with the superseded rule restored. A guard that has
never moved a number cannot be distinguished from one that is not wired up.

These are contract tests, not result tests. Nothing here asserts a research finding.
"""

from __future__ import annotations

import ast
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
        "a1-one-to-one",
        "a2-none-global",
        "a3-one-to-many-outside-region",
        "a4-candidate-miss",
        "a5-ranking-miss",
        "a6-collision-winner",
        "a7-collision-loser",
        "a8-suggested-only",
        "a9-uncertain",
        "a10-challenge-absence",
        "a11-region-only-none",
        "a12-cross-region-escape",
        "a13-suggestion-list-none",
        "a14-duplicate-text-wrong-node",
        "a15-duplicate-text-right-node",
        # round 4
        "a16-incomplete-document-sweep",
        "a17-pairwise-false-keep",
    ):
        assert shape in ids, f"the contract fixture no longer covers {shape}"


def test_the_duplicate_text_pair_really_is_a_duplicate(records):
    """The adversarial case only tests anything if the two nodes genuinely share a content hash."""
    a14 = next(r for r in records if r["anchor_id"] == "a14-duplicate-text-wrong-node")
    a15 = next(r for r in records if r["anchor_id"] == "a15-duplicate-text-right-node")
    dup_a = a14["truth"]["counterparts"][0]
    dup_b = a15["truth"]["counterparts"][0]
    assert dup_a["text_sha256"] == dup_b["text_sha256"], "the two nodes must share body text"
    assert dup_a["node_ordinal"] != dup_b["node_ordinal"], "but must be distinct nodes"


# --------------------------------------------------------------------------------------------
# the five metrics
# --------------------------------------------------------------------------------------------


def test_all_five_metrics_are_computable_and_non_degenerate(evaluator, records):
    r = evaluator.evaluate(records)

    cr = r["candidate_recall"]
    assert (cr["counterparts_found"], cr["counterparts_total"]) == (5, 9)
    assert cr["anchors_eligible"] == 8
    assert {a for a, _ in cr["misses"]} == {
        "a3-one-to-many-outside-region",
        "a4-candidate-miss",
        "a12-cross-region-escape",
        "a14-duplicate-text-wrong-node",
    }

    assert r["ranking"]["n"] == 5
    assert r["ranking"]["top1"] == pytest.approx(0.6)
    assert r["ranking"]["mrr"] == pytest.approx((1 + 1 / 3 + 1 + 1 + 1 / 2) / 5)

    assert r["assignment"]["collision_groups"] == 3
    assert r["assignment"]["anchors_in_collision"] == 4
    assert r["assignment"]["accuracy"] == pytest.approx(0.5)
    assert set(r["assignment"]["wrong"]) == {"a7-collision-loser", "a14-duplicate-text-wrong-node"}

    assert r["diff_correctness"]["n"] == 11
    assert r["diff_correctness"]["accuracy"] == pytest.approx(6 / 11)
    assert r["diff_correctness"]["matrix"]["truth=moved -> system=removed"] == 2

    strata = r["failure_modes"]["strata"]
    assert strata["no-counterpart-anywhere"]["requires"] == "complete-in-document"
    assert strata["high-containment-pairwise"]["requires"] == "affirmed-negative"
    for s in strata.values():
        assert "rigged" in s["NOT_a_precision"]


def test_a_candidate_miss_is_counted_as_a_recall_miss_not_a_ranking_miss(evaluator, records):
    r = evaluator.evaluate(records)
    assert "a4-candidate-miss" in {a for a, _ in r["candidate_recall"]["misses"]}
    assert r["ranking"]["n"] == 5


# --------------------------------------------------------------------------------------------
# round 4: coverage, not effort
# --------------------------------------------------------------------------------------------


def test_a_searched_but_unreviewed_document_does_not_grant_completeness(evaluator, records):
    """R4's central case. a16 names `document-exhaustive` but adjudicated 40 of 161 provisions.

    Under v2 the oracle's presence alone granted `complete-in-document`, so "I searched and found
    nothing" became "no counterpart exists" — and a transformed counterpart (changed header,
    rewritten wording, moved somewhere unexpected) survives any number of queries nobody thought to
    type. v3 grants completeness on a measured count, so this record is refused.
    """
    r = evaluator.evaluate(records)
    for metric in ("candidate_recall", "assignment", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert "a16-incomplete-document-sweep" in refused, metric


def test_completing_the_sweep_admits_the_record(evaluator, schema, records):
    """The mirror: the guard must be about coverage, not about disliking the record."""
    a16 = next(r for r in records if r["anchor_id"] == "a16-incomplete-document-sweep")
    assert not schema.establishes(a16["truth"], "complete-in-document")

    completed = copy.deepcopy(records)
    for rec in completed:
        if rec["anchor_id"] == "a16-incomplete-document-sweep":
            rec["truth"]["coverage"]["reviewed"] = rec["truth"]["coverage"]["eligible_total"]
    after = evaluator.evaluate(completed)
    refused = {a["anchor_id"] for a in after["diff_correctness"]["refused"]["anchors"]}
    assert "a16-incomplete-document-sweep" not in refused
    assert after["diff_correctness"]["n"] == 12


def test_the_coverage_rule_must_be_measure_independent(schema, records):
    """A coverage rule that consulted a similarity measure would let a system under evaluation set
    the denominator of its own completeness claim — the central defect, one layer further out."""
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a1-one-to-one")
    target["truth"]["coverage"]["rule"] = "nodes-above-containment-0.3"
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "coverage.rule" in str(exc.value)


def test_admitting_bounded_negatives_would_inflate_diff_correctness(evaluator, records):
    """Prove the refusal changes the answer, by removing it.

    a11 (region-only), a13 (suggestion-list) and a16 (searched but not reviewed) all carry truth
    ``removed`` opposite a system that also said ``removed``. Admitting them adds three free correct
    answers, scored on searches that never covered most of the document.
    """
    before = evaluator.evaluate(records)["diff_correctness"]

    promoted = copy.deepcopy(records)
    for rec in promoted:
        if rec["anchor_id"] in ("a11-region-only-none", "a13-suggestion-list-none", "a16-incomplete-document-sweep"):
            rec["truth"]["oracles"] = ["region-exhaustive", "document-exhaustive"]
            rec["truth"].setdefault("region_id", "title IV")
            rec["truth"]["coverage"] = {"rule": "all-nodes-with-body", "eligible_total": 161, "reviewed": 161}
    after = evaluator.evaluate(promoted)["diff_correctness"]

    assert (before["n"], after["n"]) == (11, 14)
    assert after["accuracy"] > before["accuracy"]
    assert after["accuracy"] == pytest.approx(9 / 14)


# --------------------------------------------------------------------------------------------
# round 4: pairwise negatives
# --------------------------------------------------------------------------------------------


def test_a_pairwise_false_keep_needs_no_document_completeness(evaluator, schema, records):
    """R4's eighth criticism. "This proposed pair is not the same provision" is complete at one
    comparison. v2 had no `affirmed-negative`, so such a stratum had to declare
    `complete-in-document` and buy a ~161-adjudication sweep for a judgment that did not need it."""
    a17 = next(r for r in records if r["anchor_id"] == "a17-pairwise-false-keep")
    assert a17["truth"]["oracles"] == ["suggested-list"]
    assert schema.establishes(a17["truth"], "affirmed-negative")
    assert not schema.establishes(a17["truth"], "complete-in-document")

    r = evaluator.evaluate(records)
    stratum = r["failure_modes"]["strata"]["high-containment-pairwise"]
    assert (stratum["mode_occurred"], stratum["n"]) == (1, 1)


def test_an_uncertain_relation_still_supports_a_pairwise_challenge(evaluator, records):
    """`uncertain` is the honest relation when nobody established the counterpart set. The four
    metrics that need that set exclude it; the pairwise challenge does not, because its claim has a
    definite answer regardless."""
    r = evaluator.evaluate(records)
    assert "a17-pairwise-false-keep" in r["uncertain"]
    assert "high-containment-pairwise" in r["failure_modes"]["strata"]


def test_a_pairwise_stratum_must_record_the_rejected_node(schema, records):
    """Without it there is nothing for the metric to test against."""
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a17-pairwise-false-keep")
    target["truth"]["rejected"] = []
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "rejected" in str(exc.value)


def test_a_stratum_may_not_mix_truth_requirements(schema, records):
    """One stratum, one claim: otherwise a single reported rate pools two different propositions."""
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a17-pairwise-false-keep")
    target["stratum"] = "no-counterpart-anywhere"
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "one claim" in str(exc.value)


# --------------------------------------------------------------------------------------------
# node identity
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric, extract",
    [
        ("candidate_recall", lambda r: r["candidate_recall"]["counterparts_found"]),
        ("ranking", lambda r: r["ranking"]["top1"]),
        ("assignment", lambda r: r["assignment"]["accuracy"]),
    ],
)
def test_a_content_hash_join_would_corrupt_this_metric(evaluator, schema, records, metric, extract):
    """Prove the node-identity fix can fire, by restoring the pre-R3 join.

    The fixture's two boilerplate-identical target nodes collapse under a text-hash key, and all
    three metrics move in the OPTIMISTIC direction: a recall miss against the wrong node scores as a
    hit, a rank-2 target scores as top-1, and a wrong assignment scores as correct. R9 measured this
    shape in 33% of real documents, reaching every version of all four answer-key bills.
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
    assert collapsed > real, f"{metric}: a content-hash join must score better on this fixture"


def test_identity_collision_is_caught_even_when_the_text_also_matches(schema, records):
    """R4's fourth criticism. v2 compared only `text_sha256` across a shared identity, so two
    genuinely distinct provisions that share a body — the boilerplate case, present in a third of
    real documents — carried the same identity AND the same text hash and raised nothing. v3
    compares every recorded attribute."""
    bad = copy.deepcopy(records)
    a14 = next(r for r in bad if r["anchor_id"] == "a14-duplicate-text-wrong-node")
    a15 = next(r for r in bad if r["anchor_id"] == "a15-duplicate-text-right-node")
    dup_b = a15["truth"]["counterparts"][0]
    # same ordinal as dupA, same text as dupA, different path: v2 saw no conflict here.
    dup_b["node_ordinal"] = a14["truth"]["counterparts"][0]["node_ordinal"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "observation id collision" in str(exc.value)


def test_element_id_is_not_part_of_the_identity(schema, records):
    """It is recorded for traceability. Changing it must not change any join, because its
    uniqueness is an empirical property of GPO markup rather than an invariant."""
    a1 = next(r for r in records if r["anchor_id"] == "a1-one-to-one")
    before = schema.observation_id(a1["anchor"])
    a1["anchor"]["element_id"] = "something-else-entirely"
    assert schema.observation_id(a1["anchor"]) == before


# --------------------------------------------------------------------------------------------
# the canonical sampling frame
# --------------------------------------------------------------------------------------------


def test_the_sampling_frame_never_imports_the_matcher():
    """R4's second criticism, as a standing gate.

    `probe_r10` selected its anchors from `diff_bills` output while the review described the frame
    as matcher-independent, and three review rounds did not catch it because prose and code were
    never forced to agree. A static import check is the cheapest way to keep them agreeing.
    """
    src = (PROBES / "study2_frame.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("diff_bill" in m for m in imported), (
        f"study2_frame imports the matcher: {sorted(imported)}. Anchor eligibility must be "
        "structural; a frame that consults diff_bills is a matcher-conditioned population."
    )


def test_the_frame_exposes_the_three_operations_the_design_names():
    frame = _mod("study2_frame")
    for fn in ("enumerate_study2_anchors", "enumerate_study2_regions", "draw_study2_sample"):
        assert callable(getattr(frame, fn, None)), f"study2_frame must expose {fn}"


def test_a_draw_is_reproducible_and_records_its_inputs():
    """A frozen algorithm is only frozen if the same seed and corpus reproduce the same sample."""
    frame = _mod("study2_frame")
    a = frame.draw_study2_sample(n_regions=4, seed=7, anchors_per_region=5)
    b = frame.draw_study2_sample(n_regions=4, seed=7, anchors_per_region=5)
    assert a["selected_regions"] == b["selected_regions"]
    assert a["selected_anchors"] == b["selected_anchors"]
    assert a["corpus_digest"] and a["seed"] == 7
    for anchor in a["selected_anchors"]:
        assert 0 < anchor["p_inclusion"] <= 1


def test_a_draw_is_stratified_across_bills():
    """One bill with many drawable regions must not be able to supply the whole sample."""
    frame = _mod("study2_frame")
    drawn = frame.draw_study2_sample(n_regions=6, seed=11, anchors_per_region=5)
    bills = {k.split(":")[0] for k in drawn["selected_regions"]}
    assert len(bills) >= min(4, drawn["frame"]["bills_drawable"])


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
        (lambda rec: rec["anchor"].pop("node_ordinal"), "node_ordinal"),
        (lambda rec: rec["anchor"].update(node_ordinal="x"), "node_ordinal"),
        (lambda rec: rec["candidates"][0].pop("retrievers"), "retriever"),
        (lambda rec: rec["truth"].pop("change_type"), "change_type"),
        (lambda rec: rec["truth"].pop("oracles"), "oracles"),
        (lambda rec: rec["truth"].update(oracles="region-exhaustive"), "oracles"),
        (lambda rec: rec["truth"].pop("judgment_mode"), "judgment_mode"),
        (lambda rec: rec["truth"].pop("coverage"), "coverage"),
        (lambda rec: rec["system"]["assigned"][0].pop("node_ordinal"), "node_ordinal"),
    ],
)
def test_schema_rejects_a_record_that_cannot_support_its_metrics(schema, records, mutate, expect):
    bad = copy.deepcopy(records)
    target = next(r for r in bad if r["anchor_id"] == "a1-one-to-one")
    mutate(target)
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert expect in str(exc.value).lower()


def test_forced_choice_cannot_establish_anything(schema, evaluator, records):
    """ "The best of these eight" is a claim about the candidate set, not the legislation."""
    assert not schema.establishes(
        {"oracles": ["document-exhaustive"], "judgment_mode": "forced-choice"}, "affirmed-positive"
    )
    forced = copy.deepcopy(records)
    for rec in forced:
        rec["truth"]["judgment_mode"] = "forced-choice"
    after = evaluator.evaluate(forced)
    assert after["ranking"]["n"] == 0
    assert after["candidate_recall"]["counterparts_total"] == 0
    assert after["failure_modes"]["strata"] == {}


def test_provenance_fields_are_present_on_every_node_reference(schema, records):
    for rec in records:
        refs = [
            rec["anchor"],
            *rec["truth"]["counterparts"],
            *rec["truth"].get("rejected", []),
            *rec["candidates"],
            *rec["system"]["assigned"],
        ]
        for ref in refs:
            for field in schema.PROVENANCE_FIELDS:
                assert field in ref, f"{rec['anchor_id']}: node ref missing {field}"
