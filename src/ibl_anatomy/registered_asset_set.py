"""Pinned atlas-projection-pack graphs for registered anatomy consumers."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .registered_slices import RegisteredProjection
from .schema import (
    validate_registered_projection_manifest,
    validate_registered_resource_index,
)


@dataclass(frozen=True)
class RegisteredResource:
    url: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class RegisteredProjectionExpectation:
    slice_count: int
    slice_shape: tuple[int, int]
    inventory_sha256: str


@dataclass(frozen=True)
class RegisteredAssetSet:
    asset_set_id: str
    reference_space_id: str
    grid_id: str
    root_pack_id: str
    root_manifest: RegisteredResource
    projections: Mapping[str, RegisteredProjectionExpectation]
    annotation_source: RegisteredResource
    lut_recipe: Mapping[str, Any]
    terms_url: str
    citation_url: str
    citation_policy_url: str


@dataclass(frozen=True)
class MaterializedRegisteredAssets:
    root: Path
    pack_id: str
    root_manifest: Mapping[str, Any]
    projections: Mapping[str, RegisteredProjection]
    file_count: int
    encoded_bytes: int


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _resource(value: Any, label: str) -> RegisteredResource:
    if not isinstance(value, dict) or set(value) != {"url", "bytes", "sha256"}:
        raise ValueError(f"{label} must contain url, bytes and sha256")
    url, size, digest = value["url"], value["bytes"], value["sha256"]
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme not in {
        "file",
        "http",
        "https",
    }:
        raise ValueError(f"{label} URL is invalid")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError(f"{label} byte count is invalid")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError(f"{label} SHA-256 is invalid")
    return RegisteredResource(url, size, digest)


def parse_registered_asset_set(value: Any) -> RegisteredAssetSet:
    required = {
        "format",
        "schema_version",
        "asset_set_id",
        "reference_space_id",
        "grid_id",
        "root_pack_id",
        "root_manifest",
        "projections",
        "provenance",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("registered asset-set fields differ")
    if (
        value["format"] != "ibl-atlas-registered-asset-set-v1"
        or value["schema_version"] != "1.0"
    ):
        raise ValueError("unsupported registered asset-set format")
    for key in ("asset_set_id", "reference_space_id", "grid_id", "root_pack_id"):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError(f"{key} is invalid")
    projections = value["projections"]
    if not isinstance(projections, dict) or set(projections) != {
        "coronal",
        "sagittal",
        "horizontal",
    }:
        raise ValueError("registered asset-set projections differ")
    parsed = {}
    for name, item in projections.items():
        if not isinstance(item, dict) or set(item) != {
            "slice_count",
            "slice_shape",
            "inventory_sha256",
        }:
            raise ValueError(f"{name} projection expectation fields differ")
        shape, digest = item["slice_shape"], item["inventory_sha256"]
        if (
            not isinstance(item["slice_count"], int)
            or item["slice_count"] < 1
            or not isinstance(shape, list)
            or len(shape) != 2
            or any(not isinstance(v, int) or v < 1 for v in shape)
        ):
            raise ValueError(f"{name} projection dimensions are invalid")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError(f"{name} inventory SHA-256 is invalid")
        parsed[name] = RegisteredProjectionExpectation(
            item["slice_count"], tuple(shape), digest
        )
    provenance = value["provenance"]
    fields = {
        "annotation_source",
        "lut_recipe",
        "terms_url",
        "citation_url",
        "citation_policy_url",
    }
    if (
        not isinstance(provenance, dict)
        or set(provenance) != fields
        or not isinstance(provenance["lut_recipe"], dict)
        or set(provenance["lut_recipe"])
        != {"path", "bytes", "sha256", "producer", "iblatlas_commit"}
    ):
        raise ValueError("registered asset-set provenance differs")
    for key in ("terms_url", "citation_url", "citation_policy_url"):
        if not isinstance(provenance[key], str) or urllib.parse.urlparse(
            provenance[key]
        ).scheme not in {"http", "https"}:
            raise ValueError(f"{key} is invalid")
    recipe = provenance["lut_recipe"]
    if (
        not isinstance(recipe["path"], str)
        or not recipe["path"]
        or not isinstance(recipe["bytes"], int)
        or isinstance(recipe["bytes"], bool)
        or recipe["bytes"] < 1
        or not isinstance(recipe["sha256"], str)
        or len(recipe["sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in recipe["sha256"])
        or not isinstance(recipe["producer"], str)
        or not recipe["producer"]
        or not isinstance(recipe["iblatlas_commit"], str)
        or len(recipe["iblatlas_commit"]) != 40
    ):
        raise ValueError("registered asset-set LUT recipe is invalid")
    return RegisteredAssetSet(
        value["asset_set_id"],
        value["reference_space_id"],
        value["grid_id"],
        value["root_pack_id"],
        _resource(value["root_manifest"], "root manifest"),
        MappingProxyType(parsed),
        _resource(provenance["annotation_source"], "annotation source"),
        _freeze(recipe),
        provenance["terms_url"],
        provenance["citation_url"],
        provenance["citation_policy_url"],
    )


def open_registered_asset_set(path: str | Path) -> RegisteredAssetSet:
    return parse_registered_asset_set(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def bundled_registered_asset_set(
    name: str = "allen-ccf-2017-10um",
) -> RegisteredAssetSet:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("asset set name is invalid")
    resource = files("ibl_anatomy.asset_sets").joinpath(f"{name}.json")
    return parse_registered_asset_set(json.loads(resource.read_text(encoding="utf-8")))


def _download(resource: RegisteredResource, destination: Path, timeout: float) -> None:
    with urllib.request.urlopen(resource.url, timeout=timeout) as response:  # noqa: S310
        payload = response.read(resource.bytes + 1)
    if (
        len(payload) != resource.bytes
        or hashlib.sha256(payload).hexdigest() != resource.sha256
    ):
        raise ValueError(f"resource integrity mismatch: {resource.url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _safe_relative(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{label} path escapes projection pack")
    return path


def _descriptor_resource(
    base_url: str, descriptor: Mapping[str, Any], label: str
) -> tuple[RegisteredResource, Path]:
    relative = _safe_relative(descriptor.get("path"), label)
    size = descriptor.get("bytes")
    digest = descriptor.get("sha256")
    return _resource(
        {
            "url": urllib.parse.urljoin(base_url, relative.as_posix()),
            "bytes": size,
            "sha256": digest,
        },
        label,
    ), relative


def _decode_descriptor(path: Path, descriptor: Mapping[str, Any], label: str) -> bytes:
    relative = _safe_relative(descriptor.get("path"), label)
    resolved = (path / relative).resolve()
    try:
        resolved.relative_to(path.resolve())
    except ValueError as error:
        raise ValueError(f"{label} path escapes projection pack") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise FileNotFoundError(f"{label} resource is missing: {relative}")
    payload = resolved.read_bytes()
    if len(payload) != descriptor.get("bytes") or hashlib.sha256(
        payload
    ).hexdigest() != descriptor.get("sha256"):
        raise ValueError(f"{label} resource integrity differs")
    codec = descriptor.get("codec")
    if not isinstance(codec, dict) or codec.get("name") not in {"gzip", "none"}:
        raise ValueError(f"{label} codec is unsupported")
    try:
        decoded = gzip.decompress(payload) if codec["name"] == "gzip" else payload
    except (gzip.BadGzipFile, OSError) as error:
        raise ValueError(f"{label} gzip data is invalid") from error
    if len(decoded) != codec.get("decoded_bytes"):
        raise ValueError(f"{label} decoded byte length differs")
    return decoded


def _validate_root(
    lock: RegisteredAssetSet, document: Any
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    if not isinstance(document, dict):
        raise ValueError("projection root is not an object")
    if (
        document.get("format") != "atlas-projection-pack-v1"
        or document.get("schema_version") != "1.0"
        or document.get("pack_id") != lock.root_pack_id
        or document.get("immutable") is not True
        or document.get("reference_space_id") != lock.reference_space_id
        or document.get("mappings") != ["allen", "beryl", "cosmos"]
    ):
        raise ValueError("projection root identity differs from lock")
    raw_entries = document.get("projections")
    if not isinstance(raw_entries, list) or any(
        not isinstance(item, dict) for item in raw_entries
    ):
        raise ValueError("projection root entries differ")
    entries = {item.get("id"): item for item in raw_entries}
    if len(entries) != len(raw_entries) or set(entries) != {
        "coronal",
        "sagittal",
        "horizontal",
        "top",
        "swanson",
    }:
        raise ValueError("projection root entries differ")
    descriptors: list[Mapping[str, Any]] = []
    for name, expected in lock.projections.items():
        projection = entries[name]
        try:
            index_descriptor = projection["resource_index"]["resource"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"{name} registered resource index is missing") from error
        _safe_relative(index_descriptor.get("path"), "registered resource index")
        validate_registered_projection_manifest(projection)
        if (
            projection["reference_space_id"] != lock.reference_space_id
            or projection["grid_id"] != lock.grid_id
            or projection["slice_count"] != expected.slice_count
            or tuple(projection["slice_shape"]) != expected.slice_shape
        ):
            raise ValueError(f"{name} projection identity differs from lock")
        descriptors.append(index_descriptor)
    for name in ("top", "swanson"):
        item = entries[name]
        if item.get("kind") != "static-regional-map" or not isinstance(
            item.get("fragment"), dict
        ):
            raise ValueError(f"{name} static projection differs")
        descriptors.append(item["fragment"]["resource"])
    try:
        license_descriptor = document["provenance"]["recipe"]["license_notice"][
            "resource"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("projection root license notice is missing") from error
    descriptors.append(license_descriptor)
    paths = [
        _safe_relative(item.get("path"), "projection resource").as_posix()
        for item in descriptors
    ]
    if len(paths) != len(set(paths)):
        raise ValueError("projection root resource paths are not unique")
    return entries, descriptors


def _inventory(root: Path, projection: dict[str, Any]) -> str:
    index_descriptor = projection["resource_index"]["resource"]
    index_path = _safe_relative(index_descriptor["path"], "registered resource index")
    index = json.loads(
        _decode_descriptor(root, index_descriptor, "registered resource index")
    )
    validate_registered_resource_index(index)
    paths = [index_path]
    paths.extend(
        _safe_relative(entry["resource"]["path"], "registered SVG pack")
        for entry in index["resources"]
    )
    entries = []
    for relative in sorted(paths, key=lambda value: value.as_posix()):
        data = (root / relative).read_bytes()
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return hashlib.sha256(
        json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def verify_materialized_registered_asset_set(
    lock: RegisteredAssetSet, root: str | Path
) -> MaterializedRegisteredAssets:
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    payload = manifest_path.read_bytes()
    if (
        len(payload) != lock.root_manifest.bytes
        or hashlib.sha256(payload).hexdigest() != lock.root_manifest.sha256
    ):
        raise ValueError("materialized root manifest differs from lock")
    document = json.loads(payload)
    entries, descriptors = _validate_root(lock, document)
    projections = {}
    expected_paths = {Path("manifest.json")}
    for name, expected in lock.projections.items():
        projection = entries[name]
        reader = RegisteredProjection(root, MappingProxyType(projection))
        reader.verify()
        if _inventory(root, projection) != expected.inventory_sha256:
            raise ValueError(f"{name} projection inventory differs from lock")
        projections[name] = reader
        index_descriptor = projection["resource_index"]["resource"]
        expected_paths.add(
            _safe_relative(index_descriptor["path"], "registered resource index")
        )
        index = json.loads(
            _decode_descriptor(root, index_descriptor, "registered resource index")
        )
        expected_paths.update(
            _safe_relative(item["resource"]["path"], "registered SVG pack")
            for item in index["resources"]
        )
    for descriptor in descriptors[3:]:
        _decode_descriptor(root, descriptor, "projection resource")
        expected_paths.add(_safe_relative(descriptor["path"], "projection resource"))
    actual_paths = {
        item.relative_to(root) for item in root.rglob("*") if item.is_file()
    }
    if actual_paths != expected_paths:
        raise ValueError("materialized projection file inventory differs")
    return MaterializedRegisteredAssets(
        root,
        document["pack_id"],
        _freeze(document),
        MappingProxyType(projections),
        len(actual_paths),
        sum((root / item).stat().st_size for item in actual_paths),
    )


def materialize_registered_asset_set(
    lock: RegisteredAssetSet, target: str | Path, *, timeout: float = 60
) -> MaterializedRegisteredAssets:
    """Atomically download, validate, and materialize the complete root graph."""
    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(
            f"registered asset destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        root_manifest = temporary / "manifest.json"
        _download(lock.root_manifest, root_manifest, timeout)
        root = json.loads(root_manifest.read_text(encoding="utf-8"))
        entries, _ = _validate_root(lock, root)
        for name, expected in lock.projections.items():
            projection = entries[name]
            index = projection["resource_index"]["resource"]
            resource, relative = _descriptor_resource(
                lock.root_manifest.url, index, "registered resource index"
            )
            _download(resource, temporary / relative, timeout)
            index_doc = json.loads(
                _decode_descriptor(temporary, index, "registered resource index")
            )
            validate_registered_resource_index(index_doc)
            if index_doc["projection_id"] != name:
                raise ValueError(f"{name} resource index projection differs")
            for item in index_doc["resources"]:
                resource, relative = _descriptor_resource(
                    lock.root_manifest.url, item["resource"], "registered SVG pack"
                )
                _download(resource, temporary / relative, timeout)
        for name in ("top", "swanson"):
            resource, relative = _descriptor_resource(
                lock.root_manifest.url,
                entries[name]["fragment"]["resource"],
                f"{name} static projection",
            )
            _download(resource, temporary / relative, timeout)
        license_resource = root["provenance"]["recipe"]["license_notice"]["resource"]
        resource, relative = _descriptor_resource(
            lock.root_manifest.url, license_resource, "projection license notice"
        )
        _download(resource, temporary / relative, timeout)
        verify_materialized_registered_asset_set(lock, temporary)
        temporary.rename(destination)
        return verify_materialized_registered_asset_set(lock, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
