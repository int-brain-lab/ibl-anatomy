"""JSON Schema loading and validation."""

from __future__ import annotations

import json
import math
from importlib.resources import files
from typing import Any

import numpy as np
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
    _validate_mesh_semantics(manifest)
    return manifest


def validate_volume_pack_manifest(manifest: Any) -> dict[str, Any]:
    """Validate and return an atlas volume-pack v1 manifest."""

    Draft202012Validator(_load_schema("volume-pack.schema.json")).validate(manifest)
    _validate_volume_semantics(manifest)
    return manifest


def _registered_validator(name: str) -> Draft202012Validator:
    common = _load_schema("common.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    return Draft202012Validator(_load_schema(name), registry=registry)


def validate_registered_projection_manifest(manifest: Any) -> dict[str, Any]:
    """Validate one 10-um registered coronal, sagittal, or horizontal stack."""

    _registered_validator("registered-projection.schema.json").validate(manifest)
    _validate_registered_projection_semantics(manifest)
    return manifest


def validate_registered_resource_index(document: Any) -> dict[str, Any]:
    """Validate a registered indexed-SVG resource index."""

    _registered_validator("registered-svg-resource-index.schema.json").validate(document)
    _validate_registered_resource_index_semantics(document)
    return document


def _validate_registered_projection_semantics(document: dict[str, Any]) -> None:
    expected_axis = {"coronal": "ap", "sagittal": "ml", "horizontal": "dv"}[document["id"]]
    if document["world_slice_axis"] != expected_axis:
        raise ValueError(f"{document['id']} must slice the {expected_axis} world axis")
    matrix = document["plane_index_to_world_um"]
    extent = document["voxel_edge_extent_um"]
    _finite([*matrix, *extent], "registered projection affine and extent")
    if matrix[12:] != [0, 0, 0, 1]:
        raise ValueError("registered projection affine homogeneous row is invalid")
    for column in range(3):
        if sum(matrix[row * 4 + column] != 0 for row in range(3)) != 1:
            raise ValueError("registered projection affine must be a signed permutation")
    world_row = {"ml": 0, "ap": 1, "dv": 2}[expected_axis]
    if matrix[world_row * 4] == 0:
        raise ValueError("registered plane slice coordinate does not map to its declared world axis")
    if document.get("world_to_plane_index") is not None:
        inverse = document["world_to_plane_index"]
        _finite(inverse, "registered projection inverse affine")
        actual = np.asarray(matrix, dtype=float).reshape(4, 4)
        expected = np.linalg.inv(actual).reshape(-1)
        if not np.allclose(inverse, expected, rtol=1e-10, atol=1e-9):
            raise ValueError("registered projection inverse does not match affine")
    shape = [document["slice_count"], *document["slice_shape"]]
    derived_extent: list[float] = []
    for world in range(3):
        column = next(column for column in range(3) if matrix[world * 4 + column] != 0)
        scale = matrix[world * 4 + column]
        offset = matrix[world * 4 + 3]
        edges = [offset + scale * -0.5, offset + scale * (shape[column] - 0.5)]
        derived_extent.extend([min(edges), max(edges)])
    if not np.allclose(extent, derived_extent, rtol=1e-10, atol=1e-9):
        raise ValueError("registered projection voxel-edge extent differs from affine")
    slices = document["display_slices"]
    if slices != sorted(slices) or any(index >= document["slice_count"] for index in slices):
        raise ValueError("registered display slices must be increasing and inside the native domain")


def _validate_registered_resource_index_semantics(document: dict[str, Any]) -> None:
    resources = document["resources"]
    _unique([entry["pack_id"] for entry in resources], "registered SVG pack id")
    _unique([entry["resource"]["path"] for entry in resources], "registered SVG resource path")
    slices: list[int] = []
    for entry in resources:
        indices = entry["slice_indices"]
        if indices != sorted(indices):
            raise ValueError("registered SVG resource slices must be increasing")
        resource = entry["resource"]
        if resource["media_type"] != "application/vnd.ibl.indexed-svg":
            raise ValueError("registered SVG packs must use the indexed-SVG media type")
        if resource["codec"]["name"] != "gzip":
            raise ValueError("registered SVG packs must be gzip-compressed")
        slices.extend(indices)
    if slices != sorted(slices) or len(slices) != len(set(slices)):
        raise ValueError("registered SVG resource index slices must be globally increasing and unique")


def _finite(values: list[float], label: str) -> None:
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{label} must be finite")


def _unique(values: list[Any], label: str) -> None:
    if len(values) != len(set(values)):
        if label == "mesh presentation id":
            raise ValueError("mesh presentation IDs are not unique")
        if label == "mesh component id":
            raise ValueError("mesh component IDs are not unique")
        raise ValueError(f"duplicate {label}")


def _validate_volume_semantics(document: dict[str, Any]) -> None:
    """Apply coordinate and resource invariants beyond JSON Schema."""

    grid = document["grid"]
    transform = grid["index_to_world_um"]
    _finite(transform, "volume index-to-world transform")
    if transform[12:] != [0, 0, 0, 1]:
        raise ValueError("volume index-to-world transform must be affine")
    matrix = [transform[index : index + 4] for index in range(0, 16, 4)]
    determinant = (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    if math.isclose(determinant, 0):
        raise ValueError("volume index-to-world transform must be invertible")
    if (
        matrix[0][0] != 0
        or matrix[0][2] != 0
        or matrix[1][1] != 0
        or matrix[1][2] != 0
        or matrix[2][0] != 0
        or matrix[2][1] != 0
        or matrix[0][1] <= 0
        or matrix[1][0] >= 0
        or matrix[2][2] >= 0
    ):
        raise ValueError("volume transform must be axis-aligned IBL AP/ML/DV")
    spacing = (matrix[0][1], -matrix[1][0], -matrix[2][2])
    if not math.isclose(spacing[0], spacing[1]) or not math.isclose(
        spacing[0], spacing[2]
    ):
        raise ValueError("volume voxel spacing must be isotropic")

    boundary = document["hemisphere_boundary"]
    ml_dimension = grid["shape"][grid["array_axes"].index("ml")]
    if boundary["first_right_index"] >= ml_dimension:
        raise ValueError("volume first-right index is outside the ML dimension")
    derived_first_right = math.floor(-matrix[0][3] / matrix[0][1])
    if boundary["first_right_index"] != derived_first_right:
        raise ValueError("volume first-right index differs from the IBL grid origin")

    paths = [document["region_catalog"]["path"]]
    paths.extend(item["path"] for item in document["volumes"].values())
    _unique(paths, "volume resource path")
    voxel_count = math.prod(grid["shape"])
    expected_decoded_bytes = voxel_count * 2
    for name, resource in document["volumes"].items():
        if resource["decoded_bytes"] != expected_decoded_bytes:
            raise ValueError(f"volume {name} decoded byte count differs from grid")


def _validate_mesh_semantics(document: dict[str, Any]) -> None:
    """Apply the mesh-specific semantic contract beyond JSON Schema."""

    coordinate = document["coordinate_system"]
    transform = coordinate["source_to_world_um"]
    _finite(transform, "mesh source-to-world transform")
    if transform[12:] != [0, 0, 0, 1]:
        raise ValueError("mesh source-to-world transform must be affine")
    determinant = (
        transform[0] * (transform[5] * transform[10] - transform[6] * transform[9])
        - transform[1] * (transform[4] * transform[10] - transform[6] * transform[8])
        + transform[2] * (transform[4] * transform[9] - transform[5] * transform[8])
    )
    if math.isclose(determinant, 0):
        raise ValueError("mesh source-to-world transform must be invertible")

    scope = document["geometry_scope"]
    active = scope["active_allen_ids"]
    excluded = scope["excluded_allen_ids"]
    inventory = document["sources"]["source_glb"]["inventory_allen_ids"]
    for values, label in (
        (active, "active Allen IDs"),
        (excluded, "excluded Allen IDs"),
        (inventory, "source inventory"),
    ):
        if values != sorted(values):
            raise ValueError(f"mesh {label} must be sorted")
    if set(active) & set(excluded):
        raise ValueError("mesh active and excluded Allen IDs overlap")

    boundary = document["presentation_boundary"]
    _finite([boundary["threshold_um"]], "mesh presentation threshold")
    if document["purpose"] == "production" and boundary["status"] != "reviewed":
        raise ValueError(
            "production mesh cannot use a provisional presentation boundary"
        )
    if (
        boundary["status"] == "provisional-review"
        and document["purpose"] != "review-only"
    ):
        raise ValueError("review boundary requires review-only mesh purpose")
    if (
        boundary["status"] == "provisional-test-only"
        and document["purpose"] != "test-only"
    ):
        raise ValueError("test boundary requires test-only mesh purpose")

    presentations = document["presentations"]
    presentation_ids = [item["presentation_id"] for item in presentations]
    signed_ids = [item["signed_allen_id"] for item in presentations]
    _unique(presentation_ids, "mesh presentation id")
    if presentation_ids != list(range(len(presentations))):
        raise ValueError("mesh presentation IDs must be contiguous in manifest order")
    presentation_by_id = {item["presentation_id"]: item for item in presentations}
    signed_by_source: dict[int, set[int]] = {}
    for presentation in presentations:
        source_id = presentation["source_allen_id"]
        signed_id = presentation["signed_allen_id"]
        sign = -1 if presentation["side"] == "left" else 1
        if abs(signed_id) != source_id:
            raise ValueError("mesh presentation source and signed ID differ")
        if signed_id != sign * source_id:
            raise ValueError("mesh presentation side and signed ID differ")
        if (
            source_id not in active
            or source_id not in inventory
            or source_id in excluded
        ):
            raise ValueError("mesh presentation is outside the declared source scope")
        if presentation["mappings"]["allen"] != signed_id:
            raise ValueError("mesh presentation Allen mapping differs")
        for name in ("beryl", "cosmos"):
            mapped = presentation["mappings"][name]
            if mapped is not None and (
                mapped == sign * 997 or (mapped < 0) != (sign < 0)
            ):
                raise ValueError(f"mesh {name} mapping is invalid for signed identity")
        signed_by_source.setdefault(source_id, set()).add(sign)
    _unique(signed_ids, "mesh signed Allen id")
    if set(signed_by_source) != set(active):
        raise ValueError("mesh presentation coverage differs from active Allen scope")

    components = document["components"]
    component_ids = [item["component_id"] for item in components]
    _unique(component_ids, "mesh component id")
    if component_ids != list(range(len(components))):
        raise ValueError("mesh component IDs must be contiguous in manifest order")
    for component in components:
        source_id = component["source_allen_id"]
        if (
            source_id not in active
            or source_id not in inventory
            or source_id in excluded
        ):
            raise ValueError(
                f"mesh component {component['component_id']} is outside the declared source scope"
            )
        identifiers = {
            "left": component["left_presentation_id"],
            "right": component["right_presentation_id"],
        }
        expected = (
            {component["lateralization"]}
            if component["lateralization"] != "neutral"
            else {"left", "right"}
        )
        actual = {
            side for side, identifier in identifiers.items() if identifier is not None
        }
        if actual != expected:
            raise ValueError(
                f"mesh component presentation sides differ: {component['component_id']}"
            )
        for side, identifier in identifiers.items():
            if identifier is not None:
                presentation = presentation_by_id.get(identifier)
                if (
                    presentation is None
                    or presentation["source_allen_id"] != source_id
                    or presentation["side"] != side
                ):
                    raise ValueError(
                        f"mesh component presentation identity differs: {component['component_id']}"
                    )
        minimum = component["bounds"]["minimum_um"]
        maximum = component["bounds"]["maximum_um"]
        centroid = component["centroid_um"]
        displacement = component["explode_displacement_um"]
        _finite(
            [*minimum, *maximum, *centroid, *displacement],
            "mesh bounds, centroids and displacement",
        )
        if any(
            low > high or center < low or center > high
            for low, high, center in zip(minimum, maximum, centroid)
        ):
            raise ValueError(
                f"mesh centroid or bounds are invalid for component {component['component_id']}"
            )
    if {component["source_allen_id"] for component in components} != set(active):
        raise ValueError("mesh component coverage differs from active Allen scope")

    lods = document["lods"]
    lod_ids = [lod["id"] for lod in lods]
    _unique(lod_ids, "mesh LOD id")
    if document["default_lod_id"] not in lod_ids:
        raise ValueError("mesh default LOD is absent")
    upgrade = document["upgrade_lod_id"]
    if upgrade is not None and (
        upgrade not in lod_ids or upgrade == document["default_lod_id"]
    ):
        raise ValueError("mesh upgrade LOD is absent or duplicates the default")
    paths = [lod["resource"]["path"] for lod in lods] + [
        document["validation"]["report"]["path"]
    ]
    _unique(paths, "mesh resource path")
    source_triangles = sum(component["triangle_count"] for component in components)
    for lod in lods:
        _finite(
            [
                lod["target_triangle_ratio"],
                lod["actual_triangle_ratio"],
                lod["maximum_error_um"],
            ],
            f"mesh LOD {lod['id']} values",
        )
        if lod["triangle_count"] > source_triangles:
            raise ValueError(f"mesh LOD {lod['id']} exceeds source triangle count")
        if not math.isclose(
            lod["actual_triangle_ratio"],
            lod["triangle_count"] / source_triangles,
            rel_tol=1e-9,
        ):
            raise ValueError(f"mesh LOD {lod['id']} triangle ratio is inconsistent")
        decoder = lod["decoder"]
        if decoder["encoding"] == "raw-v1" and (
            decoder["position_bits"] != 0 or decoder["normal_bits"] != 0
        ):
            raise ValueError("raw mesh LOD cannot declare quantization bits")
        if decoder["encoding"] == "meshopt-quantized-v1" and (
            decoder["position_bits"] != 14 or decoder["normal_bits"] != 8
        ):
            raise ValueError(
                "meshopt mesh LOD must use the reviewed 14/8-bit quantization"
            )
