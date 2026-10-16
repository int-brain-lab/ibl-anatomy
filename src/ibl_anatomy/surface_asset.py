"""Verified reference surfaces for display, separate from regional mesh packs."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import numpy as np

from .asset_set import PinnedResource, _download, _resource


@dataclass(frozen=True)
class SurfaceAsset:
    """Immutable source, preparation policy and world-coordinate contract."""

    asset_id: str
    reference_space_id: str
    role: str
    variant: str
    source_allen_id: int
    source: PinnedResource
    source_to_world_um: tuple[tuple[float, ...], ...]
    expected_vertices: int
    expected_triangles: int
    expected_boundary_edges: int


@dataclass(frozen=True)
class SurfaceGeometry:
    """Owned ML/AP/DV µm arrays; a display surface need not be watertight."""

    positions_um: np.ndarray
    normals: np.ndarray
    indices: np.ndarray
    asset: SurfaceAsset


def parse_surface_asset(value: dict) -> SurfaceAsset:
    """Validate a surface lock without loading source bytes."""
    required = {
        "format",
        "schema_version",
        "asset_id",
        "reference_space_id",
        "role",
        "variant",
        "source_allen_id",
        "source",
        "coordinate_system",
        "preparation",
        "expectations",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("surface asset fields differ")
    if (
        value["format"] != "ibl-reference-surface-v1"
        or value["schema_version"] != "1.0"
    ):
        raise ValueError("unsupported surface asset format")
    for name in ("asset_id", "reference_space_id"):
        if not isinstance(value[name], str) or not value[name]:
            raise ValueError(f"invalid surface {name}")
    if (
        value["role"] not in {"brain-envelope", "regional-context"}
        or value["variant"] != "source-native"
    ):
        raise ValueError("unsupported surface role or variant")
    if type(value["source_allen_id"]) is not int or value["source_allen_id"] <= 0:
        raise ValueError("surface must identify a positive Allen ID")
    if value["role"] == "brain-envelope" and value["source_allen_id"] != 997:
        raise ValueError("brain envelope must identify Allen root 997")
    if value["role"] == "regional-context" and value["source_allen_id"] == 997:
        raise ValueError("regional context cannot identify Allen root 997")
    coordinate = value["coordinate_system"]
    if (
        not isinstance(coordinate, dict)
        or set(coordinate)
        != {"units", "world_axes", "source_axes", "source_to_world_um"}
        or coordinate["units"] != "um"
        or coordinate["world_axes"] != ["ml", "ap", "dv"]
        or coordinate["source_axes"] != ["ap", "dv", "ml"]
    ):
        raise ValueError("unsupported surface coordinate system")
    affine = np.asarray(coordinate["source_to_world_um"], dtype=float)
    if (
        affine.shape != (4, 4)
        or not np.isfinite(affine).all()
        or not np.array_equal(affine[3], [0, 0, 0, 1])
        or not np.allclose(affine[:3, :3].T @ affine[:3, :3], np.eye(3))
        or not np.isclose(np.linalg.det(affine[:3, :3]), 1)
    ):
        raise ValueError("surface transform must be a rigid right-handed affine")
    if value["preparation"] != {
        "geometry": "source positions and triangles unchanged",
        "normals": "source vertex normals, normalized after world transform",
        "smoothing": False,
        "decimation": False,
    }:
        raise ValueError("unsupported surface preparation policy")
    counts = value["expectations"]
    if not isinstance(counts, dict) or set(counts) != {
        "vertices",
        "triangles",
        "boundary_edges",
    }:
        raise ValueError("surface expectations differ")
    for name, minimum in (("vertices", 4), ("triangles", 1), ("boundary_edges", 0)):
        if type(counts[name]) is not int or counts[name] < minimum:
            raise ValueError(f"invalid surface expected {name}")
    return SurfaceAsset(
        value["asset_id"],
        value["reference_space_id"],
        value["role"],
        value["variant"],
        value["source_allen_id"],
        _resource(value["source"], "surface source"),
        tuple(tuple(float(x) for x in row) for row in affine),
        counts["vertices"],
        counts["triangles"],
        counts["boundary_edges"],
    )


def bundled_surface_asset(name: str = "allen-root") -> SurfaceAsset:
    """Select the shared source-native Allen envelope by default."""
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("surface asset name is invalid")
    resource = files("ibl_anatomy.asset_sets").joinpath(f"{name}.json")
    return parse_surface_asset(json.loads(resource.read_text(encoding="utf-8")))


def _decode_obj(payload: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode the pinned triangular OBJ layout, preserving its vertex identities."""
    positions, normals, faces = [], [], []
    for line in payload.decode("ascii").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] in ("g", "usemtl") and len(fields) == 2:
            continue  # Source grouping/material labels do not change geometry.
        if fields[0] in ("v", "vn") and len(fields) == 4:
            (positions if fields[0] == "v" else normals).append(
                [float(x) for x in fields[1:]]
            )
        elif fields[0] == "f" and len(fields) == 4:
            face = []
            for entry in fields[1:]:
                parts = entry.split("//")
                if len(parts) != 2 or parts[0] != parts[1] or int(parts[0]) <= 0:
                    raise ValueError(
                        "surface OBJ requires aligned positive vertex/normal indices"
                    )
                face.append(int(parts[0]) - 1)
            faces.append(face)
        else:
            raise ValueError("unsupported surface OBJ record")
    return (
        np.array(positions, dtype=np.float32, order="C"),
        np.array(normals, dtype=np.float32, order="C"),
        np.array(faces, dtype=np.uint32, order="C").reshape(-1, 3),
    )


def load_surface_asset(
    path: str | Path, asset: SurfaceAsset | None = None
) -> SurfaceGeometry:
    """Verify a local source OBJ and return owned world arrays; never download."""
    asset = bundled_surface_asset() if asset is None else asset
    path = Path(path)
    if path.is_dir():
        path = path / "surface.obj"
    if path.stat().st_size != asset.source.bytes:
        raise ValueError("surface source byte length differs")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != asset.source.sha256:
        raise ValueError("surface source SHA-256 differs")
    positions, normals, faces = _decode_obj(payload)
    if (
        positions.shape != (asset.expected_vertices, 3)
        or normals.shape != positions.shape
        or faces.shape != (asset.expected_triangles, 3)
        or not np.isfinite(positions).all()
        or not np.isfinite(normals).all()
        or faces.max() >= len(positions)
        or np.any(np.linalg.norm(normals, axis=1) == 0)
    ):
        raise ValueError("surface source arrays differ from expectations")
    edges = np.sort(
        np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1
    )
    _, counts = np.unique(edges, axis=0, return_counts=True)
    if np.count_nonzero(counts == 1) != asset.expected_boundary_edges or np.any(
        counts > 2
    ):
        raise ValueError("surface topology differs from expectations")
    affine = np.asarray(asset.source_to_world_um)
    positions = np.array(
        positions @ affine[:3, :3].T + affine[:3, 3], dtype=np.float32, order="C"
    )
    normals = np.array(normals @ affine[:3, :3].T, dtype=np.float32, order="C")
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    cross = np.cross(
        positions[faces[:, 1]] - positions[faces[:, 0]],
        positions[faces[:, 2]] - positions[faces[:, 0]],
    )
    if np.any(np.linalg.norm(cross, axis=1) == 0):
        raise ValueError("surface has degenerate triangles")
    return SurfaceGeometry(positions, normals, faces.ravel().copy(), asset)


def materialize_surface_asset(
    target: str | Path,
    asset: SurfaceAsset | None = None,
    *,
    source_path: str | Path | None = None,
    timeout: float = 60,
) -> SurfaceGeometry:
    """Materialize a verified envelope atomically from a local source or pinned URL."""
    asset = bundled_surface_asset() if asset is None else asset
    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(f"surface destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        source = temporary / "surface.obj"
        if source_path is None:
            _download(asset.source, source, timeout=timeout)
        else:
            shutil.copyfile(source_path, source)
        load_surface_asset(source, asset)
        temporary.rename(destination)
        return load_surface_asset(destination, asset)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
