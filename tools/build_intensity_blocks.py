"""Build a projection-oriented indexed intensity pack from a uint16 NumPy array."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np

from tools.allen_nrrd import open_allen_nrrd_ap_ml_dv

_AXES = ("ap", "ml", "dv")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _gzip(payload: bytes, *, compression_level: int = 9) -> bytes:
    encoded = bytearray(
        gzip.compress(payload, compresslevel=compression_level, mtime=0)
    )
    encoded[9] = 255
    return bytes(encoded)


def _exact_ranges(values: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    value_range = (int(values.min()), int(values.max()))
    nonzero_low = 65535
    nonzero_high = 0
    found = False
    for section in values:
        mask = section != 0
        if np.any(mask):
            found = True
            present = section[mask]
            nonzero_low = min(nonzero_low, int(present.min()))
            nonzero_high = max(nonzero_high, int(present.max()))
    display_range = (nonzero_low, nonzero_high) if found else value_range
    return value_range, display_range


def build(
    values: np.ndarray,
    output: Path,
    *,
    dataset_id: str,
    reference_space_id: str,
    grid_id: str,
    index_to_world_um: list[float],
    recommended_display_range: tuple[int, int] | None = None,
    sections_per_block: int = 8,
    compression_level: int = 9,
    provenance: dict | None = None,
) -> None:
    """Write three deterministic projection-native indexed resources."""

    values = np.asarray(values)
    if values.ndim != 3 or values.dtype != np.uint16:
        raise ValueError("intensity source must be a three-dimensional uint16 array")
    if (
        not dataset_id
        or not reference_space_id
        or not grid_id
        or len(index_to_world_um) != 16
        or sections_per_block < 1
        or compression_level not in range(1, 10)
    ):
        raise ValueError("intensity identity, transform, or block size is invalid")
    if output.exists():
        raise FileExistsError(f"intensity pack destination already exists: {output}")
    value_range, default_display_range = _exact_ranges(values)
    if recommended_display_range is None:
        recommended_display_range = default_display_range
    if (
        recommended_display_range[0] > recommended_display_range[1]
        or recommended_display_range[0] < value_range[0]
        or recommended_display_range[1] > value_range[1]
    ):
        raise ValueError("recommended intensity display range is invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-", dir=output.parent
    ) as temporary:
        stage = Path(temporary) / "pack"
        stage.mkdir()
        _write_pack(
            values,
            stage,
            dataset_id=dataset_id,
            reference_space_id=reference_space_id,
            grid_id=grid_id,
            index_to_world_um=index_to_world_um,
            value_range=value_range,
            recommended_display_range=recommended_display_range,
            sections_per_block=sections_per_block,
            compression_level=compression_level,
            provenance=provenance,
        )
        stage.rename(output)


def _write_pack(
    values: np.ndarray,
    output: Path,
    *,
    dataset_id: str,
    reference_space_id: str,
    grid_id: str,
    index_to_world_um: list[float],
    value_range: tuple[int, int],
    recommended_display_range: tuple[int, int],
    sections_per_block: int,
    compression_level: int,
    provenance: dict | None,
) -> None:
    provenance_document = dict(
        provenance or {"kind": "local derived intensity transport"}
    )
    provenance_document["transport"] = {
        "codec": "gzip",
        "compression_level": compression_level,
        "sections_per_block": sections_per_block,
    }
    projections = {}
    for axis_index, axis in enumerate(_AXES):
        oriented = np.moveaxis(values, axis_index, 0)
        blocks = []
        offset = 0
        path = f"{axis}.u16.blocks"
        resource_hash = hashlib.sha256()
        with (output / path).open("wb") as stream:
            for block_id, first in enumerate(
                range(0, oriented.shape[0], sections_per_block)
            ):
                block_values = np.ascontiguousarray(
                    oriented[first : first + sections_per_block], dtype="<u2"
                )
                decoded = block_values.tobytes(order="C")
                encoded = _gzip(decoded, compression_level=compression_level)
                blocks.append(
                    {
                        "block_id": block_id,
                        "first_section": first,
                        "section_count": len(block_values),
                        "offset": offset,
                        "bytes": len(encoded),
                        "sha256": _sha(encoded),
                        "decoded_bytes": len(decoded),
                        "decoded_sha256": _sha(decoded),
                    }
                )
                stream.write(encoded)
                resource_hash.update(encoded)
                offset += len(encoded)
        projections[axis] = {
            "axis": axis,
            "plane_axes": [item for item in _AXES if item != axis],
            "sections_per_block": sections_per_block,
            "resource": {
                "path": path,
                "bytes": offset,
                "sha256": resource_hash.hexdigest(),
            },
            "blocks": blocks,
        }
    manifest = {
        "format": "ibl-atlas-intensity-blocks-v1",
        "schema_version": "1.0",
        "dataset_id": dataset_id,
        "reference_space_id": reference_space_id,
        "grid_id": grid_id,
        "array_axes": list(_AXES),
        "shape": list(values.shape),
        "world_axes": ["ml", "ap", "dv"],
        "world_units": "um",
        "voxel_coordinates": "centers",
        "index_to_world_um": index_to_world_um,
        "data_type": "uint16",
        "byte_order": "little",
        "encoding": "gzip-members",
        "value_range": list(value_range),
        "recommended_display_range": list(recommended_display_range),
        "projections": projections,
        "provenance": provenance_document,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


@contextmanager
def _open_source(path: Path, *, temporary_dir: Path) -> Iterator[np.ndarray]:
    if path.suffix == ".npy":
        yield np.load(path, allow_pickle=False, mmap_mode="r")
        return
    if path.suffix == ".nrrd":
        with open_allen_nrrd_ap_ml_dv(path, temporary_dir=temporary_dir) as volume:
            yield volume.values
        return
    raise ValueError(
        "intensity source must be an AP/ML/DV .npy or official Allen .nrrd"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source", type=Path, help="C-order AP/ML/DV uint16 .npy or official Allen .nrrd"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--reference-space-id", required=True)
    parser.add_argument("--grid-id", required=True)
    parser.add_argument("--index-to-world-um", required=True, nargs=16, type=float)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--display-low", type=int)
    parser.add_argument("--display-high", type=int)
    parser.add_argument("--sections-per-block", type=int, default=8)
    parser.add_argument(
        "--compression-level", type=int, choices=range(1, 10), default=9
    )
    args = parser.parse_args()
    if _file_sha(args.source) != args.source_sha256:
        raise ValueError("intensity source SHA-256 differs")
    if (args.display_low is None) != (args.display_high is None):
        raise ValueError("both intensity display range endpoints are required")
    with _open_source(args.source, temporary_dir=args.output.parent) as values:
        build(
            values,
            args.output,
            dataset_id=args.dataset_id,
            reference_space_id=args.reference_space_id,
            grid_id=args.grid_id,
            index_to_world_um=args.index_to_world_um,
            recommended_display_range=(
                (args.display_low, args.display_high)
                if args.display_low is not None
                else None
            ),
            sections_per_block=args.sections_per_block,
            compression_level=args.compression_level,
            provenance={
                "source_id": args.source_id,
                "source_sha256": args.source_sha256,
                "kind": "local derived intensity transport",
            },
        )


if __name__ == "__main__":
    main()
