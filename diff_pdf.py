#!/usr/bin/env python3
"""`./diff_pdf.py` -- the command, wrapping `deltatrack.diff_pdf` (#398).

See `diff_bill.py` beside this file for why the wrapper exists and why `build_parser` is
re-exported rather than only `main`.
"""

from deltatrack.diff_pdf import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
