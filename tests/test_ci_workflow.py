"""Guardrails on the triggers of the workflows that own a required status check.

Three properties are pinned here: that the test suite runs when a commit lands on the
integration branch (#412), that both required checks answer the merge_group event so
a merge queue can complete a merge (#416), and that every module carrying a @slow test
is named by some workflow, since the marker alone makes a gate runnable but never run.


Nothing ran the test suite when a commit landed on ``develop``, so a broken integration
branch went unreported: ``ci.yml`` fired on ``pull_request`` and on pushes to ``main``
only, while ``security.yml`` did cover ``develop`` on push. The branch therefore showed
green marks after a merge that had left the suite uncollectable, because the workflows
producing those marks never run the tests.

The fix is two words in a YAML list, which is exactly why it is worth pinning: it can be
undone by a reformat, a merge resolution, or a well-meant "align the triggers" edit, and
nothing else in the repository would notice. The comment block in ``ci.yml`` argues both
decisions at length; prose that no test enforces reads as settled while being ungated.

These are deliberately narrow. They assert the two properties #412 turns on and say
nothing about the rest of the workflow, so adding a job or a step does not touch them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "ci.yml"

# The workflows that own a REQUIRED status check on `develop`, by the context name branch
# protection asks for: `test` from ci.yml, `pip-audit (production deps)` from
# security.yml. A merge queue waits on every required context, so each of these has to
# answer the merge_group event or the queue never completes a merge (#416).
REQUIRED_CHECK_WORKFLOWS = {"ci.yml": "test", "security.yml": "pip-audit (production deps)"}


def _triggers(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML resolves a bare `on:` key to the boolean True (the YAML 1.1 truthy set),
    # not the string "on". Both spellings are looked up so this does not silently find
    # nothing -- an empty read here would pass the assertions below vacuously if it
    # returned an empty dict instead of raising.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, f"no trigger block parsed from {path}"
    return triggers


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _push_branches(workflow: dict) -> list[str]:
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, f"no trigger block parsed from {WORKFLOW}"
    return triggers["push"]["branches"]


@pytest.mark.parametrize(("filename", "context"), sorted(REQUIRED_CHECK_WORKFLOWS.items()))
def test_required_checks_report_to_a_merge_queue(filename: str, context: str) -> None:
    """Every required check answers `merge_group`, or a queue stalls on all merges.

    This is inert while no merge queue is enabled, since the event never fires. It is
    pinned anyway because the failure it prevents is both severe and silent: a queue
    waits on a context that is never reported, so nothing merges, and the workflow files
    look correct. Dropping the trigger from either workflow is what would cause it.
    """
    triggers = _triggers(WORKFLOWS / filename)
    assert "merge_group" in triggers, (
        f"{filename} no longer answers the merge_group event, so the required "
        f"'{context}' check would never report for a queued pull request and the merge "
        "queue would stall on every merge -- see #416."
    )


def test_required_test_context_is_an_aggregator_over_the_matrix() -> None:
    """The required `test` context must survive any matrix rename or resize.

    A matrix job reports one context per leg (`test-suite (3.12)`, ...), so a
    required check pointing at the matrix job is stranded by the next matrix edit:
    branch protection keeps waiting on `test` while only per-leg contexts report
    (#426 review). The aggregator job named exactly `test` closes that: it needs
    the matrix job, runs unconditionally, and fails unless every leg succeeded.

    Each pinned property fails silently without the other: without `if: always()`
    a skipped matrix leg skips the aggregator too (no verdict at all), and without
    the explicit result comparison a skipped or cancelled leg counts as a pass,
    making the aggregator a rubber stamp.
    """
    jobs = _workflow()["jobs"]
    aggregator = jobs.get("test")
    assert aggregator is not None, (
        "ci.yml has no job named exactly 'test': the required check context stops "
        "reporting the next time the matrix job is renamed or resized."
    )
    needs = aggregator.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert len(needs) == 1, f"the 'test' aggregator should need exactly the matrix job, got: {needs}"
    matrix_job = jobs[needs[0]]
    assert "matrix" in matrix_job.get("strategy", {}), (
        f"the 'test' aggregator needs '{needs[0]}', which is not a matrix job"
    )
    assert aggregator.get("if") == "always()", (
        "the 'test' aggregator must run even when the matrix fails or is skipped, "
        "or a skipped leg leaves the required check with no verdict"
    )
    assert any(f"needs.{needs[0]}.result" in str(step) for step in aggregator.get("steps", [])), (
        "the 'test' aggregator must compare needs.*.result explicitly: a skipped "
        "dependency reports 'skipped', not 'success', and without the comparison "
        "the aggregator is a rubber stamp"
    )


def test_ci_runs_on_pushes_to_develop() -> None:
    """The integration branch gets a verdict of its own, not just its pull requests.

    Without this, the first person to discover ``develop`` is broken is whoever cuts the
    next branch from it, and the failure surfaces attached to the wrong change.
    """
    branches = _push_branches(_workflow())
    assert "develop" in branches, (
        f"ci.yml no longer runs on pushes to develop (push branches: {branches}). "
        "A merge into the integration branch would land with no test verdict -- see #412."
    )


def test_ci_still_runs_on_pushes_to_main() -> None:
    """Adding `develop` must not come at the cost of the coverage that already existed."""
    branches = _push_branches(_workflow())
    assert "main" in branches, f"ci.yml no longer runs on pushes to main: {branches}"


def test_ci_does_not_cancel_in_progress_runs() -> None:
    """A cancelled run leaves a merge commit with no verdict, which is #412 again.

    ``ci.yml`` has no ``concurrency`` group today and does not need one. If a future
    change adds one -- ``update-examples.yml`` is the nearby example to copy from, and it
    does cancel -- this fails rather than quietly reopening the gap. A group with
    ``cancel-in-progress: false`` is fine and passes.
    """
    workflow = _workflow()
    concurrency = workflow.get("concurrency")
    if concurrency is None:
        return
    if isinstance(concurrency, str):
        return
    assert concurrency.get("cancel-in-progress") is not True, (
        "ci.yml cancels in-progress runs. On develop that means a merge commit finishes "
        "with no verdict, recreating the gap #412 closed. Use cancel-in-progress: false."
    )


# --- Every @slow module is named by a workflow ---------------------------------
# Every slow step in ci.yml selects modules by PATH, not by marker: the fast step
# deselects `-m slow`, and each slow step lists the files it runs. So a new @slow module
# is collected by no step at all and reports nothing, while the author sees it pass
# locally and CI go green. The failure is silent in the worst direction -- a gate that
# has never run looks identical to a gate that runs and passes.
#
# ci.yml already argues this in prose at three separate steps ("the marker makes a gate
# runnable, naming its module is what makes it RUN"), which is precisely the situation
# this repository treats as under-gated: a convention carried only in comments. It has
# been rediscovered twice, by the packaging gate (#398) and by the draft extraction
# recall gate (#6 review).
#
# Scanning EVERY workflow, not just ci.yml, is deliberate: test_govinfo_corpus_parity.py
# is excluded from ci.yml on purpose because it fetches live, and runs from
# corpus-parity.yml instead. Naming a module in any workflow satisfies this.


def _slow_test_modules() -> list[Path]:
    """Test modules that define at least one @slow test, found by AST, not by grep.

    A text search for "pytest.mark.slow" also matches the many modules that only
    discuss the marker in a docstring or comment (test_corpus_manifest.py explains at
    length why it is deliberately NOT slow). Those are not gaps, and a false positive
    here would be an unfixable failure, so the marker is read from the syntax tree.
    """
    modules = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_slow_marker(node) for node in ast.walk(tree)):
            modules.append(path)
    return modules


def _is_slow_marker(node: ast.AST) -> bool:
    """True for the `pytest.mark.slow` attribute chain, wherever it appears.

    This covers all three spellings the suite uses -- a `@pytest.mark.slow` decorator, a
    module-level `pytestmark = pytest.mark.slow`, and a list of marks -- because every
    one of them contains this attribute access. Walking for the access rather than
    matching each shape means a fourth spelling is caught too.
    """
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "slow"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
    )


def test_every_slow_module_is_named_by_a_workflow() -> None:
    """A @slow module named by no workflow runs nowhere and reports green by absence."""
    slow_modules = _slow_test_modules()
    # Fails closed: an AST change or a moved directory that found nothing would
    # otherwise satisfy the assertion below while checking no module at all.
    assert slow_modules, "found no @slow test modules, so this gate asserted nothing"

    workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml")))
    unnamed = [path.name for path in slow_modules if path.name not in workflow_text]
    assert not unnamed, (
        f"{len(unnamed)} module(s) define @slow tests but are named by no workflow in "
        f".github/workflows, so those tests run nowhere in CI: {unnamed}. Add each to a "
        "slow step in ci.yml -- the marker makes the gate runnable, naming the module is "
        "what makes it run."
    )
