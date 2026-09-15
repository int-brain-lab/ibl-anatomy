"""Build the deterministic synthetic atlas-volume-pack-v1 fixture."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resource(path: str, semantic: str, values: np.ndarray) -> tuple[dict, bytes]:
    decoded = np.ascontiguousarray(values, dtype="<u2").tobytes(order="C")
    encoded = gzip.compress(decoded, compresslevel=9, mtime=0)
    return (
        {
            "semantic": semantic,
            "path": path,
            "data_type": "uint16",
            "byte_order": "little",
            "encoding": "gzip",
            "bytes": len(encoded),
            "sha256": _digest(encoded),
            "decoded_bytes": len(decoded),
            "decoded_sha256": _digest(decoded),
            "outside_value": 0,
        },
        encoded,
    )


def build(output: Path, catalog_source: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    shape = (4, 5, 3)  # AP, ML, DV
    ap, ml, dv = np.indices(shape)
    template = (100 * ap + 10 * ml + dv).astype(np.uint16)
    annotation = np.zeros(shape, dtype=np.uint16)
    annotation[1, 1, 1] = 4  # left grey
    annotation[2, 1, 1] = 3  # left root
    annotation[1, 2, 1] = 2  # right grey; center remains at world ML=-39 um
    annotation[2, 2, 1] = 1  # right root
    annotation[1, 3, 1] = 2
    annotation[2, 3, 1] = 1

    template_descriptor, template_bytes = _resource(
        "template.u16.gz", "anatomical-template-intensity", template
    )
    annotation_descriptor, annotation_bytes = _resource(
        "annotation.u16.gz", "region-catalog-source-index", annotation
    )
    catalog = catalog_source.read_bytes()
    manifest = {
        "format": "ibl-atlas-volume-pack-v1",
        "schema_version": "1.0",
        "pack_id": "synthetic-atlas-volume-v1",
        "purpose": "test-only",
        "reference_space_id": "allen-ccf-2017",
        "grid": {
            "array_axes": ["ap", "ml", "dv"],
            "shape": list(shape),
            "world_axes": ["ml", "ap", "dv"],
            "world_units": "um",
            "voxel_coordinates": "centers",
            "index_to_world_um": [
                0,
                100,
                0,
                -239,
                -100,
                0,
                0,
                100,
                0,
                0,
                -100,
                100,
                0,
                0,
                0,
                1,
            ],
        },
        "hemisphere_boundary": {
            "array_axis": "ml",
            "first_right_index": 2,
            "on_boundary_side": "right",
        },
        "region_catalog": {
            "path": "regions.json",
            "bytes": len(catalog),
            "sha256": _digest(catalog),
            "format": "ibl-atlas-regions-v1",
            "index_field": "mappings.allen[].idx",
        },
        "volumes": {
            "template": template_descriptor,
            "annotation": annotation_descriptor,
        },
        "provenance": {
            "kind": "deterministic synthetic test fixture",
            "generator": "tools/build_volume_fixture.py",
            "license": "MIT",
        },
    }
    (output / "template.u16.gz").write_bytes(template_bytes)
    (output / "annotation.u16.gz").write_bytes(annotation_bytes)
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(catalog_source, output / "regions.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("tests/fixtures/atlas-regions-v1/regions.json"),
    )
    args = parser.parse_args()
    build(args.output, args.catalog)


if __name__ == "__main__":
    main()
