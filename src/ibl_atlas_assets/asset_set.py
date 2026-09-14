"""Pinned, renderer-neutral atlas asset sets for local consumers."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from .mesh_pack import MeshGeometry, MeshPack, open_mesh_pack
from .regions import AtlasRegionCatalog, open_region_catalog


@dataclass(frozen=True)
class PinnedResource:
    """One immutable remote resource."""

    url: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class AtlasAssetSet:
    """A pinned mesh-pack root and matching region catalog."""

    asset_set_id: str
    reference_space_id: str
    mesh_manifest: PinnedResource
    region_catalog: PinnedResource
    expected_pack_id: str
    expected_geometry_sha256: str
    expected_vertices: int
    expected_triangles: int
    expected_components: int
    expected_presentations: int
    expected_vertex_presentations_sha256: str
    expected_face_presentations_sha256: str


@dataclass(frozen=True)
class MaterializedAtlasAssets:
    """A verified local asset graph ready for a renderer adapter."""

    root: Path
    mesh_pack: MeshPack
    geometry: MeshGeometry
    regions: AtlasRegionCatalog


def _resource(value: Any, label: str) -> PinnedResource:
    if not isinstance(value, dict) or set(value) != {"url", "bytes", "sha256"}:
        raise ValueError(f"{label} must contain url, bytes and sha256")
    url, byte_count, digest = value["url"], value["bytes"], value["sha256"]
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme not in {
        "file",
        "http",
        "https",
    }:
        raise ValueError(f"{label} URL is invalid")
    if (
        not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 1
    ):
        raise ValueError(f"{label} byte count is invalid")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} SHA-256 is invalid")
    return PinnedResource(url, byte_count, digest)


def parse_asset_set(value: Any) -> AtlasAssetSet:
    """Validate an ``ibl-atlas-asset-set-v1`` document."""

    if not isinstance(value, dict):
        raise TypeError("atlas asset set must be an object")
    required = {
        "format",
        "schema_version",
        "asset_set_id",
        "reference_space_id",
        "mesh_manifest",
        "region_catalog",
        "expectations",
    }
    if set(value) != required:
        raise ValueError("atlas asset set fields differ")
    if value["format"] != "ibl-atlas-asset-set-v1" or value["schema_version"] != "1.0":
        raise ValueError("unsupported atlas asset set format")
    expectations = value["expectations"]
    expected_fields = {
        "pack_id",
        "geometry_sha256",
        "vertices",
        "triangles",
        "components",
        "presentations",
        "vertex_presentations_sha256",
        "face_presentations_sha256",
    }
    if not isinstance(expectations, dict) or set(expectations) != expected_fields:
        raise ValueError("atlas asset set expectations differ")
    counts = [
        expectations[name]
        for name in ("vertices", "triangles", "components", "presentations")
    ]
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 1
        for count in counts
    ):
        raise ValueError("atlas asset set expected counts are invalid")
    for name in (
        "geometry_sha256",
        "vertex_presentations_sha256",
        "face_presentations_sha256",
    ):
        digest = expectations[name]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"atlas asset set expected {name} is invalid")
    for label in ("asset_set_id", "reference_space_id"):
        if not isinstance(value[label], str) or not value[label]:
            raise ValueError(f"atlas asset set {label} is invalid")
    return AtlasAssetSet(
        asset_set_id=value["asset_set_id"],
        reference_space_id=value["reference_space_id"],
        mesh_manifest=_resource(value["mesh_manifest"], "mesh manifest"),
        region_catalog=_resource(value["region_catalog"], "region catalog"),
        expected_pack_id=expectations["pack_id"],
        expected_geometry_sha256=expectations["geometry_sha256"],
        expected_vertices=expectations["vertices"],
        expected_triangles=expectations["triangles"],
        expected_components=expectations["components"],
        expected_presentations=expectations["presentations"],
        expected_vertex_presentations_sha256=expectations[
            "vertex_presentations_sha256"
        ],
        expected_face_presentations_sha256=expectations["face_presentations_sha256"],
    )


def open_asset_set(path: str | Path) -> AtlasAssetSet:
    """Read and validate an asset-set lock document."""

    return parse_asset_set(json.loads(Path(path).read_text(encoding="utf-8")))


def bundled_asset_set(name: str = "d070") -> AtlasAssetSet:
    """Open a lock document shipped with this package."""

    if not name or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in name
    ):
        raise ValueError("asset set name is invalid")
    resource = files("ibl_atlas_assets.asset_sets").joinpath(f"{name}.json")
    return parse_asset_set(json.loads(resource.read_text(encoding="utf-8")))


def _download(resource: PinnedResource, destination: Path, *, timeout: float) -> None:
    request = urllib.request.Request(
        resource.url, headers={"User-Agent": "ibl-atlas-assets/0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = response.read(resource.bytes + 1)
    if len(payload) != resource.bytes:
        raise ValueError(f"downloaded byte length differs: {resource.url}")
    if hashlib.sha256(payload).hexdigest() != resource.sha256:
        raise ValueError(f"downloaded SHA-256 differs: {resource.url}")
    destination.write_bytes(payload)


def _descriptor_resource(base_url: str, descriptor: Any) -> PinnedResource:
    if not isinstance(descriptor, dict):
        raise ValueError("mesh resource descriptor is invalid")
    return PinnedResource(
        urllib.parse.urljoin(base_url, descriptor["path"]),
        descriptor["bytes"],
        descriptor["sha256"],
    )


def materialize_asset_set(
    asset_set: AtlasAssetSet, target: str | Path, *, timeout: float = 60
) -> MaterializedAtlasAssets:
    """Download a pinned asset graph atomically and verify all semantic contracts."""

    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(f"atlas asset destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        pack_root = temporary / "mesh-pack"
        pack_root.mkdir()
        _download(asset_set.mesh_manifest, pack_root / "manifest.json", timeout=timeout)
        manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
        descriptors = [lod["resource"] for lod in manifest.get("lods", [])]
        descriptors.append(manifest.get("validation", {}).get("report"))
        for descriptor in descriptors:
            resource = _descriptor_resource(asset_set.mesh_manifest.url, descriptor)
            relative = Path(descriptor["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("mesh resource escapes materialized pack")
            output = pack_root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            _download(resource, output, timeout=timeout)
        _download(asset_set.region_catalog, temporary / "regions.json", timeout=timeout)
        verify_materialized_asset_set(asset_set, temporary)
        temporary.rename(destination)
        return verify_materialized_asset_set(asset_set, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_materialized_asset_set(
    asset_set: AtlasAssetSet, root: str | Path
) -> MaterializedAtlasAssets:
    """Verify a local graph against its lock and cross-asset semantic invariants."""

    root = Path(root).resolve()
    manifest_path = root / "mesh-pack" / "manifest.json"
    manifest_payload = manifest_path.read_bytes()
    if len(manifest_payload) != asset_set.mesh_manifest.bytes:
        raise ValueError("mesh manifest byte length differs from asset set")
    if hashlib.sha256(manifest_payload).hexdigest() != asset_set.mesh_manifest.sha256:
        raise ValueError("mesh manifest SHA-256 differs from asset set")
    pack = open_mesh_pack(manifest_path)
    pack.verify()
    geometry = pack.load_geometry()
    regions = open_region_catalog(
        root / "regions.json", sha256=asset_set.region_catalog.sha256
    )
    manifest = pack.manifest
    lod = next(
        item for item in manifest["lods"] if item["id"] == manifest["default_lod_id"]
    )
    actual = (
        manifest["pack_id"],
        lod["resource"]["sha256"],
        len(geometry.positions),
        len(geometry.indices) // 3,
        len(geometry.ranges),
        len(geometry.presentations),
    )
    expected = (
        asset_set.expected_pack_id,
        asset_set.expected_geometry_sha256,
        asset_set.expected_vertices,
        asset_set.expected_triangles,
        asset_set.expected_components,
        asset_set.expected_presentations,
    )
    if actual != expected:
        raise ValueError("materialized atlas asset expectations differ")
    if (
        geometry.reference_space != asset_set.reference_space_id
        or regions.reference_space_id != asset_set.reference_space_id
    ):
        raise ValueError("materialized atlas reference spaces differ")
    for mapping in ("allen", "beryl", "cosmos"):
        catalog_ids = {region.atlas_id for region in regions.physical(mapping)}
        missing = {
            presentation["mappings"][mapping]
            for presentation in geometry.presentations
            if presentation["mappings"][mapping] is not None
            and presentation["mappings"][mapping] not in catalog_ids
        }
        if missing:
            raise ValueError(
                f"mesh {mapping} presentations are absent from region catalog"
            )
    vertex_presentations = geometry.vertex_presentation_ids()
    face_presentations = geometry.face_presentation_ids()
    if (
        hashlib.sha256(vertex_presentations.tobytes(order="C")).hexdigest()
        != asset_set.expected_vertex_presentations_sha256
    ):
        raise ValueError("mesh vertex presentation semantics differ from asset set")
    if (
        hashlib.sha256(face_presentations.tobytes(order="C")).hexdigest()
        != asset_set.expected_face_presentations_sha256
    ):
        raise ValueError("mesh face presentation semantics differ from asset set")
    return MaterializedAtlasAssets(root, pack, geometry, regions)
