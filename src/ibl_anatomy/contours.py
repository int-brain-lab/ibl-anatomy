"""Numerical even-odd contours for the registered voxel-edge SVG profile.

This is deliberately not a general SVG or polygon-repair library. Coordinates must
be finite half-grid values, and edges must be horizontal or vertical. Point
contacts are permitted; crossings and shared edge intervals are rejected.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np

from .registered_slices import RegisteredSlice

_TOKEN = re.compile(
    r"[MmLlHhVvZz]|[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
)
_MAX_TEXT = 16_000_000
_MAX_VERTICES = 1_000_000
_MAX_RINGS = 20_000
_MAX_WORK = 10_000_000
_MAX_NUMBER_TEXT = 128


class _WorkBudget:
    def __init__(self):
        self.remaining = _MAX_WORK

    def consume(self, count):
        self.remaining -= count
        if self.remaining < 0:
            raise ValueError("registered contour topology work limit exceeded")


def _number(token):
    # Normalize exact decimal integers before constructing a binary float. This
    # rejects lexemes that float() would round or underflow onto the half grid.
    if len(token) > _MAX_NUMBER_TEXT:
        raise ValueError("SVG contour number exceeds text limit")
    if "." not in token and "e" not in token and "E" not in token:
        integer = int(token)
        if abs(integer) > 2**31:
            raise ValueError("SVG contour numeric operand exceeds coordinate limit")
        return float(integer)
    mantissa, _, exponent = token.lower().partition("e")
    sign = -1 if mantissa.startswith("-") else 1
    mantissa = mantissa.lstrip("+-")
    whole, _, fraction = mantissa.partition(".")
    integer = int(whole + fraction)
    power = (int(exponent) if exponent else 0) - len(fraction)
    if integer == 0:
        return 0.0
    while integer % 10 == 0:
        integer //= 10
        power += 1
    if power < -1 or (power == -1 and integer % 5):
        raise ValueError("contours require exact half-grid numeric operands")
    if power > 10:
        raise ValueError("SVG contour numeric operand exceeds coordinate limit")
    doubled = integer // 5 if power == -1 else integer * 2 * 10**power
    if doubled > 2**32:
        raise ValueError("SVG contour numeric operand exceeds coordinate limit")
    return sign * doubled * 0.5


@dataclass(frozen=True)
class ContourComponent:
    """One filled exterior and its immediate holes, with explicit closure.

    Arrays own their float64 storage and are read-only; consumers needing writable
    arrays must copy them. Coordinates remain in the source (u, v) index plane.
    """

    outer: np.ndarray
    holes: tuple[np.ndarray, ...]

    def __post_init__(self):
        def retain(ring):
            array = np.array(ring, dtype=np.float64, order="C", copy=True)
            if (
                array.ndim != 2
                or array.shape[1] != 2
                or len(array) < 5
                or not np.all(np.isfinite(array))
                or not np.array_equal(array[0], array[-1])
            ):
                raise ValueError("component rings must be finite closed N-by-2 arrays")
            array.flags.writeable = False
            return array

        object.__setattr__(self, "outer", retain(self.outer))
        object.__setattr__(self, "holes", tuple(retain(hole) for hole in self.holes))


@dataclass(frozen=True)
class RegisteredContourPath:
    """Numerical components belonging to one original signed-identity path."""

    atlas_ids: Mapping[str, int]
    components: tuple[ContourComponent, ...]

    def __post_init__(self):
        object.__setattr__(self, "atlas_ids", MappingProxyType(dict(self.atlas_ids)))
        object.__setattr__(self, "components", tuple(self.components))


def decode_registered_contours(
    section: RegisteredSlice,
) -> tuple[RegisteredContourPath, ...]:
    """Decode exact rectilinear half-grid paths without changing source identity.

    Accept M/m, L/l, H/h, V/v, Z/z (including repeated operands, relative moves
    after close, and scientific notation). Every subpath must explicitly close.
    Repeated-vertex walks split into simple loops. Even-odd nesting determines
    holes and islands independently of winding and serialized ring order.
    Limits are 16 MB per path, one million vertices and 20,000 loops per slice;
    coordinates are bounded to +/-2**30, operands to +/-2**31, and numeric
    lexemes to 128 characters. A ten-million-unit per-slice topology work budget
    bounds sweep visits, ring comparisons and point-in-ring edge tests.
    The existing projection affine, rather than this decoder, maps to world space.
    """
    result = []
    budget = _WorkBudget()
    vertex_count = ring_count = 0
    for path in section.paths:
        if path.fill_rule != "evenodd":
            raise ValueError("registered contours require evenodd fill")
        rings = _parse(path.d)
        vertex_count += sum(len(ring) for ring in rings)
        ring_count += len(rings)
        if vertex_count > _MAX_VERTICES or ring_count > _MAX_RINGS:
            raise ValueError("registered contour slice exceeds numerical limits")
        _validate_intersections(rings, budget)
        components = _classify(rings, budget)
        result.append(RegisteredContourPath(path.atlas_ids, components))
    return tuple(result)


def _parse(d: str) -> list[np.ndarray]:
    if len(d) > _MAX_TEXT:
        raise ValueError("registered contour path exceeds text limit")
    tokens = []
    end = 0
    previous = None
    for match in _TOKEN.finditer(d):
        token = match.group()
        separator = d[end : match.start()]
        if (
            separator.strip(" \t\r\n,")
            or separator.count(",") > 1
            or (
                "," in separator
                and (previous is None or previous.isalpha() or token.isalpha())
            )
        ):
            raise ValueError("unsupported or invalid SVG contour token")
        tokens.append(token)
        end = match.end()
        previous = token
        if len(tokens) > 3 * _MAX_VERTICES:
            raise ValueError("registered contour path exceeds token limit")
    if d[end:].strip() or not tokens:
        raise ValueError("invalid or empty SVG contour path")
    current = (0.0, 0.0)
    walk = None
    rings = []
    command = None
    i = 0
    vertex_count = 0
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command in "Zz":
                if walk is None:
                    raise ValueError("SVG close without an open subpath")
                current = walk[0]
                if walk[-1] != walk[0]:
                    walk.append(walk[0])
                rings.extend(_split_walk(walk))
                if len(rings) > _MAX_RINGS:
                    raise ValueError("registered contour path exceeds ring limit")
                walk = None
                command = None
                continue
        if command is None or i >= len(tokens):
            raise ValueError("missing SVG contour command or operands")
        count = 1 if command in "HhVv" else 2
        if (
            i + count > len(tokens)
            or tokens[i].isalpha()
            or (count == 2 and tokens[i + 1].isalpha())
        ):
            raise ValueError("missing SVG contour operands")
        values = (
            (_number(tokens[i]),)
            if count == 1
            else (_number(tokens[i]), _number(tokens[i + 1]))
        )
        i += count
        if command in "Hh":
            point = (values[0] + (current[0] if command == "h" else 0), current[1])
        elif command in "Vv":
            point = (current[0], values[0] + (current[1] if command == "v" else 0))
        elif command.islower():
            point = (values[0] + current[0], values[1] + current[1])
        else:
            point = values
        # _number validates exact finite half-grid operands within +/-2**31.
        # Their bounded scalar sums are exactly representable binary halves;
        # allocating NumPy arrays for each vertex adds no further validation.
        if abs(point[0]) > 2**30 or abs(point[1]) > 2**30:
            raise ValueError("contours require bounded half-grid coordinates")
        vertex_count += 1
        if vertex_count > _MAX_VERTICES:
            raise ValueError("registered contour path exceeds vertex limit")
        if command in "Mm":
            if walk is not None:
                raise ValueError("every SVG contour subpath must explicitly close")
            walk = [point]
            command = "l" if command == "m" else "L"
        else:
            if walk is None:
                raise ValueError("SVG edge outside a subpath")
            if point == walk[-1]:
                raise ValueError("degenerate zero-length contour edge")
            walk.append(point)
        current = point
    if walk is not None:
        raise ValueError("every SVG contour subpath must explicitly close")
    if not rings:
        raise ValueError("no nondegenerate contour rings")
    return rings


def _split_walk(walk):
    stack = []
    positions = {}
    rings = []
    for point in walk:
        if point in positions:
            start = positions[point]
            loop = stack[start:] + [point]
            ring = np.array(loop, dtype=np.float64)
            delta = np.diff(ring, axis=0)
            if len(loop) < 5 or np.any(np.sum(delta != 0, axis=1) != 1):
                raise ValueError("degenerate or nonrectilinear contour ring")
            area = _area(ring)
            if area == 0:
                raise ValueError("degenerate zero-area contour ring")
            ring.flags.writeable = False
            rings.append(ring)
            for old in stack[start + 1 :]:
                del positions[old]
            del stack[start + 1 :]
        else:
            positions[point] = len(stack)
            stack.append(point)
    if len(stack) != 1:
        raise ValueError("unclosed contour walk")
    return rings


def _area(ring):
    # Exact signed eight-times-area: integer products avoid cancellation even
    # near the coordinate limit. Only sign and relative area are used internally.
    p = ((ring - ring[0]) * 2).astype(np.int64)
    extent = np.max(np.abs(p), axis=0)
    bound = 2 * (len(p) - 1) * int(extent[0]) * int(extent[1])
    if bound <= np.iinfo(np.int64).max:
        return int(np.sum(p[:-1, 0] * p[1:, 1] - p[1:, 0] * p[:-1, 1], dtype=np.int64))
    # Extreme legal coordinates can overflow fixed-width products or sums.
    # Preserve arbitrary-precision arithmetic for those uncommon rings.
    points = p.tolist()
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points[:-1], points[1:]))


def _inside(points, ring, budget):
    budget.consume(len(points) * len(ring))
    points = np.asarray(points)
    a, b = ring[:-1], ring[1:]
    vertical = a[:, 0] == b[:, 0]
    a, b = a[vertical], b[vertical]
    return np.array(
        [
            np.count_nonzero(((a[:, 1] > y) != (b[:, 1] > y)) & (a[:, 0] > x)) % 2 == 1
            for x, y in points
        ]
    )


def _validate_intersections(rings, budget):
    budget.consume(sum(len(ring) for ring in rings))
    # Orthogonal sweep: sorted horizontal levels avoid an all-edge-pairs scan.
    horizontal = {}
    vertical = {}
    edges = []
    for ri, ring in enumerate(rings):
        # Plain scalar edge records avoid constructing NumPy row views in this
        # Python sweep. The numerical rings remain unchanged and independently owned.
        points = ring.tolist()
        for a, b in zip(points[:-1], points[1:]):
            axis = 0 if a[1] == b[1] else 1
            level = a[1 - axis]
            lo, hi = a[axis], b[axis]
            if lo > hi:
                lo, hi = hi, lo
            record = (lo, hi, ri, len(edges))
            (horizontal if axis == 0 else vertical).setdefault(level, []).append(record)
            edges.append((lo, hi, ri))
    for groups in (horizontal, vertical):
        for records in groups.values():
            records.sort()
            high = -np.inf
            for lo, hi, _, _ in records:
                if lo < high:
                    raise ValueError("contour rings share or retrace an edge")
                high = hi
    levels = sorted(horizontal)
    events = []
    for y, records in horizontal.items():
        for lo, hi, ri, ei in records:
            events.extend(((lo, 0, y, ei), (hi, 2, y, ei)))
    for x, records in vertical.items():
        for lo, hi, ri, ei in records:
            events.append((x, 1, (lo, hi), ei))
    active = {}
    contacts = set()
    for x, kind, data, ei in sorted(events):
        if kind == 0:
            active.setdefault(data, set()).add(ei)
        elif kind == 2:
            active[data].remove(ei)
            if not active[data]:
                del active[data]
        else:
            lo, hi = data
            first, last = (
                bisect.bisect_left(levels, lo),
                bisect.bisect_right(levels, hi),
            )
            budget.consume(last - first)
            for y in levels[first:last]:
                budget.consume(len(active.get(y, ())))
                for other in active.get(y, ()):
                    horizontal_lo, horizontal_hi, ri = edges[other]
                    rj = edges[ei][2]
                    if horizontal_lo < x < horizontal_hi and lo < y < hi:
                        raise ValueError("contour edges cross")
                    if ri == rj and (horizontal_lo < x < horizontal_hi or lo < y < hi):
                        raise ValueError("contour ring touches itself along an edge")
                    if ri != rj:
                        contacts.add((min(ri, rj), max(ri, rj), x, y))
    for ri, rj, x, y in contacts:
        samples = np.array(
            [(x + dx, y + dy) for dx in (-0.125, 0.125) for dy in (-0.125, 0.125)]
        )
        a, b = _inside(samples, rings[ri], budget), _inside(samples, rings[rj], budget)
        if np.any(a & b) and np.any(a & ~b) and np.any(b & ~a):
            raise ValueError("contour interiors cross at a point contact")


def _classify(rings, budget):
    # Charge before the all-ring vector comparisons, even if bboxes are disjoint.
    budget.consume(len(rings) ** 2)
    signed_areas = [_area(ring) for ring in rings]
    areas = np.array([abs(area) for area in signed_areas], dtype=object)
    bounds = np.array([(ring.min(axis=0), ring.max(axis=0)) for ring in rings])
    parents = np.full(len(rings), -1, dtype=int)
    for i, ring in enumerate(rings):
        a, b = ring[:2]
        delta = b - a
        normal = np.array([-delta[1], delta[0]]) / np.max(np.abs(delta))
        sample = (a + b) / 2 + (1 if signed_areas[i] > 0 else -1) * 0.125 * normal
        candidates = np.flatnonzero(
            (areas > areas[i])
            & np.all(bounds[:, 0] <= sample, axis=1)
            & np.all(bounds[:, 1] >= sample, axis=1)
        )
        containing = [j for j in candidates if _inside([sample], rings[j], budget)[0]]
        if containing:
            parents[i] = min(containing, key=lambda j: areas[j])
    depths = np.zeros(len(rings), dtype=int)
    for i in np.argsort(-areas):
        if parents[i] >= 0:
            depths[i] = depths[parents[i]] + 1
    children = [[] for _ in rings]
    for j, parent in enumerate(parents):
        if parent >= 0:
            children[parent].append(rings[j])
    return tuple(
        ContourComponent(ring, tuple(children[i]))
        for i, ring in enumerate(rings)
        if depths[i] % 2 == 0
    )
