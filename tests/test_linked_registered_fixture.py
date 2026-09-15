from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from ibl_atlas_assets import open_anatomy_pack, open_registered_projection

FIXTURE = Path(__file__).parent / "fixtures" / "linked-registered-slices-v1" / "pack"


def test_linked_registered_fixture_covers_all_three_planes() -> None:
    expected = {"coronal": 9, "sagittal": 8, "horizontal": 7}
    for projection, count in expected.items():
        stack = open_registered_projection(FIXTURE / f"{projection}.json")
        assert stack.reference_space_id == "allen-ccf-2017"
        assert stack.grid_id == "synthetic-10um-grid-v1"
        assert stack.slice_count == count
        assert stack.display_slices == tuple(range(count))
        first = stack.load_slice(0)
        last = stack.load_slice(count - 1)
        assert first.paths[0].atlas_ids == {
            "allen": -997,
            "beryl": -997,
            "cosmos": -997,
        }
        assert first.paths[0].ring_count == 2
        assert last.paths[-1].atlas_ids == {"allen": 997, "beryl": 997, "cosmos": 997}


def test_linked_registered_fixture_is_reproducible(tmp_path: Path) -> None:
    output = tmp_path / "pack"
    subprocess.run(
        [sys.executable, "-m", "tools.build_linked_registered_fixture", str(output)],
        cwd=Path(__file__).parents[1],
        check=True,
    )
    expected = sorted(
        path.relative_to(FIXTURE) for path in FIXTURE.rglob("*") if path.is_file()
    )
    actual = sorted(
        path.relative_to(output) for path in output.rglob("*") if path.is_file()
    )
    assert actual == expected
    for relative in expected:
        assert (
            hashlib.sha256((output / relative).read_bytes()).digest()
            == hashlib.sha256((FIXTURE / relative).read_bytes()).digest()
        )


def test_linked_fixture_is_also_a_complete_anatomy_v2_pack() -> None:
    pack = open_anatomy_pack(
        FIXTURE / "anatomy-v2.json",
        reference_space_id="allen-ccf-2017",
        grid_id="synthetic-10um-grid-v1",
    )
    assert {item.world_slice_axis for item in pack.projections.values()} == {
        "ap",
        "ml",
        "dv",
    }
    pack.verify()
