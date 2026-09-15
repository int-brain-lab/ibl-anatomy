# Spike 003: 10-um intensity block transport

Status: real local 10-um transport built and benchmarked on 2026-09-15; no Allen intensity bytes
are committed or published.

## Problem

The Allen 10-um template has an AP/ML/DV shape of 1320 by 1140 by 800: 1,203,840,000 `uint16`
voxels, or 2,407,680,000 decoded bytes. Loading that volume merely to display one orthogonal plane
is not an acceptable viewer boundary.

`ibl-atlas-intensity-blocks-v1` stores three projection-native copies. Each projection is reordered
with its section axis first, divided into consecutive section blocks, compressed as independent
deterministic gzip members, and concatenated into one indexed resource. A section read seeks to and
validates one byte range, decompresses one bounded block, extracts one plane, and never materializes
the full volume.

The cost is explicit: the decoded transport contains three logical copies. The real local build
below establishes its compression ratio and navigation latency; publication and multi-host review
remain separate decisions.

## Registration

Every pack declares `reference_space_id`, `grid_id`, AP/ML/DV shape, ML/AP/DV world axes,
micrometre units, voxel-center convention and a finite invertible 4-by-4 index-to-world transform.
Shape is never treated as registration identity. The reader exposes exact forward and inverse
transforms so mixed-resolution slices can share a world crosshair.

The manifest also records the exact scalar minimum/maximum and a reviewed recommended display
range. When the builder receives no explicit display range it scans the resident source exactly
and uses its nonzero minimum and maximum; it never invents a sampled percentile. A nonresident
consumer can therefore initialize contrast without scanning the 10-um dataset.

## Reader

```python
from ibl_anatomy import open_intensity_block_pack

pack = open_intensity_block_pack(
    "path/to/intensity-blocks",
    max_decoded_block_bytes=64 << 20,
    max_cache_bytes=128 << 20,
)
pack.verify()
section = pack.read_section("ap", 540)
world_um = pack.index_to_world([540, 570, 33.2])
index = pack.world_to_index(world_um)
print(section.values.shape, section.array_axes, pack.cache_info())
print(pack.value_range, pack.recommended_display_range)
```

Decoded blocks live in a byte-accounted LRU keyed by projection and block ID. Returned planes are
owned C-contiguous native `uint16` arrays, so callers cannot mutate cached blocks. A zero-byte cache
is supported. Encoded blocks, declared decoded blocks and actual decompression output are bounded;
both encoded and decoded SHA-256 identities are checked before exposure. `verify()` additionally
streams whole-resource hashes and rejects undeclared files, traversal and symlinks.

## 10-um sizing with eight-section blocks

| Projection | Plane bytes | Maximum decoded block | Blocks |
| --- | ---: | ---: | ---: |
| AP | 1,824,000 | 14,592,000 | 165 |
| ML | 2,112,000 | 16,896,000 | 143 |
| DV | 3,009,600 | 24,076,800 | 100 |

All are below the reader's 64 MiB default decode limit. The 128 MiB cache holds at least five of
the largest blocks. The full three-orientation decoded representation is 7,223,040,000 bytes, but
only indexed compressed resources are stored and only one requested block is decoded.

## Fixture and benchmark

The committed 9-by-8-by-7 axis-coded fixture contains no Allen data. It proves byte-identical
generation, all projection orientations, partial-block coverage, per-block and whole-resource
integrity, deep metadata immutability, coordinate parity, LRU hits/eviction, zero-cache operation,
decode bounds, malformed indices, traversal and symlink rejection.

Run the reusable benchmark on a local pack:

```console
python tools/benchmark_intensity_blocks.py path/to/pack --iterations 100 \
  --json build/intensity-blocks-benchmark.json
```

The tiny fixture benchmark is a functional regression only; its roughly 0.05 ms cold reads do not
predict 10-um performance.

As an intermediate implementation check, the pinned real 50-um template produced three resources
of 5.49 MB (AP), 5.47 MB (ML), and 5.44 MB (DV). With eight-section blocks and 50 random reads per
axis on the recorded development host, median cold reads were 2.72 ms, 3.01 ms, and 3.99 ms; cached
same-block reads were about 0.003 ms before copying the returned plane. These are transport
measurements, not promises for the 125-times-larger 10-um volume.

## Real 10-um local result

The official `average_template_10.nrrd` was downloaded as 342,560,843 bytes and matched the
previously recorded SHA-256
`055b79034ea3ac47cf8776ecdb0c61d2b338d38ee5fd87d0962753efe600a775`. It decodes to
`uint16[1320, 1140, 800]` in AP/ML/DV order, with exact range 0–516 and a whole-volume 1st/99th
percentile display window of 0–252.

Eight-section blocks and gzip level 6 produced:

| Projection | Encoded bytes | Median cold read | Median warm read |
| --- | ---: | ---: | ---: |
| AP | 426,521,317 | 52.4 ms | 0.066 ms |
| ML | 412,257,113 | 56.2 ms | 0.063 ms |
| DV | 419,138,310 | 75.8 ms | 0.099 ms |

Total encoded transport is 1,257,916,740 bytes plus the manifest. The build took 3 minutes 41
seconds on the recorded development host. Full verification completed in 1.3 seconds with about 51
MB peak RSS after the source mapping was released. Thirty seeded random reads per axis produced
45.4, 57.5 and 70.4 ms browse medians. Adjacent navigation normally reuses the same decoded block:
seven of eight single-slice steps are warm until a block boundary is crossed.

Representative central blocks showed gzip level 6 at roughly 28–32 MB/s and level 9 at 8–11
MB/s, while level 9 saved less than 1% of encoded bytes. The builder therefore retains level 9 as
the deterministic fixture default but records and accepts an explicit level for real transports.

## Builder and provenance

`tools/build_intensity_blocks.py` accepts a C-order AP/ML/DV `uint16` NumPy volume or the official
embedded-gzip Allen NRRD and requires logical source ID/hash, reference-space ID, grid ID and
transform arguments. NRRD input is inflated to a temporary memory map rather than the Python heap;
resources stream to a temporary output and become visible atomically only when complete. The
builder never serializes a developer's local source path into tracked provenance. Gzip headers are
normalized across supported Python versions, and compression level plus block depth are recorded.

## Deferred

HTTP range fetching, persistent disk caching, request coalescing, workers, alternate codecs,
multiresolution pyramids, GPU bricking, arbitrary scalar types and publication are deliberately
deferred. This transport is for scalar anatomical intensity, not categorical annotation or vector
slice geometry.
