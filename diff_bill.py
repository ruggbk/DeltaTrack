#!/usr/bin/env python3
"""`./diff_bill.py` -- the command, wrapping `deltatrack.diff_bill` (#398).

The engine moved into `src/deltatrack/` and a module inside a package cannot be run as a
script: direct execution puts the package's own directory on `sys.path`, so `deltatrack`
is not importable from within it. This file is what keeps the documented invocation
working, and it resolves the engine through the INSTALLED distribution -- `source ./init`
(which runs `uv sync`) is what puts it there.

`build_parser` is re-exported, not merely imported for side effects:
`tests/test_docs_consistency.py` imports this module by name and walks its parser to
enumerate the subcommands that must appear in the README's command reference. Dropping it
would leave that gate discovering a bare `./diff_bill.py` and reporting the table complete
while every subcommand went undocumented.
"""

from deltatrack.diff_bill import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
