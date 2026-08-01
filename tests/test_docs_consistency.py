"""Guardrails that keep the docs from drifting out of sync with how the suite runs.

These are plain text checks over Markdown files, not behavior tests, so they carry
no markers and run in the default fast suite.
"""

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Docs that show how to run the tests. The fast/no-setup suite must EXCLUDE the
# browser tests (they need a one-time `playwright install chromium`), so the
# canonical marker is `not slow and not browser`. The bare `not slow` is stale:
# it now also selects the browser tests. See issue #124, fixed across #118/#120/#121.
_DOCS_WITH_RUN_COMMANDS = [
    "README.md",
    "TESTING.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
]

_STALE_MARKERS = ('-m "not slow"', "-m 'not slow'")


def test_docs_use_current_fast_test_marker():
    """No doc should show the stale `-m "not slow"` fast-test command.

    Whenever a new marker is added that should stay out of the fast run, update
    that marker list AND every command below, or this test fails on purpose.
    """
    offenders = []
    for rel in _DOCS_WITH_RUN_COMMANDS:
        path = ROOT / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if any(marker in line for marker in _STALE_MARKERS):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Docs show the stale fast-test marker (now selects browser tests). "
        'Use `-m "not slow and not browser"` instead:\n' + "\n".join(offenders)
    )


# --- Sourced setup commands name an explicit path (#313) ------------------------
# Given a bare word, bash's `source` searches PATH before the current directory.
# On most Linux distributions /usr/sbin is on PATH and holds systemd's `init`, so
# `source init` reads that instead of this repo's script and setup dies on step one
# with "cannot execute binary file". macOS has no /usr/sbin/init, so the search
# falls through to the current directory and the same instruction works -- which is
# why the broken form survived in the docs: it cannot reproduce on a Mac, and not
# from an established checkout on any OS. `source ./init` skips the PATH search.
#
# Read out of the fenced shell blocks, never as a substring over the whole file: the
# surrounding prose deliberately quotes the broken `source init` to explain the
# hazard, so a substring check would fail on the very docs that get this right.

# Every fence language that marks a block a reader will copy commands out of. The
# docs use `bash` throughout today; the rest are here so a block opened with an
# equivalent tag is not silently skipped, which would let the broken form back in
# through a gate that still reports green.
_SHELL_FENCES = {"```bash", "```sh", "```shell", "```console", "```zsh"}


def _shell_blocks(text: str) -> list[str]:
    """The contents of every fenced shell block, without the fence lines."""
    blocks, current = [], None
    for line in text.splitlines():
        if current is None:
            if line.strip() in _SHELL_FENCES:
                current = []
        elif line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
        else:
            current.append(line)
    return blocks


def _sourced_commands() -> list[tuple[str, str]]:
    """Every `source <arg>` / `. <arg>` line a reader would copy out of the docs.

    Matched on the split words rather than a literal `"source "` prefix, so a tab
    between the builtin and its argument is read rather than skipped, and a leading
    `$ ` prompt is dropped first, which is how a `console` block writes a command.
    Both are ways for a line to be copyable by a reader and invisible to the gate.
    """
    found = []
    for rel in _DOCS_WITH_RUN_COMMANDS:
        for block in _shell_blocks((ROOT / rel).read_text()):
            for line in block.splitlines():
                stripped = line.strip().removeprefix("$ ").strip()
                words = stripped.split()
                if len(words) >= 2 and words[0] in ("source", "."):
                    found.append((rel, stripped))
    return found


def _sourced_argument(line: str) -> str:
    """The path a `source`/`.` line names, with any quoting removed.

    `source "./init"` is correct and must not be reported: the quotes are the
    reader's, not part of the path, and bash strips them before the PATH search
    decision that this gate is about.
    """
    return line.split()[1].strip("\"'")


def test_sourced_setup_commands_use_an_explicit_path():
    """A sourced script must be named by path, so PATH is never consulted.

    Fails on `source init`, passes on `source ./init` -- and equally covers any
    future setup script the same collision would reach.
    """
    offenders = [
        f"{rel}: {line}"
        for rel, line in _sourced_commands()
        if not _sourced_argument(line).startswith(("./", "../", "/", "$", "~"))
    ]

    assert not offenders, (
        "Docs source a script by bare name, which searches PATH first and on Linux "
        "finds the system /usr/sbin/init instead (#313). Add a leading `./`:\n" + "\n".join(offenders)
    )


def test_the_sourced_command_gate_actually_read_a_command():
    """Completeness floor for the gate above.

    The gate is a parse, and a parse that quietly matches nothing passes green over
    docs that are entirely wrong. Floor both steps: that some bash block was read at
    all, and that the specific setup command this exists to protect was among them.

    Floors rather than pins the exact line, matching the convention of the command
    gate's floor below: an inline comment on the setup line, or a second legitimate
    mention of it elsewhere in the README, must not turn this red -- the docs would
    be correct and the failure would point at them anyway.
    """
    commands = _sourced_commands()
    assert commands, "no `source` line found in any documented shell block -- the block parse is broken, not the docs"

    setup = [line for rel, line in commands if rel == "README.md" and "init" in line]
    assert setup, f"README quickstart setup command was not read at all -- parsed {commands}"


# --- CLI surface vs the README command reference (#135) -------------------------
# The product commands are wrapper scripts in the project root, and the README's
# "Command reference" table is where a user finds them. Nothing tied the two
# together, so a new subcommand could ship fully working and undiscoverable.
#
# Both the wrapper roster and each script's subcommands are discovered, never
# listed by hand: a hand-maintained roster would need the same discipline the table
# already lacked, and would pass while both drifted together. Discovering it also
# covers the larger version of the failure -- a whole new wrapper script shipping
# undocumented, which a fixed list would not have looked at.


def _command_roots() -> list[Path]:
    """Directories that can hold a runnable command.

    Derived from `ROOT` at call time, never captured at import, so the isolated-root test
    below can still substitute a fake tree and have the whole discovery chain follow it.
    `tools/` is included only when it exists, which is what lets that fake tree describe a
    repo with no tooling directory at all.
    """
    return [root for root in (ROOT, ROOT / "tools") if root.is_dir()]


def _wrapper_paths() -> list[Path]:
    """Every executable `.py` across the command roots, as paths."""
    return [p for root in _command_roots() for p in sorted(root.glob("*.py")) if p.stat().st_mode & 0o111]


def _wrapper_scripts() -> dict[str, str]:
    """Every product command: importable module name -> the command a user types.

    Discovery keys on the executable bit because that is a property of *commands*: a
    file carrying the bit has a shebang and is meant to be run directly. The previous
    rule -- "is a symlink in the project root" -- was a property of how the commands
    happened to be laid out, since each shipped a bare-name symlink beside it purely to
    drop the `.py` from the invocation (#319). Anything else linked into the root was
    therefore reported as an undocumented command, and it failed quietly rather than
    loudly: `_cli_commands` imports each name it discovers, and a directory with no
    `__init__.py` still imports as a namespace package, so `build_parser` was simply
    absent and the directory was recorded as a bare command name.

    That collided with something the project actively encourages. AGENTS.md notes a git
    worktree is fail-open for the fetched-bill suites, and linking `bills_corpus` /
    `bills_bulk_text` into the root is the direct way to make those gates run. Doing so
    made this gate demand README rows for two data directories, so the more completely
    you arranged for the corpus gates to run, the more certainly this one failed,
    naming a file the branch never touched. The alias symlinks are gone as of that fix,
    which removes the collision at its source rather than teaching discovery to
    tolerate it.

    A shebang alone would not discriminate: `fetch_govinfo.py` carries one but is a
    module, not a command. The bit is tracked in git (mode 100755 vs 100644), so it
    travels with a clone and shows up in review.

    `init` is absent for free -- it is extensionless, and is sourced to set up the
    environment rather than run. So are the root modules (`bill_tree.py`,
    `fetch_govinfo.py`, ...), which are imported, carry no bit, and are not commands.

    Returns module names rather than filenames because `_cli_commands` imports each one;
    the `.py` is re-added there, where the command is spelled the way a user types it.

    Filesystems that do not carry an executable bit (a Windows checkout) yield an empty
    roster, which the completeness floor below turns into a loud failure rather than a
    silently passing gate.

    Returns the invocation alongside the module name because commands no longer all live
    in one place (#367): the bill-fetching scripts moved to `tools/`, so a user types
    `./tools/fetch_bills.py` while the module still imports as `fetch_bills`. Deriving the
    typed form from the file's own location keeps the README rows checked against where
    the command actually is, instead of a prefix hardcoded here that a later move would
    leave pointing at the old tree.
    """
    return {p.stem: f"./{p.relative_to(ROOT).as_posix()}" for p in _wrapper_paths()}


def _cli_commands() -> dict[str, list[str]]:
    """Every documentable command, keyed by the wrapper script that provides it.

    A parser with subcommands contributes one entry per subcommand (`./tools/fetch_bills.py
    search`); a parser that takes only options contributes the bare script name,
    which is how the README names it. A wrapper with no `build_parser` at all
    (fetch_bill_archives runs a hardcoded congress range with no flags and has no
    argparse yet, #10) contributes the bare script name for the same reason.

    Spelled the way a user actually types it, path included -- `./diff_bill.py` but
    `./tools/fetch_bills.py` (#367). The bare-name alias symlinks that once made `./name`
    work are gone (#319).
    """
    commands: dict[str, list[str]] = {}
    for script, invocation in _wrapper_scripts().items():
        build_parser = getattr(importlib.import_module(script), "build_parser", None)
        if build_parser is None:
            commands[script] = [invocation]
            continue
        parser = build_parser()
        subcommands = [
            name
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for name in action.choices
        ]
        commands[script] = [f"{invocation} {name}" for name in subcommands] if subcommands else [invocation]
    return commands


def _command_reference_section() -> str:
    """The README's "Command reference" section, up to the next heading."""
    text = (ROOT / "README.md").read_text()
    start = text.index("## Command reference")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def _documented_commands() -> list[str]:
    """The command each "Command reference" row documents, from its leading cell.

    A row reads ``| `./fetch_bills.py download <congress> …` | What it does |``, so the
    first backticked span of the first cell is the command plus its arguments.
    """
    return [line.split("`")[1] for line in _command_reference_section().splitlines() if line.startswith("| `./")]


def _is_documented(command: str, rows: list[str]) -> bool:
    """Whether a row documents `command` -- matched on a whole-token boundary.

    Never a bare substring. `./fetch_bills.py download` is a prefix of the
    `download-all` row, so a plain `in` test reports the download row as present
    after it has been deleted -- the same defect this change removes from the money
    assertions (#264), which this gate must not reintroduce. Requiring the row to be
    the command exactly, or the command followed by a space, is what makes it able
    to fail.
    """
    return any(row == command or row.startswith(command + " ") for row in rows)


def test_every_cli_command_appears_in_the_readme_command_reference():
    """A command that is not in the table is a command nobody will find.

    Fails when a new subcommand lands undocumented, and equally when a rename
    silently orphans the row that used to describe it.
    """
    rows = _documented_commands()
    missing = [cmd for cmds in _cli_commands().values() for cmd in cmds if not _is_documented(cmd, rows)]

    assert not missing, (
        "CLI commands missing from the README 'Command reference' table: "
        f"{missing}. Add a row for each, or rename the existing row to match."
    )


def test_a_row_documents_only_its_own_command():
    """The row match is a whole-token boundary, asserted on literals (#264).

    The only part of this gate a mutation survives. Every other step has a
    completeness floor below, but `_is_documented` is exercised solely through the
    live README, where every command currently has a row -- so relaxing it to a bare
    `in` test passes the whole suite while silently restoring the pre-#264 defect:
    the surviving `download-all` row would report `download` as documented after the
    download row was deleted, which is exactly the deletion this gate exists to catch.
    """
    rows = ["./fetch_bills.py download-all --start_year <Y>"]

    assert not _is_documented("./fetch_bills.py download", rows), (
        "a longer command's row must not document the shorter command it starts with"
    )
    assert _is_documented("./fetch_bills.py download-all", rows), "the row's own command, plus arguments"
    assert _is_documented("./diff_pdf.py", ["./diff_pdf.py"]), "a bare command matched exactly"


def test_the_command_gate_actually_found_commands():
    """Completeness floor for the gate above.

    Every step above is discovery, and discovery that quietly finds nothing makes the
    gate pass green over an entirely undocumented CLI. So floor each step: the wrapper
    roster, the subcommand walk through `parser._actions`, and the row parse the
    commands are matched against.

    Deliberately floors rather than pins exact rosters or counts -- a pinned list is
    the hand-maintained thing this gate replaced, and would fail on every legitimate
    new command.
    """
    scripts = _wrapper_scripts()
    # Named wrappers, not a count: a count passes while discovery returns the wrong set.
    # Every shipped command is named, not a sample: an unnamed one can lose its
    # executable bit and vanish from discovery while this floor still passes, which is
    # the silent direction. A new command joins this list along with its README row.
    for expected in (
        "fetch_bills",
        "diff_bill",
        "diff_pdf",
        "fetch_bill_archives",
        "fetch_bill_text_archives",
    ):
        assert expected in scripts, f"wrapper discovery missed {expected!r} -- found {scripts}"

    commands = _cli_commands()
    empty = sorted(script for script, cmds in commands.items() if not cmds)
    assert not empty, f"no commands discovered for {empty} -- introspection is broken, not the docs"

    # fetch_bills is the multi-subcommand script; a bare "./tools/fetch_bills.py" from it would
    # mean the subparser walk found nothing while still returning a plausible answer.
    assert len(commands["fetch_bills"]) > 1, "fetch_bills subcommands were not discovered"

    # The row parse feeds every match; if it returned [] the gate would report every
    # command missing, but if it silently under-parsed it would report none.
    rows = _documented_commands()
    assert len(rows) >= len(scripts), f"parsed only {len(rows)} command rows for {len(scripts)} wrappers"

    section = _command_reference_section()
    assert "| Command | What it does |" in section, "README 'Command reference' table not found"


def test_only_executable_root_scripts_are_discovered_as_commands(tmp_path, monkeypatch):
    """#319: discovery keys on the executable bit, not on the shape of the root.

    Pins both directions at once, because each is a way the gate goes wrong:

    * A linked data directory is not a command. The real trigger is linking the shared
      bill corpus into a git worktree so the corpus-gated suites run instead of
      skipping, which AGENTS.md asks for. Under the old "any root symlink" rule,
      discovery reported `bills_corpus` as an undocumented command and told the reader
      to add a README row for a data directory.
    * A root module is not a command either. `fetch_govinfo.py` carries a shebang but
      no executable bit, so a shebang test would over-discover where the bit does not.

    Builds a fake root rather than writing into the real one, so the test is isolated
    from whatever a given developer has linked in and cannot alter the checkout it
    runs from.
    """
    (tmp_path / "real_command.py").write_text("#!/usr/bin/env python3\ndef build_parser():\n    pass\n")
    (tmp_path / "real_command.py").chmod(0o755)
    (tmp_path / "a_module.py").write_text("#!/usr/bin/env python3\n# shebang, but imported, not run\n")
    (tmp_path / "a_module.py").chmod(0o644)
    (tmp_path / "corpus_data").mkdir()
    (tmp_path / "bills_corpus").symlink_to(tmp_path / "corpus_data", target_is_directory=True)
    (tmp_path / "init").write_text("# sourced, not run\n")
    # A second command root, so the tools/ half of discovery is pinned too (#367): the
    # invocation must carry the subdirectory, or the README rows would be checked against
    # a path no user can type.
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a_tool.py").write_text("#!/usr/bin/env python3\ndef build_parser():\n    pass\n")
    (tmp_path / "tools" / "a_tool.py").chmod(0o755)
    (tmp_path / "tools" / "tool_module.py").write_text("#!/usr/bin/env python3\n# imported, not run\n")
    (tmp_path / "tools" / "tool_module.py").chmod(0o644)

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert _wrapper_scripts() == {"real_command": "./real_command.py", "a_tool": "./tools/a_tool.py"}


def test_command_names_are_unique_across_command_roots():
    """Two roots share one flat module namespace, so a duplicate stem must be loud (#367).

    `_wrapper_scripts` is keyed by module name because `_cli_commands` imports each one,
    and `tools/` is on pytest's pythonpath rather than being a package. A `tools/x.py`
    added beside a root `x.py` would therefore collide: the dict keeps one, discovery
    silently reports a single command, and the other ships with no README row -- the
    undocumented-command failure this whole section exists to catch, reintroduced through
    the back door. Checks the paths, not the deduplicated mapping, which cannot show it.
    """
    stems = [p.stem for p in _wrapper_paths()]

    duplicates = sorted({stem for stem in stems if stems.count(stem) > 1})
    assert not duplicates, (
        f"command names collide across roots: {duplicates}. Two roots share one module "
        "namespace, so one would shadow the other and vanish from the README gate; rename one."
    )


def test_a_runnable_root_script_carries_the_executable_bit():
    """A new command that forgets `chmod +x` must fail loudly, not vanish quietly.

    Keying discovery on the executable bit means a command without it is not a command
    as far as the gate is concerned, so it ships with no README row and nothing
    complains -- the same silent-omission failure #135 exists to prevent, relocated.

    A root `.py` that both declares a shebang and runs a `__main__` block is asking to
    be executed directly, so it is a command missing its bit rather than a module.
    Neither half alone is enough to say that: `fetch_govinfo.py` has a shebang and no
    `__main__` (a library whose interpreter line is vestigial), while the opposite shape
    is a dev script invoked as `python <path>.py` -- `scripts/render_examples.py`, which
    has a `__main__` and no shebang. Both halves together is the shape only a command has.
    """
    offenders = []
    for root in _command_roots():
        for path in sorted(root.glob("*.py")):
            text = path.read_text()
            runnable = text.startswith("#!") and "__main__" in text
            if runnable and not path.stat().st_mode & 0o111:
                offenders.append(path.relative_to(ROOT).as_posix())

    assert not offenders, (
        f"Scripts look runnable but are not executable: {offenders}. A product command "
        "needs `chmod +x` to be discovered by the README gate above; if it is not a command, "
        "drop the shebang or the `__main__` block so it reads as a module."
    )


# --- No doc command names the retired fixture directory (#428) -------------------
# The fixture trees moved out of a top-level `test_data/` into `tests/data/` (#404), but
# TESTING.md kept telling the reader to reclaim the extraction cache with
# `rm -rf test_data/extract_cache`. That path is not merely stale, it is inert: the suite
# writes the cache to `tests/data/extract_cache/` (`tests/pdf_corpus.py`), so running the
# documented command frees nothing while reporting success, and the real cache -- which
# never reclaims superseded entries by design -- keeps growing unattended.
#
# `tests/test_fixture_layout.py` already rejects this path, but it builds its scan list
# from `rglob("*.py")`, so it sees Python only. A retired path living in a Markdown
# command sits outside every pattern it checks. This is that gate's docs half.
_RETIRED_FIXTURE_DIR = "test_data/"


def _tracked_markdown() -> list[str]:
    """Every Markdown file git tracks, as repo-relative POSIX paths.

    Enumerated from the index rather than by globbing doc roots: a glob over
    `*.md` + `docs/` + `.github/` misses `examples/README.md`, `scripts/README.md`,
    `schema/canonical-diff.md` and a fixture `.md`, while picking up the gitignored
    generated `worklist_sample.md`. Both errors point the wrong way for a gate -- the
    first narrows what is checked, the second reddens the suite over a file nobody
    committed.
    """
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.md"],
        capture_output=True,
        check=True,
        text=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def _code_spans(text: str) -> list[str]:
    """Every stretch of text a reader would copy as code, inline or fenced.

    Two shapes, because the defect this gate exists for was in the first and the
    obvious place for the next one is the second:

    - an inline span between backticks, which is how prose embeds a command
      ("just delete it: `rm -rf ...`"), and
    - each line of a fenced shell block, which `_shell_blocks` already isolates.

    Inline spans are read by splitting on the backtick rather than by regex: on a line
    outside a fence, the odd-numbered pieces of that split are exactly the spans. Lines
    inside any fence are excluded from the inline pass so a fence's own delimiters are
    never mistaken for span boundaries.
    """
    spans = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            pieces = line.split("`")
            spans += [piece for piece in pieces[1::2] if piece.strip()]
    for block in _shell_blocks(text):
        spans += [line.strip().removeprefix("$ ").strip() for line in block.splitlines() if line.strip()]
    return spans


def _retired_path_instructions() -> list[str]:
    """Doc code spans that tell a reader to act on the retired fixture directory.

    A span counts only when it names the retired path AND carries more than one word.
    That is the line between an instruction and a reference, and both genuinely occur:
    ADR 0015 (the corpus fixture split) deliberately records the old name in bare spans
    -- "the second fixture tree this record calls `test_data/` moved to `tests/data/`" --
    because an ADR documents the decision as it was made. A bare path is history; a path
    with a verb in front of it is something a reader will run.
    """
    offenders = []
    for rel in _tracked_markdown():
        for span in _code_spans((ROOT / rel).read_text()):
            if _RETIRED_FIXTURE_DIR in span and len(span.split()) > 1:
                offenders.append(f"{rel}: {span}")
    return offenders


def test_no_doc_command_names_the_retired_fixture_directory():
    """Fails on `rm -rf test_data/extract_cache`, passes on `rm -rf tests/data/extract_cache`.

    Bare `test_data/` references stay legal, so the ADRs that record the pre-move layout
    do not have to be rewritten to keep this green.
    """
    offenders = _retired_path_instructions()

    assert not offenders, (
        f"Docs give a command naming the retired top-level `{_RETIRED_FIXTURE_DIR}` tree, which "
        "the suite no longer reads or writes -- running it silently does nothing (#404 moved "
        "these under `tests/data/`). Repoint the command:\n" + "\n".join(offenders)
    )


def test_the_retired_path_gate_actually_read_code_spans():
    """Completeness floor for the gate above.

    The gate asserts an absence, so it passes green whether the docs are clean or the
    parse matched nothing at all -- a `git ls-files` that answered nothing, a fence
    tracker that swallowed every line, and correct docs are indistinguishable from its
    result alone. Floor both halves: that markdown was found, and that spans were read
    out of the one doc known to carry the cache instructions.
    """
    docs = _tracked_markdown()
    assert "TESTING.md" in docs, (
        f"`git ls-files` returned no TESTING.md -- the file enumeration is broken, not the docs ({len(docs)} found)"
    )

    spans = _code_spans((ROOT / "TESTING.md").read_text())
    assert spans, "no code span parsed out of TESTING.md -- the span parse is broken, not the docs"
    assert any("extract_cache" in span for span in spans), (
        "TESTING.md parsed to spans but none mention the extraction cache -- the doc changed "
        "shape and this gate is now watching nothing"
    )


def test_the_retired_path_rule_can_fire():
    """The rule must reject an instruction and accept a reference.

    A gate for a defect that is already fixed passes on its first run, which proves
    nothing about whether it can fail. Both directions are pinned here against literal
    input, so neither the retired-path match nor the instruction/reference distinction
    can be loosened without a red test.
    """
    instruction = _code_spans("just delete it: `rm -rf test_data/extract_cache`. The next run")
    assert instruction == ["rm -rf test_data/extract_cache"]
    assert [s for s in instruction if _RETIRED_FIXTURE_DIR in s and len(s.split()) > 1]

    reference = _code_spans("the tree this record calls `test_data/` moved to `tests/data/`")
    assert reference == ["test_data/", "tests/data/"]
    assert not [s for s in reference if _RETIRED_FIXTURE_DIR in s and len(s.split()) > 1]

    fenced = _code_spans("```bash\n$ rm -rf test_data/extract_cache\n```")
    assert fenced == ["rm -rf test_data/extract_cache"]
