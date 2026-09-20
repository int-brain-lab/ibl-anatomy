# Registered 10 µm anatomy publication

Status: the strict lock and materializer are implemented and point to the deployed immutable
projection graph. Live verification covers 59 files and 5,700,497 encoded bytes, including the
root manifest, three registered stacks, Top/Swanson fragments, and the license notice.

The root pack is `ibl-atlas-projections-05b9f3f85db9`, SHA-256
`5c6ad6fb49b8ad9281c954c3fc7948300997b60b98097043dbe6d26ddc5b8a46`, produced by Ephys builder
commit `62199f51d81a7833480c64559930cdec9993f702`. The bundled lock is
`src/ibl_anatomy/asset_sets/allen-ccf-2017-10um.json`.

The lock records the official Allen annotation URL and hash separately from the derived bilateral
LUT recipe, including its path, bytes, hash, Ephys builder, and `iblatlas` revision. Terms and
citation are recorded as provenance; Allen terms are not asserted to be MIT or CC. Top/Swanson
remain separately licensed curated assets under the producer's MIT notice.

The parent anatomy and LUT provenance paths are evidence only; they are not runtime resources in
the deployed projection graph. The Python materializer verifies the root identity, all registered
resource indexes and packs, static fragments, license notice, and deterministic inventories.

The deployed origin currently lacks `Access-Control-Allow-Origin` for external browser origins.
This does not block Python materialization, but browser consumption requires CORS configuration or
a controlled proxy.

Consumer order:

1. merge and release `ibl-anatomy` with this lock;
2. pin and cut over `ibl-datoviz` to the released lock;
3. update browser consumers only after CORS or a proxy is available and browser parity passes.
