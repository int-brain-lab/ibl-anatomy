# Spike 001: independent mesh-pack reader

Status: proposed first implementation task.

## Question

Can the existing `atlas-mesh-pack-v1` contract and miniature fixture from
`ephys-atlas-web-v2` be consumed cleanly by an independent Python package,
without importing ephys application, publishing, browser, or rendering code?

## Why this experiment

The mesh pack is the most mature candidate for sharing and is immediately
useful to the Datoviz v0.4 viewer. A successful reader demonstrates a natural
repository boundary. An awkward extraction is equally useful evidence that the
contract or proposed ownership needs refinement.

## Scope

- Copy the minimum deterministic miniature fixture with explicit provenance.
- Bring across or adapt only the schema definitions required to validate its
  manifest.
- Validate manifest structure, referenced resources, byte sizes, and SHA-256.
- Decode the fixture's EAM3 geometry into NumPy arrays.
- Expose component and signed presentation metadata.
- Expose reference-space and coordinate metadata without applying a renderer
  transform.
- Test malformed metadata, corrupt bytes, missing mappings, and invalid
  component/presentation references.
- Document every dependency on the current ephys schema or implementation.

## Out of scope

- HTTP fetching or persistent caches.
- Datoviz, Vulkan, Three.js, WebGPU, GUI, or picking.
- Real D070 asset distribution.
- Mesh building, simplification, or LOD selection unless decoding the fixture
  proves impossible to test independently without a minimal builder utility.
- Annotation volumes and projection packs.
- Atlas ontology computation.
- Python or npm publication.
- Changes to `ephys-atlas-web-v2`.

## Candidate Python surface

The spike may revise these names. The important boundary is validated,
renderer-neutral output.

```python
from ibl_atlas_assets import open_mesh_pack

pack = open_mesh_pack("manifest.json")
pack.verify()
geometry = pack.load_geometry()

geometry.positions
geometry.normals
geometry.indices
geometry.component_ids
geometry.components
geometry.presentations
geometry.reference_space
```

Expected arrays should have explicit dtype, shape, contiguity, ownership, and
coordinate-unit documentation.

## Acceptance criteria

- The package reads and verifies the complete miniature file graph.
- Tests run without a network connection or GPU.
- The package has no dependency on `ephys-atlas-web-v2`, Datoviz, or Three.js.
- Wrong encoded-byte size or SHA-256 fails before decoding.
- Malformed component and presentation references fail explicitly.
- Signed IDs and `null` mapping values are preserved exactly.
- Decoded arrays and metadata are deterministic.
- Fixture provenance and source revision are recorded.
- The implementation remains small enough to review as an experiment.

## Follow-up consumer

If the reader succeeds, `ibl-datoviz` will consume its output in a small
Datoviz v0.4 scene. That consumer, rather than this spike, owns visual creation,
mapping-driven display state, picking, transparency, camera control, and GPU
resource destruction.

## Decision produced by the spike

The completion note must recommend one of:

1. keep and stabilize the independent mesh reader here;
2. retain only a shared contract and conformance fixture while keeping separate
   language-specific readers; or
3. stop extraction because the apparent shared boundary is not useful enough.

It must also list concrete candidates for a second extraction, without starting
that extraction in the same task.
