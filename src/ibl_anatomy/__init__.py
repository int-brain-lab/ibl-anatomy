"""Portable contracts and readers for versioned IBL reference anatomy."""

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
from .intensity_blocks import (
    IntensityBlockPack,
    IntensityCacheInfo,
    IntensityGrid,
    IntensitySection,
    open_intensity_block_pack,
)
from .mesh_pack import MeshComponentRange, MeshGeometry, MeshPack, open_mesh_pack
from .regions import (
    AtlasRegion,
    AtlasRegionCatalog,
    open_region_catalog,
    parse_region_catalog,
)
from .registered_slices import (
    AnatomyPack,
    IndexedSvgPack,
    RegisteredProjection,
    RegisteredSlice,
    RegisteredSlicePath,
    open_anatomy_pack,
    open_registered_projection,
)
from .registered_asset_set import (
    RegisteredAssetSet,
    RegisteredProjectionExpectation,
    RegisteredResource,
    materialize_registered_asset_set,
    bundled_registered_asset_set,
    open_registered_asset_set,
    parse_registered_asset_set,
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
    "AnatomyPack",
    "AtlasRegion",
    "AtlasRegionCatalog",
    "AtlasVolumeGrid",
    "AtlasVolumePack",
    "AtlasVolumeSlice",
    "AtlasVolumes",
    "IndexedSvgPack",
    "IntensityBlockPack",
    "IntensityCacheInfo",
    "IntensityGrid",
    "IntensitySection",
    "MaterializedAtlasAssets",
    "MeshComponentRange",
    "MeshGeometry",
    "MeshPack",
    "PinnedResource",
    "RegisteredProjection",
    "RegisteredAssetSet",
    "RegisteredProjectionExpectation",
    "RegisteredResource",
    "bundled_registered_asset_set",
    "RegisteredSlice",
    "RegisteredSlicePath",
    "bundled_asset_set",
    "materialize_asset_set",
    "open_anatomy_pack",
    "open_asset_set",
    "open_intensity_block_pack",
    "open_mesh_pack",
    "open_region_catalog",
    "open_registered_projection",
    "open_registered_asset_set",
    "open_volume_pack",
    "parse_asset_set",
    "parse_region_catalog",
    "parse_registered_asset_set",
    "materialize_registered_asset_set",
    "verify_materialized_asset_set",
]

__version__ = "0.1.0"
