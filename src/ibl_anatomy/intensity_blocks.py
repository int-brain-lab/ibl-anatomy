"""Projection-oriented indexed-block transport for large atlas intensities."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
from jsonschema import Draft202012Validator
from numpy.typing import NDArray

from .schema import _load_schema

ProjectionAxis = Literal["ap", "ml", "dv"]
_AXES = ("ap", "ml", "dv")
_DEFAULT_MAX_BLOCK_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_CACHE_BYTES = 128 * 1024 * 1024
_MAX_ENCODED_BLOCK_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class IntensitySection:
    """One owned, C-contiguous uint16 plane with explicit array axes."""

    values: NDArray[np.uint16]
    array_axes: tuple[str, str]


@dataclass(frozen=True)
class IntensityCacheInfo:
    """Current decoded-block LRU accounting."""

    entries: int
    bytes: int
    hits: int
    misses: int


@dataclass(frozen=True)
class IntensityGrid:
    """Registered voxel-center grid for the transported volume."""

    reference_space_id: str
    grid_id: str
    shape: tuple[int, int, int]
    index_to_world_um_matrix: tuple[float, ...]

    @property
    def array_axes(self) -> tuple[str, str, str]:
        return _AXES

    @property
    def world_axes(self) -> tuple[str, str, str]:
        return ("ml", "ap", "dv")

    def index_to_world(self, indices: Any) -> NDArray[np.float64]:
        """Transform AP/ML/DV center indices to ML/AP/DV micrometres."""

        points = _points(indices, "intensity indices")
        matrix = np.asarray(self.index_to_world_um_matrix).reshape(4, 4)
        return np.ascontiguousarray(points @ matrix[:3, :3].T + matrix[:3, 3])

    def world_to_index(self, positions_um: Any) -> NDArray[np.float64]:
        """Transform ML/AP/DV micrometres to fractional AP/ML/DV indices."""

        points = _points(positions_um, "intensity world positions")
        inverse = np.linalg.inv(
            np.asarray(self.index_to_world_um_matrix, dtype=np.float64).reshape(4, 4)
        )
        return np.ascontiguousarray(points @ inverse[:3, :3].T + inverse[:3, 3])


class IntensityBlockPack:
    """Random-access reader for a local projection-oriented intensity pack."""

    def __init__(
        self,
        root: Path,
        manifest: Mapping[str, Any],
        grid: IntensityGrid,
        *,
        max_decoded_block_bytes: int,
        max_cache_bytes: int,
    ) -> None:
        if max_decoded_block_bytes < 1 or max_cache_bytes < 0:
            raise ValueError("intensity decode/cache limits are invalid")
        self.root = root
        self.manifest = manifest
        self.grid = grid
        self.shape = grid.shape
        self.max_decoded_block_bytes = max_decoded_block_bytes
        self.max_cache_bytes = max_cache_bytes
        self._cache: OrderedDict[tuple[str, int], NDArray[np.uint16]] = OrderedDict()
        self._cache_bytes = 0
        self._hits = 0
        self._misses = 0
        self._cache_lock = threading.RLock()

    @property
    def dataset_id(self) -> str:
        return self.manifest["dataset_id"]

    @property
    def reference_space_id(self) -> str:
        return self.grid.reference_space_id

    @property
    def grid_id(self) -> str:
        return self.grid.grid_id

    @property
    def value_range(self) -> tuple[int, int]:
        return tuple(self.manifest["value_range"])

    @property
    def recommended_display_range(self) -> tuple[int, int]:
        return tuple(self.manifest["recommended_display_range"])

    def index_to_world(self, indices: Any) -> NDArray[np.float64]:
        return self.grid.index_to_world(indices)

    def world_to_index(self, positions_um: Any) -> NDArray[np.float64]:
        return self.grid.world_to_index(positions_um)

    def cache_info(self) -> IntensityCacheInfo:
        with self._cache_lock:
            return IntensityCacheInfo(
                len(self._cache), self._cache_bytes, self._hits, self._misses
            )

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._cache_bytes = 0

    def read_section(self, axis: ProjectionAxis, index: int) -> IntensitySection:
        """Decode one projection-native block and return an owned plane."""

        projection = self._projection(axis)
        axis_index = _AXES.index(axis)
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("intensity section index must be an integer")
        if index < 0 or index >= self.shape[axis_index]:
            raise IndexError("intensity section index is outside the volume")
        block = next(
            item
            for item in projection["blocks"]
            if item["first_section"]
            <= index
            < item["first_section"] + item["section_count"]
        )
        decoded = self._decoded_block(axis, projection, block)
        within = index - block["first_section"]
        values = np.array(decoded[within], dtype=np.uint16, order="C", copy=True)
        return IntensitySection(values, tuple(projection["plane_axes"]))

    def verify(self) -> None:
        """Verify the complete graph, whole resources, and every indexed block."""

        expected = {"manifest.json"}
        expected.update(
            item["resource"]["path"] for item in self.manifest["projections"].values()
        )
        actual = {
            item.relative_to(self.root).as_posix()
            for item in self.root.rglob("*")
            if item.is_file() or item.is_symlink()
        }
        if actual != expected:
            raise ValueError("intensity pack complete file graph differs from manifest")
        for axis, projection in self.manifest["projections"].items():
            resource = projection["resource"]
            path = _safe_path(self.root, resource["path"])
            if path.stat().st_size != resource["bytes"]:
                raise ValueError(f"intensity {axis} resource byte length differs")
            if _file_sha256(path) != resource["sha256"]:
                raise ValueError(f"intensity {axis} resource SHA-256 differs")
            for block in projection["blocks"]:
                self._read_block_bytes(axis, projection, block)

    def _projection(self, axis: str) -> Mapping[str, Any]:
        if axis not in _AXES:
            raise ValueError("intensity projection axis must be ap, ml or dv")
        return self.manifest["projections"][axis]

    def _decoded_block(
        self,
        axis: str,
        projection: Mapping[str, Any],
        block: Mapping[str, Any],
    ) -> NDArray[np.uint16]:
        key = (axis, block["block_id"])
        with self._cache_lock:
            cached = self._cache.pop(key, None)
            if cached is not None:
                self._cache[key] = cached
                self._hits += 1
                return cached
            self._misses += 1
        encoded = self._read_block_bytes(axis, projection, block)
        if block["decoded_bytes"] > self.max_decoded_block_bytes:
            raise ValueError("intensity decoded block exceeds configured limit")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
                decoded = stream.read(block["decoded_bytes"] + 1)
        except (EOFError, OSError) as error:
            raise ValueError("intensity block gzip data is invalid") from error
        if len(decoded) != block["decoded_bytes"]:
            raise ValueError("intensity block decoded byte length differs")
        if hashlib.sha256(decoded).hexdigest() != block["decoded_sha256"]:
            raise ValueError("intensity block decoded SHA-256 differs")
        plane_shape = tuple(
            self.shape[_AXES.index(item)] for item in projection["plane_axes"]
        )
        shape = (block["section_count"], *plane_shape)
        values = np.frombuffer(decoded, dtype="<u2").reshape(shape)
        values = np.array(values, dtype=np.uint16, order="C", copy=True)
        if values.nbytes <= self.max_cache_bytes:
            with self._cache_lock:
                # Another worker may have populated this key while this worker
                # decoded it. Keep the resident array and avoid double-accounting.
                resident = self._cache.pop(key, None)
                if resident is not None:
                    self._cache[key] = resident
                    return resident
                while (
                    self._cache
                    and self._cache_bytes + values.nbytes > self.max_cache_bytes
                ):
                    _, evicted = self._cache.popitem(last=False)
                    self._cache_bytes -= evicted.nbytes
                if self._cache_bytes + values.nbytes <= self.max_cache_bytes:
                    self._cache[key] = values
                    self._cache_bytes += values.nbytes
        return values

    def _read_block_bytes(
        self,
        axis: str,
        projection: Mapping[str, Any],
        block: Mapping[str, Any],
    ) -> bytes:
        path = _safe_path(self.root, projection["resource"]["path"])
        if block["bytes"] > _MAX_ENCODED_BLOCK_BYTES:
            raise ValueError("intensity encoded block exceeds resource limit")
        with path.open("rb") as stream:
            stream.seek(block["offset"])
            encoded = stream.read(block["bytes"])
        if len(encoded) != block["bytes"]:
            raise ValueError(f"intensity {axis} block byte length differs")
        if hashlib.sha256(encoded).hexdigest() != block["sha256"]:
            raise ValueError(f"intensity {axis} block SHA-256 differs")
        return encoded


def _safe_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("intensity resource path is invalid")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("intensity resource escapes pack")
    candidate = root / part
    current = candidate
    while current != root and current != current.parent:
        if current.is_symlink():
            raise ValueError("intensity resource must not be a symbolic link")
        current = current.parent
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("intensity resource escapes pack") from error
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _points(value: Any, label: str) -> NDArray[np.float64]:
    points = np.asarray(value, dtype=np.float64)
    if points.shape == () or points.shape[-1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError(f"{label} must be finite triples")
    return points


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _validate_manifest(document: Any) -> dict[str, Any]:
    Draft202012Validator(_load_schema("intensity-blocks.schema.json")).validate(
        document
    )
    transform = document["index_to_world_um"]
    if not all(math.isfinite(value) for value in transform):
        raise ValueError("intensity index-to-world transform must be finite")
    if transform[12:] != [0, 0, 0, 1]:
        raise ValueError("intensity index-to-world transform must be affine")
    matrix = np.asarray(transform, dtype=np.float64).reshape(4, 4)
    if math.isclose(float(np.linalg.det(matrix[:3, :3])), 0):
        raise ValueError("intensity index-to-world transform must be invertible")
    value_range = document["value_range"]
    display_range = document["recommended_display_range"]
    if value_range[0] > value_range[1]:
        raise ValueError("intensity value range is reversed")
    if (
        display_range[0] > display_range[1]
        or display_range[0] < value_range[0]
        or display_range[1] > value_range[1]
    ):
        raise ValueError("intensity recommended display range is invalid")
    shape = document["shape"]
    resource_paths = [
        projection["resource"]["path"]
        for projection in document["projections"].values()
    ]
    if len(resource_paths) != len(set(resource_paths)):
        raise ValueError("intensity projection resource paths are not unique")
    for axis, projection in document["projections"].items():
        axis_index = _AXES.index(axis)
        expected_plane_axes = [item for item in _AXES if item != axis]
        if (
            projection["axis"] != axis
            or projection["plane_axes"] != expected_plane_axes
        ):
            raise ValueError(f"intensity {axis} projection axes differ")
        first = 0
        offset = 0
        plane_values = math.prod(
            shape[_AXES.index(item)] for item in expected_plane_axes
        )
        for expected_id, block in enumerate(projection["blocks"]):
            if block["block_id"] != expected_id:
                raise ValueError(f"intensity {axis} block IDs are not contiguous")
            if block["first_section"] != first or block["offset"] != offset:
                raise ValueError(f"intensity {axis} block index is not contiguous")
            if block["section_count"] > projection["sections_per_block"]:
                raise ValueError(f"intensity {axis} block exceeds section count")
            if block["decoded_bytes"] != block["section_count"] * plane_values * 2:
                raise ValueError(f"intensity {axis} block decoded byte count differs")
            first += block["section_count"]
            offset += block["bytes"]
        if first != shape[axis_index]:
            raise ValueError(f"intensity {axis} blocks do not cover the projection")
        if offset != projection["resource"]["bytes"]:
            raise ValueError(f"intensity {axis} block bytes differ from resource")
    return document


def open_intensity_block_pack(
    path: str | Path,
    *,
    max_decoded_block_bytes: int = _DEFAULT_MAX_BLOCK_BYTES,
    max_cache_bytes: int = _DEFAULT_MAX_CACHE_BYTES,
) -> IntensityBlockPack:
    """Open an indexed intensity pack without decoding blocks."""

    source = Path(path)
    manifest_path = source / "manifest.json" if source.is_dir() else source
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("intensity block manifest is invalid JSON") from error
    _validate_manifest(document)
    grid = IntensityGrid(
        document["reference_space_id"],
        document["grid_id"],
        tuple(document["shape"]),
        tuple(document["index_to_world_um"]),
    )
    return IntensityBlockPack(
        manifest_path.parent.resolve(),
        _freeze(document),
        grid,
        max_decoded_block_bytes=max_decoded_block_bytes,
        max_cache_bytes=max_cache_bytes,
    )
