"""Test the saved-archive failure status at the command process boundary (#325)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from bill_index import BillIndex
from fetch_bill_archives import DEFAULT_BILLS_DIR
from shared.bill_types import BILL_TYPES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FETCH_ARCHIVES_SCRIPT = REPOSITORY_ROOT / "tools" / "fetch_bill_archives.py"

# The smallest BILLSTATUS record that extract_bill_metadata_from_archive_xml accepts.
BILLSTATUS_XML = b"<billStatus><bill><congress>119</congress><type>S</type><number>1</number></bill></billStatus>"

OFFLINE_NETWORK_GUARD = """
import os
import pathlib
import socket


class OfflineNetworkAccess(BaseException):
    pass


pathlib.Path(os.environ["DELTA_OFFLINE_GUARD_MARKER"]).write_text("loaded", encoding="utf-8")


def _deny_network(*args, **kwargs):
    raise OfflineNetworkAccess("network access disabled for archive command test")


socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network
socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
"""


def _stage_saved_archives(project: Path, *, include_bad_archive: bool) -> Path:
    """Stage every saved archive the command would otherwise download.

    The command's range and bill-type list are intentionally hardcoded, so a hermetic
    invocation must satisfy the download phase for all of them. Existing extracted
    folders make every archive except the two cases under test a cache hit; the child
    process also rejects any attempted network operation.
    """
    bills_dir = project / DEFAULT_BILLS_DIR.name
    bills_dir.mkdir(parents=True)

    for congress in range(112, 120):
        for bill_type in BILL_TYPES:
            is_bad = include_bad_archive and (congress, bill_type) == (119, "hr")
            is_healthy_case = (congress, bill_type) == (119, "s")
            archive_path = bills_dir / f"{congress}-{bill_type}.zip"

            if is_bad:
                archive_path.write_bytes(b"not a zip")
            else:
                with zipfile.ZipFile(archive_path, "w") as archive:
                    if is_healthy_case:
                        archive.writestr("BILLSTATUS-119s1.xml", BILLSTATUS_XML)

            # Leave the two focused cases for phase 2. Every other archive is a
            # pre-existing extraction, so the process stays small while remaining a
            # complete successful download/extraction setup.
            if not is_healthy_case and not is_bad:
                (bills_dir / archive_path.stem).mkdir()

    return bills_dir


def _run_command(tmp_path: Path, *, include_bad_archive: bool) -> subprocess.CompletedProcess[str]:
    """Run the checked-in command script in a temporary project root."""
    project = tmp_path / "project"
    script = project / "tools" / FETCH_ARCHIVES_SCRIPT.name
    guard_dir = tmp_path / "offline_guard"
    guard_marker = guard_dir / "loaded"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(OFFLINE_NETWORK_GUARD, encoding="utf-8")
    script.parent.mkdir(parents=True)
    shutil.copy2(FETCH_ARCHIVES_SCRIPT, script)
    _stage_saved_archives(project, include_bad_archive=include_bad_archive)

    env = os.environ.copy()
    env["DELTA_OFFLINE_GUARD_MARKER"] = str(guard_marker)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(guard_dir), str(REPOSITORY_ROOT / "tools"), env.get("PYTHONPATH")) if part
    )
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_bad_saved_archive_fails_the_process_after_indexing_a_healthy_archive(tmp_path):
    result = _run_command(tmp_path, include_bad_archive=True)

    assert (tmp_path / "offline_guard" / "loaded").exists()
    index = BillIndex(tmp_path / "project" / DEFAULT_BILLS_DIR.name / (DEFAULT_BILLS_DIR.name + ".csv"))
    assert [record["id"] for record in index.bills] == ["119-s-1"]
    assert result.returncode != 0, result.stderr


def test_a_completely_successful_run_exits_zero(tmp_path):
    result = _run_command(tmp_path, include_bad_archive=False)

    assert (tmp_path / "offline_guard" / "loaded").exists()
    assert result.returncode == 0, result.stderr
