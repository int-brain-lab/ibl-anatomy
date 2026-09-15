"""Reader for immutable 10-um registered orthogonal slice stacks."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from xml.etree import ElementTree

import numpy as np

from .schema import (
    validate_registered_projection_manifest,
    validate_registered_resource_index,
)

ProjectionId = Literal["coronal", "sagittal", "horizontal"]
MappingName = Literal["allen", "beryl", "cosmos"]


@dataclass(frozen=True)
class RegisteredSlicePath:
    """One indexed-SVG path with all signed atlas identities preserved."""

    atlas_ids: Mapping[str, int]
    fill_rule: str
    d: str

    @property
    def ring_count(self) -> int:
        """Return the number of SVG subpaths, including hole rings."""

        return len(re.findall(r"[Mm]", self.d))


@dataclass(frozen=True)
class RegisteredSlice:
    """One decoded registered slice; path order and SVG topology are retained."""

    slice_index: int
    world_coordinate_um: float
    paths: tuple[RegisteredSlicePath, ...]


@dataclass(frozen=True)
class IndexedSvgPack:
    """Decoded indexed-SVG pack with immutable slice fragments."""

    projection: str
    pack_id: str
    slices: tuple[RegisteredSlice, ...]

    def slice(self, slice_index: int) -> RegisteredSlice | None:
        return next((item for item in self.slices if item.slice_index == slice_index), None)


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

        self._validate_slice_index(slice_index)
        index = self.load_resource_index()
        for entry in index["resources"]:
            if slice_index in entry["slice_indices"]:
                return entry["resource"]
        raise KeyError(f"registered slice has no resource: {slice_index}")

    def load_slice(self, slice_index: int) -> RegisteredSlice:
        """Decode one indexed-SVG slice while preserving IDs, rings, and holes."""

        self._validate_slice_index(slice_index)
        index = self.load_resource_index()
        entry = next(
            (item for item in index["resources"] if slice_index in item["slice_indices"]),
            None,
        )
        if entry is None:
            raise KeyError(f"registered slice has no resource: {slice_index}")
        descriptor = entry["resource"]
        decoded = _read_resource(self.root, descriptor, "registered SVG pack")
        pack = _decode_indexed_svg_pack(decoded)
        if pack.projection != self.projection_id or pack.pack_id != entry["pack_id"]:
            raise ValueError("registered SVG pack identity differs from resource index")
        inventory = tuple(item.slice_index for item in pack.slices)
        declared = tuple(entry["slice_indices"])
        if inventory != declared:
            raise ValueError("registered SVG pack slice inventory differs from resource index")
        result = pack.slice(slice_index)
        if result is None:
            raise KeyError(f"registered SVG pack has no slice: {slice_index}")
        expected = self.index_to_world([slice_index, 0, 0])[
            {"ml": 0, "ap": 1, "dv": 2}[self.world_slice_axis]
        ]
        if not np.isclose(result.world_coordinate_um, expected, rtol=1e-10, atol=1e-9):
            raise ValueError("registered SVG slice world coordinate differs from projection affine")
        return result

    def _validate_slice_index(self, slice_index: int) -> None:
        if not isinstance(slice_index, int) or isinstance(slice_index, bool):
            raise TypeError("registered slice index must be an integer")
        if slice_index < 0 or slice_index >= self.slice_count:
            raise IndexError("registered slice index is outside the native domain")


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


def _decode_indexed_svg_pack(data: bytes) -> IndexedSvgPack:
    """Decode ISVG-1 bytes matching the browser's fixed-header codec."""

    header_size = 28
    entry_size = 20
    if len(data) < header_size or data[:4] != b"ISVG":
        raise ValueError("indexed SVG pack header is invalid")
    version, flags, declared_header = data[4], data[5], struct.unpack_from("<H", data, 6)[0]
    projection_len, pack_len, count, table_offset, payload_offset, payload_length = struct.unpack_from("<HHIIII", data, 8)
    if version != 1 or flags != 0 or declared_header != header_size:
        raise ValueError("indexed SVG pack version or header is invalid")
    strings_end = header_size + projection_len + pack_len
    if count > 1_000_000 or table_offset != strings_end or payload_offset != table_offset + count * entry_size or payload_offset + payload_length != len(data):
        raise ValueError("indexed SVG pack offsets are invalid")
    try:
        projection = data[header_size : header_size + projection_len].decode("utf-8")
        pack_id = data[header_size + projection_len : strings_end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("indexed SVG pack identity is invalid UTF-8") from error
    if not projection or not pack_id or "\0" in projection + pack_id:
        raise ValueError("indexed SVG pack identity is invalid")
    entries: list[tuple[int, float, int, int]] = []
    previous = -1
    expected_offset = 0
    for offset in range(count):
        at = table_offset + offset * entry_size
        slice_index, world_coordinate, payload_start, length = struct.unpack_from("<idII", data, at)
        if slice_index <= previous or not np.isfinite(world_coordinate) or payload_start != expected_offset or payload_start + length > payload_length:
            raise ValueError("indexed SVG pack fragment table is invalid")
        entries.append((slice_index, world_coordinate, payload_start, length))
        previous = slice_index
        expected_offset += length
    if expected_offset != payload_length:
        raise ValueError("indexed SVG pack fragment table does not cover payload")
    slices: list[RegisteredSlice] = []
    for slice_index, world_coordinate, payload_start, length in entries:
        fragment = data[payload_offset + payload_start : payload_offset + payload_start + length]
        try:
            root = ElementTree.fromstring(fragment)
        except ElementTree.ParseError as error:
            raise ValueError("indexed SVG fragment is invalid XML") from error
        paths: list[RegisteredSlicePath] = []
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "path":
                continue
            d = element.attrib.get("d")
            fill_rule = element.attrib.get("fill-rule")
            if d is None or not d.startswith(("M", "m")):
                raise ValueError("indexed SVG path geometry is invalid")
            if fill_rule != "evenodd":
                raise ValueError("indexed SVG path fill-rule must be evenodd")
            try:
                atlas_ids = {name: int(element.attrib[f"data-{name}-id"]) for name in ("allen", "beryl", "cosmos")}
            except (KeyError, ValueError) as error:
                raise ValueError("indexed SVG path mapping IDs are invalid") from error
            if any(value == 0 for value in atlas_ids.values()) or len({value < 0 for value in atlas_ids.values()}) != 1:
                raise ValueError("indexed SVG path signed mappings are inconsistent")
            paths.append(RegisteredSlicePath(MappingProxyType(atlas_ids), fill_rule, d))
        if not paths:
            raise ValueError("indexed SVG slice contains no paths")
        slices.append(RegisteredSlice(slice_index, world_coordinate, tuple(paths)))
    return IndexedSvgPack(projection, pack_id, tuple(slices))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
