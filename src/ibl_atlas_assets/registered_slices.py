"""Reader for immutable 10-um registered orthogonal slice stacks."""

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

from .schema import (
    validate_registered_projection_manifest,
    validate_registered_resource_index,
)

ProjectionId = Literal["coronal", "sagittal", "horizontal"]


@dataclass(frozen=True)
class RegisteredProjection:
    """A validated registered projection manifest and its local resource graph."""

    root: Path
    manifest: Mapping[str, Any]

    @property
    def projection_id(self) -> ProjectionId:
        return self.manifest["id"]

    @property
    def reference_space_id(self) -> str:
        return self.manifest["reference_space_id"]

    @property
    def grid_id(self) -> str:
        return self.manifest["grid_id"]

    @property
    def world_slice_axis(self) -> str:
        return self.manifest["world_slice_axis"]

    @property
    def slice_count(self) -> int:
        return self.manifest["slice_count"]

    @property
    def slice_shape(self) -> tuple[int, int]:
        return tuple(self.manifest["slice_shape"])

    @property
    def display_slices(self) -> tuple[int, ...]:
        return tuple(self.manifest["display_slices"])

    @property
    def plane_index_to_world_um(self) -> tuple[float, ...]:
        return tuple(self.manifest["plane_index_to_world_um"])

    @property
    def world_to_plane_index(self) -> tuple[float, ...]:
        matrix = self.manifest.get("world_to_plane_index")
        if matrix is None:
            matrix = np.linalg.inv(
                np.asarray(self.plane_index_to_world_um).reshape(4, 4)
            ).reshape(-1)
        return tuple(matrix)

    @property
    def voxel_edge_extent_um(self) -> tuple[float, ...]:
        return tuple(self.manifest["voxel_edge_extent_um"])

    def index_to_world(self, indices: Any) -> np.ndarray:
        """Transform plane indices to ML/AP/DV world micrometres."""

        points = np.asarray(indices, dtype=np.float64)
        if points.shape == () or points.shape[-1] != 3 or not np.all(np.isfinite(points)):
            raise ValueError("registered plane indices must be finite triples")
        matrix = np.asarray(self.plane_index_to_world_um).reshape(4, 4)
        return np.ascontiguousarray(points @ matrix[:3, :3].T + matrix[:3, 3])

    def world_to_index(self, positions_um: Any) -> np.ndarray:
        """Transform ML/AP/DV world micrometres to fractional plane indices."""

        points = np.asarray(positions_um, dtype=np.float64)
        if points.shape == () or points.shape[-1] != 3 or not np.all(np.isfinite(points)):
            raise ValueError("registered world positions must be finite triples")
        matrix = np.asarray(self.world_to_plane_index).reshape(4, 4)
        return np.ascontiguousarray(points @ matrix[:3, :3].T + matrix[:3, 3])

    def load_resource_index(self) -> Mapping[str, Any]:
        """Verify and decode the transitive registered-SVG resource index."""

        descriptor = self.manifest["resource_index"]["resource"]
        payload = _read_resource(self.root, descriptor, "registered resource index")
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("registered resource index is invalid JSON") from error
        validate_registered_resource_index(document)
        if document["projection_id"] != self.projection_id:
            raise ValueError("registered resource index projection differs")
        return _freeze(document)

    def resource_for_slice(self, slice_index: int) -> Mapping[str, Any]:
        """Return the verified resource descriptor containing one native slice."""

        if not isinstance(slice_index, int) or isinstance(slice_index, bool):
            raise TypeError("registered slice index must be an integer")
        if slice_index < 0 or slice_index >= self.slice_count:
            raise IndexError("registered slice index is outside the native domain")
        index = self.load_resource_index()
        for entry in index["resources"]:
            if slice_index in entry["slice_indices"]:
                return entry["resource"]
        raise KeyError(f"registered slice has no resource: {slice_index}")


def open_registered_projection(path: str | Path) -> RegisteredProjection:
    """Open and validate a registered projection manifest from a local path."""

    source = Path(path)
    manifest_path = source / "manifest.json" if source.is_dir() else source
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("registered projection manifest is invalid JSON") from error
    validate_registered_projection_manifest(manifest)
    return RegisteredProjection(manifest_path.parent.resolve(), _freeze(manifest))


def _read_resource(root: Path, descriptor: Mapping[str, Any], label: str) -> bytes:
    relative = descriptor["path"]
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path escapes projection pack")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} path escapes projection pack") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise FileNotFoundError(f"{label} resource is missing: {relative}")
    encoded = resolved.read_bytes()
    if len(encoded) != descriptor["bytes"]:
        raise ValueError(f"{label} encoded byte length differs")
    if hashlib.sha256(encoded).hexdigest() != descriptor["sha256"]:
        raise ValueError(f"{label} encoded SHA-256 differs")
    codec = descriptor["codec"]
    if codec["name"] == "gzip":
        try:
            decoded = gzip.decompress(encoded)
        except (gzip.BadGzipFile, OSError) as error:
            raise ValueError(f"{label} gzip data is invalid") from error
    elif codec["name"] == "none":
        decoded = encoded
    else:
        raise ValueError(f"{label} codec is unsupported")
    if len(decoded) != codec["decoded_bytes"]:
        raise ValueError(f"{label} decoded byte length differs")
    return decoded


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
