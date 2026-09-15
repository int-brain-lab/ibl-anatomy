from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from jsonschema import ValidationError

from ibl_anatomy import open_intensity_block_pack

FIXTURE = Path(__file__).parent / "fixtures" / "intensity-blocks-v1" / "pack"


def _copy_pack(tmp_path: Path) -> Path:
    target = tmp_path / "pack"
    shutil.copytree(FIXTURE, target)
    return target


def _manifest(pack: Path) -> dict:
    return json.loads((pack / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(pack: Path, document: dict) -> None:
    (pack / "manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _expected() -> np.ndarray:
    ap, ml, dv = np.indices((9, 8, 7))
    return np.asarray(1000 * ap + 100 * ml + dv, dtype=np.uint16)


def test_fixture_identities_and_deterministic_builder(tmp_path) -> None:
    expected = {
        "ap.u16.blocks": (
            1032,
            "cc0341fe454fdef7163a732194ff7bd5497ac4f00d5fccd133b7afda89efe8c8",
        ),
        "dv.u16.blocks": (
            1077,
            "23ffa84ef847d74342a8c0b531e2af13a48a68d10f4986539f974ac5bd303569",
        ),
        "manifest.json": (
            5313,
            "751bd44d3c0032a2ff41a58e65a7c6ed6045be67ffcfbeab43106c166f692974",
        ),
        "ml.u16.blocks": (
            1062,
            "07b3a68ef45ee8d8d830f6c1f26f06292d3f5952b911f57fa61bc42617333604",
        ),
    }
    rebuilt = tmp_path / "rebuilt"
    subprocess.run(
        [sys.executable, "-m", "tools.build_intensity_fixture", str(rebuilt)],
        cwd=Path(__file__).parents[1],
        check=True,
    )
    for name, (size, digest) in expected.items():
        payload = (FIXTURE / name).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest
        assert (rebuilt / name).read_bytes() == payload


def test_verify_and_projection_native_sections() -> None:
    pack = open_intensity_block_pack(FIXTURE)
    assert pack.dataset_id == "synthetic-projection-intensity-v1"
    assert pack.reference_space_id == "allen-ccf-2017"
    assert pack.grid_id == "synthetic-10um-grid-v1"
    assert pack.value_range == (0, 8706)
    assert pack.recommended_display_range == (1, 8706)
    assert pack.shape == (9, 8, 7)
    pack.verify()
    expected = _expected()
    for axis, axis_index in zip(("ap", "ml", "dv"), range(3)):
        for index in (
            0,
            expected.shape[axis_index] // 2,
            expected.shape[axis_index] - 1,
        ):
            section = pack.read_section(axis, index)
            assert section.array_axes == tuple(
                item for item in ("ap", "ml", "dv") if item != axis
            )
            assert section.values.dtype == np.uint16
            assert section.values.flags.c_contiguous and section.values.flags.owndata
            np.testing.assert_array_equal(
                section.values, np.take(expected, index, axis=axis_index)
            )


def test_registered_voxel_center_transform_round_trip() -> None:
    pack = open_intensity_block_pack(FIXTURE)
    indices = np.asarray([[0, 0, 0], [4, 3.5, 2], [8, 7, 6]], dtype=float)
    expected_world = [[-35, 40, 20], [0, 0, 0], [35, -40, -40]]
    np.testing.assert_allclose(pack.index_to_world(indices), expected_world)
    np.testing.assert_allclose(pack.world_to_index(expected_world), indices)
    assert pack.grid.array_axes == ("ap", "ml", "dv")
    assert pack.grid.world_axes == ("ml", "ap", "dv")
    with pytest.raises(ValueError, match="finite triples"):
        pack.index_to_world([0, np.nan, 0])


def test_lru_cache_hits_eviction_clear_and_zero_cache() -> None:
    pack = open_intensity_block_pack(FIXTURE, max_cache_bytes=400)
    pack.read_section("ap", 0)
    first = pack.cache_info()
    assert (first.entries, first.bytes, first.hits, first.misses) == (1, 336, 0, 1)
    pack.read_section("ap", 2)
    assert pack.cache_info().hits == 1
    pack.read_section("ap", 4)
    evicted = pack.cache_info()
    assert (evicted.entries, evicted.bytes, evicted.hits, evicted.misses) == (
        1,
        336,
        1,
        2,
    )
    pack.clear_cache()
    assert pack.cache_info() == type(first)(0, 0, 1, 2)

    uncached = open_intensity_block_pack(FIXTURE, max_cache_bytes=0)
    uncached.read_section("dv", 0)
    uncached.read_section("dv", 0)
    assert uncached.cache_info() == type(first)(0, 0, 0, 2)


def test_concurrent_projection_reads_have_safe_cache_accounting() -> None:
    pack = open_intensity_block_pack(FIXTURE, max_cache_bytes=4096)
    expected = _expected()
    requests = [
        (axis, index)
        for _ in range(12)
        for axis, index in (("ap", 4), ("ml", 3), ("dv", 2))
    ]

    def read(request: tuple[str, int]) -> tuple[str, int, np.ndarray]:
        axis, index = request
        return axis, index, pack.read_section(axis, index).values

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(read, requests))

    for axis, index, values in results:
        np.testing.assert_array_equal(
            values, np.take(expected, index, axis=("ap", "ml", "dv").index(axis))
        )
    info = pack.cache_info()
    assert info.hits + info.misses == len(requests)
    assert info.entries == 3
    assert info.bytes == 1146


def test_configured_decode_bound_and_arguments() -> None:
    pack = open_intensity_block_pack(FIXTURE, max_decoded_block_bytes=335)
    with pytest.raises(ValueError, match="decoded block exceeds"):
        pack.read_section("ap", 0)
    with pytest.raises(ValueError, match="limits"):
        open_intensity_block_pack(FIXTURE, max_cache_bytes=-1)
    with pytest.raises(ValueError, match="projection axis"):
        open_intensity_block_pack(FIXTURE).read_section("x", 0)
    with pytest.raises(TypeError, match="integer"):
        open_intensity_block_pack(FIXTURE).read_section("ap", True)
    with pytest.raises(IndexError, match="outside"):
        open_intensity_block_pack(FIXTURE).read_section("ap", 9)


@pytest.mark.parametrize(
    ("mutate", "error", "message"),
    [
        (lambda x: x.__setitem__("format", "bad"), ValidationError, "was expected"),
        (
            lambda x: x["projections"]["ml"].__setitem__("axis", "ap"),
            ValueError,
            "axes differ",
        ),
        (
            lambda x: x["projections"]["dv"]["blocks"][0].__setitem__("block_id", 1),
            ValueError,
            "IDs",
        ),
        (
            lambda x: x["projections"]["ap"]["blocks"][1].__setitem__("offset", 0),
            ValueError,
            "index",
        ),
        (
            lambda x: x["projections"]["ml"]["blocks"][0].__setitem__(
                "section_count", 4
            ),
            ValueError,
            "section count",
        ),
        (
            lambda x: x["projections"]["dv"]["blocks"][0].__setitem__(
                "decoded_bytes", 2
            ),
            ValueError,
            "decoded byte",
        ),
        (lambda x: x["projections"]["ap"]["blocks"].pop(), ValueError, "cover"),
        (
            lambda x: x["projections"]["ml"]["resource"].__setitem__("bytes", 1),
            ValueError,
            "resource",
        ),
        (
            lambda x: x["projections"]["ml"]["resource"].__setitem__(
                "path", "ap.u16.blocks"
            ),
            ValueError,
            "paths are not unique",
        ),
        (
            lambda x: x["index_to_world_um"].__setitem__(15, 0),
            ValueError,
            "affine",
        ),
        (
            lambda x: x.__setitem__("index_to_world_um", [0] * 15 + [1]),
            ValueError,
            "invertible",
        ),
        (
            lambda x: x.__setitem__("value_range", [10, 1]),
            ValueError,
            "value range",
        ),
        (
            lambda x: x.__setitem__("recommended_display_range", [1, 9000]),
            ValueError,
            "display range",
        ),
    ],
)
def test_manifest_semantics(tmp_path, mutate, error, message) -> None:
    pack = _copy_pack(tmp_path)
    document = _manifest(pack)
    mutate(document)
    _write_manifest(pack, document)
    with pytest.raises(error, match=message):
        open_intensity_block_pack(pack)


def test_block_and_whole_resource_integrity(tmp_path) -> None:
    pack = _copy_pack(tmp_path)
    document = _manifest(pack)
    block = document["projections"]["ap"]["blocks"][0]
    path = pack / "ap.u16.blocks"
    payload = bytearray(path.read_bytes())
    payload[block["offset"] + 2] ^= 1
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="block SHA-256"):
        open_intensity_block_pack(pack).read_section("ap", 0)
    with pytest.raises(ValueError, match="resource SHA-256"):
        open_intensity_block_pack(pack).verify()


def test_complete_graph_traversal_symlink_and_invalid_json(tmp_path) -> None:
    pack = _copy_pack(tmp_path)
    (pack / "extra").write_bytes(b"x")
    with pytest.raises(ValueError, match="complete file graph"):
        open_intensity_block_pack(pack).verify()

    pack = _copy_pack(tmp_path / "traversal")
    document = _manifest(pack)
    document["projections"]["ap"]["resource"]["path"] = "../ap.u16.blocks"
    _write_manifest(pack, document)
    with pytest.raises(ValueError, match="escapes"):
        open_intensity_block_pack(pack).read_section("ap", 0)

    pack = _copy_pack(tmp_path / "symlink")
    source = tmp_path / "source.blocks"
    source.write_bytes((pack / "ap.u16.blocks").read_bytes())
    (pack / "ap.u16.blocks").unlink()
    (pack / "ap.u16.blocks").symlink_to(source)
    with pytest.raises(ValueError, match="symbolic|escapes"):
        open_intensity_block_pack(pack).read_section("ap", 0)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        open_intensity_block_pack(invalid)


def test_manifest_is_deeply_immutable() -> None:
    pack = open_intensity_block_pack(FIXTURE)
    with pytest.raises(TypeError, match="item assignment"):
        pack.manifest["shape"][0] = 1
