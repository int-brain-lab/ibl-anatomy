# Contract and compatibility policy

`ibl-anatomy` versions its Python distribution independently from its serialized formats. Existing format names, schema identifiers, immutable bytes, and hashes do not change when the repository or package is renamed.

## Compatibility

- A reader release may add support for another existing format without changing that format.
- Compatible schema clarifications and stricter rejection of documents that were already invalid may remain within a format version.
- Any change to valid serialized meaning, required fields, coordinate interpretation, or binary layout requires a new format version.
- Published asset locks are immutable. Replacement data receives a new asset, geometry, grid, or pack identity as appropriate.
- Consumers should pin a released package or immutable Git revision and validate representative shared fixtures. They should not depend on adjacent source checkouts in committed production configuration.

## Provenance

New generated asset families must record the builder version or commit, exact input identities and hashes, applicable source terms and citations, and the scientific upstream version or commit. Anatomy derived from `iblatlas` must also record exact hashes for the packaged ontology and mapping resources it uses. Existing v1 formats remain frozen; stronger required provenance belongs in a new format version rather than a silent rewrite.

Reference-space identity, grid identity, ontology and mapping provenance, geometry identity, pack identity, and scientific dataset/release identity are distinct and must not be substituted for one another.

## Supported contracts

The package currently validates `ibl-atlas-regions-v1`, `atlas-mesh-pack-v1`, `ibl-atlas-volume-pack-v1`, `ibl-atlas-intensity-blocks-v1`, registered projection/index documents, and the legacy `anatomy-slice-pack-v2` integration surface. Each supported family has deterministic fixtures under `tests/fixtures/` and focused tests under `tests/`.

The Python reader is shared by Python consumers. Browser consumers use language-native adapters against the same schemas, immutable bytes, hashes, and parity vectors; this repository does not impose a cross-language runtime.
