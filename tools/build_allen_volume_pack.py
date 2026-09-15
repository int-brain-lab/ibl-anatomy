"""Build the reviewed Allen CCF 2017 50-um volume pack from pinned sources.

This publication helper intentionally supports only the source pair audited for
Spike 002. It requires ``pynrrd`` in the invoking environment.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import nrrd
import numpy as np

_TEMPLATE_SHA256 = "6114c341d526f9782ca93b314b3244bb0c4c6cea17045f432d4cda63339915aa"
_ANNOTATION_SHA256 = "84e7cecea1b03af16e923c3639602b8324929f833425ba03582bf56f962ea0d4"
_TEMPLATE_URL = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_50.nrrd"
_ANNOTATION_URL = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_50.nrrd"
_SHAPE = (264, 228, 160)
_FIRST_RIGHT = 114


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_source(path: Path, expected_sha256: str) -> np.ndarray:
    payload = path.read_bytes()
    if _sha(payload) != expected_sha256:
        raise ValueError(f"Allen source SHA-256 differs: {path}")
    values, header = nrrd.read(path, index_order="C")
    if tuple(header["sizes"]) != (264, 160, 228):
        raise ValueError(f"Allen source NRRD grid differs: {path}")
    return np.ascontiguousarray(np.transpose(values, (2, 0, 1)))


def _encode(path: str, semantic: str, values: np.ndarray) -> tuple[dict, bytes]:
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
            "sha256": _sha(encoded),
            "decoded_bytes": len(decoded),
            "decoded_sha256": _sha(decoded),
            "outside_value": 0,
        },
        encoded,
    )


def _annotation_source_indices(
    allen_ids: np.ndarray, catalog_document: dict
) -> np.ndarray:
    signed = np.asarray(allen_ids, dtype=np.int64)
    signed[:, :_FIRST_RIGHT, :] *= -1
    rows = catalog_document["mappings"]["allen"]
    atlas_ids = np.asarray([row["atlas_id"] for row in rows], dtype=np.int64)
    source_indices = np.asarray([row["idx"] for row in rows], dtype=np.uint16)
    order = np.argsort(atlas_ids)
    atlas_ids = atlas_ids[order]
    source_indices = source_indices[order]
    flat = signed.ravel()
    positions = np.searchsorted(atlas_ids, flat)
    valid = positions < len(atlas_ids)
    valid[valid] &= atlas_ids[positions[valid]] == flat[valid]
    if not np.all(valid):
        raise ValueError("Allen annotation contains IDs absent from the region catalog")
    return np.ascontiguousarray(source_indices[positions].reshape(_SHAPE))


def build(
    template_source: Path, annotation_source: Path, catalog: Path, output: Path
) -> None:
    if output.exists():
        raise FileExistsError(f"volume-pack destination already exists: {output}")
    template = _read_source(template_source, _TEMPLATE_SHA256)
    annotation_ids = _read_source(annotation_source, _ANNOTATION_SHA256)
    if template.shape != _SHAPE or template.dtype != np.uint16:
        raise ValueError("Allen template decoded shape or dtype differs")
    if annotation_ids.shape != _SHAPE or annotation_ids.dtype != np.uint32:
        raise ValueError("Allen annotation decoded shape or dtype differs")
    catalog_payload = catalog.read_bytes()
    catalog_document = json.loads(catalog_payload)
    annotation = _annotation_source_indices(annotation_ids, catalog_document)
    template_descriptor, template_payload = _encode(
        "template.u16.gz", "anatomical-template-intensity", template
    )
    annotation_descriptor, annotation_payload = _encode(
        "annotation.u16.gz", "region-catalog-source-index", annotation
    )
    manifest = {
        "format": "ibl-atlas-volume-pack-v1",
        "schema_version": "1.0",
        "pack_id": "allen-ccf-2017-50um-20260915",
        "purpose": "production",
        "reference_space_id": "allen-ccf-2017",
        "grid": {
            "array_axes": ["ap", "ml", "dv"],
            "shape": list(_SHAPE),
            "world_axes": ["ml", "ap", "dv"],
            "world_units": "um",
            "voxel_coordinates": "centers",
            "index_to_world_um": [
                0,
                50,
                0,
                -5739,
                -50,
                0,
                0,
                5400,
                0,
                0,
                -50,
                332,
                0,
                0,
                0,
                1,
            ],
        },
        "hemisphere_boundary": {
            "array_axis": "ml",
            "first_right_index": _FIRST_RIGHT,
            "on_boundary_side": "right",
        },
        "region_catalog": {
            "path": "regions.json",
            "bytes": len(catalog_payload),
            "sha256": _sha(catalog_payload),
            "format": "ibl-atlas-regions-v1",
            "index_field": "mappings.allen[].idx",
        },
        "volumes": {
            "template": template_descriptor,
            "annotation": annotation_descriptor,
        },
        "provenance": {
            "source_acquired": "2026-09-15",
            "template": {"url": _TEMPLATE_URL, "sha256": _TEMPLATE_SHA256},
            "annotation": {"url": _ANNOTATION_URL, "sha256": _ANNOTATION_SHA256},
            "derivation": "IBL AP/ML/DV transpose and signed source-index lateralization",
            "copyright": "© 2015 Allen Institute for Brain Science",
            "terms": "https://alleninstitute.org/terms-of-use/",
            "citation_policy": "https://alleninstitute.org/legal/citation-policy",
        },
    }
    output.mkdir(parents=True)
    (output / "template.u16.gz").write_bytes(template_payload)
    (output / "annotation.u16.gz").write_bytes(annotation_payload)
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(catalog, output / "regions.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("annotation", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.template, args.annotation, args.catalog, args.output)


if __name__ == "__main__":
    main()
