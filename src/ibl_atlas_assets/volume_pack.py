"""Read and verify renderer-neutral atlas volume packs."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from .regions import AtlasRegion, AtlasRegionCatalog, open_region_catalog
from .schema import validate_volume_pack_manifest

ArrayAxis = Literal["ap", "ml", "dv"]
VolumeName = Literal["template", "annotation"]
_MAX_RESOURCE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class AtlasVolumeGrid:
    """A regular AP/ML/DV array embedded in ML/AP/DV world micrometres."""

    shape: tuple[int, int, int]
    index_to_world_um_matrix: tuple[float, ...]

    @property
    def array_axes(self) -> tuple[str, str, str]:
        return ("ap", "ml", "dv")

    @property
    def world_axes(self) -> tuple[str, str, str]:
        return ("ml", "ap", "dv")

    def index_to_world(self, indices: Any) -> NDArray[np.float64]:
        """Transform ``[..., (ap, ml, dv)]`` indices to ML/AP/DV micrometres."""

        points = np.asarray(indices, dtype=np.float64)
        if (
            points.shape == ()
            or points.shape[-1] != 3
            or not np.all(np.isfinite(points))
        ):
            raise ValueError("volume indices must be finite AP/ML/DV triples")
        matrix = np.asarray(self.index_to_world_um_matrix).reshape(4, 4)
        return np.ascontiguousarray(points @ matrix[:3, :3].T + matrix[:3, 3])

    def world_to_index(self, positions_um: Any) -> NDArray[np.float64]:
        """Transform ``[..., (ml, ap, dv)]`` micrometres to fractional array indices."""

        points = np.asarray(positions_um, dtype=np.float64)
        if (
            points.shape == ()
            or points.shape[-1] != 3
            or not np.all(np.isfinite(points))
        ):
            raise ValueError("world positions must be finite ML/AP/DV triples")
        inverse = np.linalg.inv(
            np.asarray(self.index_to_world_um_matrix, dtype=np.float64).reshape(4, 4)
        )
        return np.ascontiguousarray(points @ inverse[:3, :3].T + inverse[:3, 3])


@dataclass(frozen=True)
class AtlasVolumeSlice:
    """An owned C-contiguous orthogonal slice and its unchanged array axes."""

    values: NDArray[np.uint16]
    array_axes: tuple[str, str]


@dataclass(frozen=True)
class AtlasVolumes:
    """Decoded anatomical template and source-index annotation arrays."""

    template: NDArray[np.uint16]
    annotation: NDArray[np.uint16]
    grid: AtlasVolumeGrid
    regions: AtlasRegionCatalog
    first_right_ml_index: int
    regions_by_source_index: Mapping[int, AtlasRegion]

    def slice(
        self, volume: VolumeName, axis: ArrayAxis, index: int
    ) -> AtlasVolumeSlice:
        """Return an owned slice without implicit axis swaps or display flips."""

        if volume not in ("template", "annotation"):
            raise ValueError("volume must be template or annotation")
        if axis not in self.grid.array_axes:
            raise ValueError("slice axis must be ap, ml or dv")
        axis_index = self.grid.array_axes.index(axis)
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("slice index must be an integer")
        if index < 0 or index >= self.grid.shape[axis_index]:
            raise IndexError("slice index is outside the volume")
        source = self.template if volume == "template" else self.annotation
        values = np.array(np.take(source, index, axis=axis_index), order="C", copy=True)
        axes = tuple(item for item in self.grid.array_axes if item != axis)
        return AtlasVolumeSlice(values, axes)  # type: ignore[arg-type]

    def annotation_index_at_world(
        self, positions_um: Any, *, mode: Literal["raise", "clip"] = "raise"
    ) -> NDArray[np.uint16]:
        """Nearest-voxel annotation source indices at ML/AP/DV positions."""

        if mode not in ("raise", "clip"):
            raise ValueError("volume lookup mode must be raise or clip")
        indices = np.rint(self.grid.world_to_index(positions_um)).astype(np.int64)
        shape = np.asarray(self.grid.shape)
        outside = np.any((indices < 0) | (indices >= shape), axis=-1)
        if np.any(outside) and mode == "raise":
            raise ValueError("world position lies outside the atlas volume")
        indices = np.clip(indices, 0, shape - 1)
        return np.asarray(self.annotation[tuple(np.moveaxis(indices, -1, 0))])

    def region_for_source_index(self, source_index: int) -> AtlasRegion:
        """Resolve one annotation value to its signed physical Allen row."""

        row = self.regions_by_source_index.get(source_index)
        if row is None:
            raise KeyError(f"unknown annotation source index: {source_index}")
        return row


@dataclass(frozen=True)
class AtlasVolumePack:
    """A validated volume-pack manifest rooted at a local directory."""

    root: Path
    manifest: Mapping[str, Any]
    grid: AtlasVolumeGrid
    first_right_ml_index: int

    @property
    def reference_space_id(self) -> str:
        return self.manifest["reference_space_id"]

    @property
    def pack_id(self) -> str:
        return self.manifest["pack_id"]

    def verify(self) -> None:
        """Verify the complete declared resource graph and semantic coupling."""

        _verify_complete_graph(self.root, self.manifest)
        catalog_descriptor = self.manifest["region_catalog"]
        catalog_path = _verified_resource(
            self.root, catalog_descriptor, "region catalog"
        )
        regions = open_region_catalog(catalog_path, sha256=catalog_descriptor["sha256"])
        if regions.reference_space_id != self.reference_space_id:
            raise ValueError("volume and region catalog reference spaces differ")
        _load_decoded_volume(self.root, self.manifest["volumes"]["template"], self.grid)
        annotation = _load_decoded_volume(
            self.root, self.manifest["volumes"]["annotation"], self.grid
        )
        _validate_annotation(annotation, regions, self.first_right_ml_index)

    def load_volumes(self) -> AtlasVolumes:
        """Verify and decode both volumes into owned C-contiguous arrays."""

        _verify_complete_graph(self.root, self.manifest)
        catalog_descriptor = self.manifest["region_catalog"]
        catalog_path = _verified_resource(
            self.root, catalog_descriptor, "region catalog"
        )
        regions = open_region_catalog(catalog_path, sha256=catalog_descriptor["sha256"])
        if regions.reference_space_id != self.reference_space_id:
            raise ValueError("volume and region catalog reference spaces differ")
        template = _load_decoded_volume(
            self.root, self.manifest["volumes"]["template"], self.grid
        )
        annotation = _load_decoded_volume(
            self.root, self.manifest["volumes"]["annotation"], self.grid
        )
        _validate_annotation(annotation, regions, self.first_right_ml_index)
        by_index = MappingProxyType(
            {row.index: row for row in regions.physical("allen")}
        )
        return AtlasVolumes(
            template,
            annotation,
            self.grid,
            regions,
            self.first_right_ml_index,
            by_index,
        )


def _safe_resource_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("volume resource path is invalid")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"volume resource escapes pack: {relative}")
    resolved_root = root.resolve()
    candidate = root / path
    current = candidate
    while current != root and current != current.parent:
        if current.is_symlink():
            raise ValueError(f"volume resource must not be a symbolic link: {relative}")
        current = current.parent
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"volume resource escapes pack: {relative}") from error
    return resolved


def _verify_complete_graph(root: Path, manifest: Mapping[str, Any]) -> None:
    declared = {"manifest.json", manifest["region_catalog"]["path"]}
    declared.update(item["path"] for item in manifest["volumes"].values())
    for relative in declared - {"manifest.json"}:
        _safe_resource_path(root, relative)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != declared:
        raise ValueError("volume pack complete file graph differs from manifest")


def _verified_resource(root: Path, descriptor: dict[str, Any], label: str) -> Path:
    path = _safe_resource_path(root, descriptor["path"])
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link")
    size = path.stat().st_size
    if size != descriptor["bytes"]:
        raise ValueError(f"{label} encoded byte length differs")
    if size > _MAX_RESOURCE_BYTES:
        raise ValueError(f"{label} exceeds resource limit")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != descriptor["sha256"]:
        raise ValueError(f"{label} encoded SHA-256 differs")
    return path


def _load_decoded_volume(
    root: Path, descriptor: dict[str, Any], grid: AtlasVolumeGrid
) -> NDArray[np.uint16]:
    label = descriptor["semantic"]
    if descriptor["decoded_bytes"] > _MAX_RESOURCE_BYTES:
        raise ValueError(f"{label} decoded data exceeds resource limit")
    path = _verified_resource(root, descriptor, label)
    try:
        with gzip.open(path, "rb") as stream:
            decoded = stream.read(descriptor["decoded_bytes"] + 1)
    except (EOFError, OSError) as error:
        raise ValueError(f"{label} gzip data is invalid") from error
    if len(decoded) != descriptor["decoded_bytes"]:
        raise ValueError(f"{label} decoded byte length differs")
    if hashlib.sha256(decoded).hexdigest() != descriptor["decoded_sha256"]:
        raise ValueError(f"{label} decoded SHA-256 differs")
    values = np.frombuffer(decoded, dtype="<u2").reshape(grid.shape)
    return np.array(values, dtype=np.uint16, order="C", copy=True)


def _validate_annotation(
    annotation: NDArray[np.uint16],
    regions: AtlasRegionCatalog,
    first_right_ml_index: int,
) -> None:
    by_index = {row.index: row for row in regions.physical("allen")}
    unknown = set(map(int, np.unique(annotation))) - set(by_index)
    if unknown:
        raise ValueError(
            f"annotation contains unknown source indices: {sorted(unknown)}"
        )
    if by_index.get(0) is None or by_index[0].atlas_id != 0:
        raise ValueError("annotation source index zero must identify void")
    left = set(map(int, np.unique(annotation[:, :first_right_ml_index, :]))) - {0}
    right = set(map(int, np.unique(annotation[:, first_right_ml_index:, :]))) - {0}
    if any(by_index[index].atlas_id >= 0 for index in left):
        raise ValueError("annotation left half contains a non-left region")
    if any(by_index[index].atlas_id <= 0 for index in right):
        raise ValueError("annotation right half contains a non-right region")


def open_volume_pack(path: str | Path) -> AtlasVolumePack:
    """Read and validate a local ``ibl-atlas-volume-pack-v1`` manifest."""

    source = Path(path)
    manifest_path = source / "manifest.json" if source.is_dir() else source
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("volume manifest is invalid JSON") from error
    validate_volume_pack_manifest(manifest)
    grid_document = manifest["grid"]
    grid = AtlasVolumeGrid(
        tuple(grid_document["shape"]), tuple(grid_document["index_to_world_um"])
    )
    return AtlasVolumePack(
        manifest_path.parent.resolve(),
        _freeze(manifest),
        grid,
        manifest["hemisphere_boundary"]["first_right_index"],
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
