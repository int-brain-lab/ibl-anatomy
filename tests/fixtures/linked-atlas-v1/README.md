# Linked atlas integration fixture

This deterministic `ibl-atlas-volume-pack-v1` fixture is deliberately small enough
to exercise the native linked atlas navigator together with the bilateral
`atlas-mesh-pack-v1` fixture. Its catalog adds signed Allen/Cosmos region `315`
(`MOp`) at source indices 5 and 6; Beryl intentionally treats both rows as
non-members mapping to root.

The grid is isotropic 1-um AP/ML/DV data. Its voxel-edge bounds contain the mesh
fixture's approximate ML/AP/DV bounds `[-2, 5]`, `[-1, 1]`, and `[-1, 1]`, while
the explicit hemisphere boundary is ML index 3.

Regenerate it from the repository root with:

```console
python tools/build_volume_fixture.py --profile linked-atlas \
  tests/fixtures/linked-atlas-v1/volume-pack
```

The fixture is test-only and contains no Allen voxel data.
