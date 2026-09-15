# IBL Anatomy

`ibl-anatomy` publishes versioned, renderer-neutral contracts and immutable assets for shared IBL reference anatomy. It includes region catalogs, geometry, registered projections, anatomical volumes, readers, validators, builders, provenance records, and conformance fixtures.

[`iblatlas`](https://github.com/int-brain-lab/iblatlas) remains the scientific authority for ontology, mappings, coordinates, labels, trajectories, and atlas computations. This repository records pinned `iblatlas` versions or commits and exact input hashes; it does not copy or replace that scientific logic.

Experimental measurements such as AGEA or MERFISH, BWM/session/unit data, scientific analysis, application state, rendering, and browser/native UI are outside this repository's scope. Consumers retain their own idiomatic runtime adapters and presentation code.

## Start here

- [Project hypothesis and boundaries](docs/PROJECT.md)
- [Immediate cross-repository steps](docs/NEXT_STEPS.md)
- [Audited source inventory](docs/SOURCE_INVENTORY.md)
- [Spike 001: independent mesh-pack reader](docs/SPIKE_001_MESH_PACK_READER.md)
- [Spike 002: registered Allen atlas volumes](docs/SPIKE_002_ATLAS_VOLUME_PACK.md)
- [Spike 003: 10-um intensity block transport](docs/SPIKE_003_INTENSITY_BLOCK_TRANSPORT.md)
- [Deferred directions and gallery ideas](docs/FUTURE_DIRECTIONS.md)
- [Contract and compatibility policy](docs/CONTRACTS.md)

## Current status

Spike 001 now provides an independent, offline Python reader for raw EAM3 `atlas-mesh-pack-v1` packs. It validates the bundled JSON Schema, the complete immutable resource graph, encoded and decoded byte sizes, SHA-256 identities, signed presentation metadata, component ranges, and decoded geometry before returning owned contiguous NumPy arrays.

The project remains in an evidence-gathering phase. The reader currently rejects `meshopt-quantized-v1`; persistent runtime caching, builders, TypeScript packaging, and renderer integration remain outside its scope.

The package now ships an immutable lock for the published D070 Allen CCF 2017 surface and the exact matching region catalog. The lock contains URLs, sizes, SHA-256 identities, decoded inventory counts, and renderer-neutral vertex/face presentation fingerprints. The numeric mesh bytes remain in the established immutable atlas origin rather than being copied into this Git repository.

```python
from ibl_anatomy import bundled_asset_set, materialize_asset_set

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
from ibl_anatomy import open_mesh_pack

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
from ibl_anatomy import open_region_catalog

catalog = open_region_catalog("regions.json", sha256="...")
for region in catalog.left("allen"):
    print(region.acronym, region.logical_id, region.color_hex)
```

`catalog.map_allen_ids(ids, mapping)` maps a batch of signed Allen identities. It returns `None`
when the legacy crosswalk uses root as the absence marker for a non-root Allen row, rather than
exposing that placeholder as scientific data. The actual Allen root still maps to root.

This is a consumer-side contract spike: the existing web builder remains the
authoritative producer and is intentionally not moved here.

## Read a local atlas volume pack

Spike 002 adds a strict, bounded reader for a registered anatomical-template and source-index
annotation pair. Arrays use explicit AP/ML/DV storage and an ML/AP/DV micrometre transform; the
annotation is cryptographically bound to its signed region catalog.

```python
from ibl_anatomy import open_volume_pack

pack = open_volume_pack("path/to/volume-pack")
pack.verify()
volumes = pack.load_volumes()
coronal = volumes.slice("annotation", "ap", 108)
region = volumes.region_for_source_index(int(coronal.values[100, 50]))
```

Only deterministic synthetic volume bytes are committed. A pinned-source 50-um Allen builder and
local verification checkpoint exist, but the real derived bytes await an immutable publication
location and must retain the Allen Institute terms and citation metadata.

For large scalar templates, the experimental indexed-block transport reads one projection-native
compressed block rather than loading a complete volume. It provides explicit grid identity and
world registration, bounded decoding, a byte-accounted in-memory LRU, and per-block integrity:

```python
from ibl_anatomy import open_intensity_block_pack

intensity = open_intensity_block_pack("path/to/intensity-blocks")
section = intensity.read_section("ml", 570)
```

The builder accepts either a C-order AP/ML/DV NumPy file or the official embedded-gzip Allen NRRD
directly. NRRD decoding uses a temporary memory map instead of allocating the 2.4 GB decoded volume
on the Python heap. Source and generated assets remain outside Git.

This remains a local prototype; no 10-um Allen intensity asset is committed or published.

## Read registered annotation slices

Registered projections retain exact signed Allen/Beryl/Cosmos identities and even-odd SVG path
semantics without coupling the asset contract to a renderer. The reader supports indexed SVG packs
and the exact gzip JSON slice packs currently produced by `ephys-atlas-web-v2`:

```python
from ibl_anatomy import open_registered_projection

coronal = open_registered_projection("path/to/coronal.json")
section = coronal.load_slice(540)
world_um = coronal.index_to_world([540, 570, 400])
```

The complete `anatomy-pack-v2` produced by `ephys-atlas-web-v2` can be consumed without copying its
resources. Because that older manifest predates explicit reference-space and grid fields, callers
must supply the identities from their pinned asset record:

```python
from ibl_anatomy import open_anatomy_pack

anatomy = open_anatomy_pack(
    "path/to/anatomy-pack-v2",
    reference_space_id="allen-ccf-2017",
    grid_id="allen-ccf-2017-10um",
)
coronal = anatomy.projections["coronal"]
```

The committed linked fixture shares one synthetic 10-um grid with the intensity-block fixture and
covers every AP, ML, and DV section. It is a contract and integration test, not scientific data.
