"""A pinned nonredundant cut of source-native Allen display surfaces."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .asset_set import PinnedResource, _resource
from .surface_asset import (
    SurfaceAsset,
    SurfaceGeometry,
    load_surface_asset,
    materialize_surface_asset,
    parse_surface_asset,
)

_HEMISPHERES = "bilateral source meshes; unsigned Allen IDs"


@dataclass(frozen=True)
class RegionalSurfaceMember:
    """One bilateral source mesh and its official Allen ontology identity."""

    asset: SurfaceAsset
    acronym: str
    name: str
    color_hex: str
    ancestor_allen_ids: tuple[int, ...]


@dataclass(frozen=True)
class SurfaceCatalog:
    """Display context, without a claim of exhaustive anatomical coverage.

    Members share no ancestor/descendant pair. This is an ontology property,
    not a claim that independently authored surfaces have disjoint geometry.
    No signed hemisphere identity is inferred from the bilateral meshes.
    """

    catalog_id: str
    reference_space_id: str
    hemisphere_policy: str
    region_catalog: PinnedResource
    terms_url: str
    citation_url: str
    members: tuple[RegionalSurfaceMember, ...]


def parse_surface_catalog(value: dict) -> SurfaceCatalog:
    """Validate a compact ontology excerpt and its pinned surface members."""
    required = {
        "format",
        "schema_version",
        "catalog_id",
        "reference_space_id",
        "hemisphere_policy",
        "region_catalog",
        "terms_url",
        "citation_url",
        "ontology",
        "members",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("surface catalog fields differ")
    if value["format"] != "ibl-surface-catalog-v1" or value["schema_version"] != "1.0":
        raise ValueError("unsupported surface catalog format")
    if value["reference_space_id"] != "allen-ccf-2017":
        raise ValueError("unsupported surface catalog reference space")
    if value["hemisphere_policy"] != _HEMISPHERES:
        raise ValueError("unsupported surface catalog hemisphere policy")
    for field in ("catalog_id", "terms_url", "citation_url"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError(f"invalid surface catalog {field}")
    source = _resource(value["region_catalog"], "surface region catalog")
    if not isinstance(value["ontology"], list) or not value["ontology"]:
        raise ValueError("surface ontology must be a nonempty list")
    ontology = {}
    for row in value["ontology"]:
        if not isinstance(row, dict) or set(row) != {
            "allen_id",
            "parent_allen_id",
            "acronym",
            "name",
            "color_hex",
        }:
            raise ValueError("surface ontology fields differ")
        identity, parent = row["allen_id"], row["parent_allen_id"]
        if type(identity) is not int or identity <= 0 or identity in ontology:
            raise ValueError("invalid or duplicate surface ontology ID")
        if parent is not None and (type(parent) is not int or parent <= 0):
            raise ValueError("invalid surface ontology parent")
        if any(not isinstance(row[k], str) or not row[k] for k in ("acronym", "name")):
            raise ValueError("invalid surface ontology labels")
        if not isinstance(row["color_hex"], str) or not re.fullmatch(
            r"#[0-9a-f]{6}", row["color_hex"]
        ):
            raise ValueError("invalid surface ontology color")
        ontology[identity] = row
    if 997 not in ontology or ontology[997]["parent_allen_id"] is not None:
        raise ValueError("surface ontology requires Allen root 997")
    ancestors = {}
    for identity in ontology:
        chain, current = [], identity
        while current != 997:
            parent = ontology[current]["parent_allen_id"]
            if parent not in ontology or parent in chain or parent == identity:
                raise ValueError("surface ontology has missing parent or cycle")
            chain.append(parent)
            current = parent
        ancestors[identity] = tuple(chain)
    if not isinstance(value["members"], list) or not value["members"]:
        raise ValueError("surface catalog members must be a nonempty list")
    members, ids = [], set()
    for raw in value["members"]:
        asset = parse_surface_asset(raw)
        identity = asset.source_allen_id
        if (
            asset.role != "regional-context"
            or asset.reference_space_id != value["reference_space_id"]
        ):
            raise ValueError("surface member role or reference space differs")
        if identity not in ontology or identity in ids:
            raise ValueError("unknown or duplicate surface member ID")
        if any(i in ancestors[identity] or identity in ancestors[i] for i in ids):
            raise ValueError("surface catalog contains ancestor/descendant overlap")
        ids.add(identity)
        row = ontology[identity]
        members.append(
            RegionalSurfaceMember(
                asset,
                row["acronym"],
                row["name"],
                row["color_hex"],
                ancestors[identity],
            )
        )
    used = ids | {i for member in members for i in member.ancestor_allen_ids}
    if used != set(ontology):
        raise ValueError("surface ontology contains unrelated rows")
    return SurfaceCatalog(
        value["catalog_id"],
        value["reference_space_id"],
        _HEMISPHERES,
        source,
        value["terms_url"],
        value["citation_url"],
        tuple(members),
    )


def bundled_surface_catalog() -> SurfaceCatalog:
    """Return the shared, explicitly incomplete major-structure context cut."""
    resource = files("ibl_anatomy.asset_sets").joinpath("allen-major-context.json")
    return parse_surface_catalog(json.loads(resource.read_text(encoding="utf-8")))


def load_surface_catalog(
    path: str | Path,
    catalog: SurfaceCatalog | None = None,
) -> tuple[SurfaceGeometry, ...]:
    """Verify every local member at ``path/<Allen ID>/surface.obj`` offline."""
    catalog = bundled_surface_catalog() if catalog is None else catalog
    return tuple(
        load_surface_asset(Path(path) / str(member.asset.source_allen_id), member.asset)
        for member in catalog.members
    )


def materialize_surface_catalog(
    target: str | Path,
    catalog: SurfaceCatalog | None = None,
    *,
    source_directory: str | Path | None = None,
    timeout: float = 60,
) -> tuple[SurfaceGeometry, ...]:
    """Atomically prepare the complete cut; local sources are ``<Allen ID>.obj``.

    Downloads occur only here and only from each member's hash-pinned URL.
    The destination must be new. Failure removes the partial bundle.
    """
    catalog = bundled_surface_catalog() if catalog is None else catalog
    destination = Path(target).resolve()
    if destination.exists():
        raise FileExistsError(
            f"surface catalog destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        for member in catalog.members:
            identity = str(member.asset.source_allen_id)
            source = (
                None
                if source_directory is None
                else Path(source_directory) / f"{identity}.obj"
            )
            materialize_surface_asset(
                temporary / identity, member.asset, source_path=source, timeout=timeout
            )
        geometry = load_surface_catalog(temporary, catalog)
        temporary.rename(destination)
        return geometry
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
