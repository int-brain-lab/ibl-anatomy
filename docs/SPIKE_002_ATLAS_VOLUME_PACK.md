# Spike 002: registered Allen atlas volumes

Status: synthetic contract and local real-source checkpoint implemented on 2026-09-15; immutable
publication of the real derived bytes remains open.

## Question

Can one compact renderer-neutral pack preserve enough of iblatlas' Allen CCF 2017 volume semantics
for linked orthogonal slices now and scalar 3-D rendering later, without making this repository a
second scientific atlas implementation?

## Contract

`ibl-atlas-volume-pack-v1` contains exactly one common grid, an anatomical template, a categorical
annotation and the exact region catalog to which annotation values refer. The decoded arrays are
little-endian `uint16`, C-contiguous, and ordered `(ap, ml, dv)`. World coordinates are
`(ml, ap, dv)` micrometres relative to bregma. The explicit 4-by-4 affine maps voxel-center array
indices to world coordinates; consumers must not infer axis order or flips from shape.

Annotation voxels contain the sparse source ontology index in `mappings.allen[].idx`, not an Allen
ID and not a dense catalog-row offset. Resolving that index yields the signed physical Allen row.
Mapping to Beryl or Cosmos happens through the catalog after resolution, so one annotation remains
authoritative and missing reduced mappings do not become root.

The hemisphere split is also explicit. iblatlas uses the first-right ML array index, not the sign
of a voxel-center world coordinate. At 50 um the first right index is 114, whose center is at
-39 um because bregma falls between samples. The synthetic fixture reproduces this important
off-grid case.

## Python surface

```python
from ibl_anatomy import open_volume_pack

pack = open_volume_pack("path/to/volume-pack")
pack.verify()
volumes = pack.load_volumes()

coronal = volumes.slice("annotation", "ap", 108)
world_um = volumes.grid.index_to_world([108, 115, 7])
source_index = int(volumes.annotation_index_at_world(world_um))
region = volumes.region_for_source_index(source_index)
```

Slices are owned arrays with named remaining axes and no hidden transpose or display flip.
Coordinate transforms accept vectors or batches. World lookup uses nearest voxels and has explicit
`raise` and `clip` modes.

## Integrity and semantic validation

The reader validates:

- JSON Schema plus finite, affine, invertible coordinate transforms;
- exact decoded size implied by the grid and `uint16` dtype;
- a complete local file graph with safe relative non-symlink paths;
- encoded and decoded byte counts and SHA-256 identities;
- bounded gzip decompression before NumPy allocation;
- exact region-catalog bytes and common reference-space identity;
- resolution of every used annotation source index, including void at index zero; and
- negative catalog identities left of `first_right_index` and positive identities at or right of
  it.

Loaded arrays and slices own C-contiguous native `uint16` memory. Nested manifest metadata and the
source-index lookup are immutable.

## Deterministic fixture

`tests/fixtures/volume-pack-v1` contains a 4-by-5-by-3 synthetic pack. Its template value is
`100 * ap + 10 * ml + dv`; six annotation voxels refer to the existing five-row synthetic region
catalog. No Allen image data is committed. `tools/build_volume_fixture.py` regenerates it exactly.

## Real 50-um checkpoint

The reviewed source pair is:

| Resource | Encoded bytes | Source SHA-256 |
| --- | ---: | --- |
| [average template](https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_50.nrrd) | 5,346,363 | `6114c341d526f9782ca93b314b3244bb0c4c6cea17045f432d4cda63339915aa` |
| [CCF 2017 annotation](https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_50.nrrd) | 880,845 | `84e7cecea1b03af16e923c3639602b8324929f833425ba03582bf56f962ea0d4` |

Their NRRD header grid is `(ml, dv, ap) = (264, 160, 228)` at 50 um. Matching
`AllenAtlas._read_volume`, normalization transposes to `(ap, ml, dv) = (264, 228, 160)`. The
index-to-world matrix is:

```text
   0   50    0  -5739
 -50    0    0   5400
   0    0  -50    332
   0    0    0      1
```

The normalized template has 9,630,720 voxels, range 0 through 516, and decoded SHA-256
`556d5ab3afce8b35c7ca8768e4de72a0ce915c4ea86c0630caed30e052106340`. The normalized annotation
uses 1,340 catalog indices, range 0 through 2630, and decoded SHA-256
`43fd015053987e636c6ffe1e7aabba4a5de350c136956fb3c6b92aff84c34421`. Every used index resolves
against the pinned D070 catalog.

`tools/build_allen_volume_pack.py` rejects any other source bytes and generated a locally verified
pack. Deterministic gzip resources were 5,481,339 bytes (`987f1788...9ef70`) and 779,973 bytes
(`c9437729...13556`) for template and annotation respectively. Their complete SHA-256 identities
are `987f1788c3d3ba24c72733a638691a15ce91cb38243c98c40c8395059c09ef70` and
`c94377294b57f766da9a25bb3b7c836807b04471f0ea33cbb355cb5f0c113556`.

## Publication limitation

The source URLs contain `current-release` and are therefore not durable content addresses. The
derived real resources must not be locked for consumers until their exact bytes are hosted at a
legitimate immutable location. The repository's MIT license covers its code and synthetic fixture,
not downloaded Allen content. Real publication must preserve © 2015 Allen Institute for Brain
Science attribution and the current [Allen Terms of Use](https://alleninstitute.org/terms-of-use/)
and [Citation Policy](https://alleninstitute.org/legal/citation-policy); this project does not claim
that those data are MIT-licensed or CC BY.

## Deferred

Pyramids, arbitrary affine/resampling support, precolored or pre-mapped annotations, bricked GPU
storage, transfer functions, gradients, isosurfaces, ray-hit identity, networking, cache policy,
histology volumes and ephys feature volumes remain consumer-evidence tasks.

## Decision

Keep the narrow schema, reader, fixture, and pinned-source builder. They preserve scientific
identity while remaining independent of rendering. Do not add a shared runtime or browser package
yet. The next evidence is the native Linked Atlas Navigator; only after that consumer is useful
should the web application assess a small conforming decoder.
