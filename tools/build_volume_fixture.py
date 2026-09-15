"""Build the deterministic synthetic atlas-volume-pack-v1 fixture."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resource(path: str, semantic: str, values: np.ndarray) -> tuple[dict, bytes]:
    decoded = np.ascontiguousarray(values, dtype="<u2").tobytes(order="C")
    # ``gzip.compress(..., mtime=0)`` delegates the OS header byte to zlib on
    # some Python versions. Pin it explicitly so fixture bytes are portable.
    encoded = bytearray(gzip.compress(decoded, compresslevel=9, mtime=0))
    encoded[9] = 3  # Unix, independent of the generating platform/runtime.
    encoded = bytes(encoded)
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


def _write_pack(
    output: Path,
    catalog: bytes,
    *,
    pack_id: str,
    shape: tuple[int, int, int],
    template: np.ndarray,
    annotation: np.ndarray,
    index_to_world_um: list[float],
    first_right_index: int,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    template_descriptor, template_bytes = _resource(
        "template.u16.gz", "anatomical-template-intensity", template
    )
    annotation_descriptor, annotation_bytes = _resource(
        "annotation.u16.gz", "region-catalog-source-index", annotation
    )
    manifest = {
        "format": "ibl-atlas-volume-pack-v1",
        "schema_version": "1.0",
        "pack_id": pack_id,
        "purpose": "test-only",
        "reference_space_id": "allen-ccf-2017",
        "grid": {
            "array_axes": ["ap", "ml", "dv"],
            "shape": list(shape),
            "world_axes": ["ml", "ap", "dv"],
            "world_units": "um",
            "voxel_coordinates": "centers",
            "index_to_world_um": index_to_world_um,
        },
        "hemisphere_boundary": {
            "array_axis": "ml",
            "first_right_index": first_right_index,
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
    (output / "regions.json").write_bytes(catalog)


def build(output: Path, catalog_source: Path) -> None:
    """Build the original compact volume-pack-v1 fixture."""

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
    _write_pack(
        output,
        catalog_source.read_bytes(),
        pack_id="synthetic-atlas-volume-v1",
        shape=shape,
        template=template,
        annotation=annotation,
        index_to_world_um=[
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
        first_right_index=2,
    )


def _linked_catalog(catalog_source: Path) -> bytes:
    """Add the bilateral Allen 315 mesh region to the small catalog."""

    document = json.loads(catalog_source.read_text(encoding="utf-8"))
    document = copy.deepcopy(document)
    rows = {
        "allen": {
            "mapped_atlas_ids": {"allen": 315, "beryl": 997, "cosmos": 315},
            "mapping_member": True,
        },
        "beryl": {
            "mapped_atlas_ids": {"allen": 315, "beryl": 997, "cosmos": 315},
            "mapping_member": False,
        },
        "cosmos": {
            "mapped_atlas_ids": {"allen": 315, "beryl": 997, "cosmos": 315},
            "mapping_member": True,
        },
    }
    for mapping, options in rows.items():
        target = document["mappings"][mapping]
        for atlas_id in (-315, 315):
            signed = dict(options["mapped_atlas_ids"])
            signed["allen"] = atlas_id
            signed["cosmos"] = atlas_id
            target.append(
                {
                    "acronym": "MOp",
                    "atlas_id": atlas_id,
                    "color_hex": "#e87d8f",
                    "depth": 2,
                    "idx": 5 if atlas_id < 0 else 6,
                    "mapped_atlas_ids": signed,
                    "mapping_member": options["mapping_member"],
                    "name": "Primary motor area",
                    "parent_id": -8 if atlas_id < 0 else 8,
                }
            )
    return json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def build_linked_atlas(output: Path, catalog_source: Path) -> None:
    """Build the small mesh/volume linked-navigation integration fixture."""

    shape = (3, 9, 3)  # AP, ML, DV; 1-um isotropic voxel centers
    ap, ml, dv = np.indices(shape)
    template = (1000 + 100 * ap + 10 * ml + dv).astype(np.uint16)
    annotation = np.zeros(shape, dtype=np.uint16)
    annotation[1, 1:3, 1] = 5  # left Allen 315
    annotation[1, 3:8, 1] = 6  # right Allen 315
    _write_pack(
        output,
        _linked_catalog(catalog_source),
        pack_id="synthetic-linked-atlas-v1",
        shape=shape,
        template=template,
        annotation=annotation,
        # World order is ML/AP/DV while array order is AP/ML/DV.
        # Centers span ML=-3..5, AP/DV=1..-1; edges cover the mesh bounds.
        index_to_world_um=[
            0,
            1,
            0,
            -3,
            -1,
            0,
            0,
            1,
            0,
            0,
            -1,
            1,
            0,
            0,
            0,
            1,
        ],
        first_right_index=3,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("tests/fixtures/atlas-regions-v1/regions.json"),
    )
    parser.add_argument(
        "--profile",
        choices=("volume", "linked-atlas"),
        default="volume",
        help="fixture profile to generate",
    )
    args = parser.parse_args()
    if args.profile == "linked-atlas":
        build_linked_atlas(args.output, args.catalog)
    else:
        build(args.output, args.catalog)


if __name__ == "__main__":
    main()
