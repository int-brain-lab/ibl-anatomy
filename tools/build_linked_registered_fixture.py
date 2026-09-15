"""Build the tiny linked 10-um registered-slice fixture."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

GRID = "synthetic-10um-grid-v1"
REFERENCE = "allen-ccf-2017"
MATRIX = [0, 10, 0, -35, -10, 0, 0, 40, 0, 0, -10, 20, 0, 0, 0, 1]
PROJECTIONS = {
    "coronal": ("ap", [9, 8, 7], MATRIX),
    "sagittal": ("ml", [8, 9, 7], [10, 0, 0, -35, 0, -10, 0, 40, 0, 0, -10, 20, 0, 0, 0, 1]),
    "horizontal": ("dv", [7, 8, 9], [0, 10, 0, -35, 0, 0, -10, 40, -10, 0, 0, 20, 0, 0, 0, 1]),
}


def _resource(path: str, payload: bytes, media_type: str = "application/json") -> dict:
    return {
        "path": path,
        "media_type": media_type,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "codec": {"name": "gzip", "decoded_bytes": len(gzip.decompress(payload))},
    }


def _pack(projection: str, count: int, matrix: list[int]) -> bytes:
    world_row = {"ml": 0, "ap": 1, "dv": 2}[PROJECTIONS[projection][0]]
    slices = []
    for index in range(count):
        paths = [{
            "atlas_ids": {"allen": -997, "beryl": -997, "cosmos": -997},
            "fill_rule": "evenodd",
            "d": "M-.5 -.5h3v3h-3zM.5 .5h1v1h-1z" if index == 0 else "M-.5 -.5h3v3h-3z",
        }]
        if index == count - 1:
            paths.append({
                "atlas_ids": {"allen": 997, "beryl": 997, "cosmos": 997},
                "fill_rule": "evenodd",
                "d": "M2.5 -.5h3v3h-3z",
            })
        slices.append({"slice_index": index, "world_coordinate_um": matrix[world_row * 4] * index + matrix[world_row * 4 + 3], "paths": paths})
    document = {
        "format": "anatomy-slice-pack-v2",
        "schema_version": "2.0",
        "anatomy_pack_id": f"synthetic-{projection}-10um-v2",
        "projection": projection,
        "pack_depth": 16,
        "pack_index": 0,
        "first_slice_index": 0,
        "slice_count": count,
        "slices": slices,
    }
    return gzip.compress(json.dumps(document, sort_keys=True, separators=(",", ":")).encode(), mtime=0)


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    registered = output / "registered"
    registered.mkdir(exist_ok=True)
    for projection, (axis, shape, matrix) in PROJECTIONS.items():
        count = shape[0]
        pack_path = registered / f"{projection}-0.json.gz"
        pack_bytes = _pack(projection, count, matrix)
        pack_path.write_bytes(pack_bytes)
        index_document = {
            "schema_version": "1.0",
            "format": "atlas-registered-svg-resource-index-v1",
            "projection_id": projection,
            "resources": [{
                "pack_id": f"synthetic-{projection}-10um-v2",
                "slice_indices": list(range(count)),
                "resource": _resource(pack_path.relative_to(output).as_posix(), pack_bytes),
            }],
        }
        index_raw = json.dumps(index_document, sort_keys=True, separators=(",", ":")).encode()
        index_bytes = gzip.compress(index_raw, mtime=0)
        (output / f"{projection}-index.json.gz").write_bytes(index_bytes)
        manifest = {
            "id": projection,
            "kind": "registered-slice-stack",
            "reference_space_id": REFERENCE,
            "grid_id": GRID,
            "world_slice_axis": axis,
            "slice_count": count,
            "slice_shape": shape[1:],
            "view_box": [0, 0, shape[1], shape[2]],
            "plane_index_to_world_um": matrix,
            "voxel_edge_extent_um": [-40, 40, -45, 45, -45, 25],
            "display_slices": list(range(count)),
            "resource_index": {"format": "atlas-registered-svg-resource-index-v1", "resource": _resource(f"{projection}-index.json.gz", index_bytes)},
        }
        (output / f"{projection}.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
