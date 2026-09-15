"""Regenerate the deterministic indexed-intensity transport fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from tools.build_intensity_blocks import build


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    ap, ml, dv = np.indices((9, 8, 7))
    values = np.asarray(1000 * ap + 100 * ml + dv, dtype=np.uint16)
    build(
        values,
        args.output,
        dataset_id="synthetic-projection-intensity-v1",
        reference_space_id="allen-ccf-2017",
        grid_id="synthetic-10um-grid-v1",
        index_to_world_um=[
            0,
            10,
            0,
            -35,
            -10,
            0,
            0,
            40,
            0,
            0,
            -10,
            20,
            0,
            0,
            0,
            1,
        ],
        sections_per_block=3,
        provenance={
            "kind": "deterministic axis-coded synthetic fixture",
            "generator": "tools/build_intensity_fixture.py",
            "license": "MIT",
        },
    )


if __name__ == "__main__":
    main()
