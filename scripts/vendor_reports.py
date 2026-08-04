#!/usr/bin/env python3
"""Download and vendor committee report HTMLs for the corpus.

Exits with non-zero code if any download fails, so CI catches missing fixtures.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# Run-from-anywhere: put the repo root on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tomllib

from tests.corpus_paths import DATA_DIR  # noqa: E402


def load_manifest() -> dict:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        return tomllib.load(f)


def extract_report_pkgs(manifest: dict) -> set[str]:
    """Extract all unique report package IDs from the manifest."""
    pkgs = set()
    for bill_entry in manifest.get("bill", []):
        for ver in bill_entry.get("versions", []):
            cr = ver.get("committee_report")
            # Handle both single object and list of report sources
            if cr:
                if isinstance(cr, list):
                    for src in cr:
                        if src.get("pkg") and src["pkg"] != "none":
                            pkgs.add(src["pkg"])
                elif cr.get("pkg") and cr["pkg"] != "none":
                    pkgs.add(cr["pkg"])
    return pkgs


def download_report(pkg: str, dest_dir: Path) -> Path:
    """Download a committee report HTML from govinfo."""
    url = f"https://www.govinfo.gov/content/pkg/{pkg}/html/{pkg}.htm"
    dest = dest_dir / f"{pkg}.htm"

    if dest.exists():
        print(f"  Already exists: {dest.name}")
        return dest

    print(f"  Downloading {pkg}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (govinfo, https)
        content = resp.read()
    if not content:
        raise RuntimeError(f"Empty response for {pkg}")
    dest.write_bytes(content)
    print(f"  Saved: {dest.name} ({len(content):,} bytes)")
    return dest


def main():
    manifest = load_manifest()
    pkgs = extract_report_pkgs(manifest)

    print(f"Found {len(pkgs)} unique report packages to vendor:")
    for pkg in sorted(pkgs):
        print(f"  {pkg}")

    dest_dir = DATA_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    for pkg in sorted(pkgs):
        download_report(pkg, dest_dir)  # Let exceptions propagate

    print("\nAll reports downloaded successfully!")


if __name__ == "__main__":
    main()
