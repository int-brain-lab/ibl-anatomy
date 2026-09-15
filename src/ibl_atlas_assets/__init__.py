"""Renderer-neutral readers for versioned IBL atlas assets."""

from .asset_set import (
    AtlasAssetSet,
    MaterializedAtlasAssets,
    PinnedResource,
    bundled_asset_set,
    materialize_asset_set,
    open_asset_set,
    parse_asset_set,
    verify_materialized_asset_set,
)
from .mesh_pack import MeshComponentRange, MeshGeometry, MeshPack, open_mesh_pack
from .regions import (
    AtlasRegion,
    AtlasRegionCatalog,
    open_region_catalog,
    parse_region_catalog,
)
from .registered_slices import (
    IndexedSvgPack,
    RegisteredProjection,
    RegisteredSlice,
    RegisteredSlicePath,
    open_registered_projection,
)
from .volume_pack import (
    AtlasVolumeGrid,
    AtlasVolumePack,
    AtlasVolumes,
    AtlasVolumeSlice,
    open_volume_pack,
)

__all__ = [
    "AtlasAssetSet",
    "AtlasRegion",
    "AtlasRegionCatalog",
    "AtlasVolumeGrid",
    "AtlasVolumePack",
    "AtlasVolumeSlice",
    "AtlasVolumes",
    "IndexedSvgPack",
    "MaterializedAtlasAssets",
    "MeshComponentRange",
    "MeshGeometry",
    "MeshPack",
    "PinnedResource",
    "RegisteredProjection",
    "RegisteredSlice",
    "RegisteredSlicePath",
    "bundled_asset_set",
    "materialize_asset_set",
    "open_asset_set",
    "open_mesh_pack",
    "open_region_catalog",
    "open_registered_projection",
    "open_volume_pack",
    "parse_asset_set",
    "parse_region_catalog",
    "verify_materialized_asset_set",
]

__version__ = "0.0.0"
