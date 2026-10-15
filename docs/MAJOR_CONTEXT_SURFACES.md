# Source-native major-structure context

The `allen-major-context.json` lock is a deliberately incomplete ontology cut
for readable anatomical display. Twelve original Allen CCF 2017 structure
meshes replace neither the root display envelope nor the D070 regional pack.
No selected member is an ancestor or descendant of another selected member.
This ontology property does not establish geometric disjointness or a complete
partition of the brain. Fiber tracts, ventricular systems and cerebellar nuclei,
among other structures, are not included.

The ontology excerpt (names, acronyms, official colors and parent chains) was
extracted from the existing D070 region catalog, verified at 657,555 bytes and
SHA-256 `0b4e18949950ddd99ed98ea06c80bc469c5e1c0fb2379dcf1afa02cc66ebd8a4`.
The lock records its immutable commit URL, and pins every original OBJ by size
and SHA-256. The Allen archive's `current-release` URL is not itself immutable;
changed upstream bytes fail verification rather than being accepted.

| Allen ID | Official name | Vertices | Triangles | Open boundary edges |
| --- | --- | ---: | ---: | ---: |
| 315 | Isocortex | 31,592 | 63,176 | 0 |
| 698 | Olfactory areas | 19,330 | 38,596 | 102 |
| 1089 | Hippocampal formation | 14,773 | 29,530 | 0 |
| 703 | Cortical subplate | 7,292 | 14,584 | 0 |
| 477 | Striatum | 17,162 | 34,330 | 12 |
| 803 | Pallidum | 8,516 | 17,038 | 20 |
| 549 | Thalamus | 6,593 | 13,170 | 0 |
| 1097 | Hypothalamus | 6,217 | 12,329 | 89 |
| 313 | Midbrain | 10,518 | 21,040 | 28 |
| 771 | Pons | 7,243 | 14,298 | 202 |
| 354 | Medulla | 10,707 | 21,180 | 364 |
| 528 | Cerebellar cortex | 16,703 | 33,362 | 88 |

The sources total 20,646,168 bytes, 156,646 vertices and 312,633 triangles.
The inventory found aligned positive vertex/normal OBJ indices, finite nonzero
normals, no nonmanifold edges and no zero-area triangles in these twelve meshes.
Open boundaries are retained and checked exactly; these are display surfaces,
not closed solids for scientific containment or volume computations.

The initially considered Cerebellum 512 source has six zero normals on
referenced vertices. It fails the strict source-normal policy and is excluded;
its SHA-256 is `9ae2c78e7c9746ac8116dac82f41ac2d74bb70d71b0c46445094020064f5a77f`.
Cerebellar cortex 528 passes and is labelled precisely. Cerebellar nuclei 519
also passed inspection (1,928 vertices, 3,848 triangles, no boundary edges),
but are omitted to keep this first display cut modest. Nothing is silently
repaired or reconstructed.

```python
from ibl_anatomy import (
    bundled_surface_catalog, materialize_surface_catalog, load_surface_catalog,
)

catalog = bundled_surface_catalog()
# Explicit preparation, only into a new destination:
geometry = materialize_surface_catalog("build/allen-major-context")
# Subsequent reads are offline and verify all members:
geometry = load_surface_catalog("build/allen-major-context")
for member, surface in zip(catalog.members, geometry):
    print(member.asset.source_allen_id, member.name, member.color_hex)
```

Use `source_directory=` for already downloaded `<Allen ID>.obj` files.
Materialization verifies the whole bundle before publishing its directory;
a failed member removes the temporary bundle. A damaged existing bundle fails
loading without replacement or downloading. Each member is stored at
`<destination>/<Allen ID>/surface.obj`.

`SurfaceGeometry` owns contiguous positions, normals and flattened indices.
Positions already use the root envelope's rigid source AP/DV/ML to world
ML/AP/DV µm transform, including the same bregma translation. Positions and
triangle identities remain source-native; normals are transformed and normalized.
No smoothing, decimation, merging, splitting, reindexing or hole filling occurs.
Each original mesh spans both hemispheres. The catalog declares bilateral source
meshes and unsigned Allen identities; it does not manufacture separate signed
left/right geometry or implement hemisphere filtering.

Metadata and locks are packaged; OBJ bytes remain ignored local build assets.
The source lock retains the [Allen terms](https://alleninstitute.org/legal/terms-of-use)
and [CCF citation](https://doi.org/10.1016/j.cell.2020.04.007). Allen data is not
relicensed by this package's software license. Live rendering, interaction and
platform acceptance remain consumer review gates.
