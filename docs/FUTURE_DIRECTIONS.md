# Deferred directions and gallery ideas

Status: planning record, not committed scope.

This document preserves useful directions identified during the initial audit
without adding them to Spike 001. Candidates should move into committed scope
only after a concrete consumer demonstrates the boundary.

## Possible extraction sequence

If the mesh reader proves useful, evaluate these independently:

1. a generated region catalog with public signed IDs, hierarchy, canonical
   colors, mapping membership, and source provenance;
2. generic mesh-pack validation and deterministic building;
3. registered anatomy projection packs for linked orthogonal slices;
4. template and annotation-volume packs with explicit grid, affine, label LUT,
   missing/outside semantics, and reference-space identity; and
5. TypeScript readers only for functionality that is truly duplicated in the
   web application.

Atlas anatomy and arbitrary scientific feature volumes remain distinct. This
repository may describe the former without absorbing ephys feature semantics,
QC policy, statistics, releases, or publishing.

## Candidate native viewer capabilities

- Searchable Allen ontology with Allen/Beryl/Cosmos/Swanson mappings.
- Explicit hemisphere and signed-region identity.
- Linked tree, surface, slice, point, and trajectory selection.
- Lazy native region surfaces with deterministic asset identity.
- Scalar anatomical and scientific volume rendering.
- Categorical annotation slices and, when supported, categorical 3-D volumes.
- Probe entry/tip, channels, regions traversed, and depth-to-region summaries.
- Points or spheres for registered units and clusters.
- GPU scalar color scales and consistent colorbars.
- Camera presets, validated position/target/up serialization, and fit to
  selection.
- Radial region explode based on canonical centroids.
- Render profiles using WBOIT, depth peeling, AO, EDL, MSAA, and volume
  occlusion where appropriate.
- Deterministic offscreen figures, video, and scene manifests with provenance.

## Candidate gallery

The gallery should be an executable API and regression suite, not only a set of
screenshots.

| Example | Main behavior | Initial browser prospect |
| --- | --- | --- |
| Hello Allen | surfaces, arcball, selection | good, opaque subset |
| Mapping explorer | Allen/Beryl/Cosmos without geometry reload | good |
| Linked atlas navigator | three annotation slices plus 3-D context | good |
| Brain-Wide Map | regional scalar colors and comparison | good |
| Probe through the brain | trajectory, channels, traversed regions | good |
| Unit cloud | registered units with scalar styling and picking | reduced data, no EDL |
| Histology alignment | planned/histology/ephys-aligned tracks | good |
| Neural activity movie | retained temporal point/region updates | good |
| Nested anatomy | WBOIT/depth-peeling comparison | native first |
| Allen volume lab | slice, MIP, composite, clipping, probing | native first |
| AGEA/MERFISH | expression slices/volume and anatomy | 2-D browser subset |
| Connectivity explorer | selected source/targets and weighted paths | likely reduced subset |
| Publication figure | fixed camera, scale, provenance, capture | native/static preview |

The first native API should be exercised by four examples: Hello Allen,
Mapping Explorer, Probe Through the Brain, and Linked Atlas Navigator.

Each example should declare its fixture, provenance, fixed camera, native and
WebGPU status, expected semantic assertions, and screenshot. Tests should cover
offscreen rendering, picking identity, coordinates, mapping changes, resource
lifetime, and browser packet/smoke behavior where applicable.

## Current WebGPU boundary

At the audited Datoviz revision, browser-live routes cover meshes, spheres,
points, paths, images, 2-D labels, text, linked/mixed panels, common
controllers, selected picking/probing, and retained updates. Python ctypes code
does not run unchanged in the browser; live routes use portable C scenarios
compiled into the Datoviz WASM scene host.

Volume rendering, WBOIT/depth peeling, EDL, AO, advanced postprocessing, ImGui,
and native capture are not part of the promoted browser subset. Browser support
should therefore be an explicit per-example status with a static fallback, not
a promise that every native viewer feature is exportable.

## Potential Datoviz follow-up

Consumer-driven candidates identified by the audit:

- ergonomic Python adapters for path subpaths, text strings, link keys, custom
  colormaps, and panel lights;
- ImGui input text, tree nodes, selectable rows, child regions, and optionally
  list clipping/table primitives;
- a clear mesh component/group identity and picking route for merged atlas
  geometry;
- later, general clipping planes, richer mesh queries, categorical label
  volumes, and volume ray-hit identity.

Only changes required by a working native consumer should be treated as
release-sensitive Datoviz work.

## Potential `iblatlas` follow-up

- Fix annotation slice comparison and invalid CCF-order error handling.
- Validate missing region IDs and hemisphere values.
- Clarify APIs that currently expose mapping-array indices.
- Preserve requested region order where required.
- Expose stable reference-space and ontology source identity.
- Make coordinate order and metre/micrometre boundaries explicit.
- Provide deterministic renderer-neutral catalog export if the shared catalog
  experiment is accepted.

These remain independent scientific-library improvements rather than a reason
to move asset codecs, GPU state, or application presentation into `iblatlas`.
