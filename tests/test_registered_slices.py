from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from ibl_atlas_assets import open_registered_projection
from ibl_atlas_assets.schema import validate_registered_projection_manifest


def _projection(identifier: str, axis: str, matrix: list[float], extent: list[float]) -> dict:
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
    _projection("coronal", "ap", [0, 0, -10, 100, 20, 0, 0, -50, 0, 30, 0, 5, 0, 0, 0, 1], [65, 105, -60, -20, -10, 80]),
    _projection("sagittal", "ml", [20, 0, 0, -50, 0, 0, -10, 100, 0, 30, 0, 5, 0, 0, 0, 1], [-60, -20, 65, 105, -10, 80]),
    _projection("horizontal", "dv", [0, 0, -10, 100, 0, 30, 0, 5, 20, 0, 0, -50, 0, 0, 0, 1], [65, 105, -10, 80, -60, -20]),
)


@pytest.mark.parametrize("document", CASES, ids=lambda item: item["id"])
def test_representative_registered_projection_semantics(document: dict) -> None:
    validate_registered_projection_manifest(document)
    projection = copy.deepcopy(document)
    projection["display_slices"] = [1, 0]
    with pytest.raises(ValueError, match="increasing"):
        validate_registered_projection_manifest(projection)


def test_registered_projection_reader_preserves_affine_and_resource_index(tmp_path: Path) -> None:
    document = copy.deepcopy(CASES[0])
    index = {
        "schema_version": "1.0",
        "format": "atlas-registered-svg-resource-index-v1",
        "projection_id": "coronal",
        "resources": [{
            "pack_id": "coronal-0",
            "slice_indices": [0, 1],
            "resource": {
                "path": "registered/coronal-0.isvg.gz",
                "media_type": "application/vnd.ibl.indexed-svg",
                "bytes": 0,
                "sha256": "0" * 64,
                "codec": {"name": "gzip", "decoded_bytes": 0},
            },
        }],
    }
    encoded_index = gzip.compress(json.dumps(index).encode(), mtime=0)
    document["resource_index"]["resource"].update({
        "bytes": len(encoded_index),
        "sha256": hashlib.sha256(encoded_index).hexdigest(),
        "codec": {"name": "gzip", "decoded_bytes": len(json.dumps(index).encode())},
    })
    (tmp_path / "coronal.json.gz").write_bytes(encoded_index)
    projection = tmp_path / "manifest.json"
    projection.write_text(json.dumps(document), encoding="utf-8")
    opened = open_registered_projection(projection)
    assert opened.projection_id == "coronal"
    np.testing.assert_allclose(opened.index_to_world([0, 0, 0]), [100, -50, 5])
    np.testing.assert_allclose(opened.world_to_index([100, -50, 5]), [0, 0, 0])
    assert opened.load_resource_index()["projection_id"] == "coronal"


def test_registered_projection_rejects_wrong_axis() -> None:
    document = copy.deepcopy(CASES[0])
    document["world_slice_axis"] = "ml"
    with pytest.raises(ValueError, match="slice the ap"):
        validate_registered_projection_manifest(document)
