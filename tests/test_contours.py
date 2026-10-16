from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from ibl_anatomy import (
    ContourComponent,
    RegisteredContourPath,
    RegisteredSlice,
    RegisteredSlicePath,
    decode_registered_contours,
    open_anatomy_pack,
)


def decode(d):
    return decode_registered_contours(
        RegisteredSlice(
            4,
            -50,
            (
                RegisteredSlicePath(
                    {"allen": -101, "beryl": -10, "cosmos": -1}, "evenodd", d
                ),
            ),
        )
    )[0]


def square(x, y, size):
    return f"M{x} {y}h{size}v{size}h{-size}z"


def area(ring):
    return abs(np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1])) / 2


def test_unordered_nested_islands_and_owned_arrays():
    path = decode(square(4, 4, 2) + square(0, 0, 10) + square(2, 2, 6))
    assert len(path.components) == 2
    assert sum(len(c.holes) for c in path.components) == 1
    assert (
        sum(area(c.outer) - sum(area(h) for h in c.holes) for c in path.components)
        == 68
    )
    assert path.atlas_ids == {"allen": -101, "beryl": -10, "cosmos": -1}
    with pytest.raises(TypeError):
        path.atlas_ids["allen"] = 1
    for c in path.components:
        for ring in (c.outer,) + c.holes:
            assert ring.dtype == np.float64 and ring.flags.owndata
            assert not ring.flags.writeable
            np.testing.assert_array_equal(ring[0], ring[-1])
            with pytest.raises(ValueError):
                ring[0] = 0


def test_disconnected_point_contacts_and_winding():
    path = decode(square(0, 0, 1) + square(1, 1, 1) + "M10 0v3h3v-3z")
    assert len(path.components) == 3
    assert sum(area(c.outer) for c in path.components) == 11
    assert not any(c.holes for c in path.components)


def test_repeated_vertex_walk_splits_touching_lobes():
    path = decode("M0 0h1v1h-1v-1h-1v-1h1z")
    assert len(path.components) == 2
    assert sum(area(c.outer) for c in path.components) == 2


def test_hole_touching_exterior_at_vertex():
    # Concave exterior and an interior square meet only at (2,2).
    path = decode("M2 0h4v6h-6v-4h2z" + square(2, 2, 2))
    assert len(path.components) == 1
    assert len(path.components[0].holes) == 1
    assert area(path.components[0].outer) - area(path.components[0].holes[0]) == 28


def test_svg_absolute_relative_repeated_operands_scientific_and_half_grid():
    path = decode("M-.5 -.5 1.5 -.5 L1.5 1.5 H-.5 V-.5 z m3e0 0 l2 0 0 2 -2 0Z")
    assert len(path.components) == 2
    assert sum(area(c.outer) for c in path.components) == 8


@pytest.mark.parametrize(
    "d",
    [
        "M0 0h2v2M3 3h1v1h-1z",  # first subpath unclosed
        "M0 0h2v2h-2",
        "M0 0C1 1 2 2 3 3z",
        "MNaN 0h1v1h-1z",
        "M0 0h1e309v1h-1z",
        "M0 0L1 1L0 2z",
        "M0 0h1h-1z",
        "M0 0h0v1h-1z",
        "M0.1 0h1v1h-1z",
        "M0 0h2v2h-2z rubbish",
        "M0 0h2v2h-2zL1 0",
        "M0 0h2v2h-2zM0 0h2v2h-2z",  # duplicate/shared boundary
        "M0 0h4v4h-4zM2 -1h4v4h-4z",  # proper crossings
        "M0 0h4v4h-4zM2 0h4v4h-4z",  # shared edges
        "M0 0h2v2h-1v-3h-1z",  # self crossing
    ],
)
def test_rejects_invalid_geometry_or_grammar(d):
    with pytest.raises(ValueError):
        decode(d)


def test_empty_slice_and_wrong_fill():
    assert decode_registered_contours(RegisteredSlice(0, 0, ())) == ()
    with pytest.raises(ValueError, match="evenodd"):
        decode_registered_contours(
            RegisteredSlice(
                0, 0, (RegisteredSlicePath({"allen": 1}, "nonzero", square(0, 0, 1)),)
            )
        )


def test_hostile_limits(monkeypatch):
    import ibl_anatomy.contours as contours

    monkeypatch.setattr(contours, "_MAX_TEXT", 4)
    with pytest.raises(ValueError, match="limit"):
        decode(square(0, 0, 1))
    monkeypatch.setattr(contours, "_MAX_TEXT", 1000)
    monkeypatch.setattr(contours, "_MAX_VERTICES", 4)
    with pytest.raises(ValueError, match="limit"):
        decode(square(0, 0, 1))


def test_optional_real_three_orientation_sections():
    source = os.environ.get("IBL_ANATOMY_CONTOUR_MANIFEST")
    if not source:
        pytest.skip(
            "set IBL_ANATOMY_CONTOUR_MANIFEST for the external exact real corpus"
        )
    pack = open_anatomy_pack(
        Path(source), reference_space_id="allen-ccf-2017", grid_id="allen-ccf-2017-10um"
    )
    for name, index, components, holes in (
        ("coronal", 660, 649, 22),
        ("sagittal", 566, 434, 15),
        ("horizontal", 393, 1086, 36),
    ):
        section = pack.projections[name].load_slice(index)
        decoded = decode_registered_contours(section)
        assert [p.atlas_ids for p in decoded] == [p.atlas_ids for p in section.paths]
        assert sum(len(p.components) for p in decoded) == components
        assert sum(len(c.holes) for p in decoded for c in p.components) == holes


def test_public_value_constructors_retain_storage_and_mappings():
    source = np.array([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]], dtype=float)
    component = ContourComponent(source, [])
    ids = {"allen": -1}
    path = RegisteredContourPath(ids, [component])
    source[:] = 99
    ids["allen"] = 1
    assert component.outer[0, 0] == 0
    assert component.outer.flags.owndata and not component.outer.flags.writeable
    assert component.holes == () and path.components == (component,)
    assert path.atlas_ids["allen"] == -1


def test_large_coordinate_areas_keep_exact_nesting_order():
    path = decode(square(-(2**30), -(2**30), 2**31) + square(0, 0, 1))
    assert len(path.components) == 1
    assert len(path.components[0].holes) == 1


@pytest.mark.parametrize(
    "number",
    [
        "0.500000000000000000001",
        "1e-400",
        "1e99999999999999999999999",
        "0.250000000000000000001",
        "1" * 129,
    ],
)
def test_rejects_inexact_half_grid_numeric_lexemes(number):
    with pytest.raises(ValueError, match="half-grid|limit"):
        decode(f"M{number} 0h1v1h-1z")


def test_exact_half_grid_decimal_normalization():
    path = decode("M0.500000000000000000000 -5e-1h1.000e0v1000e-3h-1z")
    np.testing.assert_array_equal(path.components[0].outer[0], [0.5, -0.5])


def test_topology_work_budget_rejects_quadratic_ring_candidates(monkeypatch):
    import ibl_anatomy.contours as contours

    # Twenty disjoint squares take <400 sweep units, but 400 ring comparisons.
    monkeypatch.setattr(contours, "_MAX_WORK", 500)
    with pytest.raises(ValueError, match="topology work limit"):
        decode("".join(square(3 * i, 0, 1) for i in range(20)))


def test_topology_work_budget_is_shared_across_paths(monkeypatch):
    import ibl_anatomy.contours as contours

    monkeypatch.setattr(contours, "_MAX_WORK", 20)
    path = RegisteredSlicePath({"allen": 1}, "evenodd", square(0, 0, 1))
    # Each path alone fits; the combined section exceeds the shared budget.
    decode_registered_contours(RegisteredSlice(0, 0, (path,)))
    with pytest.raises(ValueError, match="topology work limit"):
        decode_registered_contours(RegisteredSlice(0, 0, (path, path, path)))
