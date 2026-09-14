# Audited source inventory

Status: read-only inventory captured on 2026-09-14.

This inventory records the evidence used to define the initial experiment. It
does not transfer ownership of any source file or immutable asset.

## Audited revisions

| Repository | Commit |
| --- | --- |
| `ibl-atlas-assets` | `895bca058801f9bc0c38429dceb262b815c12993` |
| `ibl-datoviz` | `4e07085a96f83519ef78a163f4f040a90ae250dd` |
| `ephys-atlas-web-v2` | `58a9418b7408ed3760016173df3a34903280cf24` |
| `iblatlas` | `52083adf44825d0622a503705e095699a5957587` |
| Datoviz | `9dbb589ca0c420a123620076442a0c759a9f5c46` |

The working trees of some source repositories contained unrelated untracked
files during the audit. They were not modified or used as authority.

## `ephys-atlas-web-v2`

This is the source of the existing reviewed asset work.

### Initial extraction candidates

- `schema/v1/mesh-pack.schema.json`: canonical mesh-pack v1 schema copy.
- `builder/ibl_ephys_atlas/_schema/v1/mesh-pack.schema.json`: packaged schema.
- `tools/mesh_pack/binary.py`: deterministic EAM3 raw container encoding.
- `tools/mesh_pack/validate.py`: complete mesh-pack file-graph validation.
- `tools/mesh_pack/synthetic.py`: deterministic synthetic GLB input.
- `tools/mesh_pack/build.py`: baseline deterministic pack compiler.
- `fixtures/mesh-pack-v1/`: committed miniature source, pack, manifest, and
  validation report.
- `web/src/rendering/3d/mesh-pack-codec.ts`: TypeScript EAM3 raw/meshopt decoder.
- `web/src/rendering/3d/mesh-presentation-boundary.ts`: physical component to
  signed presentation selection at the reviewed ML boundary.

These are candidates only. Spike 001 should take the smallest coherent subset
and record the provenance of every copied or adapted file.

### Likely web-owned code

- `web/src/rendering/3d/brain-scene-viewport.ts`: Three.js scene, materials,
  picking, camera, and renderer lifecycle.
- `web/src/rendering/3d/weighted-transparency.ts`: web renderer implementation
  of weighted blended OIT.
- `web/src/rendering/3d/lazy-brain-scene-viewport.ts`: application-specific lazy
  viewport lifecycle.
- `web/src/application/regional-presentation.ts`: currently renderer-neutral,
  but coupled to the web application's feature and state contracts; extraction
  requires evidence rather than assumption.
- `web/src/ui/regional/`: DOM tree, accessibility, and regional UI.
- Browser fetching, persistent caching, URL state, dataset sessions, release
  navigation, publishing, and ephys feature semantics.

### Relevant accepted evidence

- `docs/rendering/3D_SELECTED_ASSET.md`: D070 native geometry selection.
- `docs/rendering/3D_INTEGRATION_PLAN.md`: component/presentation separation,
  reference-space rules, immutable resource validation, and lazy lifecycle.
- `docs/rendering/3D_TRANSPARENCY.md`: implemented web WBOIT policy and tests.
- `docs/data/NATIVE_3D_SELECTION.json`: hash-bound selection evidence.

## `iblatlas`

`iblatlas` remains the scientific source rather than an asset transport layer.

- `iblatlas/regions.py`: region IDs, names, acronyms, colors, hierarchy,
  signed lateralization, Allen/Beryl/Cosmos/Swanson mappings, and remapping.
- `iblatlas/atlas.py`: atlas volumes, label lookup, slices, coordinate systems,
  CCF conversion, trajectories, insertions, and region-volume computation.
- `examples/3D/meshes_load_and_display.py`: existing GLB loading and AP/DV/ML
  to ML/AP/DV conversion example.

Potential independent upstream work includes safe region lookup, explicit
reference-space metadata, clearer units/coordinate contracts, and correctness
fixes identified during the audit. Mesh-pack codecs, GPU state, and browser
cache policy are not proposed as `iblatlas` responsibilities.

## `ibl-datoviz`

- `ibl_datoviz/meshes.py`: current GLB download, region lookup, hemisphere
  slicing, mesh data, and Datoviz 0.3 rendering.
- `ibl_datoviz/points.py`: point data and scalar/RGBA presentation.
- `ibl_datoviz/insertions.py`: probe/insertion paths.
- `ibl_datoviz/glyphs.py`: text/glyph annotations.
- `ibl_datoviz/viewer.py`: current viewer composition and constructor-time atlas
  loading.

The current implementation targets the removed Datoviz 0.3 object API and will
be replaced rather than adapted behind a compatibility facade.

## Datoviz v0.4

- `include/datoviz/scene.h`: retained scene, panels, visuals, bounds, partial
  updates, paths, lights, and attachment APIs.
- `include/datoviz/scene/interaction.h`: query capabilities and stable link
  keys.
- `include/datoviz/scene/text.h`: semantic text APIs.
- `include/datoviz/gui.h`: current ImGui wrapper surface.
- `docs/reference/visual-families/mesh.md`: indexed mesh behavior.
- `docs/reference/webgpu-subset.md`: experimental browser subset.
- `docs/reference/v03-visible-parity.md`: promoted and deferred v0.4 features.

The first native consumer should establish actual API gaps. Known candidates
include ergonomic Python adapters, ontology-oriented ImGui primitives, and a
documented mesh component/group identity route. Volume, advanced WebGPU
postprocessing, and categorical 3-D label volumes are not required by Spike 001.
