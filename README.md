# IBL Atlas Assets

This repository is an experimental home for renderer-neutral Allen atlas
assets used by IBL applications.

The immediate goal is deliberately narrow: determine whether the existing
`atlas-mesh-pack-v1` work in `ephys-atlas-web-v2` can be consumed cleanly by an
independent Python package and by the Datoviz-based native viewer. The result of
that experiment will determine the repository's permanent scope.

This is not currently a released package or the authority for scientific atlas
semantics. [`iblatlas`](https://github.com/int-brain-lab/iblatlas) remains the
scientific authority for ontology, mappings, coordinates, labels, trajectories,
and atlas computations.

## Start here

- [Project hypothesis and boundaries](docs/PROJECT.md)
- [Immediate cross-repository steps](docs/NEXT_STEPS.md)
- [Audited source inventory](docs/SOURCE_INVENTORY.md)
- [Spike 001: independent mesh-pack reader](docs/SPIKE_001_MESH_PACK_READER.md)
- [Deferred directions and gallery ideas](docs/FUTURE_DIRECTIONS.md)

## Current status

Spike 001 now provides an independent, offline Python reader for raw EAM3 `atlas-mesh-pack-v1` packs. It validates the bundled JSON Schema, the complete immutable resource graph, encoded and decoded byte sizes, SHA-256 identities, signed presentation metadata, component ranges, and decoded geometry before returning owned contiguous NumPy arrays.

The project remains in an evidence-gathering phase. The reader currently rejects `meshopt-quantized-v1`; persistent runtime caching, builders, TypeScript packaging, and renderer integration remain outside its scope.

The package now ships an immutable lock for the published D070 Allen CCF 2017 surface and the exact matching region catalog. The lock contains URLs, sizes, SHA-256 identities, decoded inventory counts, and renderer-neutral vertex/face presentation fingerprints. The numeric mesh bytes remain in the established immutable atlas origin rather than being copied into this Git repository.

```python
from ibl_atlas_assets import bundled_asset_set, materialize_asset_set

assets = materialize_asset_set(bundled_asset_set("d070"), "build/atlas-d070")
print(assets.geometry.positions.shape, assets.regions.reference_space_id)
```

Materialization creates a new destination atomically, verifies every downloaded byte before decoding, validates the complete mesh graph and region catalog, checks their common reference space and mapped IDs, and proves that every vertex and triangle resolves to the pinned bilateral presentation fingerprint. It does not maintain a cache, overwrite a destination, or select a renderer.

## Development

```sh
uv sync --extra test
uv run pytest -q
uv build
```

## Read a local mesh pack

```python
from ibl_atlas_assets import open_mesh_pack

pack = open_mesh_pack("path/to/pack/manifest.json")
pack.verify()
geometry = pack.load_geometry()

print(geometry.positions.shape, geometry.positions.dtype)
print(geometry.indices.shape, geometry.indices.dtype)
print(geometry.reference_space, geometry.coordinate_system)
print(geometry.vertex_presentation_ids().shape)
print(geometry.face_presentation_ids().shape)
```

`open_mesh_pack()` accepts a configurable decoded-resource size limit and defaults to 2 GiB. Decoded EAM3 positions are already in the manifest's declared world axes and micrometre units. `source_to_world_um` records the source-to-compiled transform for provenance and must not be applied to decoded positions again. The reader never applies an atlas-to-renderer display transform.

## Read the Allen region catalog

`open_region_catalog()` is a strict reader for the browser's pinned
`ibl-atlas-regions-v1` document. It checks the schema, signed physical rows,
parent closure/depth, matching left/right identities, mapping fields, and
reference-space/provenance identity. The reader deliberately keeps three
explicit views: `physical(mapping)` preserves all signed rows, `left(mapping)`
is the canonical signed left tree (plus void), and `logical(mapping)` selects
one hemisphere-independent/right row per absolute ID.

```python
from ibl_atlas_assets import open_region_catalog

catalog = open_region_catalog("regions.json", sha256="...")
for region in catalog.left("allen"):
    print(region.acronym, region.logical_id, region.color_hex)
```

This is a consumer-side contract spike: the existing web builder remains the
authoritative producer and is intentionally not moved here.
