from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ibl_atlas_assets import (
    bundled_asset_set,
    materialize_asset_set,
    open_asset_set,
    open_mesh_pack,
    parse_asset_set,
    verify_materialized_asset_set,
)

FIXTURES = Path(__file__).parent / "fixtures"
PACK = FIXTURES / "mesh-pack-v1" / "pack"
REGIONS = FIXTURES / "atlas-regions-v1" / "regions.json"


def _identity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "url": path.resolve().as_uri(),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _fixture_lock(tmp_path: Path) -> Path:
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    regions = json.loads(REGIONS.read_text(encoding="utf-8"))
    for rows in regions["mappings"].values():
        for row in rows:
            sign = -1 if row["atlas_id"] < 0 else 1
            if abs(row["atlas_id"]) == 8:
                row["atlas_id"] = sign * 315
                row["mapped_atlas_ids"]["allen"] = sign * 315
                row["mapped_atlas_ids"]["cosmos"] = sign * 315
    compatible_regions = tmp_path / "regions.json"
    compatible_regions.write_text(json.dumps(regions), encoding="utf-8")
    geometry = open_mesh_pack(PACK).load_geometry()
    document = {
        "format": "ibl-atlas-asset-set-v1",
        "schema_version": "1.0",
        "asset_set_id": "synthetic-test",
        "reference_space_id": "allen-ccf-2017",
        "mesh_manifest": _identity(PACK / "manifest.json"),
        "region_catalog": _identity(compatible_regions),
        "expectations": {
            "pack_id": manifest["pack_id"],
            "geometry_sha256": manifest["lods"][0]["resource"]["sha256"],
            "vertices": 10,
            "triangles": 12,
            "components": 2,
            "presentations": 2,
            "vertex_presentations_sha256": hashlib.sha256(
                geometry.vertex_presentation_ids().tobytes(order="C")
            ).hexdigest(),
            "face_presentations_sha256": hashlib.sha256(
                geometry.face_presentation_ids().tobytes(order="C")
            ).hexdigest(),
        },
    }
    path = tmp_path / "asset-set.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_bundled_real_asset_set_is_immutable_and_explicit() -> None:
    asset_set = bundled_asset_set()
    assert asset_set.asset_set_id == "allen-ccf-2017-d070-20260908"
    assert asset_set.reference_space_id == "allen-ccf-2017"
    assert asset_set.expected_triangles == 966_645
    assert asset_set.expected_components == 1_140
    assert asset_set.mesh_manifest.url.startswith("https://ephys-atlas.iblcore.org/")
    assert "/e91f021ac7ca096db2b408a7d691a6c32cc336ad/" in asset_set.region_catalog.url


def test_materialize_and_verify_fixture_asset_set(tmp_path: Path) -> None:
    asset_set = open_asset_set(_fixture_lock(tmp_path))
    result = materialize_asset_set(asset_set, tmp_path / "materialized")
    assert result.geometry.positions.shape == (10, 3)
    assert result.regions.reference_space_id == result.geometry.reference_space
    assert verify_materialized_asset_set(
        asset_set, result.root
    ).geometry.indices.shape == (36,)
    with pytest.raises(FileExistsError):
        materialize_asset_set(asset_set, result.root)


def test_asset_set_fails_closed_on_identity_and_reference_space(tmp_path: Path) -> None:
    lock_path = _fixture_lock(tmp_path)
    document = json.loads(lock_path.read_text(encoding="utf-8"))
    document["expectations"]["triangles"] = 11
    with pytest.raises(ValueError, match="expectations differ"):
        root = tmp_path / "wrong-count"
        root.mkdir()
        (root / "mesh-pack").symlink_to(PACK, target_is_directory=True)
        (root / "regions.json").symlink_to(tmp_path / "regions.json")
        verify_materialized_asset_set(parse_asset_set(document), root)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.__setitem__("extra", True),
        lambda document: document["mesh_manifest"].__setitem__("sha256", "bad"),
        lambda document: document["expectations"].__setitem__("vertices", 0),
    ],
)
def test_asset_set_rejects_invalid_lock(tmp_path: Path, mutation) -> None:
    document = json.loads(_fixture_lock(tmp_path).read_text(encoding="utf-8"))
    mutation(document)
    with pytest.raises(ValueError):
        parse_asset_set(document)
