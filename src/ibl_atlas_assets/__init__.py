"""Renderer-neutral readers for versioned IBL atlas assets."""

from .mesh_pack import MeshComponentRange, MeshGeometry, MeshPack, open_mesh_pack
from .regions import (
    AtlasRegion,
    AtlasRegionCatalog,
    open_region_catalog,
    parse_region_catalog,
)

__all__ = [
    "AtlasRegion",
    "AtlasRegionCatalog",
    "MeshComponentRange",
    "MeshGeometry",
    "MeshPack",
    "open_mesh_pack",
    "open_region_catalog",
    "parse_region_catalog",
]

__version__ = "0.0.0"
