"""Strict, renderer-neutral reader for the Allen region catalog v1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker

from .schema import _load_schema

_MAPPINGS = ("allen", "beryl", "cosmos")
_COLOR = re.compile(r"^#[0-9a-f]{6}$")
RegionView = Literal["physical", "left", "logical"]


@dataclass(frozen=True)
class AtlasRegion:
    """One signed ontology row from the generated catalog."""

    atlas_id: int
    index: int
    acronym: str
    name: str
    parent_id: int | None
    depth: int
    color_hex: str
    mapping_member: bool
    mapped_atlas_ids: Mapping[str, int]

    @property
    def logical_id(self) -> int:
        """Return the hemisphere-independent identity."""

        return abs(self.atlas_id)

    @property
    def is_left(self) -> bool:
        return self.atlas_id < 0


@dataclass(frozen=True)
class AtlasRegionCatalog:
    """Validated Allen catalog with explicit physical and logical views.

    ``physical`` preserves every signed source row. ``left`` is the canonical
    left-hemisphere tree (the void row is retained), while ``logical`` exposes
    one hemisphere-independent row per absolute atlas ID, choosing the
    positive/right row. No view silently invents an atlas ID or remaps colors.
    """

    atlas: str
    reference_space_id: str
    provenance: Mapping[str, Any]
    mappings: Mapping[str, tuple[AtlasRegion, ...]]

    def rows(self, mapping: str, view: RegionView = "physical") -> tuple[AtlasRegion, ...]:
        if mapping not in self.mappings:
            raise KeyError(f"unknown atlas mapping: {mapping}")
        rows = self.mappings[mapping]
        if view == "physical":
            return rows
        if view == "left":
            return tuple(row for row in rows if row.atlas_id <= 0)
        if view == "logical":
            return tuple(row for row in rows if row.atlas_id >= 0)
        raise ValueError(f"unknown region view: {view}")

    def physical(self, mapping: str) -> tuple[AtlasRegion, ...]:
        return self.rows(mapping, "physical")

    def left(self, mapping: str) -> tuple[AtlasRegion, ...]:
        return self.rows(mapping, "left")

    def logical(self, mapping: str) -> tuple[AtlasRegion, ...]:
        return self.rows(mapping, "logical")

    def map_allen_ids(
        self, atlas_ids: Iterable[int], mapping: str
    ) -> tuple[int | None, ...]:
        """Map signed Allen IDs without turning absent reduced rows into root.

        Legacy crosswalks use root (997) when a non-root Allen row is absent from
        a reduced mapping. That placeholder is returned as ``None``; the actual
        Allen root continues to map to root.
        """

        self.physical(mapping)  # validate the target mapping before consuming IDs
        by_id = {row.atlas_id: row for row in self.physical("allen")}
        result: list[int | None] = []
        for raw_atlas_id in atlas_ids:
            atlas_id = int(raw_atlas_id)
            row = by_id.get(atlas_id)
            if row is None:
                raise KeyError(f"unknown signed Allen region ID: {atlas_id}")
            mapped = int(row.mapped_atlas_ids[mapping])
            is_reduced_root_fallback = (
                mapping != "allen" and abs(mapped) == 997 and abs(atlas_id) != 997
            )
            result.append(None if is_reduced_root_fallback else mapped)
        return tuple(result)


def _record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _validate_rows(mapping: str, raw_rows: Any) -> tuple[AtlasRegion, ...]:
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError(f"{mapping} mapping must be a non-empty array")
    rows: list[AtlasRegion] = []
    ids: set[int] = set()
    indexes: set[int] = set()
    for position, raw in enumerate(raw_rows):
        row = _record(raw, f"{mapping}[{position}]")
        try:
            atlas_id = row["atlas_id"]
            index = row["idx"]
            parent_id = row["parent_id"]
            depth = row["depth"]
            color = row["color_hex"]
            mapped = row["mapped_atlas_ids"]
            if not isinstance(atlas_id, int) or isinstance(atlas_id, bool):
                raise TypeError("atlas_id must be an integer")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                raise TypeError("idx must be a non-negative integer")
            if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
                raise TypeError("depth must be a non-negative integer")
            if parent_id is not None and (not isinstance(parent_id, int) or isinstance(parent_id, bool)):
                raise TypeError("parent_id must be an integer or null")
            if not isinstance(color, str) or not _COLOR.fullmatch(color):
                raise TypeError("color_hex must be lowercase #rrggbb")
            if not isinstance(mapped, dict) or set(mapped) != set(_MAPPINGS):
                raise TypeError("mapped_atlas_ids must contain Allen, Beryl and Cosmos")
            if any(not isinstance(value, int) or isinstance(value, bool) for value in mapped.values()):
                raise TypeError("mapped_atlas_ids values must be integers")
            acronym = row["acronym"]
            name = row["name"]
            member = row["mapping_member"]
            if not isinstance(acronym, str) or not acronym or not isinstance(name, str) or not name:
                raise TypeError("acronym and name must be non-empty strings")
            if not isinstance(member, bool):
                raise TypeError("mapping_member must be boolean")
        except KeyError as exc:
            raise ValueError(f"{mapping}[{position}] is missing {exc.args[0]}") from exc
        if atlas_id in ids:
            raise ValueError(f"{mapping} contains duplicate atlas_id {atlas_id}")
        if index in indexes:
            raise ValueError(f"{mapping} contains duplicate idx {index}")
        ids.add(atlas_id)
        indexes.add(index)
        rows.append(AtlasRegion(atlas_id, index, acronym, name, parent_id, depth, color, member, MappingProxyType(dict(mapped))))
    if [row.index for row in rows] != sorted(indexes):
        raise ValueError(f"{mapping} rows must be sorted by idx")
    by_id = {row.atlas_id: row for row in rows}
    for row in rows:
        if row.parent_id is not None:
            parent = by_id.get(row.parent_id)
            if parent is None:
                raise ValueError(f"{mapping} region {row.atlas_id} has missing parent {row.parent_id}")
            if parent.depth != row.depth - 1:
                raise ValueError(f"{mapping} region {row.atlas_id} has inconsistent parent depth")
            if (parent.atlas_id < 0) != (row.atlas_id < 0):
                raise ValueError(f"{mapping} region {row.atlas_id} crosses hemisphere parent")
    if 0 not in by_id:
        raise ValueError(f"{mapping} must contain the void row with atlas_id 0")
    positive = {row.atlas_id for row in rows if row.atlas_id > 0}
    negative = {-row.atlas_id for row in rows if row.atlas_id < 0}
    if positive != negative:
        raise ValueError(f"{mapping} physical rows must have matching left/right IDs")
    return tuple(rows)


def parse_region_catalog(value: Any) -> AtlasRegionCatalog:
    """Validate and parse an ``ibl-atlas-regions-v1`` document."""

    root = _record(value, "atlas regions")
    Draft202012Validator(
        _load_schema("atlas-regions.schema.json"), format_checker=FormatChecker()
    ).validate(root)
    if root.get("format") != "ibl-atlas-regions-v1" or root.get("schema_version") != "1.0":
        raise ValueError("unsupported atlas region catalog format")
    if root.get("reference_space_id") != "allen-ccf-2017":
        raise ValueError("atlas region reference space must be allen-ccf-2017")
    if root.get("hemisphere_encoding") != "signed atlas IDs; negative is left":
        raise ValueError("unsupported hemisphere encoding")
    mappings = _record(root.get("mappings"), "atlas regions mappings")
    if set(mappings) != set(_MAPPINGS):
        raise ValueError("atlas regions must contain exactly allen, beryl and cosmos mappings")
    provenance = _record(root.get("provenance"), "atlas regions provenance")
    for key in ("iblatlas_commit", "legacy_svg_crosswalk_sha256", "legacy_svg_crosswalk_url"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ValueError(f"atlas regions provenance requires {key}")
    return AtlasRegionCatalog(
        atlas=root.get("atlas", ""),
        reference_space_id=root["reference_space_id"],
        provenance=MappingProxyType(dict(provenance)),
        mappings=MappingProxyType({name: _validate_rows(name, mappings[name]) for name in _MAPPINGS}),
    )


def open_region_catalog(path: str | Path, *, sha256: str | None = None) -> AtlasRegionCatalog:
    """Read a local catalog, optionally enforcing its byte-level SHA-256."""

    source = Path(path)
    payload = source.read_bytes()
    if sha256 is not None and hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError(f"atlas region catalog SHA-256 mismatch: {source}")
    return parse_region_catalog(json.loads(payload))
