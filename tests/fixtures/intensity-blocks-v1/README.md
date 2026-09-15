# Projection-oriented indexed intensity fixture

This 9-by-8-by-7 AP/ML/DV `uint16` volume contains the axis-coded value
`1000 * ap + 100 * ml + dv`. Each of its three projection resources stores
independently gzipped groups of three native planes behind a byte-range index.

The fixture contains no Allen data and is MIT licensed. Regenerate it with:

```console
python -m tools.build_intensity_fixture tests/fixtures/intensity-blocks-v1/pack
```
