#!/usr/bin/env python3
"""Restore header comments to corpus_manifest.toml after tomlkit rewrite."""

from pathlib import Path

# Get the header comments from the original manifest
header_comments = """# Corpus test-fixture manifest — the single source of truth for the committed bill
# set the CI correctness gates run against. See docs/decisions/0015-corpus-test-fixtures.md.
#
# WHY THIS FILE EXISTS
# The corpus correctness gates (tests/test_corpus_properties.py,
# tests/test_corpus_tree_properties.py, tests/test_diff_validation.py) used to
# parametrize over `bills/*/[0-9]*_*.xml` discovered at collection time. `bills/` is
# gitignored, so the collected set was whatever each machine had fetched: counts were
# not reproducible, and on an unfetched checkout (including CI) the gates collected
# zero cases and passed green with no assertions — the fail-open trap ADR 0009 exists
# to prevent. This manifest replaces that glob: the gates parametrize over exactly the
# bills named here, every one of which is committed to git, so the collected set is
# byte-identical on every machine and in CI.
#
# HOW THE GATES READ IT
# tests/conftest.py loads this file once (stdlib tomllib) and derives the XML-file
# list, the PDF-file list, and the adjacent-version pairs the gates parametrize over.
# A file `tests/corpus/<id>/<stage>.<format>` is built for every (bill, version, format)
# below. Because those files are committed, a normal checkout always has them; the
# per-module completeness floor (test_manifest_fixtures_committed) fails closed if any
# is absent — that is the CI signal that a manifested fixture was not committed.
#
# ADDING A FIXTURE — see the "Adding a corpus fixture" recipe in TESTING.md. In short:
# put the bill files under tests/corpus/<id>/ and `git add` them, add a [[bill]] entry
# here, and run the gates so any per-bill baseline (_KNOWN_DUPLICATE_COUNTS,
# _XML_DROP_BUDGET, ...) is calibrated. Manifest and committed files must move together.
# NOT bills/ — that tree is wholly gitignored since #308, so `git add` there is a silent
# no-op and the fixture would live only on your disk.
# An entry here also ENROLLS the bill in the corpus property gates, which may then
# content-skip on it; an undeclared skip fails the session. TESTING.md's "When a skip
# has to be declared" covers which allowlist applies, and when the right answer is to
# withhold the fixture instead — see this file's 115-hr-244 note for that case (#330).
#
# SCOPE (#217 / #126): this is the initial curated floor — the bills the gates encode
# hand-pinned baselines for, plus one bill per appropriations subcommittee and the
# key structural shapes (omnibus, enrolled, minibus, reconciliation, Senate print).
# Broadening the curation (e.g. per-subcommittee reported-House PDFs) is #126. The
# opt-in `CORPUS_SWEEP=1` exploratory mode still sweeps every locally-fetched bill.

# --- Diff-validation baselines -------------------------------------------------

"""

manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
content = manifest_path.read_text(encoding="utf-8")

# Check if header already exists
if not content.startswith("# Corpus test-fixture manifest"):
    # Prepend header
    content = header_comments + content
    manifest_path.write_text(content, encoding="utf-8")
    print("Header comments restored!")
else:
    print("Header comments already present")

# Also restore section comments that may have been lost
# Check for section markers
section_comments = {
    "# --- Structural-shape coverage -------------------------------------------------": "Structural-shape",
    "# --- PDF pipeline + XML/PDF diff ----------------------------------------------": "PDF pipeline",
    "# --- PDF-golden SEC.-catchline false-positive repros (#89, committed by #287) ---": "PDF-golden",
    "# --- One Senate reported print per appropriations subcommittee -----------------": "Senate reported",
    "# --- Legislative Branch external-validation set (#278) -------------------------": "Legislative Branch",
    "# --- Account-vocabulary floor bills (previously fetch-only) --------------------": "Account-vocabulary",
}

# We'll add these before the relevant bills
# For now, just the header is the main fix
print("Done!")
