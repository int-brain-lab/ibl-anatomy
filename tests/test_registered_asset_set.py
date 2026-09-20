import gzip
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from ibl_anatomy import (
    materialize_registered_asset_set,
    parse_registered_asset_set,
    verify_materialized_registered_asset_set,
)


FIXTURE = Path(__file__).parent / "fixtures" / "linked-registered-slices-v1" / "pack"


def _resource(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "url": path.as_uri(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _inventory(path: Path, name: str) -> str:
    entries = []
    for item in sorted(path.rglob("*")):
        if item.is_file() and (
            item.name == f"{name}-index.json.gz"
            or f"registered/{name}-" in item.as_posix()
        ):
            data = item.read_bytes()
            relative = item.relative_to(path).as_posix()
            entries.append(
                {
                    "path": relative,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return hashlib.sha256(
        json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _descriptor(
    path: Path,
    relative: str,
    *,
    codec: str = "gzip",
    media_type: str = "application/octet-stream",
) -> dict:
    data = path.read_bytes()
    decoded = gzip.decompress(data) if codec == "gzip" else data
    return {
        "path": relative,
        "media_type": media_type,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "codec": {"name": codec, "decoded_bytes": len(decoded)},
    }


def _published_graph(tmp_path: Path) -> tuple[dict, Path]:
    source = tmp_path / "source"
    shutil.copytree(FIXTURE, source)
    static = source / "static"
    static.mkdir()
    for name in ("top", "swanson"):
        (static / f"{name}.isvg.gz").write_bytes(
            gzip.compress(b'<path d="M0 0Z"/>', mtime=0)
        )
    licenses = source / "LICENSES"
    licenses.mkdir()
    (licenses / "NOTICE.txt").write_text("synthetic fixture\n", encoding="utf-8")

    projections = {}
    root_projections = []
    for name in ("coronal", "sagittal", "horizontal"):
        manifest = json.loads((source / f"{name}.json").read_text())
        root_projections.append(manifest)
        projections[name] = {
            "slice_count": manifest["slice_count"],
            "slice_shape": manifest["slice_shape"],
            "inventory_sha256": _inventory(source, name),
        }
    for name in ("top", "swanson"):
        relative = f"static/{name}.isvg.gz"
        root_projections.append(
            {
                "id": name,
                "kind": "static-regional-map",
                "path_count": 1,
                "view_box": [0, 0, 1, 1],
                "fragment": {
                    "format": "ibl-regional-svg-fragment-v1",
                    "encoding": "utf-8",
                    "resource": _descriptor(
                        source / relative, relative, media_type="image/svg+xml"
                    ),
                },
            }
        )
    notice = "LICENSES/NOTICE.txt"
    root = {
        "format": "atlas-projection-pack-v1",
        "schema_version": "1.0",
        "pack_id": "synthetic-root",
        "immutable": True,
        "reference_space_id": "allen-ccf-2017",
        "mappings": ["allen", "beryl", "cosmos"],
        "projections": root_projections,
        "provenance": {
            "recipe": {
                "license_notice": {
                    "format": "ibl-static-asset-license-v1",
                    "resource": _descriptor(
                        source / notice, notice, codec="none", media_type="text/plain"
                    ),
                }
            }
        },
    }
    (source / "manifest.json").write_text(
        json.dumps(root, indent=2) + "\n", encoding="utf-8"
    )
    lock = {
        "format": "ibl-atlas-registered-asset-set-v1",
        "schema_version": "1.0",
        "asset_set_id": "synthetic-registered-v1",
        "reference_space_id": "allen-ccf-2017",
        "grid_id": "synthetic-10um-grid-v1",
        "root_pack_id": "synthetic-root",
        "root_manifest": _resource(source / "manifest.json"),
        "projections": projections,
        "provenance": {
            "annotation_source": _resource(source / "anatomy-v2.json"),
            "lut_recipe": {
                "path": "fixture-lut",
                "bytes": 1,
                "sha256": "0" * 64,
                "producer": "test",
                "iblatlas_commit": "0" * 40,
            },
            "terms_url": "https://alleninstitute.org/terms-of-use/",
            "citation_url": "https://doi.org/10.1016/j.cell.2020.04.007",
            "citation_policy_url": "https://alleninstitute.org/legal/citation-policy",
        },
    }
    return lock, source


def test_registered_asset_set_rejects_non_projection_root_atomically(tmp_path):
    document, _ = _published_graph(tmp_path)
    document["root_manifest"] = _resource(FIXTURE / "coronal.json")
    lock = parse_registered_asset_set(document)
    with pytest.raises(ValueError, match="projection root identity"):
        materialize_registered_asset_set(lock, tmp_path / "invalid-assets")
    assert not (tmp_path / "invalid-assets").exists()


def test_registered_asset_set_materializes_and_verifies_complete_graph(tmp_path):
    document, _ = _published_graph(tmp_path)
    target = tmp_path / "assets"

    result = materialize_registered_asset_set(
        parse_registered_asset_set(document), target
    )

    assert result.root == target.resolve()
    assert result.pack_id == "synthetic-root"
    assert set(result.projections) == {"coronal", "sagittal", "horizontal"}
    assert result.file_count == 10
    assert result.encoded_bytes == sum(
        path.stat().st_size for path in target.rglob("*") if path.is_file()
    )
    assert result.root_manifest["immutable"] is True


def test_registered_asset_set_rejects_corrupt_transitive_resource_atomically(tmp_path):
    document, source = _published_graph(tmp_path)
    path = source / "registered/coronal-0.json.gz"
    path.write_bytes(path.read_bytes() + b"corrupt")
    target = tmp_path / "assets"

    with pytest.raises(ValueError, match="integrity mismatch"):
        materialize_registered_asset_set(parse_registered_asset_set(document), target)

    assert not target.exists()
    assert not list(tmp_path.glob(".assets-*"))


def test_registered_asset_set_verifier_rejects_corrupt_materialization(tmp_path):
    document, _ = _published_graph(tmp_path)
    lock = parse_registered_asset_set(document)
    target = tmp_path / "assets"
    materialize_registered_asset_set(lock, target)
    path = target / "registered/coronal-0.json.gz"
    path.write_bytes(path.read_bytes() + b"corrupt")

    with pytest.raises(ValueError, match="encoded byte length differs"):
        verify_materialized_registered_asset_set(lock, target)


def test_registered_asset_set_rejects_escaping_resource_path_atomically(tmp_path):
    document, source = _published_graph(tmp_path)
    root = json.loads((source / "manifest.json").read_text())
    root["projections"][0]["resource_index"]["resource"]["path"] = "../outside.json.gz"
    (source / "manifest.json").write_text(
        json.dumps(root, indent=2) + "\n", encoding="utf-8"
    )
    document["root_manifest"] = _resource(source / "manifest.json")
    target = tmp_path / "assets"

    with pytest.raises(ValueError, match="does not match|escapes projection pack"):
        materialize_registered_asset_set(parse_registered_asset_set(document), target)

    assert not target.exists()
    assert not list(tmp_path.glob(".assets-*"))


def test_registered_asset_set_rejects_extra_materialized_file(tmp_path):
    document, _ = _published_graph(tmp_path)
    lock = parse_registered_asset_set(document)
    target = tmp_path / "assets"
    materialize_registered_asset_set(lock, target)
    (target / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(ValueError, match="file inventory differs"):
        verify_materialized_registered_asset_set(lock, target)


def test_registered_asset_set_failure_cleans_temporary_directory(tmp_path):
    document, _ = _published_graph(tmp_path)
    document["projections"]["coronal"]["inventory_sha256"] = "0" * 64
    target = tmp_path / "assets"
    with pytest.raises(ValueError, match="inventory differs"):
        materialize_registered_asset_set(parse_registered_asset_set(document), target)
    assert not (tmp_path / "assets").exists()
    assert not list(tmp_path.glob(".assets-*"))


def test_registered_asset_set_is_strict(tmp_path):
    document, _ = _published_graph(tmp_path)
    document["unexpected"] = True
    with pytest.raises(ValueError, match="fields differ"):
        parse_registered_asset_set(document)
