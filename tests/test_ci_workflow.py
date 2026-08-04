"""Guardrails on the triggers of the workflows that own a required status check.

Two properties are pinned here: that the test suite runs when a commit lands on the
integration branch (#412), and that both required checks answer the merge_group event so
a merge queue can complete a merge (#416).


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

import re
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


# Slow modules CI deliberately does not run, each with the reason it is exempt.
# An entry here is a claim that the module is covered somewhere else or is not an
# offline gate -- not a place to park a module nobody wired up.
SLOW_MODULES_NOT_IN_CI_YML = {
    "tests/test_govinfo_corpus_parity.py": (
        "fetches BILLSTATUS live, so it is not an offline gate; it runs in corpus-parity.yml"
    ),
}


# A real marker: the decorator on its own line, or a module-level `pytestmark`.
# Matched structurally rather than as a substring, so a module that merely mentions
# the marker in prose (this one does, at length) is not counted as carrying it.
_SLOW_MARKER = re.compile(r"^\s*@pytest\.mark\.slow\b|^pytestmark\s*=.*\bpytest\.mark\.slow\b", re.MULTILINE)


def _slow_test_modules() -> set[str]:
    """Every tests/*.py module that marks at least one case @pytest.mark.slow."""
    root = Path(__file__).parent
    return {
        f"tests/{path.name}"
        for path in sorted(root.glob("test_*.py"))
        if _SLOW_MARKER.search(path.read_text(encoding="utf-8"))
    }


def _modules_named_in_ci() -> set[str]:
    """Every tests/*.py path named by any step's `run:` block in ci.yml."""
    text = WORKFLOW.read_text(encoding="utf-8")
    return {token.strip() for token in text.split() if token.strip().startswith("tests/") and token.endswith(".py")}


def test_every_slow_module_is_named_by_a_ci_step() -> None:
    """A @slow module named by no step is collected by nothing and passes by absence.

    Every slow step in ci.yml selects modules BY PATH, and the fast step excludes the
    slow marker, so adding a @slow file wires it into no job at all. The suite goes
    green because the file's assertions never ran -- indistinguishable, from the outside,
    from a file whose assertions all passed.

    ci.yml argues this in prose in three separate step comments, and it had still
    happened at least twice (the packaging gate, then the committee-report fixture gate
    in #295). Prose that no test enforces reads as settled while being ungated, which is
    the same reasoning that put the trigger assertions above in this file.
    """
    slow_modules = _slow_test_modules()
    named = _modules_named_in_ci()

    # Neither half may be empty, or the comparison below passes having compared nothing.
    assert slow_modules, "found no @slow test modules; the scan is broken, not the workflow"
    assert named, "found no tests/*.py paths in ci.yml; the parse is broken, not the workflow"

    unwired = slow_modules - named - set(SLOW_MODULES_NOT_IN_CI_YML)
    assert not unwired, (
        "these @slow test modules are named by no ci.yml step, so CI collects none of "
        "their cases and they pass green-by-absence:\n"
        + "\n".join(f"  {m}" for m in sorted(unwired))
        + "\n\nAdd each to a slow step's `run:` list, or declare it in "
        "SLOW_MODULES_NOT_IN_CI_YML with the reason it is covered elsewhere."
    )


def test_slow_module_exemptions_still_exist() -> None:
    """An exemption naming a deleted or de-marked module is stale, and hides the next one."""
    slow_modules = _slow_test_modules()
    stale = {m for m in SLOW_MODULES_NOT_IN_CI_YML if m not in slow_modules}
    assert not stale, (
        f"SLOW_MODULES_NOT_IN_CI_YML names module(s) that no longer exist or no longer "
        f"mark any case @slow: {sorted(stale)}. Remove the entry."
    )
