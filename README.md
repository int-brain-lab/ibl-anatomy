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
- [Audited source inventory](docs/SOURCE_INVENTORY.md)
- [Spike 001: independent mesh-pack reader](docs/SPIKE_001_MESH_PACK_READER.md)
- [Deferred directions and gallery ideas](docs/FUTURE_DIRECTIONS.md)

## Current status

The project is in an evidence-gathering phase. No decision has yet been made to
move all anatomy builders, publish Python or TypeScript packages, create a
cross-language runtime, or replace an application's renderer.
