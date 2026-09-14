# Immediate cross-repository steps

Status: active near-term work plan, captured on 2026-09-14.

Current checkpoint:

- `ibl-atlas-assets` Spike 001 is implemented on `main`; the raw EAM3 reader,
  packaged fixture, validation tests, and completion decision are committed. Mesh semantic parity
  with the web-v2 v1 validator, immutable metadata, presentation-boundary helpers, and decoded-byte
  hash gates are now implemented; see `MESH_CONTRACT_PARITY.md`.
- `iblatlas` hardening is implemented on
  `feature/atlas-contract-hardening` (never on `main`) and its complete unittest
  suite passes. The branch is pushed to the `rossant/iblatlas` fork; the local
  `origin` continues to point at `int-brain-lab/iblatlas` and no pull request is
  open.
- the Datoviz retained tree/table contract, native implementation, generated
  Python facade, C/Python examples, and documentation are committed on Datoviz
  `main`. The overlay handles sRGB targets correctly, mesh faces have an explicit
  query target, and linked identities are scoped by channel plus 64-bit key. The
  combined atlas example has a darker, denser presentation modeled on the established
  Allen hierarchy browser; its reviewed gallery image is committed in the data submodule.
- the first `ibl-datoviz` v0.4 consumer is implemented on
  `feature/datoviz-v04-atlas-spike`: real offscreen rendering, dense mesh upload, mapping-only
  updates, per-face signed query keys, probe path, arcball, and explicit destruction are green.
  A docked retained Allen ontology browser now consumes this package's region catalog, with
  Allen/Beryl/Cosmos switching, filtering, collapse/expand, official swatches, and linked
  surface/tree selection.
- `ephys-atlas-web-v2` now has one deliberately narrow extraction seam: its authoritative region
  builder emits an explicit `allen-ccf-2017` reference-space identity and its browser decoder now
  exposes the same strict physical, left, and logical views as the Python reader. Real D070 parity
  is green on `feature/shared-atlas-region-contract`; projection and volume extraction remain
  deferred.
- the representative real D070 surface is now captured by a packaged immutable asset-set lock.
  The Python materializer verifies the published mesh graph and exact region catalog together,
  including complete vertex/triangle presentation fingerprints, without copying numeric geometry
  into Git or adding a shared cross-language runtime.

This document separates immediate, evidence-producing work from the broader
possibilities in `FUTURE_DIRECTIONS.md`. Work should use small green commits.
Pull requests are not part of the current workflow unless the repository owner
later requests them.

Branch policy for the current work:

- changes to `iblatlas` must be made on a dedicated feature branch, never
  directly on `main`;
- before committing in any other repository, record and confirm the intended
  branch in the working plan; and
- pushing commits is allowed, but opening pull requests is not currently part
  of the workflow.

## Order and dependencies

```text
Datoviz pre-final improvements ───────────────┐
                                              ├─> ibl-datoviz v0.4 vertical slice
ibl-atlas-assets mesh reader ─────────────────┘

iblatlas correctness work ──────> later catalog/reference-space integration

ephys-atlas-web-v2 ─────────────> authoritative region-catalog producer
                                  shared reader contract after consumer evidence
```

Datoviz pre-final work and the renderer-independent asset reader may proceed in
parallel. The `ibl-datoviz` consumer begins only as part of its breaking
Datoviz v0.4 cutover, not as an addition to the current v0.3 implementation.

## Datoviz: before v0.4 final

The goal is to close small, proven public-API gaps without delaying v0.4 for
large atlas-specific features.

### Recommended to land

The facade adapters and retained tree/table work below have now landed on Datoviz `main`. The list
remains as rationale and as a release checklist for any composable primitive that is still absent.

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
   v0.4, add the small composable primitives needed by custom interfaces:

   - input text;
   - tree node and tree pop;
   - selectable row;
   - begin/end child region; and
   - tooltip and disabled-state helpers.

   Python editable-string ownership must be explicit and tested. These
   primitives are not by themselves a scalable Python ontology-browser API.

3. Design and, if the ownership and event semantics can be settled before the
   ABI freeze, add retained batched tree and table widgets. Datoviz v0.3 had
   batched `dvz_gui_tree()` and `dvz_gui_table()` calls, but their `char**`
   inputs were re-encoded and allocated by ctypes on every frame. The v0.4
   design should instead:

   - copy packed node/row records and UTF-8 string storage when data changes;
   - draw an entire tree or table with one Python-to-C call per GUI frame;
   - use stable application keys rather than row indices for identity;
   - keep expansion, sorting, and other ephemeral UI state in native code;
   - support batched application-driven selection and visibility updates;
   - return compact events for selection, activation, expansion, sorting, and
     optional row actions; and
   - share row styling, filtering, selection, and event concepts between the
     tree and table without forcing them into one universal widget.

   The Allen ontology browser is the initial demanding test case, but the
   Datoviz API must remain domain-neutral. A generic serialized ImGui command
   stream and a fully retained GUI framework are out of scope.

### Investigate and decide, but do not force into final

4. Establish the intended identity/picking route for multiple anatomical
   components in one indexed mesh. Determine whether existing item, instance,
   face, primitive, or link-key semantics are sufficient. Add a narrow API only
   if the first consumer demonstrates a real gap and the semantics are clear.

5. Confirm the minimal NumPy mesh upload path with an offscreen test:

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

The intended branch for this slice is `feature/datoviz-v04-atlas-spike`. Record
the actual branch and remote again immediately before the first commit; do not
start this work on the repository's default branch.

## `iblatlas`: independent hardening

All commits in this section must be made on a dedicated feature branch, not on
`main`. Record the exact branch name before the first commit. Keep this small
and compatible where practical:

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

Treat the production application as the working reference and source evidence.
The first post-spike change is limited to making the already-versioned region
catalog independently consumable by declaring its reference-space identity.

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

The two-consumer checkpoint is now recorded in `PROJECT.md`. It supports shared immutable assets,
schemas, semantic validators, and parity vectors with small language-native adapters. The next
asset-family spike should begin only from a concrete volume or projection use case with a pinned
source artifact; it should not start by designing a generic cross-language runtime.
