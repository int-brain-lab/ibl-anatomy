"""Copy or check a selector-contract bundle between explicit directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def _inventory(root: Path) -> dict[str, str]:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != "ibl-region-selector" or manifest.get("version") != 1:
        raise ValueError(f"unsupported selector contract manifest: {manifest_path}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files must be a nonempty path-to-SHA-256 object")
    actual: dict[str, str] = {}
    for relative, expected in files.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
            raise ValueError(f"unsafe manifest path: {relative!r}")
        payload = (root / path).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected:
            raise ValueError(f"SHA-256 mismatch for {relative} in {root}")
        actual[relative] = digest
    declared = {"manifest.json", *actual}
    present = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if present != declared:
        raise ValueError(f"bundle file graph differs in {root}: {sorted(present ^ declared)}")
    return actual


def sync(source: Path, destination: Path, *, check: bool = False) -> None:
    """Validate a source bundle, then copy it or require an identical destination."""
    source = source.resolve()
    destination = destination.resolve()
    source_hashes = _inventory(source)
    if check:
        if _inventory(destination) != source_hashes:
            raise ValueError(f"selector contract differs: {destination}")
        if (source / "manifest.json").read_bytes() != (destination / "manifest.json").read_bytes():
            raise ValueError(f"selector contract manifest differs: {destination}")
        return
    destination.mkdir(parents=True, exist_ok=True)
    for relative in [*source_hashes, "manifest.json"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    _inventory(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing manifest.json and bundle files")
    parser.add_argument("destination", type=Path, help="explicit destination directory")
    parser.add_argument("--check", action="store_true", help="verify destination without writing")
    args = parser.parse_args()
    sync(args.source, args.destination, check=args.check)


if __name__ == "__main__":
    main()
