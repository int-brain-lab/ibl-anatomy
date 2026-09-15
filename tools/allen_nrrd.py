"""Bounded reader for the embedded-gzip layout of official Allen NRRD volumes."""

from __future__ import annotations

import gzip
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

import numpy as np
from numpy.typing import NDArray

_CHUNK_BYTES = 16 * 1024 * 1024
_UINT16_TYPES = {"unsigned short", "ushort", "uint16", "uint16_t"}


@dataclass(frozen=True)
class AllenNrrdVolume:
    """One temporary memory-mapped Allen volume in AP/ML/DV array order."""

    values: NDArray[np.uint16]
    source_sizes: tuple[int, int, int]
    fields: dict[str, str]


def _read_header(stream: BinaryIO) -> dict[str, str]:
    magic = stream.readline().rstrip(b"\r\n")
    if magic not in {b"NRRD0004", b"NRRD0005"}:
        raise ValueError("Allen intensity source is not an NRRD0004/5 file")
    fields: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            raise ValueError("NRRD header is not terminated")
        stripped = line.rstrip(b"\r\n")
        if not stripped:
            break
        if stripped.startswith(b"#"):
            continue
        try:
            key, value = stripped.decode("ascii").split(":", 1)
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("NRRD header field is invalid") from error
        key = key.strip().lower()
        if not key or key in fields:
            raise ValueError("NRRD header fields must be unique and named")
        fields[key] = value.strip()
    return fields


def _validate_header(fields: dict[str, str]) -> tuple[int, int, int]:
    if fields.get("type", "").lower() not in _UINT16_TYPES:
        raise ValueError("Allen intensity NRRD must contain unsigned 16-bit values")
    if fields.get("dimension") != "3":
        raise ValueError("Allen intensity NRRD must be three-dimensional")
    if fields.get("encoding", "").lower() not in {"gzip", "gz"}:
        raise ValueError("Allen intensity NRRD must use embedded gzip encoding")
    if fields.get("endian", "").lower() != "little":
        raise ValueError("Allen intensity NRRD must use little-endian values")
    if "data file" in fields or "datafile" in fields:
        raise ValueError("detached NRRD data files are not supported")
    try:
        sizes = tuple(int(item) for item in fields["sizes"].split())
    except (KeyError, ValueError) as error:
        raise ValueError("NRRD sizes are invalid") from error
    if len(sizes) != 3 or any(item < 1 for item in sizes):
        raise ValueError("NRRD sizes must contain three positive dimensions")
    return sizes


@contextmanager
def open_allen_nrrd_ap_ml_dv(
    path: str | Path, *, temporary_dir: str | Path | None = None
) -> Iterator[AllenNrrdVolume]:
    """Inflate an official Allen NRRD to a temporary AP/ML/DV memory map.

    Allen's embedded stream is laid out as AP/DV/ML with its first axis
    contiguous. The returned view swaps the last two axes without allocating
    the decoded multi-gigabyte volume in RAM.
    """

    source_path = Path(path)
    temporary_root = None if temporary_dir is None else Path(temporary_dir)
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    raw_path: Path | None = None
    raw = None
    try:
        with source_path.open("rb") as source:
            fields = _read_header(source)
            sizes = _validate_header(fields)
            expected_bytes = int(np.prod(sizes, dtype=np.int64)) * 2
            with tempfile.NamedTemporaryFile(
                prefix=".allen-nrrd-",
                suffix=".u16",
                dir=temporary_root,
                delete=False,
            ) as destination:
                raw_path = Path(destination.name)
                decoded_bytes = 0
                try:
                    with gzip.GzipFile(fileobj=source) as encoded:
                        while chunk := encoded.read(_CHUNK_BYTES):
                            decoded_bytes += len(chunk)
                            if decoded_bytes > expected_bytes:
                                raise ValueError(
                                    "NRRD decoded data exceeds its declared shape"
                                )
                            destination.write(chunk)
                except (EOFError, OSError) as error:
                    raise ValueError("NRRD embedded gzip data is invalid") from error
        if decoded_bytes != expected_bytes:
            raise ValueError("NRRD decoded byte length differs from its declared shape")
        raw = np.memmap(raw_path, dtype="<u2", mode="r", shape=sizes, order="F")
        values = np.transpose(raw, (0, 2, 1))
        yield AllenNrrdVolume(values, sizes, fields)
    finally:
        if raw is not None:
            raw._mmap.close()
        if raw_path is not None:
            raw_path.unlink(missing_ok=True)
