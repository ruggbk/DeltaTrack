"""Tests for extract_archives cache coherence (issue #61).

``TestDownloadArchiveZip`` in tests/test_fetch_bill_archives.py already covers the
download side -- whether a partial body is committed to disk (#63). This file covers
the stage after it: turning a cached ZIP into an extracted folder, where the failure
modes are about *reuse* rather than transfer.

Two invariants carry the weight. Extraction is skipped when the destination folder
already exists, which is what keeps a re-run cheap -- but it means the folder's mere
existence is taken as proof of a complete extraction, so a folder left behind by a
crashed run would be trusted forever. That is exactly why the failure path removes a
partial folder rather than leaving it: the cleanup is what makes the skip safe.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from fetch_bill_archives import archive_extract_dir, extract_archive, extract_archives


def write_archive(source: Path, name: str, members: dict[str, bytes] | None = None) -> Path:
    """Write a well-formed ZIP named ``{name}.zip`` into source."""
    # `is None`, not `or`: an explicitly empty dict means a zero-member ZIP, and
    # falling back on falsiness would silently write a one-member archive instead.
    if members is None:
        members = {f"{name}-1.xml": b"<billStatus/>"}
    path = source / f"{name}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    path.write_bytes(buf.getvalue())
    return path


class TestExtractArchive:
    def test_creates_the_destination_and_writes_members(self, tmp_path):
        archive = write_archive(tmp_path, "119-hr", {"a.xml": b"<a/>", "sub/b.xml": b"<b/>"})
        dest = tmp_path / "out"

        extract_archive(archive, dest)

        assert (dest / "a.xml").read_bytes() == b"<a/>"
        assert (dest / "sub" / "b.xml").read_bytes() == b"<b/>"

    @pytest.mark.parametrize(
        "member",
        [
            pytest.param("../escaped.xml", id="parent-traversal"),
            pytest.param("../../escaped.xml", id="double-parent-traversal"),
            pytest.param("/etc/escaped.xml", id="absolute-path"),
            pytest.param("sub/../../escaped.xml", id="traversal-after-descent"),
        ],
    )
    def test_members_cannot_escape_the_destination_directory(self, tmp_path, member):
        # These archives are third-party input (govinfo bulk data), so a member path
        # is untrusted. zipfile.extractall sanitizes traversal and absolute paths
        # itself, so this passes today and is not a live vulnerability -- it is here
        # because the obvious refactor, replacing extractall with a per-member loop
        # to add filtering or progress output, reintroduces a real escape while every
        # other test in this file stays green. That is not hypothetical: writing such
        # a loop and running this file did land a file outside the test directory.
        #
        # Containment is asserted structurally, against paths under tmp_path only.
        # Asserting on a fixed absolute location instead would make the test depend
        # on global filesystem state -- shared with every other process on the
        # machine, so a stale file from an unrelated run fails it and a concurrent
        # run makes it flaky.
        archive = write_archive(tmp_path, "119-hr", {member: b"<escaped/>"})
        dest = tmp_path / "out"

        extract_archive(archive, dest)

        written = [p for p in dest.rglob("*") if p.is_file()]
        assert written, "nothing extracted, so the containment check proved nothing"
        for path in written:
            assert dest.resolve() in path.resolve().parents
        # Nothing escaped one level up into the directory holding the archive.
        assert not (tmp_path / "escaped.xml").exists()

    def test_raises_on_a_corrupt_archive(self, tmp_path):
        archive = tmp_path / "119-hr.zip"
        archive.write_bytes(b"not a zip")

        with pytest.raises(zipfile.BadZipFile):
            extract_archive(archive, tmp_path / "out")


class TestExtractArchivesCacheCoherence:
    def test_extracts_each_archive_into_a_folder_named_for_its_stem(self, tmp_path):
        # Written out of alphabetical order so the assertion below tests the sort
        # rather than the order the files happened to be created in.
        write_archive(tmp_path, "119-s")
        write_archive(tmp_path, "119-hr")

        extracted = extract_archives(tmp_path)

        # Compared in order, not sorted: extract_archives sorts its glob, and other
        # tests here rely on that ordering being deterministic (the batch-resilience
        # test needs the corrupt archive to come first). Sorting the actual value
        # would discard the very property those tests lean on, leaving the return
        # order free to follow filesystem order unnoticed.
        assert [p.name for p in extracted] == ["119-hr", "119-s"]
        assert (tmp_path / "119-hr" / "119-hr-1.xml").exists()

    def test_existing_folder_is_skipped_and_left_untouched(self, tmp_path):
        # The skip is keyed on folder existence alone, so a pre-existing folder wins
        # over the archive's actual contents. Pinning it keeps the re-run cheap and
        # documents that the folder, not the ZIP, is the cache.
        write_archive(tmp_path, "119-hr", {"fresh.xml": b"<fresh/>"})
        stale_dir = tmp_path / "119-hr"
        stale_dir.mkdir()
        (stale_dir / "stale.xml").write_bytes(b"<stale/>")

        extracted = extract_archives(tmp_path)

        assert extracted == []  # skipped, so not reported as newly extracted
        assert (stale_dir / "stale.xml").exists()
        assert not (stale_dir / "fresh.xml").exists()

    def test_partial_folder_from_a_failed_extract_is_removed(self, tmp_path):
        # The cleanup is what makes the existence-based skip safe: a folder left
        # behind here would be treated as a complete extraction by every later run,
        # silently serving a truncated corpus.
        corrupt = tmp_path / "119-hr.zip"
        corrupt.write_bytes(b"not a zip")

        extracted = extract_archives(tmp_path)

        assert extracted == []
        assert not archive_extract_dir(tmp_path, corrupt).exists()

    def test_a_failed_archive_does_not_abort_the_batch(self, tmp_path):
        # Sorted order puts the corrupt archive first, so a bare raise would cost the
        # healthy ones too.
        (tmp_path / "119-aaa.zip").write_bytes(b"not a zip")
        write_archive(tmp_path, "119-zzz")

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-zzz"]
        assert (tmp_path / "119-zzz" / "119-zzz-1.xml").exists()
        assert not (tmp_path / "119-aaa").exists()

    def test_only_zip_files_are_considered(self, tmp_path, capsys):
        # The bills directory holds bills.csv and extracted folders alongside the
        # archives, so the glob is what keeps them out. Asserting the extracted list
        # alone would not catch a widened glob: a non-ZIP that gets attempted fails to
        # open and is swallowed by the same except that handles a corrupt archive, so
        # the list comes out identical either way and only the log betrays it.
        write_archive(tmp_path, "119-hr")
        (tmp_path / "notes.txt").write_text("ignore me")
        (tmp_path / "bills.csv").write_text("id\n")

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-hr"]
        assert not (tmp_path / "notes").exists()
        err = capsys.readouterr().err
        assert "notes.txt" not in err
        assert "bills.csv" not in err

    def test_zero_member_archive_still_creates_its_folder(self, tmp_path):
        # A zero-member ZIP is structurally valid and is deliberately not treated as a
        # failed download (see _verify_archive_complete). zipfile.extractall does not
        # create the destination when there is nothing to write, so the explicit
        # mkdir in extract_archive is the only thing that does -- and without the
        # folder the run would report an extraction that left no cache entry, so the
        # next run would extract it again instead of skipping.
        write_archive(tmp_path, "119-hr", members={})

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-hr"]
        assert (tmp_path / "119-hr").is_dir()
        assert extract_archives(tmp_path) == []  # now a coherent cache entry

    def test_empty_source_directory_yields_nothing(self, tmp_path):
        assert extract_archives(tmp_path) == []

    def test_missing_source_directory_raises(self, tmp_path):
        missing = tmp_path / "nope"
        with pytest.raises(ValueError, match="Source folder does not exist"):
            extract_archives(missing)

    def test_rerun_after_a_successful_extract_is_a_no_op(self, tmp_path):
        # The cache-coherence property stated end to end: extract, then extract again
        # and get nothing new, with the first run's output intact.
        write_archive(tmp_path, "119-hr")

        first = extract_archives(tmp_path)
        second = extract_archives(tmp_path)

        assert [p.name for p in first] == ["119-hr"]
        assert second == []
        assert (tmp_path / "119-hr" / "119-hr-1.xml").exists()
