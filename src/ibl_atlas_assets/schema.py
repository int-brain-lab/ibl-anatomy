"""JSON Schema loading and validation."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def _load_schema(name: str) -> dict[str, Any]:
    resource = files("ibl_atlas_assets.schemas").joinpath(name)
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_mesh_pack_manifest(manifest: Any) -> dict[str, Any]:
    """Validate and return an atlas mesh-pack v1 manifest."""

    mesh_schema = _load_schema("mesh-pack.schema.json")
    common_schema = _load_schema("common.schema.json")
    registry = Registry().with_resource(
        common_schema["$id"], Resource.from_contents(common_schema)
    )
    Draft202012Validator(mesh_schema, registry=registry).validate(manifest)
    return manifest
