"""The `browser` tier fails closed under `--run-browser` (#599).

CI's dedicated browser step exists to run the Playwright tests with Chromium
present. Its launch helper — the module-scoped `chromium` fixture in both browser
modules — skips when the browser can't start: the right behavior for the default
`-m "not slow and not browser"` tier, where a contributor's machine may lack
Playwright, but a silent no-op under that CI step, where every test "passes" by
skipping and the step reports green while asserting nothing.

`--run-browser` is the CI step's signal (ci.yml): when set, a launch failure
raises instead of skipping, so a drifted or uninstallable Chromium reddens CI
instead of being reported as a clean pass. These tests prove the flag flips each
module's fixture from skip to raise, in both directions — a guard that has never
fired in the raise direction cannot distinguish "Chromium is fine" from "the
guard is broken".

The module-level ``importorskip("playwright")`` needs no counterpart here: it
guards the Python *package*, which CI's preceding ``playwright install chromium``
step would already fail loudly on if missing (#599).
"""

import pytest

from tests import test_frontend_browser as frontend
from tests import test_labeling_form_browser as labeling

_BROWSER_MODULES = (frontend, labeling)


class _Config:
    def __init__(self, run_browser):
        self._run_browser = run_browser

    def getoption(self, name):
        assert name == "--run-browser", name
        return self._run_browser


class _Request:
    def __init__(self, run_browser):
        self.config = _Config(run_browser)


def _force_launch_failure(monkeypatch, module, exc):
    """Make ``sync_playwright()`` raise before a browser is ever launched."""

    def boom():
        raise exc

    monkeypatch.setattr(module, "sync_playwright", boom)


@pytest.mark.parametrize(
    "module",
    _BROWSER_MODULES,
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_launch_failure_skips_without_run_browser(module, monkeypatch):
    """Default tier: a Chromium that can't launch still skips, not fails."""
    _force_launch_failure(monkeypatch, module, RuntimeError("chromium binary missing"))
    fixture = module.chromium.__wrapped__
    with pytest.raises(pytest.skip.Exception):
        next(fixture(_Request(run_browser=False)))


@pytest.mark.parametrize(
    "module",
    _BROWSER_MODULES,
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_launch_failure_raises_under_run_browser(module, monkeypatch):
    """Browser-tier strictness: the same failure reddens the test instead of hiding it."""
    _force_launch_failure(monkeypatch, module, RuntimeError("chromium binary missing"))
    fixture = module.chromium.__wrapped__
    with pytest.raises(RuntimeError, match="chromium binary missing"):
        next(fixture(_Request(run_browser=True)))
