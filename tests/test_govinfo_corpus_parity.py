"""Parity gate: govinfo enumeration reproduces the on-disk corpus filenames (#10).

The #10 migration made BILLSTATUS date the single version-ordering authority and the
govinfo version code the naming authority. That legitimately renamed corpus files
(``4_reported-to-senate`` -> ``4_reported-in-senate``; 115-hr-1625 enrolled ``7_`` ->
``6_`` once the url-less Engrossed-Amendment-House phantom is excluded from the count).
This gate locks that alignment: every version filename already on disk must be one
govinfo enumeration would produce *today*, so a future ordering/naming change can't
leave the corpus pinned to stale names that then silently mis-key the property gates.

Live BILLSTATUS fetch per bill, so it is ``slow`` + ``network``: skipped by default, run
with ``pytest --run-network -m slow``. It needs both a network and a fully fetched corpus
(the >= 31-dir floor below), so it stays maintainer-run rather than a CI gate. It fetches
BILLSTATUS directly rather than reading a cache so it validates the *current* live
enumeration, not a snapshot that could drift with it.

The ``network`` marker replaced REQUIRE_CORPUS=1 in #278: the requirement is a network,
which no fixture scheme can supply, and the marker says that where the env var did not.
"""

from __future__ import annotations

import re

import httpx
import pytest

import fetch_govinfo as gi
from fetch_bills import sanitize_version_name
from tests.conftest import BILLS_DIR

pytestmark = [pytest.mark.slow, pytest.mark.network]

# bills/<congress>-<type>-<number>. Non-matching entries (bulk .zip archives, .error
# markers) are not per-bill corpus dirs and are skipped.
_DIR_RE = re.compile(r"^(\d+)-([a-z]+)-(\d+)$")

# The curated corpus is a *subset* of each bill's versions and may carry a version the
# bill textVersions enumeration path does not serve. 119-hr-1's Public Law text is the
# PLAW-* collection (a different govinfo collection, excluded by design), hand-added to
# the corpus. Keyed by bill dir -> the on-disk stems enumeration will not reproduce.
_ACCEPTED_EXTRA_STEMS: dict[str, set[str]] = {
    "119-hr-1": {"6_public-law"},
}

# Floor: the reproducible corpus currently has this many per-bill dirs. A FLOOR, not a
# pin — it fails if the corpus shrank (a fetch dropped bills, which would let the gate
# pass while comparing fewer bills, #167), and grows freely (a new bill is still checked
# by the per-dir assertion below).
_MIN_CORPUS_DIRS = 31


def _corpus_dirs():
    if not BILLS_DIR.exists():
        return []
    return sorted(d for d in BILLS_DIR.iterdir() if d.is_dir() and _DIR_RE.match(d.name))


def _enumeration_stems(client: httpx.Client, congress: int, btype: str, number: int) -> set[str]:
    """The ``{index}_{slug}`` stems download would write for this bill, from live enumeration."""
    versions = gi.enumerate_versions(client, congress, btype, number)
    return {f"{i}_{sanitize_version_name(v['type'])}" for i, v in enumerate(versions, 1)}


def test_govinfo_enumeration_reproduces_corpus_filenames():
    """Every on-disk version stem must be one govinfo enumeration produces now.

    Subset invariant, not set equality: the corpus keeps only some versions of a bill,
    so enumeration may list stems absent from disk (fine — just not fetched). The failure
    is the reverse — a stem ON disk that enumeration does NOT produce, i.e. a stale name.
    """
    dirs = _corpus_dirs()
    # Completeness floor: without it an empty/partial corpus would pass as
    # "0 compared, 0 stale" (#167 fail-open).
    assert len(dirs) >= _MIN_CORPUS_DIRS, (
        f"parity gate found {len(dirs)} corpus dirs under {BILLS_DIR}, expected >= "
        f"{_MIN_CORPUS_DIRS}. An incomplete corpus would pass without comparing — run the "
        "bill downloads in the README 'corpus setup' block before enforcing this gate. "
        "(scripts/fetch_test_assets.py does not help here: it only adds files to bill "
        "directories those downloads already create.)"
    )

    client = httpx.Client(timeout=30, follow_redirects=True)
    compared = 0
    stale: dict[str, list[str]] = {}
    try:
        for d in dirs:
            congress, btype, number = _DIR_RE.match(d.name).groups()
            enum_stems = _enumeration_stems(client, int(congress), btype, int(number))
            disk_stems = {f.stem for f in d.iterdir() if f.suffix in (".xml", ".pdf")}
            drift = disk_stems - enum_stems - _ACCEPTED_EXTRA_STEMS.get(d.name, set())
            compared += 1
            if drift:
                stale[d.name] = sorted(drift)
    finally:
        client.close()

    # Guards the loop actually ran to completion over every discovered dir.
    assert compared == len(dirs), f"compared {compared} of {len(dirs)} dirs (enumeration aborted early)"
    assert not stale, (
        f"{sum(len(v) for v in stale.values())} on-disk stem(s) across {len(stale)} bill(s) "
        "diverge from govinfo enumeration — stale names. Re-download the bill "
        "(fetch_bills.py download <congress> <type> <number> --format both), or add to "
        f"_ACCEPTED_EXTRA_STEMS if legitimate (e.g. a Public Law text): {stale}"
    )
