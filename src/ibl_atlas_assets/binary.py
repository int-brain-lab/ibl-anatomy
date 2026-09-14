"""Decode the versioned EAM3 raw geometry container."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

MAGIC = b"EAM3"
VERSION = 1
PREFIX_BYTES = 12

_ARRAY_SPECS = {
    "positions": (np.dtype("<f4"), 3),
    "normals": (np.dtype("<f4"), 3),
    "component_ids": (np.dtype("<u2"), 1),
    "indices": (np.dtype("<u4"), 1),
}


@dataclass(frozen=True)
class RawChunk:
    """One independently indexed geometry chunk decoded from EAM3."""

    chunk_id: str
    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    component_ids: NDArray[np.uint16]
    indices: NDArray[np.uint32]
    ranges: tuple[dict[str, Any], ...]


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{label} is invalid")
    return value


def _header(data: bytes) -> tuple[dict[str, Any], int]:
    if len(data) < PREFIX_BYTES:
        raise ValueError("mesh LOD is truncated")
    if data[:4] != MAGIC:
        raise ValueError("mesh LOD magic is invalid")
    version, header_length = struct.unpack_from("<II", data, 4)
    if version != VERSION:
        raise ValueError("mesh LOD version is unsupported")
    payload_offset = (PREFIX_BYTES + header_length + 3) // 4 * 4
    if payload_offset > len(data):
        raise ValueError("mesh LOD header is truncated")
    try:
        header = json.loads(data[PREFIX_BYTES : PREFIX_BYTES + header_length])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("mesh LOD header is invalid") from error
    if not isinstance(header, dict) or header.get("encoding") != "raw-v1":
        raise ValueError("mesh LOD encoding is unsupported")
    if not isinstance(header.get("chunks"), list) or not header["chunks"]:
        raise ValueError("mesh LOD chunks are invalid")
    if any(data[PREFIX_BYTES + header_length : payload_offset]):
        raise ValueError("mesh LOD header padding is invalid")
    return header, payload_offset


def decode_raw_lod(data: bytes) -> tuple[RawChunk, ...]:
    """Decode a raw-v1 EAM3 LOD into owned, contiguous NumPy arrays."""

    header, payload_offset = _header(data)
    chunks: list[RawChunk] = []
    chunk_ids: set[str] = set()
    for chunk_index, chunk in enumerate(header["chunks"]):
        if not isinstance(chunk, dict):
            raise ValueError(f"mesh LOD chunk {chunk_index} is invalid")  # noqa: TRY004
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in chunk_ids:
            raise ValueError("mesh LOD chunk inventory is invalid")
        chunk_ids.add(chunk_id)
        descriptors = chunk.get("arrays")
        if not isinstance(descriptors, dict) or set(descriptors) != set(_ARRAY_SPECS):
            raise ValueError(f"mesh LOD arrays differ: {chunk_id}")

        arrays: dict[str, NDArray[Any]] = {}
        spans: list[tuple[int, int, str]] = []
        for name, (dtype, item_size) in _ARRAY_SPECS.items():
            descriptor = descriptors[name]
            if not isinstance(descriptor, dict):
                raise ValueError(f"mesh LOD array descriptor is invalid: {name}")  # noqa: TRY004
            offset = _integer(descriptor.get("byte_offset"), f"{name} byte offset")
            count = _integer(descriptor.get("count"), f"{name} count")
            if descriptor.get("component_type") != dtype.name:
                raise ValueError(f"mesh LOD array type differs: {name}")
            if descriptor.get("item_size") != item_size:
                raise ValueError(f"mesh LOD array item size differs: {name}")
            byte_count = count * dtype.itemsize
            start = payload_offset + offset
            end = start + byte_count
            if start < payload_offset or end < start or end > len(data):
                raise ValueError(f"mesh LOD array is out of bounds: {name}")
            spans.append((start, end, name))
            values = np.frombuffer(data, dtype=dtype, count=count, offset=start).copy()
            arrays[name] = np.ascontiguousarray(values)

        for (_, previous_end, previous_name), (start, _, name) in zip(
            sorted(spans), sorted(spans)[1:]
        ):
            if start < previous_end:
                raise ValueError(f"mesh LOD arrays overlap: {previous_name}, {name}")

        positions = arrays["positions"]
        normals = arrays["normals"]
        component_ids = arrays["component_ids"]
        indices = arrays["indices"]
        vertex_count = len(component_ids)
        if len(positions) != 3 * vertex_count or len(normals) != 3 * vertex_count:
            raise ValueError(f"mesh LOD vertex arrays differ: {chunk_id}")
        if len(indices) == 0 or len(indices) % 3 != 0:
            raise ValueError(f"mesh LOD indices differ: {chunk_id}")
        if np.any(indices >= vertex_count):
            raise ValueError(f"mesh LOD index is out of bounds: {chunk_id}")
        ranges = chunk.get("ranges")
        if not isinstance(ranges, list) or not ranges:
            raise ValueError(f"mesh LOD ranges differ: {chunk_id}")

        chunks.append(
            RawChunk(
                chunk_id=chunk_id,
                positions=np.ascontiguousarray(positions.reshape((-1, 3))),
                normals=np.ascontiguousarray(normals.reshape((-1, 3))),
                component_ids=component_ids,
                indices=indices,
                ranges=tuple(ranges),
            )
        )
    return tuple(chunks)
