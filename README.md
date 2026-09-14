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

The project remains in an evidence-gathering phase. The reader currently rejects `meshopt-quantized-v1`; HTTP fetching, persistent caching, builders, TypeScript, real atlas asset publication, and renderer integration remain deliberately outside the first spike.

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
```

`open_mesh_pack()` accepts a configurable decoded-resource size limit and defaults to 2 GiB. It never applies an atlas-to-renderer coordinate transform.

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
