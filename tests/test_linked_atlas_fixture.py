from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np

from ibl_anatomy import open_region_catalog, open_volume_pack

FIXTURE = Path(__file__).parent / "fixtures" / "linked-atlas-v1" / "volume-pack"


def _digests(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def test_fixture_is_byte_identical_and_reproducible(tmp_path: Path) -> None:
    expected = {
        "annotation.u16.gz": "cd5fe17c1cd890932b7cd2632a52a920565a732ad8f5cb5605e2bb607c2050bd",
        "manifest.json": "06b2d5dd239a7ecf51a6a8cf9cec555b9f481aa0785ec37f966d68e49130bce6",
        "regions.json": "e1a7da62db7fa5806090de08f931d1b320059d31f2fa86feb7103b0903870f0e",
        "template.u16.gz": "76aa5db6d04a8a1f09107ed840aba266411542887b8dc14d4bb0693ea66d1e7e",
    }
    assert _digests(FIXTURE) == expected
    generated = tmp_path / "volume-pack"
    root = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            str(root / "tools/build_volume_fixture.py"),
            "--profile",
            "linked-atlas",
            str(generated),
            "--catalog",
            str(root / "tests/fixtures/atlas-regions-v1/regions.json"),
        ],
        check=True,
    )
    assert _digests(generated) == expected


def test_fixture_covers_mesh_and_preserves_signed_region_identity() -> None:
    pack = open_volume_pack(FIXTURE)
    pack.verify()
    volumes = pack.load_volumes()
    assert volumes.template.shape == (3, 9, 3)
    assert volumes.first_right_ml_index == 3
    # Voxel edges, rather than centers, are used for mesh coverage.
    centers = volumes.grid.index_to_world([[0, 0, 0], [2, 8, 2]])
    edges_min = centers.min(axis=0) - 0.5
    edges_max = centers.max(axis=0) + 0.5
    np.testing.assert_array_equal(edges_min, [-3.5, -1.5, -1.5])
    np.testing.assert_array_equal(edges_max, [5.5, 1.5, 1.5])
    # Compare each world axis to the mesh fixture's approximate bounds.
    assert edges_min[0] <= -2 <= edges_max[0]
    assert edges_min[0] <= 5 <= edges_max[0]
    assert edges_min[1] <= -1 <= 1 <= edges_max[1]
    assert edges_min[2] <= -1 <= 1 <= edges_max[2]
    assert set(np.unique(volumes.annotation)) == {0, 5, 6}
    assert volumes.region_for_source_index(5).atlas_id == -315
    assert volumes.region_for_source_index(6).atlas_id == 315


def test_fixture_catalog_mapping_parity() -> None:
    catalog = open_region_catalog(FIXTURE / "regions.json")
    assert [row.atlas_id for row in catalog.physical("allen")[-2:]] == [-315, 315]
    assert catalog.map_allen_ids([-315, 315], "allen") == (-315, 315)
    assert catalog.map_allen_ids([-315, 315], "cosmos") == (-315, 315)
    assert catalog.map_allen_ids([-315, 315], "beryl") == (None, None)
    assert catalog.physical("beryl")[-2].mapping_member is False
    assert catalog.physical("beryl")[-1].mapping_member is False
