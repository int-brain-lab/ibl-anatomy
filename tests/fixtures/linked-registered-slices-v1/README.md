# Linked registered 10-um slice fixture

This tiny test-only fixture uses the same `synthetic-10um-grid-v1` identity,
Allen CCF reference space, and affine as the synthetic 9-by-8-by-7 intensity
fixture. It contains every coronal, sagittal, and horizontal slice in compact
gzip JSON `anatomy-slice-pack-v2` resources. Signed ±997 Allen/Beryl/Cosmos
paths are synthetic identities; the first coronal path includes an evenodd
hole. No scientific data is represented.

Regenerate with:

```console
python -m tools.build_linked_registered_fixture tests/fixtures/linked-registered-slices-v1/pack
```
