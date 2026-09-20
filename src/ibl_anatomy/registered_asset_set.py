"""Pinned atlas-projection-pack graphs for registered anatomy consumers."""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .registered_slices import RegisteredProjection
from .schema import validate_registered_projection_manifest, validate_registered_resource_index


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
    projections: dict[str, RegisteredProjectionExpectation]
    annotation_source: RegisteredResource
    lut_recipe: dict[str, Any]
    terms_url: str
    citation_url: str
    citation_policy_url: str

@dataclass(frozen=True)
class MaterializedRegisteredAssets:
    root: Path
    pack_id: str
    projections: dict[str, RegisteredProjection]


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
    required = {"format", "schema_version", "asset_set_id", "reference_space_id", "grid_id", "root_pack_id", "root_manifest", "projections", "provenance"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("registered asset-set fields differ")
    if value["format"] != "ibl-atlas-registered-asset-set-v1" or value["schema_version"] != "1.0":
        raise ValueError("unsupported registered asset-set format")
    projections = value["projections"]
    if not isinstance(projections, dict) or set(projections) != {"coronal", "sagittal", "horizontal"}:
        raise ValueError("registered asset-set projections differ")
    parsed = {}
    for name, item in projections.items():
        if not isinstance(item, dict) or set(item) != {"slice_count", "slice_shape", "inventory_sha256"}:
            raise ValueError(f"{name} projection expectation fields differ")
        shape, digest = item["slice_shape"], item["inventory_sha256"]
        if not isinstance(item["slice_count"], int) or item["slice_count"] < 1 or not isinstance(shape, list) or len(shape) != 2 or any(not isinstance(v, int) or v < 1 for v in shape):
            raise ValueError(f"{name} projection dimensions are invalid")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"{name} inventory SHA-256 is invalid")
        parsed[name] = RegisteredProjectionExpectation(item["slice_count"], tuple(shape), digest)
    provenance = value["provenance"]
    fields = {"annotation_source", "lut_recipe", "terms_url", "citation_url", "citation_policy_url"}
    if not isinstance(provenance, dict) or set(provenance) != fields or not isinstance(provenance["lut_recipe"], dict) or set(provenance["lut_recipe"]) != {"path", "bytes", "sha256", "producer", "iblatlas_commit"}:
        raise ValueError("registered asset-set provenance differs")
    for key in ("terms_url", "citation_url", "citation_policy_url"):
        if not isinstance(provenance[key], str) or urllib.parse.urlparse(provenance[key]).scheme not in {"http", "https"}:
            raise ValueError(f"{key} is invalid")
    return RegisteredAssetSet(value["asset_set_id"], value["reference_space_id"], value["grid_id"], value["root_pack_id"], _resource(value["root_manifest"], "root manifest"), parsed, _resource(provenance["annotation_source"], "annotation source"), provenance["lut_recipe"], provenance["terms_url"], provenance["citation_url"], provenance["citation_policy_url"])


def open_registered_asset_set(path: str | Path) -> RegisteredAssetSet:
    return parse_registered_asset_set(json.loads(Path(path).read_text(encoding="utf-8")))


def bundled_registered_asset_set(name: str = "allen-ccf-2017-10um") -> RegisteredAssetSet:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("asset set name is invalid")
    resource = files("ibl_anatomy.asset_sets").joinpath(f"{name}.json")
    return parse_registered_asset_set(json.loads(resource.read_text(encoding="utf-8")))


def _download(resource: RegisteredResource, destination: Path, timeout: float) -> None:
    with urllib.request.urlopen(resource.url, timeout=timeout) as response:  # noqa: S310
        payload = response.read(resource.bytes + 1)
    if len(payload) != resource.bytes or hashlib.sha256(payload).hexdigest() != resource.sha256:
        raise ValueError(f"resource integrity mismatch: {resource.url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _inventory(root: Path, projection: dict[str, Any]) -> str:
    paths = [projection["resource_index"]["resource"]["path"]]
    index = json.loads(gzip.decompress((root / paths[0]).read_bytes()))
    paths.extend(entry["resource"]["path"] for entry in index["resources"])
    entries = []
    for relative in sorted(paths):
        data = (root / relative).read_bytes()
        entries.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return hashlib.sha256(json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()).hexdigest()

def verify_materialized_registered_asset_set(lock: RegisteredAssetSet, root: str | Path) -> MaterializedRegisteredAssets:
    root = Path(root).resolve()
    document = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if document.get("pack_id") != lock.root_pack_id or document.get("format") != "atlas-projection-pack-v1":
        raise ValueError("materialized root identity differs from lock")
    entries = {item["id"]: item for item in document["projections"]}
    projections = {}
    for name, expected in lock.projections.items():
        projection = entries[name]
        reader = RegisteredProjection(root, MappingProxyType(projection))
        reader.verify()
        if _inventory(root, projection) != expected.inventory_sha256:
            raise ValueError(f"{name} projection inventory differs from lock")
        projections[name] = reader
    return MaterializedRegisteredAssets(root, document["pack_id"], projections)


def materialize_registered_asset_set(lock: RegisteredAssetSet, target: str | Path, *, timeout: float = 60) -> MaterializedRegisteredAssets:
    """Atomically download, validate, and materialize the complete root graph."""
    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(f"registered asset destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        root_manifest = temporary / "manifest.json"
        _download(lock.root_manifest, root_manifest, timeout)
        root = json.loads(root_manifest.read_text(encoding="utf-8"))
        if root.get("format") != "atlas-projection-pack-v1" or root.get("pack_id") != lock.root_pack_id or root.get("reference_space_id") != lock.reference_space_id or set(root.get("mappings", [])) != {"allen", "beryl", "cosmos"}:
            raise ValueError("projection root identity differs from lock")
        entries = {item["id"]: item for item in root.get("projections", [])}
        if set(entries) != {"coronal", "sagittal", "horizontal", "top", "swanson"}:
            raise ValueError("projection root entries differ")
        for name, expected in lock.projections.items():
            projection = entries[name]
            validate_registered_projection_manifest(projection)
            if projection["reference_space_id"] != lock.reference_space_id or projection["grid_id"] != lock.grid_id or projection["slice_count"] != expected.slice_count or tuple(projection["slice_shape"]) != expected.slice_shape:
                raise ValueError(f"{name} projection identity differs from lock")
            index = projection["resource_index"]["resource"]
            _download(RegisteredResource(urllib.parse.urljoin(lock.root_manifest.url, index["path"]), index["bytes"], index["sha256"]), temporary / index["path"], timeout)
            index_doc = json.loads(gzip.decompress((temporary / index["path"]).read_bytes()))
            validate_registered_resource_index(index_doc)
            for item in index_doc["resources"]:
                resource = item["resource"]
                _download(RegisteredResource(urllib.parse.urljoin(lock.root_manifest.url, resource["path"]), resource["bytes"], resource["sha256"]), temporary / resource["path"], timeout)
            reader = RegisteredProjection(temporary, MappingProxyType(projection))
            reader.verify()
            if _inventory(temporary, projection) != expected.inventory_sha256:
                raise ValueError(f"{name} projection inventory differs from lock")
        for name in ("top", "swanson"):
            resource = entries[name]["fragment"]["resource"]
            _download(RegisteredResource(urllib.parse.urljoin(lock.root_manifest.url, resource["path"]), resource["bytes"], resource["sha256"]), temporary / resource["path"], timeout)
        license_resource = root["provenance"]["recipe"]["license_notice"]["resource"]
        _download(RegisteredResource(urllib.parse.urljoin(lock.root_manifest.url, license_resource["path"]), license_resource["bytes"], license_resource["sha256"]), temporary / license_resource["path"], timeout)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(destination)
        return verify_materialized_registered_asset_set(lock, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
