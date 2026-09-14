# Immediate cross-repository steps

Status: active near-term work plan, captured on 2026-09-14.

This document separates immediate, evidence-producing work from the broader
possibilities in `FUTURE_DIRECTIONS.md`. Work should use small green commits on
each repository's `main` branch. Pull requests are not part of the current
workflow unless the repository owner later requests them.

## Order and dependencies

```text
Datoviz pre-final improvements ───────────────┐
                                              ├─> ibl-datoviz v0.4 vertical slice
ibl-atlas-assets mesh reader ─────────────────┘

iblatlas correctness work ──────> later catalog/reference-space integration

ephys-atlas-web-v2 ─────────────> unchanged during Spike 001
                                  extraction decision after consumer evidence
```

Datoviz pre-final work and the renderer-independent asset reader may proceed in
parallel. The `ibl-datoviz` consumer begins only as part of its breaking
Datoviz v0.4 cutover, not as an addition to the current v0.3 implementation.

## Datoviz: before v0.4 final

The goal is to close small, proven public-API gaps without delaying v0.4 for
large atlas-specific features.

### Recommended to land

1. Add ergonomic Python facade adapters for existing public C functions needed
   by ordinary scientific viewers:

   - `dvz_path_set_subpaths` from Python sequences/NumPy arrays;
   - `dvz_text_set_strings` from Python strings;
   - `dvz_visual_set_link_keys` from `uint64` arrays;
   - `dvz_colormap_custom` from RGBA arrays; and
   - `dvz_panel_set_lights` from Python light handles.

   These should preserve the C API and improve parity rather than introduce a
   new abstraction.

2. If the public ImGui wrapper is intended to support application panels in
   v0.4, add the small primitives needed for a scalable ontology browser:

   - input text;
   - tree node and tree pop;
   - selectable row;
   - begin/end child region; and
   - tooltip and disabled-state helpers.

   A table or list clipper is useful but may be deferred if its API is not
   settled. Python editable-string ownership must be explicit and tested.

### Investigate and decide, but do not force into final

3. Establish the intended identity/picking route for multiple anatomical
   components in one indexed mesh. Determine whether existing item, instance,
   face, primitive, or link-key semantics are sufficient. Add a narrow API only
   if the first consumer demonstrates a real gap and the semantics are clear.

4. Confirm the minimal NumPy mesh upload path with an offscreen test:

   - `float32[N, 3]` position and normal attributes;
   - `uint8[N, 4]` colors;
   - flattened `uint32` indices;
   - material, depth, alpha mode, visibility, and destruction.

   The first consumer should use dense attribute upload rather than the opaque
   `DvzGeometry` Python type.

### Explicitly not v0.4-final blockers

- General clipping planes for every visual family.
- Categorical 3-D label volumes.
- Volume ray-hit identity.
- Isosurface extraction.
- WBOIT, AO, EDL, or volume parity in browser WebGPU.
- A stable general-purpose Python-to-WebGPU exporter.
- Atlas-specific high-level objects in Datoviz itself.

## `ibl-atlas-assets`: Spike 001

Implement the independent raw EAM3 mesh-pack reader described in
`SPIKE_001_MESH_PACK_READER.md`:

1. add a minimal Python package and offline test setup;
2. copy the deterministic test-only fixture with source revision and license
   provenance;
3. validate the manifest and complete declared file graph;
4. verify encoded byte sizes and SHA-256 before decoding;
5. decode raw EAM3 data to typed, contiguous NumPy arrays;
6. validate component ranges and signed presentation references;
7. test corruption, traversal, missing resources, invalid mappings, and array
   bounds; and
8. write a short completion decision before adding meshopt, networking,
   builders, TypeScript, or other asset families.

## `ibl-datoviz`: first breaking v0.4 slice

This work follows a successful mesh-reader spike and starts the `ibl-datoviz`
0.2 line. It does not preserve the Datoviz 0.3 runtime.

1. change the package to a reproducible Datoviz v0.4 dependency;
2. remove or replace obsolete v0.3 imports and examples rather than carrying a
   compatibility layer;
3. implement explicit scene/app/view ownership and deterministic destruction;
4. add a minimal mesh layer using dense NumPy attribute and index uploads;
5. consume the miniature `ibl-atlas-assets` mesh pack;
6. preserve signed presentation identity and switch Allen/Beryl/Cosmos display
   without geometry reload;
7. add arcball, selection or picking where supported;
8. render a probe path; and
9. add an offline offscreen smoke image plus semantic assertions.

Start with one visual per region/component if necessary. Batching is an
optimization and API-evidence task, not a prerequisite for the first slice.

## `iblatlas`: independent hardening

Keep this small and compatible where practical:

1. fix annotation slice equality handling;
2. raise the invalid CCF-order error correctly;
3. add explicit errors for missing region IDs/acronyms and invalid hemisphere
   values without silently changing established valid behavior;
4. clarify coordinate order and metre/micrometre boundaries;
5. add signed-ID and all-mapping regression tests; and
6. design, but do not yet require, stable reference-space and ontology source
   metadata for later asset generation.

Catalog export and broader mapping API changes should follow the asset-reader
and native-consumer evidence.

## `ephys-atlas-web-v2`: hold stable, then assess extraction

Do not change the production application during Spike 001. Treat it as the
working reference and source evidence.

After the Python reader and native consumer exist:

1. compare their schema, decoding, validation, and presentation logic with the
   current web implementation;
2. identify exact generic code rather than moving whole directories;
3. freeze existing schema, fixture, and representative real-asset hashes;
4. extract one coherent generic unit at a time;
5. make the web application consume the extracted unit;
6. prove existing generated assets remain byte-identical; and
7. delete the former local copy only after the full web gate passes.

Three.js rendering, DOM UI, browser cache/fetch integration, URL state,
dataset sessions, ephys scientific features, and publishing remain web-owned.

## Checkpoint before broadening the project

Do not begin volume/projection extraction or a shared cross-language runtime
until the first reader and native consumer answer:

- whether the asset contract is independently useful;
- which ephys dependencies are accidental versus essential;
- whether code sharing is better than small conforming adapters;
- what Datoviz APIs are genuinely missing; and
- who owns and versions the extracted contract.

Record those answers in `PROJECT.md`, revise this plan, and select one next
vertical slice.
