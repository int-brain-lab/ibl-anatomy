"""Pinned, renderer-neutral registered anatomy projection asset graphs."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .registered_slices import RegisteredProjection, open_registered_projection
from .schema import validate_registered_projection_manifest


@dataclass(frozen=True)
class RegisteredResource:
    """One immutable manifest or resource in a registered graph."""

    url: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class RegisteredProjectionExpectation:
    """Expected identity for one registered projection."""

    manifest: RegisteredResource
    slice_count: int
    slice_shape: tuple[int, int]
    inventory_sha256: str


@dataclass(frozen=True)
class RegisteredAssetSet:
    """Strict lock for three registered projections and their provenance."""

    asset_set_id: str
    reference_space_id: str
    grid_id: str
    projections: dict[str, RegisteredProjectionExpectation]
    annotation_source: RegisteredResource
    lut_recipe: str
    terms_url: str
    citation_url: str


def _resource(value: Any, label: str) -> RegisteredResource:
    if not isinstance(value, dict) or set(value) != {"url", "bytes", "sha256"}:
        raise ValueError(f"{label} must contain url, bytes and sha256")
    url, size, digest = value["url"], value["bytes"], value["sha256"]
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme not in {"file", "http", "https"}:
        raise ValueError(f"{label} URL is invalid")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError(f"{label} byte count is invalid")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError(f"{label} SHA-256 is invalid")
    return RegisteredResource(url, size, digest)


def parse_registered_asset_set(value: Any) -> RegisteredAssetSet:
    """Parse a strict ``ibl-atlas-registered-asset-set-v1`` lock."""
    required = {"format", "schema_version", "asset_set_id", "reference_space_id", "grid_id", "projections", "provenance"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("registered asset-set fields differ")
    if value["format"] != "ibl-atlas-registered-asset-set-v1" or value["schema_version"] != "1.0":
        raise ValueError("unsupported registered asset-set format")
    if any(not isinstance(value[key], str) or not value[key] for key in ("asset_set_id", "reference_space_id", "grid_id")):
        raise ValueError("registered asset-set identity is invalid")
    projections = value["projections"]
    if not isinstance(projections, dict) or set(projections) != {"coronal", "sagittal", "horizontal"}:
        raise ValueError("registered asset-set projections differ")
    parsed: dict[str, RegisteredProjectionExpectation] = {}
    for name, item in projections.items():
        fields = {"manifest", "slice_count", "slice_shape", "inventory_sha256"}
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError(f"{name} projection expectation fields differ")
        shape = item["slice_shape"]
        if not isinstance(item["slice_count"], int) or item["slice_count"] < 1 or not isinstance(shape, list) or len(shape) != 2 or any(not isinstance(v, int) or v < 1 for v in shape):
            raise ValueError(f"{name} projection dimensions are invalid")
        digest = item["inventory_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"{name} inventory SHA-256 is invalid")
        parsed[name] = RegisteredProjectionExpectation(_resource(item["manifest"], f"{name} manifest"), item["slice_count"], tuple(shape), digest)
    provenance = value["provenance"]
    fields = {"annotation_source", "lut_recipe", "terms_url", "citation_url"}
    if not isinstance(provenance, dict) or set(provenance) != fields:
        raise ValueError("registered asset-set provenance fields differ")
    if not isinstance(provenance["lut_recipe"], str) or not provenance["lut_recipe"]:
        raise ValueError("LUT recipe is invalid")
    for key in ("terms_url", "citation_url"):
        if not isinstance(provenance[key], str) or urllib.parse.urlparse(provenance[key]).scheme not in {"http", "https"}:
            raise ValueError(f"{key} is invalid")
    return RegisteredAssetSet(value["asset_set_id"], value["reference_space_id"], value["grid_id"], parsed, _resource(provenance["annotation_source"], "annotation source"), provenance["lut_recipe"], provenance["terms_url"], provenance["citation_url"])


def open_registered_asset_set(path: str | Path) -> RegisteredAssetSet:
    return parse_registered_asset_set(json.loads(Path(path).read_text(encoding="utf-8")))


def _download(resource: RegisteredResource, destination: Path, timeout: float) -> None:
    with urllib.request.urlopen(resource.url, timeout=timeout) as response:  # noqa: S310
        payload = response.read(resource.bytes + 1)
    if len(payload) != resource.bytes or hashlib.sha256(payload).hexdigest() != resource.sha256:
        raise ValueError(f"resource integrity mismatch: {resource.url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _inventory(root: Path, projection: RegisteredProjection) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            data = path.read_bytes()
            entries.append({"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return hashlib.sha256(json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def materialize_registered_asset_set(lock: RegisteredAssetSet, target: str | Path, *, timeout: float = 60) -> Path:
    """Download and verify the complete graph atomically."""
    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(f"registered asset destination already exists: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for name, expected in lock.projections.items():
            root = temporary / name
            manifest_path = root / "manifest.json"
            _download(expected.manifest, manifest_path, timeout)
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_registered_projection_manifest(document)
            if document["id"] != name or document["reference_space_id"] != lock.reference_space_id or document["grid_id"] != lock.grid_id:
                raise ValueError(f"{name} projection identity differs from lock")
            if document["slice_count"] != expected.slice_count or tuple(document["slice_shape"]) != expected.slice_shape:
                raise ValueError(f"{name} projection dimensions differ from lock")
            index = document["resource_index"]["resource"]
            index_path = root / index["path"]
            _download(RegisteredResource(urllib.parse.urljoin(expected.manifest.url, index["path"]), index["bytes"], index["sha256"]), index_path, timeout)
            index_doc = json.loads(__import__("gzip").decompress(index_path.read_bytes()))
            for entry in index_doc["resources"]:
                resource = entry["resource"]
                _download(RegisteredResource(urllib.parse.urljoin(expected.manifest.url, resource["path"]), resource["bytes"], resource["sha256"]), root / resource["path"], timeout)
            projection = open_registered_projection(root)
            projection.verify()
            if _inventory(root, projection) != expected.inventory_sha256:
                raise ValueError(f"{name} projection inventory differs from lock")
        temporary.rename(destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
