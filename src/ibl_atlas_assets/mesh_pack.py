"""Read and verify immutable atlas mesh packs."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .binary import RawChunk, decode_raw_lod
from .schema import validate_mesh_pack_manifest

_RESULT_KEYS = {
    "rebuild",
    "coverage",
    "midline",
    "topology",
    "mapping",
    "bounds",
    "integrity",
    "complete_file_graph",
}


@dataclass(frozen=True)
class MeshComponentRange:
    """Contiguous geometry ranges associated with one mesh component."""

    component_id: int
    vertex_start: int
    vertex_count: int
    index_start: int
    index_count: int
    left_presentation_id: int | None
    right_presentation_id: int | None


@dataclass(frozen=True)
class MeshGeometry:
    """Validated renderer-neutral mesh geometry for one LOD."""

    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    component_ids: NDArray[np.uint16]
    indices: NDArray[np.uint32]
    ranges: tuple[MeshComponentRange, ...]
    components: tuple[dict[str, Any], ...]
    presentations: tuple[dict[str, Any], ...]
    reference_space: str
    coordinate_system: dict[str, Any]


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")  # noqa: TRY004
    return value


def _safe_resource_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("mesh resource path is invalid")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"mesh resource escapes pack: {relative}")
    resolved_root = root.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"mesh resource escapes pack: {relative}") from error
    return resolved


def _nonnegative_int(value: Any, label: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{label} is invalid")
    return value


class MeshPack:
    """An immutable mesh-pack manifest and its local resource graph."""

    def __init__(
        self, manifest_path: Path, manifest: dict[str, Any], max_resource_bytes: int
    ):
        self.manifest_path = manifest_path
        self.root = manifest_path.parent
        self.manifest = manifest
        self.max_resource_bytes = max_resource_bytes
        self._decoded_resources: dict[tuple[Any, ...], bytes] = {}
        self._verified = False

    @property
    def components(self) -> tuple[dict[str, Any], ...]:
        """Return component metadata in component-ID order."""

        return tuple(self.manifest["components"])

    @property
    def presentations(self) -> tuple[dict[str, Any], ...]:
        """Return signed region presentation metadata."""

        return tuple(self.manifest["presentations"])

    @property
    def reference_space(self) -> str:
        """Return the exact atlas reference-space identifier."""

        return self.manifest["reference_space_id"]

    @property
    def coordinate_system(self) -> dict[str, Any]:
        """Return the declared coordinate-system metadata without transforming it."""

        return self.manifest["coordinate_system"]

    def _resource(self, descriptor: dict[str, Any]) -> bytes:
        relative = descriptor["path"]
        codec = descriptor["codec"]
        cache_key = (
            relative,
            descriptor["bytes"],
            descriptor["sha256"],
            codec["name"],
            codec["decoded_bytes"],
        )
        if cache_key in self._decoded_resources:
            return self._decoded_resources[cache_key]
        path = _safe_resource_path(self.root, relative)
        if not path.is_file():
            raise FileNotFoundError(f"mesh resource is missing: {relative}")
        if descriptor["bytes"] > self.max_resource_bytes:
            raise ValueError(f"mesh resource exceeds configured byte limit: {relative}")
        if codec["decoded_bytes"] > self.max_resource_bytes:
            raise ValueError(
                f"mesh resource exceeds configured decoded limit: {relative}"
            )
        if path.stat().st_size != descriptor["bytes"]:
            raise ValueError(f"mesh resource byte length differs: {relative}")
        encoded = path.read_bytes()
        if len(encoded) != descriptor["bytes"]:
            raise ValueError(f"mesh resource byte length differs: {relative}")
        if hashlib.sha256(encoded).hexdigest() != descriptor["sha256"]:
            raise ValueError(f"mesh resource SHA-256 differs: {relative}")
        if codec["name"] == "gzip":
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
                    decoded = stream.read(codec["decoded_bytes"] + 1)
            except (gzip.BadGzipFile, EOFError, OSError) as error:
                raise ValueError(
                    f"mesh resource gzip is invalid: {relative}"
                ) from error
        elif codec["name"] == "none":
            decoded = encoded
        else:
            raise ValueError(f"mesh resource codec is unsupported: {relative}")
        if len(decoded) != codec["decoded_bytes"]:
            raise ValueError(f"mesh resource decoded length differs: {relative}")
        self._decoded_resources[cache_key] = decoded
        return decoded

    def _validate_lod(self, lod: dict[str, Any]) -> tuple[RawChunk, ...]:
        decoder = lod["decoder"]
        if decoder["container"] != "EAM3" or decoder["container_version"] != 1:
            raise ValueError(f"mesh LOD decoder contract differs: {lod['id']}")
        if decoder["encoding"] != "raw-v1":
            raise ValueError(f"mesh LOD encoding is unsupported: {lod['id']}")
        chunks = decode_raw_lod(self._resource(lod["resource"]))
        triangle_count = sum(len(chunk.indices) // 3 for chunk in chunks)
        if triangle_count != lod["triangle_count"]:
            raise ValueError(f"mesh LOD triangle count differs: {lod['id']}")
        self._validate_chunks(lod["id"], chunks)
        return chunks

    def _validate_chunks(self, lod_id: str, chunks: tuple[RawChunk, ...]) -> None:
        component_by_id = {
            component["component_id"]: component
            for component in self.manifest["components"]
        }
        if len(component_by_id) != len(self.manifest["components"]):
            raise ValueError("mesh component IDs are not unique")
        if set(component_by_id) != set(range(len(component_by_id))):
            raise ValueError("mesh component IDs must be contiguous")
        seen_components: list[int] = []
        for chunk in chunks:
            index_spans: list[tuple[int, int]] = []
            vertex_spans: list[tuple[int, int]] = []
            for raw_range in chunk.ranges:
                if not isinstance(raw_range, dict):
                    raise ValueError(f"mesh LOD range is invalid: {lod_id}")  # noqa: TRY004
                component_id = _nonnegative_int(
                    raw_range.get("component_id"), "mesh range component ID"
                )
                if component_id not in component_by_id:
                    raise ValueError(f"mesh LOD component range differs: {lod_id}")
                vertex_start = _nonnegative_int(
                    raw_range.get("vertex_start"), "mesh range vertex start"
                )
                vertex_count = _nonnegative_int(
                    raw_range.get("vertex_count"),
                    "mesh range vertex count",
                    positive=True,
                )
                index_start = _nonnegative_int(
                    raw_range.get("index_start"), "mesh range index start"
                )
                index_count = _nonnegative_int(
                    raw_range.get("index_count"),
                    "mesh range index count",
                    positive=True,
                )
                vertex_end = vertex_start + vertex_count
                index_end = index_start + index_count
                if vertex_end > len(chunk.positions) or index_end > len(chunk.indices):
                    raise ValueError(
                        f"mesh LOD component range is out of bounds: {lod_id}"
                    )
                if index_count % 3 != 0:
                    raise ValueError(
                        f"mesh LOD component range is not triangular: {lod_id}"
                    )
                component = component_by_id[component_id]
                if (
                    raw_range.get("left_presentation_id")
                    != component["left_presentation_id"]
                    or raw_range.get("right_presentation_id")
                    != component["right_presentation_id"]
                ):
                    raise ValueError(
                        f"mesh LOD component presentation identity differs: {lod_id}"
                    )
                vertex_components = chunk.component_ids[vertex_start:vertex_end]
                if np.any(vertex_components != component_id):
                    raise ValueError(
                        f"mesh LOD vertex component identity differs: {lod_id}"
                    )
                range_indices = chunk.indices[index_start:index_end]
                if np.any(range_indices < vertex_start) or np.any(
                    range_indices >= vertex_end
                ):
                    raise ValueError(
                        f"mesh LOD component index identity differs: {lod_id}"
                    )
                seen_components.append(component_id)
                vertex_spans.append((vertex_start, vertex_end))
                index_spans.append((index_start, index_end))
            if sorted(vertex_spans) != _partition_spans(
                len(chunk.positions), vertex_spans
            ):
                raise ValueError(
                    f"mesh LOD vertex ranges are not a partition: {lod_id}"
                )
            if sorted(index_spans) != _partition_spans(len(chunk.indices), index_spans):
                raise ValueError(f"mesh LOD index ranges are not a partition: {lod_id}")
        if sorted(seen_components) != list(range(len(component_by_id))):
            raise ValueError(f"mesh LOD component ranges differ: {lod_id}")
        for component_id, component in component_by_id.items():
            component_ranges = [
                raw_range
                for chunk in chunks
                for raw_range in chunk.ranges
                if raw_range["component_id"] == component_id
            ]
            vertex_count = sum(
                raw_range["vertex_count"] for raw_range in component_ranges
            )
            triangle_count = sum(
                raw_range["index_count"] // 3 for raw_range in component_ranges
            )
            if (
                vertex_count != component["vertex_count"]
                or triangle_count != component["triangle_count"]
            ):
                raise ValueError(f"mesh component declared counts differ: {lod_id}")

    def verify(self) -> None:
        """Verify every declared resource and the complete immutable file graph."""

        lod_ids = [lod["id"] for lod in self.manifest["lods"]]
        if len(lod_ids) != len(set(lod_ids)):
            raise ValueError("mesh LOD IDs are not unique")
        if self.manifest["default_lod_id"] not in lod_ids:
            raise ValueError("mesh default LOD is missing")
        upgrade = self.manifest["upgrade_lod_id"]
        if upgrade is not None and upgrade not in lod_ids:
            raise ValueError("mesh upgrade LOD is missing")
        presentation_ids = [
            item["presentation_id"] for item in self.manifest["presentations"]
        ]
        if len(presentation_ids) != len(set(presentation_ids)):
            raise ValueError("mesh presentation IDs are not unique")
        presentation_set = set(presentation_ids)
        presentation_by_id = {
            item["presentation_id"]: item for item in self.manifest["presentations"]
        }
        for presentation in self.manifest["presentations"]:
            signed_id = presentation["signed_allen_id"]
            expected_sign = -1 if presentation["side"] == "left" else 1
            if expected_sign * signed_id <= 0:
                raise ValueError("mesh presentation side and signed ID differ")
            if abs(signed_id) != presentation["source_allen_id"]:
                raise ValueError("mesh presentation source and signed ID differ")
            if presentation["mappings"]["allen"] != signed_id:
                raise ValueError("mesh presentation Allen mapping differs")
        for component in self.manifest["components"]:
            for side in ("left", "right"):
                presentation_id = component[f"{side}_presentation_id"]
                if (
                    presentation_id is not None
                    and presentation_id not in presentation_set
                ):
                    raise ValueError("mesh component presentation is missing")
                if presentation_id is not None:
                    presentation = presentation_by_id[presentation_id]
                    if presentation["side"] != side:
                        raise ValueError("mesh component presentation side differs")
                    if presentation["source_allen_id"] != component["source_allen_id"]:
                        raise ValueError("mesh component presentation source differs")

        declared = {"manifest.json"}
        for lod in self.manifest["lods"]:
            declared.add(lod["resource"]["path"])
            self._validate_lod(lod)

        report_descriptor = self.manifest["validation"]["report"]
        declared.add(report_descriptor["path"])
        try:
            report = json.loads(self._resource(report_descriptor))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("mesh validation report is invalid JSON") from error
        expected_results = {
            key: self.manifest["validation"][key] for key in _RESULT_KEYS
        }
        if (
            not isinstance(report, dict)
            or report.get("format") != "atlas-mesh-pack-validation-report-v1"
            or report.get("pack_id") != self.manifest["pack_id"]
            or report.get("test_only") != (self.manifest["purpose"] == "test-only")
            or report.get("results") != expected_results
            or set(report.get("results", {})) != _RESULT_KEYS
        ):
            raise ValueError("mesh validation report identity differs")

        actual = {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        missing = declared - actual
        undeclared = actual - declared
        if missing:
            raise FileNotFoundError(
                "mesh pack graph is missing: " + ", ".join(sorted(missing))
            )
        if undeclared:
            raise ValueError(
                "mesh pack graph contains undeclared files: "
                + ", ".join(sorted(undeclared))
            )
        self._verified = True

    def load_geometry(self, lod_id: str | None = None) -> MeshGeometry:
        """Load one verified LOD and concatenate its independently indexed chunks."""

        if not self._verified:
            self.verify()
        selected_id = lod_id or self.manifest["default_lod_id"]
        lod = next(
            (item for item in self.manifest["lods"] if item["id"] == selected_id), None
        )
        if lod is None:
            raise KeyError(f"unknown mesh LOD: {selected_id}")
        chunks = self._validate_lod(lod)
        positions: list[NDArray[np.float32]] = []
        normals: list[NDArray[np.float32]] = []
        component_ids: list[NDArray[np.uint16]] = []
        indices: list[NDArray[np.uint32]] = []
        ranges: list[MeshComponentRange] = []
        vertex_base = 0
        index_base = 0
        for chunk in chunks:
            positions.append(chunk.positions)
            normals.append(chunk.normals)
            component_ids.append(chunk.component_ids)
            indices.append(
                np.ascontiguousarray(chunk.indices + vertex_base, dtype=np.uint32)
            )
            for raw_range in chunk.ranges:
                ranges.append(
                    MeshComponentRange(
                        component_id=raw_range["component_id"],
                        vertex_start=vertex_base + raw_range["vertex_start"],
                        vertex_count=raw_range["vertex_count"],
                        index_start=index_base + raw_range["index_start"],
                        index_count=raw_range["index_count"],
                        left_presentation_id=raw_range["left_presentation_id"],
                        right_presentation_id=raw_range["right_presentation_id"],
                    )
                )
            vertex_base += len(chunk.positions)
            index_base += len(chunk.indices)
        return MeshGeometry(
            positions=_concatenate(positions, np.dtype(np.float32), (0, 3)),
            normals=_concatenate(normals, np.dtype(np.float32), (0, 3)),
            component_ids=_concatenate(component_ids, np.dtype(np.uint16), (0,)),
            indices=_concatenate(indices, np.dtype(np.uint32), (0,)),
            ranges=tuple(ranges),
            components=self.components,
            presentations=self.presentations,
            reference_space=self.reference_space,
            coordinate_system=self.coordinate_system,
        )


def _partition_spans(total: int, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    expected: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(spans):
        if start != cursor or end <= start:
            return []
        expected.append((start, end))
        cursor = end
    return expected if cursor == total else []


def _concatenate(
    arrays: list[NDArray[Any]], dtype: np.dtype[Any], empty_shape: tuple[int, ...]
) -> NDArray[Any]:
    if not arrays:
        return np.empty(empty_shape, dtype=dtype)
    return np.ascontiguousarray(np.concatenate(arrays), dtype=dtype)


def open_mesh_pack(
    path: str | Path, *, max_resource_bytes: int = 2 * 1024**3
) -> MeshPack:
    """Open and schema-validate a local mesh-pack manifest without loading resources."""

    if max_resource_bytes < 1:
        raise ValueError("max_resource_bytes must be positive")
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"mesh manifest is missing: {manifest_path}")
    manifest = validate_mesh_pack_manifest(_read_json(manifest_path, "mesh manifest"))
    return MeshPack(manifest_path.resolve(), manifest, max_resource_bytes)
