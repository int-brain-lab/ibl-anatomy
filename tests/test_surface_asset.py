from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ibl_anatomy import (
    PinnedResource,
    bundled_surface_asset,
    load_surface_asset,
    materialize_surface_asset,
    parse_surface_asset,
)


OBJ = b"""# synthetic tetrahedron
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
vn -1 -1 -1
vn 1 0 0
vn 0 1 0
vn 0 0 1
f 1//1 3//3 2//2
f 1//1 2//2 4//4
f 1//1 4//4 3//3
f 2//2 3//3 4//4
"""


def fixture_source(tmp_path):
    path = tmp_path / "fixture.obj"
    path.write_bytes(OBJ)
    asset = replace(
        bundled_surface_asset(),
        asset_id="synthetic-test-only",
        source=PinnedResource(path.as_uri(), len(OBJ), hashlib.sha256(OBJ).hexdigest()),
        expected_vertices=4,
        expected_triangles=4,
        expected_boundary_edges=0,
    )
    return path, asset


def test_default_is_pinned_allen_reference_envelope():
    asset = bundled_surface_asset()
    assert asset.role == "brain-envelope"
    assert asset.variant == "source-native"
    assert asset.source_allen_id == 997
    assert (asset.expected_vertices, asset.expected_triangles) == (49324, 98638)
    assert asset.expected_boundary_edges == 6
    assert asset.reference_space_id == "allen-ccf-2017"


def test_world_transform_normals_winding_and_owned_arrays(tmp_path):
    path, asset = fixture_source(tmp_path)
    geometry = load_surface_asset(path, asset)
    np.testing.assert_array_equal(geometry.positions_um[0], [-5739, 5400, 332])
    np.testing.assert_array_equal(geometry.positions_um[1], [-5739, 5399, 332])
    np.testing.assert_array_equal(geometry.positions_um[2], [-5739, 5400, 331])
    np.testing.assert_array_equal(geometry.positions_um[3], [-5738, 5400, 332])
    np.testing.assert_allclose(geometry.normals[0], [-1, 1, 1] / np.sqrt(3), rtol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(geometry.normals, axis=1), 1, rtol=1e-6)
    assert geometry.indices.tolist() == [0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]
    for array in (geometry.positions_um, geometry.normals, geometry.indices):
        assert array.flags.owndata and array.flags.c_contiguous
    geometry.positions_um[:] = 0
    assert load_surface_asset(path, asset).positions_um[0, 0] == -5739


def test_materialization_download_local_source_and_no_overwrite(tmp_path):
    source, asset = fixture_source(tmp_path)
    target = tmp_path / "downloaded"
    result = materialize_surface_asset(target, asset)
    assert result.asset == asset
    assert (target / "surface.obj").read_bytes() == OBJ
    local = tmp_path / "copied"
    materialize_surface_asset(local, asset, source_path=source)
    with pytest.raises(FileExistsError):
        materialize_surface_asset(local, asset)


def test_integrity_and_failed_materialization_cleanup(tmp_path):
    source, asset = fixture_source(tmp_path)
    source.write_bytes(OBJ.replace(b"v 1 0 0", b"v 2 0 0"))
    with pytest.raises(ValueError, match="SHA-256"):
        load_surface_asset(source, asset)
    target = tmp_path / "failed"
    with pytest.raises(ValueError, match="SHA-256"):
        materialize_surface_asset(target, asset, source_path=source)
    assert not target.exists()
    assert not list(tmp_path.glob(".failed-*"))
    source.write_bytes(OBJ + b"\n")
    with pytest.raises(ValueError, match="byte length"):
        load_surface_asset(source, asset)


def test_expectations_and_topology_fail_closed(tmp_path):
    source, asset = fixture_source(tmp_path)
    with pytest.raises(ValueError, match="expectations"):
        load_surface_asset(source, replace(asset, expected_triangles=3))
    with pytest.raises(ValueError, match="topology"):
        load_surface_asset(source, replace(asset, expected_boundary_edges=1))


@pytest.mark.parametrize(
    "field,value", [("variant", "smoothed"), ("role", "region"), ("source_allen_id", 8)]
)
def test_lock_rejects_unsupported_policies(field, value):
    from importlib.resources import files

    document = json.loads(
        files("ibl_anatomy.asset_sets").joinpath("allen-root.json").read_text()
    )
    document[field] = value
    with pytest.raises(ValueError):
        parse_surface_asset(document)


def test_lock_rejects_nonrigid_transform():
    from importlib.resources import files

    document = json.loads(
        files("ibl_anatomy.asset_sets").joinpath("allen-root.json").read_text()
    )
    document["coordinate_system"]["source_to_world_um"][0][2] = 2
    with pytest.raises(ValueError, match="rigid"):
        parse_surface_asset(document)


@pytest.mark.skipif(
    not os.environ.get("IBL_ALLEN_ROOT_SOURCE"), reason="real source not configured"
)
def test_real_allen_envelope():
    geometry = load_surface_asset(Path(os.environ["IBL_ALLEN_ROOT_SOURCE"]))
    assert geometry.positions_um.shape == (49324, 3)
    assert geometry.indices.shape == (295914,)
    np.testing.assert_allclose(
        geometry.positions_um.min(axis=0), [-5253.271, -7792.5, -7232.24], atol=0.002
    )
    np.testing.assert_allclose(
        geometry.positions_um.max(axis=0), [5151.5996, 5416.83, 198.07], atol=0.002
    )
