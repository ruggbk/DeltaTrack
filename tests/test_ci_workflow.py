"""Guardrails on the CI workflow's own triggers (#412).

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

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _push_branches(workflow: dict) -> list[str]:
    # PyYAML resolves a bare `on:` key to the boolean True (the YAML 1.1 truthy set),
    # not the string "on". Both spellings are looked up so this does not silently find
    # nothing -- an empty read here would pass the `develop` assertion vacuously if it
    # returned an empty list instead of raising.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, f"no trigger block parsed from {WORKFLOW}"
    return triggers["push"]["branches"]


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
