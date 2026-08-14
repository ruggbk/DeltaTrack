"""The canonical-diff schema contract tests must fail closed without jsonschema (#585).

`jsonschema>=4.21` is a declared dev dependency (pyproject.toml), not an optional
extra, so a missing import means a broken environment and must be loud. This spawns
a child pytest session with `jsonschema` made unimportable and asserts the schema
contract tests redden rather than silently skip green — the same child-session
pattern as the skip-ceiling end-to-end tests in tests/test_corpus_manifest.py.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_TESTS = REPO_ROOT / "tests" / "test_formatters_canonical.py"

# Loaded via `-p` before any test module (or conftest) is imported, so the poison
# is in place at collection time. The `sys.modules` shim alone covers `import
# jsonschema`; the meta_path finder covers submodule imports too.
_BLOCKER = '''\
"""Child-session plugin making jsonschema unimportable (#585)."""
import sys

sys.modules["jsonschema"] = None  # any `import jsonschema` raises ImportError


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == "jsonschema" or name.startswith("jsonschema."):
            raise ImportError(f"{name} made unimportable for this session (#585)")
        return None


sys.meta_path.insert(0, _Blocker())
'''


def test_schema_contract_tests_redden_when_jsonschema_is_missing(tmp_path):
    blocker = tmp_path / "jsonschema_blocker_for_585.py"
    blocker.write_text(_BLOCKER)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:randomly",
            "-p",
            "jsonschema_blocker_for_585",
            "-n0",
            "-q",
            str(CONTRACT_TESTS),
            "-k",
            "schema",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0, (
        "schema contract tests stayed green with jsonschema unimportable — "
        f"a missing declared dependency must fail, not skip (#585)\n{r.stdout}\n{r.stderr}"
    )
    assert "jsonschema" in r.stdout + r.stderr, (
        f"session reddened for an unrelated reason, not the missing import\n{r.stdout}\n{r.stderr}"
    )
