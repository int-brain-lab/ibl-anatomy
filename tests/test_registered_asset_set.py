import hashlib
import json
from pathlib import Path

import pytest

from ibl_anatomy import (
    materialize_registered_asset_set,
    parse_registered_asset_set,
)


FIXTURE = Path(__file__).parent / "fixtures" / "linked-registered-slices-v1" / "pack"


def _resource(path: Path) -> dict:
    data = path.read_bytes()
    return {"url": path.as_uri(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _inventory(path: Path, name: str) -> str:
    entries = []
    for item in sorted(path.rglob("*")):
        if item.is_file() and (item.name == f"{name}-index.json.gz" or f"registered/{name}-" in item.as_posix()):
            data = item.read_bytes()
            relative = item.relative_to(path).as_posix()
            entries.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return hashlib.sha256(json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _lock() -> dict:
    projections = {}
    for name in ("coronal", "sagittal", "horizontal"):
        manifest = json.loads((FIXTURE / f"{name}.json").read_text())
        source = FIXTURE / f"{name}.json"
        projections[name] = {
            "manifest": _resource(source),
            "slice_count": manifest["slice_count"],
            "slice_shape": manifest["slice_shape"],
            "inventory_sha256": _inventory(FIXTURE, name),
        }
    return {
        "format": "ibl-atlas-registered-asset-set-v1",
        "schema_version": "1.0",
        "asset_set_id": "synthetic-registered-v1",
        "reference_space_id": "allen-ccf-2017",
        "grid_id": "synthetic-10um-grid-v1",
        "projections": projections,
        "provenance": {
            "annotation_source": _resource(FIXTURE / "anatomy-v2.json"),
            "lut_recipe": "synthetic fixture LUT; test-only",
            "terms_url": "https://alleninstitute.org/terms-of-use/",
            "citation_url": "https://alleninstitute.org/legal/citation-policy",
        },
    }


def test_registered_asset_set_materializes_complete_graph(tmp_path):
    lock = parse_registered_asset_set(_lock())
    root = materialize_registered_asset_set(lock, tmp_path / "assets")
    assert (root / "coronal" / "manifest.json").exists()
    assert (root / "horizontal" / "registered" / "horizontal-0.json.gz").exists()


def test_registered_asset_set_is_strict():
    document = _lock()
    document["unexpected"] = True
    with pytest.raises(ValueError, match="fields differ"):
        parse_registered_asset_set(document)
