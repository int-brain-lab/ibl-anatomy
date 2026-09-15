"""Benchmark cold, warm and browsing reads from an indexed intensity pack."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path

from ibl_anatomy import open_intensity_block_pack


def _milliseconds(call) -> float:
    started = time.perf_counter_ns()
    call()
    return (time.perf_counter_ns() - started) / 1_000_000


def benchmark(pack_path: Path, iterations: int, seed: int) -> dict:
    pack = open_intensity_block_pack(pack_path)
    generator = random.Random(seed)
    result = {
        "dataset_id": pack.dataset_id,
        "reference_space_id": pack.reference_space_id,
        "grid_id": pack.grid_id,
        "shape_ap_ml_dv": list(pack.shape),
        "iterations": iterations,
        "axes": {},
    }
    for axis_index, axis in enumerate(("ap", "ml", "dv")):
        count = pack.shape[axis_index]
        indices = [generator.randrange(count) for _ in range(iterations)]
        cold = []
        for index in indices:
            pack.clear_cache()
            cold.append(
                _milliseconds(
                    lambda axis=axis, index=index: pack.read_section(axis, index)
                )
            )
        center = count // 2
        pack.clear_cache()
        pack.read_section(axis, center)
        warm = [
            _milliseconds(
                lambda axis=axis, center=center: pack.read_section(axis, center)
            )
            for _ in range(iterations)
        ]
        pack.clear_cache()
        before_browse = pack.cache_info()
        browse = [
            _milliseconds(lambda axis=axis, index=index: pack.read_section(axis, index))
            for index in indices
        ]
        plane_bytes = 2
        for dimension, size in zip(("ap", "ml", "dv"), pack.shape):
            if dimension != axis:
                plane_bytes *= size
        projection = pack.manifest["projections"][axis]
        maximum_decoded = max(block["decoded_bytes"] for block in projection["blocks"])
        after_browse = pack.cache_info()
        result["axes"][axis] = {
            "plane_bytes": plane_bytes,
            "maximum_block_decoded_bytes": maximum_decoded,
            "maximum_decode_amplification": maximum_decoded / plane_bytes,
            "cold_median_ms": statistics.median(cold),
            "warm_median_ms": statistics.median(warm),
            "browse_median_ms": statistics.median(browse),
            "browse_cache": {
                "entries": after_browse.entries,
                "bytes": after_browse.bytes,
                "hits": after_browse.hits - before_browse.hits,
                "misses": after_browse.misses - before_browse.misses,
            },
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.iterations < 1:
        raise ValueError("benchmark iterations must be positive")
    result = benchmark(args.pack, args.iterations, args.seed)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
