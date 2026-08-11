"""The engine installs into a clean environment and runs there (#398).

This is the gate the rest of the suite cannot be. Every other test imports `deltatrack`
from an editable install pointed straight at `src/`, which reports on the working tree,
not on the distribution -- a module left out of the wheel, a packaging config that drifts
from the layout, or a dependency declared in the wrong place all pass that way and break
on the first person who actually installs the thing.

So build the wheel, install it into a throwaway environment with no dev groups, and run a
real diff from a directory that is not the checkout. Three separate claims, each of which
has its own way of going quietly wrong:

* **It imports at all**, and imports from the *installed* copy. Asserted on
  `deltatrack.__file__`, not inferred from the import succeeding: with the checkout on
  `sys.path` the import would succeed either way, which is the fallback that makes an
  install check pass for the wrong reason. Running from a temp cwd already prevents it;
  the assertion is what proves the prevention worked.
* **The whole package shipped, not just the top level.** The diff exercises `parsers`,
  `diff_bill`, `formatters` and `compare` in one call, so a subpackage missing from the
  wheel fails here rather than on a user's machine.
* **`[project.dependencies]` is honest in both directions.** `pypdfium2` must arrive with
  the engine, and the web stack must not -- the claim ADR 0016 makes and #367 shipped
  with no way to check.

Marked `slow`: it builds a wheel and creates a virtualenv, so it belongs to the gate CI
runs for engine changes rather than to the fast inner loop.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.corpus_paths import fixture_path

ROOT = Path(__file__).resolve().parents[1]

#: A small committed XML pair -- ~180 KB a side, the lightest in the corpus that still
#: exercises the full parse-diff-render chain.
BILL_ID = "118-hr-8752"
OLD_STEM = "1_reported-in-house"
NEW_STEM = "2_engrossed-in-house"

pytestmark = pytest.mark.slow


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a step, and surface its stderr in the failure rather than a bare exit code."""
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    assert result.returncode == 0, (
        f"{' '.join(str(c) for c in command[:3])} … failed ({result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


@pytest.fixture(scope="module")
def installed_engine(tmp_path_factory) -> Path:
    """Interpreter of a throwaway venv holding ONLY the built engine and its deps.

    Built once per module: three assertions read from the same environment, and building
    a wheel plus resolving an install for each of them separately would triple the cost
    to re-verify the identical artifact.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH; the packaging gate needs it to build and install")

    workspace = tmp_path_factory.mktemp("engine-install")
    dist = workspace / "dist"

    _run([uv, "build", "--wheel", "--out-dir", str(dist)], cwd=ROOT)
    wheels = sorted(dist.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, built {[w.name for w in wheels]}"

    venv = workspace / "venv"
    # `--python sys.executable`, not a bare `uv venv`: uv resolves an unpinned request
    # through `.python-version` (3.12) first, so on any other leg every assertion below
    # would report on 3.12 while labelled as evidence for that leg's version.
    # `test_the_clean_install_uses_the_interpreter_running_the_test` fails without it.
    _run([uv, "venv", "--python", sys.executable, str(venv)])
    # A venv lays its interpreter out per-platform: POSIX `bin/python`, Windows
    # `Scripts\python.exe`. CI and the team run POSIX, so the second arm is for a
    # future Windows contributor rather than any environment this runs in today.
    if sys.platform == "win32":
        python = venv / "Scripts" / "python.exe"
    else:
        python = venv / "bin" / "python"
    assert python.is_file(), f"uv venv produced no interpreter at {python}"

    # No `--group` flags: this installs what a CONSUMER gets, which is the thing under test.
    _run([uv, "pip", "install", "--python", str(python), str(wheels[0])])
    return python


def test_the_installed_engine_runs_a_diff_from_outside_the_checkout(installed_engine, tmp_path):
    """The headline gate: a real diff, from an environment that never saw the source tree."""
    old = fixture_path(BILL_ID, f"{OLD_STEM}.xml")
    new = fixture_path(BILL_ID, f"{NEW_STEM}.xml")
    # Fail loudly rather than skipping: these are committed, so an absence is a corpus
    # defect, and skipping would retire the gate silently (#288).
    assert old.is_file() and new.is_file(), f"committed fixtures missing for {BILL_ID}"

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "import deltatrack\n"
        "from deltatrack.compare.xml import compare_xml_files_html\n"
        "html = compare_xml_files_html(Path(sys.argv[1]), Path(sys.argv[2]))\n"
        "print(json.dumps({'origin': deltatrack.__file__, 'length': len(html), "
        "'head': html[:200]}))\n"
    )

    # cwd is tmp_path, NOT the checkout: with the repo as cwd, `src/` is still absent from
    # sys.path but the dev-only modules would be importable as `tests.*` / `scripts.*`
    # namespace packages (#401), and a stray engine import of one of them would resolve
    # instead of failing. Running elsewhere removes that.
    result = _run([str(installed_engine), str(probe), str(old), str(new)], cwd=tmp_path)
    report = json.loads(result.stdout.strip().splitlines()[-1])

    assert Path(report["origin"]).is_relative_to(installed_engine.parent.parent), (
        f"the engine resolved from {report['origin']}, not from the installed environment "
        f"under {installed_engine.parent.parent} -- the checkout answered instead, so this "
        "gate proved nothing about the wheel"
    )
    # A floor, not an exact size: the renderer's output changes with every engine change,
    # but an empty or error-page result cannot reach five figures.
    assert report["length"] > 10_000, f"diff produced {report['length']} chars, which is not a report"
    assert "<" in report["head"], f"output is not HTML: {report['head']!r}"


def test_the_engine_install_brings_its_runtime_dependency(installed_engine):
    """`pypdfium2` must arrive with the engine, or PDF diffing is broken on install.

    Imported rather than read off `uv pip list`: the question is whether the dependency is
    usable in that environment, and a name appearing in a list does not answer it.
    """
    _run([str(installed_engine), "-c", "import pypdfium2"])


def test_the_engine_install_does_not_drag_in_the_web_channel(installed_engine):
    """ADR 0016's central claim, finally checkable.

    #367 narrowed `[project.dependencies]` so that installing DeltaTrack to diff two bills
    would not install a web server -- but with nothing installable, that was an assertion
    about a config file rather than about an install. It is a real environment now, so
    check the environment.

    Asserted as an ABSENCE, which is the vacuous-pass shape: a probe that could never
    import anything would pass this while proving nothing. The dependency test above is
    the known-good case that proves this probe can resolve a package at all.
    """
    for absent in ("fastapi", "uvicorn", "httpx"):
        result = subprocess.run(
            [str(installed_engine), "-c", f"import {absent}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"{absent!r} is importable in an engine-only install. The engine's "
            "[project.dependencies] has re-acquired a delivery-channel or tooling "
            "dependency; it belongs in a dependency-group instead (ADR 0016)."
        )
        assert "ModuleNotFoundError" in result.stderr, (
            f"importing {absent!r} failed for an unexpected reason, so this assertion is "
            f"not evidence of absence:\n{result.stderr}"
        )


def test_the_wrapper_commands_run_against_the_installed_engine(installed_engine, tmp_path):
    """`./diff_bill.py` is the documented invocation, so check it, not just the library.

    The wrapper is the only part of the product that stayed at the repo root, and it is the
    one piece whose import of `deltatrack` cannot be satisfied by the working tree. Copied
    next to the temp cwd rather than run in place, so a repo-root run cannot mask a broken
    wrapper by resolving something else.

    Asserts on the diff's actual content, not merely that JSON came back. `assert payload`
    accepted any truthy object, and a review demonstrated the cost concretely: with
    `compare/` excluded from the wheel this test still passed, because `--format json`
    never enters that subpackage. The headline test above caught that fault, so nothing
    shipped vacuously -- but a wrapper test that cannot tell a real diff from an empty one
    is not evidence about the wrapper.
    """
    wrapper = tmp_path / "diff_bill.py"
    wrapper.write_text((ROOT / "diff_bill.py").read_text())

    old = fixture_path(BILL_ID, f"{OLD_STEM}.xml")
    new = fixture_path(BILL_ID, f"{NEW_STEM}.xml")

    result = _run(
        [str(installed_engine), str(wrapper), "compare", str(old), str(new), "--format", "json"],
        cwd=tmp_path,
    )
    payload = json.loads(result.stdout)

    assert payload.get("summary"), f"no diff summary in the wrapper's output: {sorted(payload)}"
    # A floor on the work done, not an exact count: these two committed versions differ
    # substantially, so a run that parsed nothing cannot reach it, while the numbers stay
    # free to move as the engine improves.
    changed = sum(payload["summary"].get(kind, 0) for kind in ("added", "removed", "modified"))
    assert changed > 0, f"the wrapper reported a diff with no changes at all: {payload['summary']}"


def test_the_pdf_wrapper_also_resolves_the_installed_engine(installed_engine, tmp_path):
    """The other wrapper, which the test above does not reach.

    `diff_pdf.py` has its own import line, and the only thing exercising it was
    `tests/test_docs_consistency.py` importing it through the DEV editable install -- which
    says nothing about whether it resolves against the wheel. A typo there would ship.

    `--help` rather than a real PDF diff: the import and argument-parser wiring are what is
    unique to the wrapper, and the engine's PDF path is already covered by the headline
    test's dependency chain. Keeps the gate off the PDF fixtures.
    """
    wrapper = tmp_path / "diff_pdf.py"
    wrapper.write_text((ROOT / "diff_pdf.py").read_text())

    result = _run([str(installed_engine), str(wrapper), "--help"], cwd=tmp_path)

    assert "usage:" in result.stdout, f"the PDF wrapper printed no usage line:\n{result.stdout}"


def test_the_clean_install_uses_the_interpreter_running_the_test(installed_engine):
    """The gate must report on the interpreter it is running on, not on `.python-version`.

    Everything else here asks "does the engine install and work"; this asks WHERE. A leg
    labelled 3.14 that quietly builds a 3.12 environment is not weaker evidence, it is
    evidence for the wrong claim, and it reads green either way.

    Compared as (major, minor, micro), so a build tag or a differing `sys.version`
    preamble cannot make two identical interpreters look unequal.
    """
    reported = _run([str(installed_engine), "-c", "import sys; print(*sys.version_info[:3])"])
    inner = tuple(int(part) for part in reported.stdout.split())

    assert inner == tuple(sys.version_info[:3]), (
        f"the clean-install environment is Python {inner}, but this test is running on "
        f"{tuple(sys.version_info[:3])}. The venv was created without `--python`, so uv "
        "resolved it through `.python-version` instead of the running interpreter, and "
        "every other assertion in this module is reporting on the wrong Python."
    )


def test_this_gate_ran_against_a_freshly_built_wheel(installed_engine):
    """Completeness floor: prove the environment is not the developer's own.

    Every assertion above is conditional on `installed_engine` having built and installed
    something. A fixture that silently handed back `sys.executable` would leave all of them
    passing against the editable install they exist to bypass -- green, and worthless.
    """
    assert Path(installed_engine) != Path(sys.executable), (
        "the install fixture returned the running interpreter; nothing was installed"
    )
    assert not Path(installed_engine).is_relative_to(ROOT), (
        f"the install environment sits inside the checkout ({installed_engine}); it must be "
        "isolated from it for any of these assertions to mean anything"
    )
