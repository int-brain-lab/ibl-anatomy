from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from jsonschema import ValidationError

from ibl_atlas_assets import open_volume_pack

FIXTURE = Path(__file__).parent / "fixtures" / "volume-pack-v1" / "pack"


def _copy_pack(tmp_path: Path) -> Path:
    target = tmp_path / "pack"
    shutil.copytree(FIXTURE, target)
    return target


def _manifest(pack: Path) -> dict:
    return json.loads((pack / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(pack: Path, manifest: dict) -> None:
    (pack / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _replace_volume(pack: Path, name: str, decoded: bytes) -> None:
    manifest = _manifest(pack)
    descriptor = manifest["volumes"][name]
    encoded = gzip.compress(decoded, compresslevel=9, mtime=0)
    (pack / descriptor["path"]).write_bytes(encoded)
    descriptor["bytes"] = len(encoded)
    descriptor["sha256"] = hashlib.sha256(encoded).hexdigest()
    descriptor["decoded_bytes"] = len(decoded)
    descriptor["decoded_sha256"] = hashlib.sha256(decoded).hexdigest()
    _write_manifest(pack, manifest)


def test_fixture_byte_identities() -> None:
    expected = {
        "annotation.u16.gz": (
            38,
            "27d7a4d6551a03acefadb8f3db4d862580281daac3505e1f3e2a43a8cdb45844",
        ),
        "manifest.json": (
            2025,
            "d715936c7b0580c0c6e7554a9cbb4b38c5d0eb9066ef7fa0b96ae913960369f4",
        ),
        "regions.json": (
            3596,
            "f757cc3c3e54f5875a75ccf0b6118f06a09443da7b199209d2fa2a20ab84895a",
        ),
        "template.u16.gz": (
            120,
            "78475364912d51fd2fafaa22b9aa97b3d5dc10caf911cddc9d6360506fe4a38c",
        ),
    }
    for name, (size, digest) in expected.items():
        payload = (FIXTURE / name).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_open_verify_and_load_owned_arrays() -> None:
    pack = open_volume_pack(FIXTURE)
    assert pack.pack_id == "synthetic-atlas-volume-v1"
    assert pack.reference_space_id == "allen-ccf-2017"
    assert pack.first_right_ml_index == 2
    pack.verify()
    volumes = pack.load_volumes()
    assert volumes.template.shape == (4, 5, 3)
    assert volumes.annotation.shape == (4, 5, 3)
    assert volumes.template.dtype == np.uint16
    assert volumes.annotation.dtype == np.uint16
    assert all(
        value.flags.c_contiguous and value.flags.owndata
        for value in (volumes.template, volumes.annotation)
    )
    ap, ml, dv = np.indices(volumes.template.shape)
    np.testing.assert_array_equal(volumes.template, 100 * ap + 10 * ml + dv)
    assert set(np.unique(volumes.annotation)) == {0, 1, 2, 3, 4}
    assert volumes.region_for_source_index(4).atlas_id == -8
    assert volumes.region_for_source_index(2).atlas_id == 8
    with pytest.raises(KeyError, match="unknown annotation"):
        volumes.region_for_source_index(5)
    assert volumes.regions_by_source_index[2].atlas_id == 8
    with pytest.raises(TypeError, match="mappingproxy|item assignment"):
        volumes.regions_by_source_index[2] = volumes.regions_by_source_index[4]
    with pytest.raises(TypeError, match="item assignment"):
        pack.manifest["grid"]["shape"][0] = 10


def test_coordinates_preserve_off_grid_hemisphere_boundary() -> None:
    volumes = open_volume_pack(FIXTURE).load_volumes()
    np.testing.assert_allclose(
        volumes.grid.index_to_world([[0, 0, 0], [0, 2, 0], [3, 4, 2]]),
        [[-239, 100, 100], [-39, 100, 100], [161, -200, -100]],
    )
    points = np.array([[-139, 0, 0], [-39, -100, 0]], dtype=float)
    np.testing.assert_allclose(
        volumes.grid.index_to_world(volumes.grid.world_to_index(points)), points
    )
    # ML index 2 is explicitly right despite its voxel center lying at -39 um.
    assert volumes.region_for_source_index(volumes.annotation[1, 2, 1]).atlas_id == 8
    np.testing.assert_array_equal(volumes.annotation_index_at_world(points), [4, 1])
    with pytest.raises(ValueError, match="outside"):
        volumes.annotation_index_at_world([[10000, 0, 0]])
    np.testing.assert_array_equal(
        volumes.annotation_index_at_world([[10000, 0, 0]], mode="clip"), [0]
    )
    with pytest.raises(ValueError, match="finite"):
        volumes.grid.index_to_world([0, np.nan, 0])


@pytest.mark.parametrize(
    ("axis", "index", "shape", "axes"),
    [
        ("ap", 1, (5, 3), ("ml", "dv")),
        ("ml", 2, (4, 3), ("ap", "dv")),
        ("dv", 1, (4, 5), ("ap", "ml")),
    ],
)
def test_slices_have_explicit_unflipped_axes(axis, index, shape, axes) -> None:
    volumes = open_volume_pack(FIXTURE).load_volumes()
    section = volumes.slice("template", axis, index)
    assert section.values.shape == shape
    assert section.array_axes == axes
    assert section.values.flags.c_contiguous and section.values.flags.owndata
    axis_index = volumes.grid.array_axes.index(axis)
    np.testing.assert_array_equal(
        section.values, np.take(volumes.template, index, axis_index)
    )
    with pytest.raises(IndexError, match="outside"):
        volumes.slice("template", axis, 100)


@pytest.mark.parametrize(
    ("mutate", "error", "message"),
    [
        (lambda x: x.__setitem__("format", "bad"), ValidationError, "was expected"),
        (
            lambda x: x["grid"].__setitem__("array_axes", ["ml", "ap", "dv"]),
            ValidationError,
            "was expected",
        ),
        (
            lambda x: x["grid"].__setitem__("world_units", "m"),
            ValidationError,
            "was expected",
        ),
        (
            lambda x: x["grid"]["index_to_world_um"].__setitem__(0, float("nan")),
            ValueError,
            "finite",
        ),
        (
            lambda x: x["grid"].__setitem__("index_to_world_um", [0] * 15 + [1]),
            ValueError,
            "invertible",
        ),
        (
            lambda x: x["grid"]["index_to_world_um"].__setitem__(0, 1),
            ValueError,
            "axis-aligned",
        ),
        (
            lambda x: x["grid"]["index_to_world_um"].__setitem__(10, -50),
            ValueError,
            "isotropic",
        ),
        (
            lambda x: x["hemisphere_boundary"].__setitem__("first_right_index", 5),
            ValueError,
            "outside",
        ),
        (
            lambda x: x["volumes"]["annotation"].__setitem__("decoded_bytes", 118),
            ValueError,
            "differs from grid",
        ),
        (
            lambda x: x["volumes"]["annotation"].__setitem__("path", "template.u16.gz"),
            ValueError,
            "resource path",
        ),
    ],
)
def test_manifest_schema_and_semantics(tmp_path, mutate, error, message) -> None:
    pack = _copy_pack(tmp_path)
    manifest = _manifest(pack)
    mutate(manifest)
    _write_manifest(pack, manifest)
    with pytest.raises(error, match=message):
        open_volume_pack(pack)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bytes", 1, "encoded byte length"),
        ("sha256", "0" * 64, "encoded SHA-256"),
        ("decoded_sha256", "0" * 64, "decoded SHA-256"),
    ],
)
def test_resource_integrity(tmp_path, field, value, message) -> None:
    pack = _copy_pack(tmp_path)
    manifest = _manifest(pack)
    manifest["volumes"]["template"][field] = value
    _write_manifest(pack, manifest)
    with pytest.raises(ValueError, match=message):
        open_volume_pack(pack).verify()


def test_missing_corrupt_and_truncated_resources(tmp_path) -> None:
    pack = _copy_pack(tmp_path)
    (pack / "template.u16.gz").unlink()
    with pytest.raises(ValueError, match="complete file graph"):
        open_volume_pack(pack).verify()

    pack = _copy_pack(tmp_path / "corrupt")
    payload = bytearray((pack / "template.u16.gz").read_bytes())
    payload[-1] ^= 1
    (pack / "template.u16.gz").write_bytes(payload)
    manifest = _manifest(pack)
    descriptor = manifest["volumes"]["template"]
    descriptor["sha256"] = hashlib.sha256(payload).hexdigest()
    _write_manifest(pack, manifest)
    with pytest.raises(ValueError, match="gzip data is invalid"):
        open_volume_pack(pack).verify()

    pack = _copy_pack(tmp_path / "short")
    decoded = gzip.decompress((pack / "template.u16.gz").read_bytes())[:-2]
    _replace_volume(pack, "template", decoded)
    manifest = _manifest(pack)
    manifest["volumes"]["template"]["decoded_bytes"] += 2
    _write_manifest(pack, manifest)
    with pytest.raises(ValueError, match="decoded byte length"):
        open_volume_pack(pack).verify()


def test_traversal_and_symlink_escape_are_rejected(tmp_path) -> None:
    pack = _copy_pack(tmp_path)
    manifest = _manifest(pack)
    manifest["volumes"]["template"]["path"] = "../template.u16.gz"
    _write_manifest(pack, manifest)
    with pytest.raises(ValueError, match="escapes"):
        open_volume_pack(pack).verify()

    pack = _copy_pack(tmp_path / "link")
    target = tmp_path / "outside.gz"
    target.write_bytes((pack / "template.u16.gz").read_bytes())
    (pack / "template.u16.gz").unlink()
    (pack / "template.u16.gz").symlink_to(target)
    with pytest.raises(ValueError, match="escapes|symbolic link"):
        open_volume_pack(pack).verify()


def test_catalog_hash_unknown_index_and_wrong_side_are_rejected(tmp_path) -> None:
    pack = _copy_pack(tmp_path)
    manifest = _manifest(pack)
    manifest["region_catalog"]["sha256"] = "0" * 64
    _write_manifest(pack, manifest)
    with pytest.raises(ValueError, match="SHA-256"):
        open_volume_pack(pack).verify()

    for dirname, index, offset, message in (
        ("unknown", 5, (1, 1, 1), "unknown source"),
        ("wrong-left", 2, (1, 1, 1), "left half"),
        ("wrong-right", 4, (1, 2, 1), "right half"),
    ):
        pack = _copy_pack(tmp_path / dirname)
        annotation = (
            np.frombuffer(
                gzip.decompress((pack / "annotation.u16.gz").read_bytes()), dtype="<u2"
            )
            .reshape(4, 5, 3)
            .copy()
        )
        annotation[offset] = index
        _replace_volume(pack, "annotation", annotation.astype("<u2").tobytes())
        with pytest.raises(ValueError, match=message):
            open_volume_pack(pack).verify()


def test_invalid_json_and_bad_lookup_options() -> None:
    volumes = open_volume_pack(FIXTURE).load_volumes()
    with pytest.raises(ValueError, match="mode"):
        volumes.annotation_index_at_world([[0, 0, 0]], mode="wrap")
    with pytest.raises(ValueError, match="volume must"):
        volumes.slice("bad", "ml", 0)
    with pytest.raises(ValueError, match="slice axis"):
        volumes.slice("template", "x", 0)


def test_invalid_json_and_decoded_resource_limit(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        open_volume_pack(manifest)

    pack = _copy_pack(tmp_path / "large")
    document = _manifest(pack)
    document["grid"]["shape"] = [65535, 4097, 1]
    decoded_bytes = 65535 * 4097 * 2
    for descriptor in document["volumes"].values():
        descriptor["decoded_bytes"] = decoded_bytes
    _write_manifest(pack, document)
    with pytest.raises(ValueError, match="resource limit"):
        open_volume_pack(pack).verify()
