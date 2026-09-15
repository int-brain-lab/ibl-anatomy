from __future__ import annotations

import copy
import gzip
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from ibl_anatomy import (
    RegisteredProjection,
    open_anatomy_pack,
    open_registered_projection,
)
from ibl_anatomy.registered_slices import _decode_indexed_svg_pack
from ibl_anatomy.schema import validate_registered_projection_manifest


def _projection(
    identifier: str, axis: str, matrix: list[float], extent: list[float]
) -> dict:
    return {
        "id": identifier,
        "kind": "registered-slice-stack",
        "reference_space_id": "allen-ccf-2017",
        "grid_id": "allen-ccf-2017-10um",
        "world_slice_axis": axis,
        "slice_count": 2,
        "slice_shape": [3, 4],
        "view_box": [0, 0, 4, 3],
        "plane_index_to_world_um": matrix,
        "voxel_edge_extent_um": extent,
        "display_slices": [0, 1],
        "resource_index": {
            "format": "atlas-registered-svg-resource-index-v1",
            "resource": {
                "path": f"{identifier}.json.gz",
                "media_type": "application/json",
                "bytes": 1,
                "sha256": "0" * 64,
                "codec": {"name": "gzip", "decoded_bytes": 1},
            },
        },
    }


CASES = (
    _projection(
        "coronal",
        "ap",
        [0, 0, -10, 100, 20, 0, 0, -50, 0, 30, 0, 5, 0, 0, 0, 1],
        [65, 105, -60, -20, -10, 80],
    ),
    _projection(
        "sagittal",
        "ml",
        [20, 0, 0, -50, 0, 0, -10, 100, 0, 30, 0, 5, 0, 0, 0, 1],
        [-60, -20, 65, 105, -10, 80],
    ),
    _projection(
        "horizontal",
        "dv",
        [0, 0, -10, 100, 0, 30, 0, 5, 20, 0, 0, -50, 0, 0, 0, 1],
        [65, 105, -10, 80, -60, -20],
    ),
)


def _binary_pack(svg: bytes, *, slice_index: int = 0, world: float = -50.0) -> bytes:
    projection = b"coronal"
    pack_id = b"coronal-0"
    table = 28 + len(projection) + len(pack_id)
    payload = table + 20
    header = struct.pack(
        "<4sBBHHHIIII",
        b"ISVG",
        1,
        0,
        28,
        len(projection),
        len(pack_id),
        1,
        table,
        payload,
        len(svg),
    )
    return (
        header
        + projection
        + pack_id
        + struct.pack("<idII", slice_index, world, 0, len(svg))
        + svg
    )


@pytest.mark.parametrize("document", CASES, ids=lambda item: item["id"])
def test_representative_registered_projection_semantics(document: dict) -> None:
    validate_registered_projection_manifest(document)
    projection = copy.deepcopy(document)
    projection["display_slices"] = [1, 0]
    with pytest.raises(ValueError, match="increasing"):
        validate_registered_projection_manifest(projection)


def test_registered_projection_reader_preserves_affine_and_resource_index(
    tmp_path: Path,
) -> None:
    document = copy.deepcopy(CASES[0])
    index = {
        "schema_version": "1.0",
        "format": "atlas-registered-svg-resource-index-v1",
        "projection_id": "coronal",
        "resources": [
            {
                "pack_id": "coronal-0",
                "slice_indices": [0],
                "resource": {
                    "path": "registered/coronal-0.isvg.gz",
                    "media_type": "application/vnd.ibl.indexed-svg",
                    "bytes": 0,
                    "sha256": "0" * 64,
                    "codec": {"name": "gzip", "decoded_bytes": 0},
                },
            }
        ],
    }
    encoded_index = gzip.compress(json.dumps(index).encode(), mtime=0)
    svg = b'<svg><path fill-rule="evenodd" data-allen-id="-101" data-beryl-id="-10" data-cosmos-id="-1" d="M0 0h4v4h-4zM1 1h2v2h-2z"/></svg>'
    svg_pack = _binary_pack(svg)
    encoded_svg = gzip.compress(svg_pack, mtime=0)
    index["resources"][0]["resource"].update(
        {
            "bytes": len(encoded_svg),
            "sha256": hashlib.sha256(encoded_svg).hexdigest(),
            "codec": {"name": "gzip", "decoded_bytes": len(svg_pack)},
        }
    )
    (tmp_path / "registered").mkdir()
    (tmp_path / "registered/coronal-0.isvg.gz").write_bytes(encoded_svg)
    encoded_index = gzip.compress(json.dumps(index).encode(), mtime=0)
    document["resource_index"]["resource"].update(
        {
            "bytes": len(encoded_index),
            "sha256": hashlib.sha256(encoded_index).hexdigest(),
            "codec": {"name": "gzip", "decoded_bytes": len(json.dumps(index).encode())},
        }
    )
    (tmp_path / "coronal.json.gz").write_bytes(encoded_index)
    projection = tmp_path / "manifest.json"
    projection.write_text(json.dumps(document), encoding="utf-8")
    opened = open_registered_projection(projection)
    assert opened.projection_id == "coronal"
    np.testing.assert_allclose(opened.index_to_world([0, 0, 0]), [100, -50, 5])
    np.testing.assert_allclose(opened.world_to_index([100, -50, 5]), [0, 0, 0])
    assert opened.load_resource_index()["projection_id"] == "coronal"
    decoded = opened.load_slice(0)
    assert decoded.paths[0].atlas_ids == {"allen": -101, "beryl": -10, "cosmos": -1}
    assert decoded.paths[0].ring_count == 2
    assert decoded.paths[0].fill_rule == "evenodd"


def test_registered_projection_rejects_wrong_axis() -> None:
    document = copy.deepcopy(CASES[0])
    document["world_slice_axis"] = "ml"
    with pytest.raises(ValueError, match="slice the ap"):
        validate_registered_projection_manifest(document)


@pytest.mark.parametrize(
    "svg",
    [
        b'<svg><path fill-rule="nonzero" data-allen-id="-1" data-beryl-id="-1" data-cosmos-id="-1" d="M0 0Z"/></svg>',
        b'<svg><path fill-rule="evenodd" data-allen-id="0" data-beryl-id="-1" data-cosmos-id="-1" d="M0 0Z"/></svg>',
        b"<svg></svg>",
    ],
)
def test_indexed_svg_corruption_rejects_invalid_path_contract(svg: bytes) -> None:
    with pytest.raises(ValueError, match="fill-rule|signed mappings|no paths"):
        _decode_indexed_svg_pack(_binary_pack(svg))


def test_registered_projection_rejects_invalid_slice_arguments() -> None:
    projection = RegisteredProjection(Path("."), CASES[0])
    with pytest.raises(TypeError, match="integer"):
        projection.resource_for_slice("0")
    with pytest.raises(IndexError, match="outside"):
        projection.resource_for_slice(2)


def test_registered_projection_decodes_anatomy_v2_json_pack(tmp_path: Path) -> None:
    payload = {
        "format": "anatomy-slice-pack-v2",
        "schema_version": "2.0",
        "anatomy_pack_id": "coronal-0",
        "projection": "coronal",
        "pack_depth": 16,
        "pack_index": 0,
        "first_slice_index": 0,
        "slice_count": 1,
        "slices": [
            {
                "slice_index": 0,
                "world_coordinate_um": -50,
                "paths": [
                    {
                        "atlas_ids": {"allen": -101, "beryl": -10, "cosmos": -1},
                        "fill_rule": "evenodd",
                        "d": "M0 0h4v4h-4zM1 1h2v2h-2z",
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    encoded = gzip.compress(raw, mtime=0)
    document = copy.deepcopy(CASES[0])
    document["resource_index"]["resource"].update(
        {
            "media_type": "application/json",
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "codec": {"name": "gzip", "decoded_bytes": len(raw)},
        }
    )
    index = {
        "schema_version": "1.0",
        "format": "atlas-registered-svg-resource-index-v1",
        "projection_id": "coronal",
        "resources": [
            {
                "pack_id": "coronal-0",
                "slice_indices": [0],
                "resource": {
                    "path": "coronal-0.json.gz",
                    "media_type": "application/json",
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "codec": {"name": "gzip", "decoded_bytes": len(raw)},
                },
            }
        ],
    }
    index_raw = json.dumps(index, separators=(",", ":")).encode()
    index_encoded = gzip.compress(index_raw, mtime=0)
    document["resource_index"]["resource"].update(
        {
            "path": "index.json.gz",
            "bytes": len(index_encoded),
            "sha256": hashlib.sha256(index_encoded).hexdigest(),
            "codec": {"name": "gzip", "decoded_bytes": len(index_raw)},
        }
    )
    (tmp_path / "coronal-0.json.gz").write_bytes(encoded)
    (tmp_path / "index.json.gz").write_bytes(index_encoded)
    (tmp_path / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
    decoded = open_registered_projection(tmp_path).load_slice(0)
    assert decoded.paths[0].atlas_ids["cosmos"] == -1
    assert decoded.paths[0].ring_count == 2


def _write_anatomy_v2(tmp_path: Path) -> Path:
    pack_id = "synthetic-complete-anatomy-v2"
    specs = {
        "coronal": (
            "ap",
            2,
            [4, 3],
            [0, 10, 0, -10, -20, 0, 0, 10, 0, 0, -30, 45, 0, 0, 0, 1],
        ),
        "sagittal": (
            "ml",
            3,
            [4, 2],
            [10, 0, 0, -10, 0, -20, 0, 10, 0, 0, -30, 45, 0, 0, 0, 1],
        ),
        "horizontal": (
            "dv",
            4,
            [2, 3],
            [0, 10, 0, -10, 0, 0, -20, 10, -30, 0, 0, 45, 0, 0, 0, 1],
        ),
    }
    projections = {}
    for name, (axis, count, shape, matrix) in specs.items():
        world_row = {"ml": 0, "ap": 1, "dv": 2}[axis]
        slices = [
            {
                "slice_index": index,
                "world_coordinate_um": matrix[world_row * 4] * index
                + matrix[world_row * 4 + 3],
                "paths": [],
            }
            for index in range(count)
        ]
        document = {
            "format": "anatomy-slice-pack-v2",
            "schema_version": "2.0",
            "anatomy_pack_id": pack_id,
            "projection": name,
            "pack_depth": 16,
            "pack_index": 0,
            "first_slice_index": 0,
            "slice_count": count,
            "slices": slices,
        }
        raw = json.dumps(document, separators=(",", ":")).encode()
        encoded = gzip.compress(raw, mtime=0)
        resource = tmp_path / "packs" / name / "0.json.gz"
        resource.parent.mkdir(parents=True)
        resource.write_bytes(encoded)
        projections[name] = {
            "fixed_world_axis": axis,
            "plane_axes": {
                "coronal": ["ml", "dv"],
                "sagittal": ["ap", "dv"],
                "horizontal": ["ml", "ap"],
            }[name],
            "slice_count": count,
            "slice_shape": shape,
            "view_box": [-0.5, -0.5, shape[1], shape[0]],
            "plane_index_to_world_um": matrix,
            "world_to_plane_index": list(
                np.linalg.inv(np.asarray(matrix).reshape(4, 4)).reshape(-1)
            ),
            "pack_sets": {
                "16": {
                    "pack_depth": 16,
                    "path_template": f"packs/{name}/{{pack}}.json.gz",
                    "packs": [
                        {
                            "bytes": len(encoded),
                            "compression": "gzip",
                            "first_slice_index": 0,
                            "media_type": "application/json",
                            "pack_index": 0,
                            "path": resource.relative_to(tmp_path).as_posix(),
                            "sha256": hashlib.sha256(encoded).hexdigest(),
                            "slice_count": count,
                            "uncompressed_bytes": len(raw),
                        }
                    ],
                }
            },
        }
    manifest = {
        "format": "anatomy-pack-v2",
        "schema_version": "2.0",
        "pack_id": pack_id,
        "immutable": True,
        "created_at": "2026-09-15T00:00:00Z",
        "source": {"kind": "synthetic"},
        "coordinate_system": {
            "matrix_order": "row-major",
            "name": "synthetic",
            "units": "um",
            "voxel_centers": "integer-indices",
            "voxel_edges": "half-integer-indices",
            "world_axes": ["ml", "ap", "dv"],
        },
        "projections": projections,
        "synchronization_sentinels": [
            {
                "name": "shared point",
                "world_um": [0, -10, -15],
                "projection_indices": {
                    "coronal": [1, 1, 2],
                    "sagittal": [1, 1, 2],
                    "horizontal": [2, 1, 1],
                },
            }
        ],
        "validation": {"coordinate_tolerance_um": 1e-6},
        "provenance": {"kind": "synthetic"},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_complete_anatomy_v2_adapter_exposes_registered_projections(
    tmp_path: Path,
) -> None:
    source = _write_anatomy_v2(tmp_path)
    pack = open_anatomy_pack(
        source,
        reference_space_id="allen-ccf-2017",
        grid_id="synthetic-10um-grid-v1",
    )
    assert pack.pack_id == "synthetic-complete-anatomy-v2"
    assert tuple(pack.projections) == ("coronal", "sagittal", "horizontal")
    assert pack.projections["coronal"].slice_shape == (3, 4)
    assert pack.projections["sagittal"].slice_shape == (2, 4)
    assert pack.projections["horizontal"].slice_shape == (3, 2)
    assert pack.projections["horizontal"].load_slice(2).world_coordinate_um == -15
    pack.verify()


def test_complete_anatomy_v2_adapter_rejects_bad_sentinel(tmp_path: Path) -> None:
    source = _write_anatomy_v2(tmp_path)
    document = json.loads(source.read_text(encoding="utf-8"))
    document["synchronization_sentinels"][0]["world_um"][0] = 1
    source.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="sentinel differs"):
        open_anatomy_pack(
            source,
            reference_space_id="allen-ccf-2017",
            grid_id="synthetic-10um-grid-v1",
        )
