"""Tests for the diff_pdf CLI entry point (issue #25)."""

from __future__ import annotations

import builtins
import io
import os
from pathlib import Path

from deltatrack.diff_pdf import build_parser, main
from tests.corpus_paths import fixture_path

V1 = fixture_path("118-hr-8752", "1_reported-in-house.pdf")
V2 = fixture_path("118-hr-8752", "2_engrossed-in-house.pdf")
REPORT = "<!doctype html><p>old → new</p><p>⚠ unanchored</p>"


def test_fixtures_committed():
    """Fail-closed floor (#326): both PDFs are committed and manifested, so an absent
    one is a broken checkout, not an optional case. This used to be a class-level
    ``skipif`` written when the corpus was fetched rather than committed; a skip is
    green, so deleting either file would have silently turned the two CLI tests below
    off (the fail-open shape epic #288 collects, same as #287)."""
    absent = sorted(str(p) for p in (V1, V2) if not p.exists())
    assert not absent, f"committed diff_pdf CLI fixtures absent from checkout: {absent}"


class TestParser:
    def test_positional_and_output(self):
        args = build_parser().parse_args(["a.pdf", "b.pdf", "-o", "out.html"])
        assert args.v1_pdf == Path("a.pdf")
        assert args.v2_pdf == Path("b.pdf")
        assert args.output == Path("out.html")

    def test_label_defaults(self):
        args = build_parser().parse_args(["a.pdf", "b.pdf"])
        assert args.v1_label is None
        assert args.v2_label is None


class TestCli:
    def test_writes_html_file(self, tmp_path):
        out = tmp_path / "diff.html"
        main([str(V1), str(V2), "-o", str(out)])
        html = out.read_text()
        assert html.lstrip().lower().startswith("<!doctype html") or "<html" in html.lower()
        assert "reported-in-house" in html
        assert "engrossed-in-house" in html
        # Delegating to compare_pdfs_html means the report carries the
        # full-bill view + embedded export, not just the changed-section cards.
        assert "full-bill" in html
        assert "diff.json" in html

    def test_html_output_uses_utf8_when_host_default_is_cp1252(self, tmp_path, monkeypatch):
        """The real CLI writer preserves report bytes independently of the host default."""
        output = tmp_path / "diff.html"
        v1_pdf = tmp_path / "old.pdf"
        v2_pdf = tmp_path / "new.pdf"
        v1_pdf.write_bytes(b"old")
        v2_pdf.write_bytes(b"new")

        import deltatrack.diff_pdf as diff_pdf

        monkeypatch.setattr(diff_pdf, "render_pdf_diff_html", lambda *_args, **_kwargs: REPORT)

        original_builtin_open = builtins.open
        original_io_open = io.open
        original_os_open = os.open
        target_fds = set()

        class _TrackedTextHandle:
            def __init__(self, handle, fd):
                self._handle = handle
                self._fd = fd

            def __enter__(self):
                self._handle.__enter__()
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return self._handle.__exit__(exc_type, exc_value, traceback)
                finally:
                    target_fds.discard(self._fd)

            def close(self):
                try:
                    return self._handle.close()
                finally:
                    target_fds.discard(self._fd)

            def __getattr__(self, name):
                return getattr(self._handle, name)

            def __del__(self):
                target_fds.discard(getattr(self, "_fd", None))

        def is_output_path(file):
            try:
                return os.fspath(file) == os.fspath(output)
            except TypeError:
                return False

        def is_target_descriptor(file):
            return isinstance(file, int) and file in target_fds

        def uses_default_text_encoding(file, mode, encoding):
            return (
                (is_output_path(file) or is_target_descriptor(file))
                and isinstance(mode, str)
                and mode.startswith("w")
                and "b" not in mode
                and encoding in (None, "locale")
            )

        def tracked_os_open(*args, **kwargs):
            fd = original_os_open(*args, **kwargs)
            path = args[0] if args else kwargs.get("path")
            if is_output_path(path):
                target_fds.add(fd)
            return fd

        monkeypatch.setattr(os, "open", tracked_os_open)

        def builtin_open_with_cp1252_default(
            file,
            mode="r",
            buffering=-1,
            encoding=None,
            errors=None,
            newline=None,
            closefd=True,
            opener=None,
        ):
            target_descriptor = is_target_descriptor(file)
            if uses_default_text_encoding(file, mode, encoding):
                encoding = "cp1252"
                handle = original_builtin_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
                if target_descriptor:
                    return _TrackedTextHandle(handle, file)
                return handle
            return original_builtin_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        def io_open_with_cp1252_default(
            file,
            mode="r",
            buffering=-1,
            encoding=None,
            errors=None,
            newline=None,
            closefd=True,
            opener=None,
        ):
            target_descriptor = is_target_descriptor(file)
            if uses_default_text_encoding(file, mode, encoding):
                encoding = "cp1252"
                handle = original_io_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
                if target_descriptor:
                    return _TrackedTextHandle(handle, file)
                return handle
            return original_io_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        monkeypatch.setattr(builtins, "open", builtin_open_with_cp1252_default)
        monkeypatch.setattr(io, "open", io_open_with_cp1252_default)

        encoding_error = None
        try:
            main([str(v1_pdf), str(v2_pdf), "-o", str(output)])
        except UnicodeEncodeError as exc:
            encoding_error = exc

        assert encoding_error is None, "report output depended on the host default encoding"
        report = output.read_bytes()
        assert report == REPORT.encode("utf-8")
        decoded = report.decode("utf-8")
        assert "→" in decoded
        assert "⚠" in decoded

        unrelated_builtin = tmp_path / "unrelated-builtins.txt"
        with builtins.open(unrelated_builtin, "w") as handle:
            handle.write("→")
        assert unrelated_builtin.read_bytes() == "→".encode("utf-8")

        unrelated_io = tmp_path / "unrelated-io.txt"
        with io.open(unrelated_io, "w") as handle:
            handle.write("⚠")
        assert unrelated_io.read_bytes() == "⚠".encode("utf-8")

        unrelated_builtin_fd_path = tmp_path / "unrelated-builtins-fd.txt"
        unrelated_builtin_fd = os.open(unrelated_builtin_fd_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        try:
            with builtins.open(unrelated_builtin_fd, "w") as handle:
                handle.write("→")
        finally:
            try:
                os.close(unrelated_builtin_fd)
            except OSError:
                pass
        assert unrelated_builtin_fd_path.read_bytes() == "→".encode("utf-8")

        unrelated_io_fd_path = tmp_path / "unrelated-io-fd.txt"
        unrelated_io_fd = os.open(unrelated_io_fd_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        try:
            with os.fdopen(unrelated_io_fd, "w") as handle:
                handle.write("⚠")
        finally:
            try:
                os.close(unrelated_io_fd)
            except OSError:
                pass
        assert unrelated_io_fd_path.read_bytes() == "⚠".encode("utf-8")
        assert not target_fds

    def test_stdout_when_no_output(self, capsys):
        main([str(V1), str(V2)])
        captured = capsys.readouterr()
        assert "<html" in captured.out.lower()
