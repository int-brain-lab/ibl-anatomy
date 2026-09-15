from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pytest

from tools.allen_nrrd import open_allen_nrrd_ap_ml_dv
from tools.build_intensity_blocks import _open_source


def _write_nrrd(path: Path, values: np.ndarray, *, truncate: bool = False) -> None:
    source_order = np.transpose(values, (0, 2, 1))
    payload = source_order.tobytes(order="F")
    if truncate:
        payload = payload[:-2]
    header = (
        "NRRD0004\n"
        "type: unsigned short\n"
        "dimension: 3\n"
        f"sizes: {' '.join(str(item) for item in source_order.shape)}\n"
        "endian: little\n"
        "encoding: gzip\n\n"
    ).encode("ascii")
    path.write_bytes(header + gzip.compress(payload, mtime=0))


def test_allen_nrrd_is_exposed_as_bounded_ap_ml_dv_memmap(tmp_path: Path) -> None:
    values = np.arange(4 * 3 * 2, dtype=np.uint16).reshape(4, 3, 2)
    source = tmp_path / "source.nrrd"
    _write_nrrd(source, values)
    with open_allen_nrrd_ap_ml_dv(source, temporary_dir=tmp_path) as volume:
        assert volume.source_sizes == (4, 2, 3)
        assert volume.values.shape == (4, 3, 2)
        np.testing.assert_array_equal(volume.values, values)
        temporary = tuple(tmp_path.glob(".allen-nrrd-*.u16"))
        assert len(temporary) == 1
    assert not tuple(tmp_path.glob(".allen-nrrd-*.u16"))


def test_intensity_builder_source_accepts_npy_and_nrrd(tmp_path: Path) -> None:
    values = np.arange(24, dtype=np.uint16).reshape(4, 3, 2)
    npy = tmp_path / "source.npy"
    nrrd = tmp_path / "source.nrrd"
    np.save(npy, values)
    _write_nrrd(nrrd, values)
    for source in (npy, nrrd):
        with _open_source(source, temporary_dir=tmp_path) as actual:
            np.testing.assert_array_equal(actual, values)


def test_allen_nrrd_rejects_truncated_and_unsupported_inputs(tmp_path: Path) -> None:
    values = np.arange(24, dtype=np.uint16).reshape(4, 3, 2)
    truncated = tmp_path / "truncated.nrrd"
    _write_nrrd(truncated, values, truncate=True)
    with pytest.raises(ValueError, match="decoded byte length"):
        with open_allen_nrrd_ap_ml_dv(truncated):
            pass

    invalid = tmp_path / "invalid.nrrd"
    invalid.write_bytes(b"not an nrrd")
    with pytest.raises(ValueError, match="not an NRRD"):
        with open_allen_nrrd_ap_ml_dv(invalid):
            pass
