# Project hypothesis and boundaries

Status: mesh and region-catalog boundary accepted after two consumers and the real D070 checkpoint.

## Motivation

`ephys-atlas-web-v2` and the planned Datoviz v0.4 rewrite of `ibl-datoviz`
both need consistent brain-region identity, mapping, coordinates, colors, mesh
metadata, and anatomical assets. They use different languages, renderers, user
interfaces, and application lifecycles.

The working hypothesis is that the highest-value shared boundary is the data
contract: both applications should consume the same verified assets and obtain
the same signed region IDs, mapping results, coordinates, and canonical colors.
Implementation code should be shared only when concrete consumers demonstrate
that sharing removes more complexity than it adds.

## Accepted direction

- `iblatlas` remains the scientific authority for the Allen ontology, mappings,
  coordinates, labels, slicing, trajectories, and atlas computations.
- `ibl-datoviz` may break compatibility with its 0.1 API during its Datoviz
  v0.4 rewrite; a v0.3 compatibility layer is not required.
- Signed Allen IDs identify physical hemispheres: negative is left and positive
  is right. Applications may expose a separate logical bilateral selection.
- Missing Beryl, Cosmos, or other mapping entries remain missing; they are not
  coerced to root or a fine Allen identity.
- Exact reference-space identity is required for spatial compatibility. Grid,
  geometry, pack, and release identity are related but distinct.
- The D070-selected native GLB-derived geometry is the initial real surface
  authority. Annotation-derived replacement surfaces are not the default.
- Mapping, coloring, visibility, selection, and explode changes should not
  require geometry reconstruction or re-upload.
- Existing immutable ephys asset bytes, identifiers, schema identifiers, and
  provenance must remain valid through any later extraction.
- Work begins with a small consumer experiment rather than a comprehensive
  cross-repository platform.

## Current repository hypothesis

The mesh experiment confirms that this repository should own:

- renderer-neutral atlas mesh schemas, readers, and semantic validators;
- immutable mesh metadata and presentation-boundary resolution; and
- deterministic byte-level and decoded-array conformance fixtures.

It may eventually also own a narrow subset of the following:

- renderer-neutral atlas asset schemas;
- small readers and validators;
- deterministic test and conformance fixtures;
- mesh, annotation-volume, and projection-pack builders that prove generic;
- Python and TypeScript consumers where both are demonstrably useful.

Spike 001 tests only the first useful boundary: reading and validating an
existing miniature mesh pack from independent Python code.

## Responsibility boundaries

| Concern | Expected authority |
| --- | --- |
| Scientific ontology, mappings, labels, coordinates | `iblatlas` |
| Renderer-neutral packaged anatomy, if extraction succeeds | `ibl-atlas-assets` |
| Ephys projects, datasets, releases, features, and browser workflows | `ephys-atlas-web-v2` |
| Native Python viewer, ImGui/Qt/notebook integration, IBL layer API | `ibl-datoviz` |
| GPU visuals, interaction, postprocessing, GUI primitives, WebGPU | Datoviz |

## Explicit non-goals for the first experiment

- A portable C, Rust, or WebAssembly atlas runtime.
- A shared application reducer or selection store.
- A universal cache or network-fetching abstraction.
- Replacing the web application's Three.js renderer.
- Moving the complete ephys release schema or publishing system.
- Designing a generic scientific feature-volume format.
- Publishing Python or npm packages before the boundary is validated.
- Migrating production ephys assets or changing their serialized bytes.

## Completed `ibl-datoviz` vertical slice

The first native consumer now:

1. load the miniature mesh geometry through this repository;
2. render it through Datoviz v0.4;
3. preserve signed region identity;
4. switch Allen, Beryl, and Cosmos presentation without reloading geometry;
5. select or pick one region;
6. render a probe trajectory;
7. use explicit resource ownership and destruction; and
8. produce a deterministic offscreen image without network access.

That implementation directly produced the Datoviz retained tree/table API, explicit mesh-face
query identity, channel-scoped linked keys, and the renderer-neutral region-catalog reader in this
repository.

## Decision checkpoint

After the mesh reader and native consumer exist, answer:

- Is `atlas-mesh-pack-v1` independent of the ephys dataset contract in practice?
- How much schema, decoding, validation, and presentation logic is duplicated?
- Is a Python reader materially useful outside `ibl-datoviz`?
- Should TypeScript decoding move here or remain in the web application?
- Is shared code simpler than small language-specific adapters plus conformance
  fixtures?
- Which asset family, if any, should be extracted next?

## First checkpoint answers

- `atlas-mesh-pack-v1` is independent of the ephys dataset contract in practice: the Python
  consumer loads geometry, presentations, provenance, and reference-space identity without an
  ephys release or browser runtime.
- The valuable shared surface is schema, immutable bytes, semantic invariants, and conformance
  fixtures. Renderer upload, GUI state, caching, and application lifecycle remain consumer-owned.
- The Python reader is materially useful: `ibl-datoviz` consumes it directly and no longer carries
  a second mesh decoder or presentation-boundary rule.
- TypeScript decoding should remain in the web application for now. Moving it would add packaging
  and release coupling before a second TypeScript consumer exists; parity should be enforced with
  the same fixtures and hashes.
- Small language-specific adapters plus shared contracts are currently simpler than a shared
  cross-language runtime.
- The next evidence-producing slice should use one representative real surface pack and the full
  region catalog in both consumers. Volume and projection extraction remain deferred until this
  proves publication, versioning, and cache boundaries on real data.

This is the accepted narrow scope for the next slice. It deliberately does not authorize a broad
asset platform, shared reducer, or renderer abstraction.

## Real D070 checkpoint

The first representative real asset set is the published D070 native Allen CCF 2017 surface plus the region catalog emitted by `ephys-atlas-web-v2` commit `e91f021ac7ca096db2b408a7d691a6c32cc336ad`. `ibl-atlas-assets` ships a small immutable lock rather than duplicating the 14 MB numeric geometry in Git. Materialization verifies the complete remote graph before exposing it locally.

This checkpoint also exposes owned world-coordinate arrays and moves per-vertex/per-face presentation classification into the renderer-neutral reader. EAM3 positions are already compiled into declared ML/AP/DV micrometres; the manifest's source transform is provenance and is not applied twice. These operations define the asset's signed anatomical identity and are shared semantics; normalization, GPU upload, colors, interaction, and application state remain consumer responsibilities.

The lock freezes:

- the exact published manifest, geometry, validation report, and region-catalog byte identities;
- 486,674 vertices, 966,645 triangles, 1,140 components, and 1,132 presentations;
- the common `allen-ccf-2017` reference space and catalog membership of every non-missing Allen/Beryl/Cosmos mapping; and
- deterministic vertex and face presentation fingerprints, which provide compact cross-language parity vectors without a shared runtime.

The real checkpoint supports the existing conclusion: share immutable contracts, semantic fingerprints, and small language-native adapters. Do not introduce a cross-language renderer or state runtime.

## Two-consumer checkpoint

The native and browser consumers now exercise the same real D070 lock independently:

- `ibl-datoviz` verifies the asset graph, uploads the surface once, maps signed Allen probe and
  regional values into Allen/Beryl/Cosmos presentations, and links native rendering to retained
  ontology and table widgets;
- `ephys-atlas-web-v2` parses strict physical, left, and logical catalog views, preserves source
  indices and mapped identities, and verifies the real mesh and region fingerprints; and
- both consumers reject malformed hierarchy, mapping, provenance, reference-space, and bilateral
  identity instead of silently repairing it.

This does not justify a shared runtime package. Python benefits from this repository's reader;
TypeScript currently has exactly one consumer, whose small language-native decoder is simpler than
an npm/Wasm release dependency. Browser fetch and cache policy, application selection state,
scientific feature derivation, GUI composition, and renderer upload remain consumer-owned.

No new `iblatlas` API is required by these slices. No additional `ibl-atlas-assets` lookup or
aggregation API is being added yet: mapping-aware weighted reduction is currently a presentation
need in one consumer, not a demonstrated cross-consumer asset primitive.

The first cross-renderer portability probe also supports this boundary. Datoviz commit
`c56ca6c36` compiles one atlas-like C scenario into both native and WASM runners and verifies mesh,
probe-site, signed-color, and arcball packet semantics. It does not make the Python viewer or its
retained ImGui interface portable, and it does not justify a shared application runtime.

The next selected asset-family experiment is a registered Allen template-and-annotation volume
pack serving a native linked slice/3-D navigator. It remains a separate spike: its exact source,
grid, encoding, and real-asset lock must be evidenced before any projection or browser extraction
is accepted.

The synthetic portion of that experiment is now implemented as `ibl-atlas-volume-pack-v1`. A
pinned-source builder also verifies the complete 50-um real pack locally. This does not yet promote
the volume boundary: the native consumer must prove it, and the real derived bytes still require a
legitimate immutable publication location under the Allen Institute's terms.
