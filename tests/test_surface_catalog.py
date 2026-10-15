import hashlib
import json
import os
from copy import deepcopy
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
from test_surface_asset import OBJ

from ibl_anatomy import (
    PinnedResource,
    bundled_surface_asset,
    bundled_surface_catalog,
    load_surface_catalog,
    materialize_surface_catalog,
    parse_surface_asset,
    parse_surface_catalog,
)


def document():
    return json.loads(
        files("ibl_anatomy.asset_sets").joinpath("allen-major-context.json").read_text()
    )


def synthetic_catalog(tmp_path):
    catalog = bundled_surface_catalog()
    members = []
    for member in catalog.members[:2]:
        identity = member.asset.source_allen_id
        path = tmp_path / f"{identity}.obj"
        path.write_bytes(OBJ)
        asset = replace(
            member.asset,
            source=PinnedResource(
                path.as_uri(), len(OBJ), hashlib.sha256(OBJ).hexdigest()
            ),
            expected_vertices=4,
            expected_triangles=4,
            expected_boundary_edges=0,
        )
        members.append(replace(member, asset=asset))
    return replace(catalog, members=tuple(members))


def test_catalog_identity_nonredundant_cut_and_root_compatibility():
    catalog = bundled_surface_catalog()
    ids = {m.asset.source_allen_id for m in catalog.members}
    assert ids == {315, 698, 1089, 703, 477, 803, 549, 1097, 313, 771, 354, 528}
    assert catalog.reference_space_id == "allen-ccf-2017"
    assert catalog.hemisphere_policy == "bilateral source meshes; unsigned Allen IDs"
    assert all(not (ids & set(m.ancestor_allen_ids)) for m in catalog.members)
    assert all(m.asset.role == "regional-context" for m in catalog.members)
    assert all(
        m.asset.source_to_world_um == bundled_surface_asset().source_to_world_um
        for m in catalog.members
    )
    assert (
        next(m for m in catalog.members if m.asset.source_allen_id == 528).name
        == "Cerebellar cortex"
    )
    assert bundled_surface_asset().role == "brain-envelope"
    assert sum(m.asset.expected_vertices for m in catalog.members) == 156646
    assert sum(m.asset.expected_triangles for m in catalog.members) == 312633


def test_regional_descriptor_requires_unsigned_nonroot_id():
    raw = document()["members"][0]
    assert parse_surface_asset(raw).source_allen_id == 315
    for identity in (997, -315, 0, True):
        altered = deepcopy(raw)
        altered["source_allen_id"] = identity
        with pytest.raises(ValueError):
            parse_surface_asset(altered)


@pytest.mark.parametrize(
    "case",
    [
        "overlap",
        "unknown",
        "duplicate",
        "cycle",
        "missing-parent",
        "unrelated",
        "hemisphere",
        "color",
        "space",
    ],
)
def test_catalog_rejects_invalid_semantics(case):
    raw = document()
    if case == "overlap":
        member = deepcopy(raw["members"][0])
        member["source_allen_id"] = 695
        raw["members"].append(member)
    elif case == "unknown":
        raw["members"][0]["source_allen_id"] = 123456
    elif case == "duplicate":
        raw["members"].append(deepcopy(raw["members"][0]))
    elif case == "cycle":
        next(r for r in raw["ontology"] if r["allen_id"] == 695)["parent_allen_id"] = (
            315
        )
    elif case == "missing-parent":
        raw["ontology"][0]["parent_allen_id"] = 123456
    elif case == "unrelated":
        raw["ontology"].append(
            {
                "allen_id": 123456,
                "parent_allen_id": 997,
                "acronym": "extra",
                "name": "extra",
                "color_hex": "#ffffff",
            }
        )
    elif case == "hemisphere":
        raw["hemisphere_policy"] = "signed left and right"
    elif case == "color":
        raw["ontology"][0]["color_hex"] = "#ABCDEF"
    elif case == "space":
        raw["members"][0]["reference_space_id"] = "other-space"
    with pytest.raises(ValueError):
        parse_surface_catalog(raw)


def test_bundle_materialization_is_atomic_owned_and_offline(tmp_path):
    catalog = synthetic_catalog(tmp_path)
    target = tmp_path / "prepared"
    geometry = materialize_surface_catalog(target, catalog, source_directory=tmp_path)
    assert len(geometry) == 2
    np.testing.assert_array_equal(geometry[0].positions_um[0], [-5739, 5400, 332])
    for g in geometry:
        for array in (g.positions_um, g.normals, g.indices):
            assert array.flags.owndata and array.flags.c_contiguous
    with pytest.raises(FileExistsError):
        materialize_surface_catalog(target, catalog)
    assert len(load_surface_catalog(target, catalog)) == 2
    # A corrupt member invalidates the bundle, including previously valid members.
    (tmp_path / "698.obj").write_bytes(OBJ.replace(b"v 1 0 0", b"v 2 0 0"))
    failed = tmp_path / "failed"
    with pytest.raises(ValueError, match="SHA-256"):
        materialize_surface_catalog(failed, catalog, source_directory=tmp_path)
    assert not failed.exists()
    assert not list(tmp_path.glob(".failed-*"))
    (target / "698" / "surface.obj").write_bytes(OBJ + b"\n")
    with pytest.raises(ValueError, match="byte length"):
        load_surface_catalog(target, catalog)


@pytest.mark.skipif(
    not os.environ.get("IBL_ALLEN_CONTEXT_SOURCES"),
    reason="real regional sources not configured",
)
def test_real_source_native_context(tmp_path):
    catalog = bundled_surface_catalog()
    geometry = materialize_surface_catalog(
        tmp_path / "context",
        source_directory=Path(os.environ["IBL_ALLEN_CONTEXT_SOURCES"]),
    )
    assert len(geometry) == len(catalog.members) == 12
    for g, member in zip(geometry, catalog.members):
        assert g.asset == member.asset
        np.testing.assert_allclose(np.linalg.norm(g.normals, axis=1), 1, rtol=1e-6)
        # Source meshes span both sides of the shared ML origin.
        assert g.positions_um[:, 0].min() < 0 < g.positions_um[:, 0].max()


@pytest.mark.skipif(
    not os.environ.get("IBL_ALLEN_CONTEXT_REGION_CATALOG"),
    reason="real ontology source not configured",
)
def test_real_catalog_membership_and_official_semantics():
    catalog = bundled_surface_catalog()
    payload = Path(os.environ["IBL_ALLEN_CONTEXT_REGION_CATALOG"]).read_bytes()
    assert len(payload) == catalog.region_catalog.bytes
    assert hashlib.sha256(payload).hexdigest() == catalog.region_catalog.sha256
    rows = {r["atlas_id"]: r for r in json.loads(payload)["mappings"]["allen"]}
    for member in catalog.members:
        row = rows[member.asset.source_allen_id]
        assert (member.name, member.acronym, member.color_hex) == (
            row["name"],
            row["acronym"],
            row["color_hex"],
        )
        chain = []
        parent = row["parent_id"]
        while parent is not None:
            chain.append(parent)
            parent = rows[parent]["parent_id"]
        assert member.ancestor_allen_ids == tuple(chain)
