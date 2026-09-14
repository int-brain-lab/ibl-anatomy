import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from ibl_atlas_assets import open_region_catalog, parse_region_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "atlas-regions-v1" / "regions.json"


def _document() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_catalog_views_and_identity() -> None:
    catalog = open_region_catalog(FIXTURE)
    assert catalog.reference_space_id == "allen-ccf-2017"
    physical = catalog.physical("allen")
    assert [row.atlas_id for row in physical] == [0, 997, 8, -997, -8]
    assert [row.atlas_id for row in catalog.left("allen")] == [0, -997, -8]
    assert [row.logical_id for row in catalog.logical("allen")] == [0, 997, 8]
    assert catalog.left("beryl")[2].mapping_member is False
    assert physical[2].mapped_atlas_ids["beryl"] == 997
    assert catalog.map_allen_ids([-8, 8, -997, 0], "allen") == (-8, 8, -997, 0)
    assert catalog.map_allen_ids([-8, 8, -997, 0], "beryl") == (None, None, 997, 0)
    with pytest.raises(KeyError, match="unknown signed Allen"):
        catalog.map_allen_ids([123456], "allen")


def test_fixture_hash_is_deterministic() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "f757cc3c3e54f5875a75ccf0b6118f06a09443da7b199209d2fa2a20ab84895a"
    )


@pytest.mark.parametrize("mutation", [
    lambda d: d["mappings"]["allen"][1].__setitem__("parent_id", 123),
    lambda d: d["mappings"]["allen"][1].__setitem__("color_hex", "#FFFFFF"),
    lambda d: d["mappings"]["allen"][1].__setitem__("idx", 0),
    lambda d: d["mappings"]["allen"][1].__setitem__("atlas_id", 8),
])
def test_catalog_rejects_broken_semantics(mutation) -> None:
    document = copy.deepcopy(_document())
    mutation(document)
    with pytest.raises((ValueError, ValidationError)):
        parse_region_catalog(document)


def test_hash_gate_rejects_wrong_source_identity() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        open_region_catalog(FIXTURE, sha256="0" * 64)


@pytest.mark.parametrize(
    ("field", "value"),
    [("iblatlas_commit", "synthetic"), ("legacy_svg_crosswalk_url", "not a uri")],
)
def test_catalog_rejects_invalid_provenance_identity(field: str, value: str) -> None:
    document = copy.deepcopy(_document())
    document["provenance"][field] = value
    with pytest.raises(ValidationError):
        parse_region_catalog(document)
