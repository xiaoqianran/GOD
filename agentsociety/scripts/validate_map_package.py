#!/usr/bin/env python3
"""Validate a GOD v1 map package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _import_validator():
    package_root = _repo_root() / "packages" / "agentsociety2"
    sys.path.insert(0, str(package_root))
    from agentsociety2.backend.services.map_packages import (  # noqa: PLC0415
        MANIFEST_FILENAMES,
        validate_manifest_path,
    )

    return MANIFEST_FILENAMES, validate_manifest_path


def main() -> int:
    manifest_names, validate_manifest_path = _import_validator()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Map package directory or manifest path.")
    args = parser.parse_args()

    target = Path(args.path).expanduser()
    if not target.is_absolute():
        target = (_repo_root() / target).resolve()
    if target.is_dir():
        manifest_path = next((target / name for name in manifest_names if (target / name).exists()), None)
        if manifest_path is None:
            print(f"ERROR no map manifest found in {target}")
            return 1
    else:
        manifest_path = target

    validation = validate_manifest_path(manifest_path)
    for message in validation.errors:
        print(f"ERROR {message}")
    for message in validation.warnings:
        print(f"WARN {message}")
    if validation.ok:
        print(f"OK {manifest_path}")
    return 0 if validation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
