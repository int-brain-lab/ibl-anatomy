# Mesh contract parity checkpoint

Status: accepted after the first independent Python reader and native Datoviz consumer.

The mesh schema and miniature raw EAM3 fixture were extracted byte-for-byte from
`ephys-atlas-web-v2`. The independent reader now applies the same mesh semantic checks as the
authoritative v1 builder validator: source scope and coverage, contiguous identities, signed
Allen/Beryl/Cosmos mappings, component lateralization, bounds, LOD ratios, quantization, and
resource identity. Public metadata is recursively immutable.

The renderer-neutral boundary is useful in practice. `MeshGeometry` exposes the validated
presentation boundary and resolves a component presentation from its original-world ML coordinate.
Applications must use manifest mappings; they must not reconstruct reduced mappings from a region
catalog because root-reduced mesh mappings are intentionally represented as missing.

## Immutable fixture gates

| Product | SHA-256 |
| --- | --- |
| `manifest.json` | `6076d1604f67b3e711506e0d400adf58db49f5f6077790ca4d96d2557c56737a` |
| `default.eam3.gz` | `750342e13223ce90dbfa09672e95159997ce2e807822a86843d4319eeffac260` |
| `validation-report.json` | `6ecd7b00c7ac84eb4b2a0675cfc316b396629827b08cf88b60823dd9924233e0` |
| decoded EAM3 | `92614e2e836828a8b8637342ea8f9384d43351817921833a9d384977b0c17a39` |
| positions | `7045ad9561e3e5e096e4b179da64cb08a200c7a12597c9f6a65addd5a5578f4b` |
| normals | `5b2dc2fe6f552d459b6e6d62a61acb2999a43cb2fd73fa363c878efc8bad3d8f` |
| component IDs | `23d141876edd0e214adc19f40b085c8d014e0d1eb54eaf6312cca9b02ea5cb15` |
| indices | `ce813f91b441de766386fa7cf3055ff218df5dd0d398043fb1d32e6e8ff8bd54` |

The selected real D070 pack also decodes through this reader: 486,674 vertices, 2,899,935 indices,
1,140 component ranges, and 1,132 presentations in `allen-ccf-2017`. Its geometry resource remains
the cross-publication sentinel even when publication metadata changes.

## Extraction decision

- Keep schemas, EAM3 decoding, semantic validation, immutable metadata, fixtures, and presentation
  resolution here.
- Keep HTTP/cache/workers, Three.js objects, shaders, WBOIT, DOM state, and dataset workflows in
  `ephys-atlas-web-v2`.
- Consider a strict region-catalog contract only after the native consumer needs authoritative
  names, hierarchy, and colors.
- Treat projection assets as a separate future spike.
- Do not reuse the ephys scalar-volume schema for atlas annotation/template volumes.
