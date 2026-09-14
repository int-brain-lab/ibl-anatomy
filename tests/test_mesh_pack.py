from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import struct
from pathlib import Path

import numpy as np
import pytest
from jsonschema import ValidationError

from ibl_atlas_assets import open_mesh_pack
from ibl_atlas_assets.binary import decode_raw_lod

FIXTURE = Path(__file__).parent / "fixtures" / "mesh-pack-v1" / "pack"


def _copy_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack"
    shutil.copytree(FIXTURE, pack)
    return pack


def _manifest(pack: Path) -> dict:
    return json.loads((pack / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(pack: Path, manifest: dict) -> None:
    (pack / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def _replace_lod(pack: Path, decoded: bytes) -> None:
    encoded = gzip.compress(decoded, compresslevel=9, mtime=0)
    (pack / "default.eam3.gz").write_bytes(encoded)
    manifest = _manifest(pack)
    descriptor = manifest["lods"][0]["resource"]
    descriptor["bytes"] = len(encoded)
    descriptor["sha256"] = hashlib.sha256(encoded).hexdigest()
    descriptor["codec"]["decoded_bytes"] = len(decoded)
    _write_manifest(pack, manifest)


def test_fixture_identities() -> None:
    expected = {
        "manifest.json": (
            3917,
            "6076d1604f67b3e711506e0d400adf58db49f5f6077790ca4d96d2557c56737a",
        ),
        "default.eam3.gz": (
            392,
            "750342e13223ce90dbfa09672e95159997ce2e807822a86843d4319eeffac260",
        ),
        "validation-report.json": (
            495,
            "6ecd7b00c7ac84eb4b2a0675cfc316b396629827b08cf88b60823dd9924233e0",
        ),
    }
    for name, (size, digest) in expected.items():
        data = (FIXTURE / name).read_bytes()
        assert len(data) == size
        assert hashlib.sha256(data).hexdigest() == digest


def test_decoded_fixture_identities() -> None:
    decoded = gzip.decompress((FIXTURE / "default.eam3.gz").read_bytes())
    assert hashlib.sha256(decoded).hexdigest() == (
        "92614e2e836828a8b8637342ea8f9384d43351817921833a9d384977b0c17a39"
    )
    chunks = decode_raw_lod(decoded)
    expected = {
        "positions": "7045ad9561e3e5e096e4b179da64cb08a200c7a12597c9f6a65addd5a5578f4b",
        "normals": "5b2dc2fe6f552d459b6e6d62a61acb2999a43cb2fd73fa363c878efc8bad3d8f",
        "component_ids": "23d141876edd0e214adc19f40b085c8d014e0d1eb54eaf6312cca9b02ea5cb15",
        "indices": "ce813f91b441de766386fa7cf3055ff218df5dd0d398043fb1d32e6e8ff8bd54",
    }
    for name, digest in expected.items():
        payload = b"".join(getattr(chunk, name).tobytes(order="C") for chunk in chunks)
        assert hashlib.sha256(payload).hexdigest() == digest


def test_open_verify_and_decode_valid_fixture() -> None:
    pack = open_mesh_pack(FIXTURE)
    pack.verify()
    geometry = pack.load_geometry()

    assert geometry.positions.shape == (10, 3)
    assert geometry.positions.dtype == np.float32
    assert geometry.normals.shape == (10, 3)
    assert geometry.normals.dtype == np.float32
    assert geometry.component_ids.shape == (10,)
    assert geometry.component_ids.dtype == np.uint16
    assert geometry.indices.shape == (36,)
    assert geometry.indices.dtype == np.uint32
    assert all(
        array.flags.c_contiguous and array.flags.owndata
        for array in (
            geometry.positions,
            geometry.normals,
            geometry.component_ids,
            geometry.indices,
        )
    )
    assert [item.component_id for item in geometry.ranges] == [0, 1]
    assert geometry.reference_space == "allen-ccf-2017"
    assert geometry.coordinate_system["world_axes"] == ["ml", "ap", "dv"]
    assert [item["signed_allen_id"] for item in geometry.presentations] == [-315, 315]
    assert [item["mappings"]["beryl"] for item in geometry.presentations] == [
        None,
        None,
    ]


def test_renderer_neutral_identity_helpers_and_immutable_metadata() -> None:
    pack = open_mesh_pack(FIXTURE)
    assert pack.presentation_for_component(0, -1)["signed_allen_id"] == -315
    assert pack.presentation_for_component(0, 0)["signed_allen_id"] == 315
    assert pack.presentation_for_component(1, -100)["signed_allen_id"] == 315
    assert pack.mapped_region_id(1, "cosmos") == 315
    with pytest.raises(TypeError, match="mappingproxy|immutable"):
        pack.components[0]["source_allen_id"] = 999
    with pytest.raises(TypeError, match="immutable"):
        pack.coordinate_system["world_axes"].append("bad")
    geometry = pack.load_geometry()
    assert geometry.presentation_boundary["coordinate"] == "original-world-ml"
    assert geometry.presentation_for_component(0, -1)["signed_allen_id"] == -315
    assert geometry.mapped_region_id(1, "allen") == 315


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda manifest: manifest["geometry_scope"]["active_allen_ids"].append(
                1009
            ),
            "overlap",
        ),
        (
            lambda manifest: manifest["components"][0]["centroid_um"].__setitem__(
                0, float("nan")
            ),
            "must be finite",
        ),
    ],
)
def test_manifest_mesh_semantics_are_validated(
    tmp_path: Path, change, message: str
) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    change(manifest)
    _write_manifest(pack_path, manifest)
    with pytest.raises(ValueError, match=message):
        open_mesh_pack(pack_path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda manifest: manifest["presentations"][1].__setitem__(
                "presentation_id", 2
            ),
            "contiguous",
        ),
        (
            lambda manifest: manifest["presentations"][0]["mappings"].__setitem__(
                "beryl", 315
            ),
            "beryl mapping",
        ),
        (
            lambda manifest: manifest["presentations"][0]["mappings"].__setitem__(
                "cosmos", -997
            ),
            "cosmos mapping",
        ),
        (
            lambda manifest: manifest["components"][1].__setitem__(
                "lateralization", "neutral"
            ),
            "presentation sides",
        ),
        (
            lambda manifest: manifest["components"][0]["centroid_um"].__setitem__(
                0, 3.0
            ),
            "centroid or bounds",
        ),
        (
            lambda manifest: manifest["lods"][0].__setitem__(
                "actual_triangle_ratio", 0.5
            ),
            "triangle ratio",
        ),
        (
            lambda manifest: manifest["lods"][0]["decoder"].__setitem__(
                "position_bits", 14
            ),
            "raw mesh LOD",
        ),
        (
            lambda manifest: manifest["validation"]["report"].__setitem__(
                "path", "default.eam3.gz"
            ),
            "resource path",
        ),
    ],
)
def test_authoritative_mesh_semantic_regressions(
    tmp_path: Path, mutate, message: str
) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    mutate(manifest)
    _write_manifest(pack_path, manifest)
    with pytest.raises(ValueError, match=message):
        open_mesh_pack(pack_path)


def test_hash_failure_precedes_decoding(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    path = pack_path / "default.eam3.gz"
    encoded = bytearray(path.read_bytes())
    encoded[0] ^= 0xFF
    path.write_bytes(encoded)

    with pytest.raises(ValueError, match="SHA-256 differs"):
        open_mesh_pack(pack_path).verify()


def test_missing_and_undeclared_resources(tmp_path: Path) -> None:
    missing = _copy_pack(tmp_path / "missing")
    (missing / "default.eam3.gz").unlink()
    with pytest.raises(FileNotFoundError, match="resource is missing"):
        open_mesh_pack(missing).verify()

    undeclared = _copy_pack(tmp_path / "undeclared")
    (undeclared / "extra.txt").write_text("not declared", encoding="utf-8")
    with pytest.raises(ValueError, match="undeclared files"):
        open_mesh_pack(undeclared).verify()


def test_manifest_rejects_resource_traversal(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["lods"][0]["resource"]["path"] = "../default.eam3.gz"
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValidationError):
        open_mesh_pack(pack_path)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "truncated"),
        (b"FAIL" + b"\0" * 8, "magic"),
        (b"EAM3" + struct.pack("<II", 2, 0), "version"),
        (b"EAM3" + struct.pack("<II", 1, 100), "header is truncated"),
    ],
)
def test_raw_decoder_rejects_invalid_prefix(data: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode_raw_lod(data)


def test_raw_decoder_rejects_out_of_bounds_array(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    decoded = bytearray(gzip.decompress((pack_path / "default.eam3.gz").read_bytes()))
    header_length = struct.unpack_from("<I", decoded, 8)[0]
    header = json.loads(decoded[12 : 12 + header_length])
    header["chunks"][0]["arrays"]["indices"]["byte_offset"] = 999
    replacement = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    assert len(replacement) == header_length
    decoded[12 : 12 + header_length] = replacement
    _replace_lod(pack_path, bytes(decoded))

    with pytest.raises(ValueError, match="out of bounds"):
        open_mesh_pack(pack_path).verify()


def test_component_range_identity_is_validated(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    decoded = bytearray(gzip.decompress((pack_path / "default.eam3.gz").read_bytes()))
    header_length = struct.unpack_from("<I", decoded, 8)[0]
    header = json.loads(decoded[12 : 12 + header_length])
    header["chunks"][0]["ranges"][0]["right_presentation_id"] = 0
    replacement = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    assert len(replacement) == header_length
    decoded[12 : 12 + header_length] = replacement
    _replace_lod(pack_path, bytes(decoded))

    with pytest.raises(ValueError, match="presentation identity differs"):
        open_mesh_pack(pack_path).verify()


def test_manifest_component_ids_are_unique(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["components"][1]["component_id"] = 0
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="component IDs are not unique"):
        open_mesh_pack(pack_path).verify()


def test_manifest_presentation_ids_are_unique(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["presentations"][1]["presentation_id"] = 0
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="presentation IDs are not unique"):
        open_mesh_pack(pack_path).verify()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("signed_allen_id", 315, "side and signed ID differ"),
        ("source_allen_id", 999, "source and signed ID differ"),
    ],
)
def test_presentation_signed_identity_is_validated(
    tmp_path: Path, field: str, value: int, message: str
) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["presentations"][0][field] = value
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match=message):
        open_mesh_pack(pack_path).verify()


def test_presentation_allen_mapping_is_validated(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["presentations"][0]["mappings"]["allen"] = -997
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="Allen mapping differs"):
        open_mesh_pack(pack_path).verify()


def test_component_declared_counts_are_validated(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    manifest = _manifest(pack_path)
    manifest["components"][0]["vertex_count"] += 1
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="declared counts differ"):
        open_mesh_pack(pack_path).verify()


def test_gzip_and_resource_limit_are_validated(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    invalid = b"not a gzip stream"
    (pack_path / "default.eam3.gz").write_bytes(invalid)
    manifest = _manifest(pack_path)
    descriptor = manifest["lods"][0]["resource"]
    descriptor["bytes"] = len(invalid)
    descriptor["sha256"] = hashlib.sha256(invalid).hexdigest()
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="gzip is invalid"):
        open_mesh_pack(pack_path).verify()
    with pytest.raises(ValueError, match="configured byte limit"):
        open_mesh_pack(FIXTURE, max_resource_bytes=300).verify()


def test_resource_symlink_may_not_escape_pack(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    outside = tmp_path / "outside.eam3.gz"
    shutil.copyfile(pack_path / "default.eam3.gz", outside)
    (pack_path / "default.eam3.gz").unlink()
    (pack_path / "default.eam3.gz").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes pack"):
        open_mesh_pack(pack_path).verify()


def test_unknown_lod_and_invalid_resource_limit() -> None:
    pack = open_mesh_pack(FIXTURE)
    with pytest.raises(KeyError, match="unknown mesh LOD"):
        pack.load_geometry("missing")
    with pytest.raises(ValueError, match="must be positive"):
        open_mesh_pack(FIXTURE, max_resource_bytes=0)


def test_validation_report_identity_is_validated(tmp_path: Path) -> None:
    pack_path = _copy_pack(tmp_path)
    report_path = pack_path / "validation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["pack_id"] = "different-pack"
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report_path.write_bytes(encoded)
    manifest = _manifest(pack_path)
    descriptor = manifest["validation"]["report"]
    descriptor["bytes"] = len(encoded)
    descriptor["sha256"] = hashlib.sha256(encoded).hexdigest()
    descriptor["codec"]["decoded_bytes"] = len(encoded)
    _write_manifest(pack_path, manifest)

    with pytest.raises(ValueError, match="report identity differs"):
        open_mesh_pack(pack_path).verify()
