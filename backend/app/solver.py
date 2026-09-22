"""Optimal affine-lattice search over a finite point set.

Problem
-------
Given uniquely identified integer pixel points ``P`` (6..60 of them), a
minimum unit-cell area ``A0`` and an outlier budget ``K`` (0..3), find an
integer affine lattice that

  1. keeps at least three non-collinear points,
  2. drops at most ``K`` points as outliers,
  3. has unit-cell area ``>= A0``,

optimizing lexicographically:

  a. minimum number of outliers,
  b. maximum absolute basis determinant (area),
  c. lexicographically smallest sorted tuple of outlier identifiers,
  d. smallest canonical Hermite normal form key (HNF entries then origin).

Why the enumeration is exact
----------------------------
For any retained set ``T`` whose points span rank 2, the lattice *generated*
by ``T`` (base point plus the Z-span of all differences) is, by inclusion,
the smallest lattice containing ``T`` -- equivalently the one with the
largest possible area: if another integer lattice contains ``T``, every
difference is one of its lattice vectors, so the generated lattice is a
sublattice and its area (the gcd of all pairwise 2x2 minors, the
Cauchy--Binet invariant) is no smaller.  Refining to this generated lattice
can only (i) keep the same area or enlarge it and (ii) keep the same points
or re-absorb dropped ones, so an optimum is always the generated lattice of
some retained set ``T = P \\ R`` with ``|R| <= K``.

Every such lattice is enumerated by deleting 0..K points, HNF-reducing the
remaining differences, canonicalizing the coset and counting membership over
all input points.  With ``K <= 3`` and ``n <= 60`` there are at most
``sum_{k<=3} C(60,k) = 34,221`` deletion sets, and all arithmetic is exact.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

from .lattice import (
    Mat2,
    Vec2,
    canonical_origin,
    extgcd,
    hnf22,
    lattice_key,
    member_coord,
)

MIN_POINTS = 6
MAX_POINTS = 60
MIN_AREA = 2
MAX_AREA = 1_000_000
MAX_OUTLIERS = 3


class ValidationError(ValueError):
    """Raised for request payloads that violate the input contract."""


def _gcd(a: int, b: int) -> int:
    g, _, _ = extgcd(a, b)
    return g


def _generated_lattice(pts: List[Vec2]) -> Optional[Mat2]:
    """Column HNF of the Z-span of differences ``p - pts[0]``.

    Returns ``None`` when the points are collinear (rank < 2).
    """
    base = pts[0]
    vectors: List[Vec2] = []
    for p in pts[1:]:
        v = (p[0] - base[0], p[1] - base[1])
        if v != (0, 0):
            vectors.append(v)

    seed: Optional[Tuple[Vec2, Vec2]] = None
    seed_area: Optional[int] = None
    for i, u in enumerate(vectors):
        for v in vectors[i + 1:]:
            candidate_area = abs(u[0] * v[1] - u[1] * v[0])
            if candidate_area != 0 and (
                seed_area is None or candidate_area < seed_area
            ):
                seed = (u, v)
                seed_area = candidate_area
    if seed is None:
        return None

    seed_hnf = hnf22(seed)
    if all(member_coord(seed_hnf, (0, 0), v) is not None for v in vectors):
        return seed_hnf

    horizontal_period = 0
    vertical_period = 0
    for x, y in vectors:
        horizontal_period = _gcd(horizontal_period, x)
        vertical_period = _gcd(vertical_period, y)
    return ((horizontal_period, 0), (0, vertical_period))


def _non_collinear(points: List[Vec2]) -> bool:
    """True if the list contains three points not on one line."""
    p0 = points[0]
    u = None
    for p in points[1:]:
        d = (p[0] - p0[0], p[1] - p0[1])
        if d == (0, 0):
            continue
        if u is None:
            u = d
        elif u[0] * d[1] - u[1] * d[0] != 0:
            return True
    return False


def validate(payload: Dict[str, Any]) -> Tuple[List[Tuple[str, int, int]], int, int]:
    """Validate the request payload, returning normalized arguments."""
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise ValidationError("`points` must be a list")
    if not (MIN_POINTS <= len(raw_points) <= MAX_POINTS):
        raise ValidationError(
            f"expected between {MIN_POINTS} and {MAX_POINTS} points, "
            f"got {len(raw_points)}"
        )

    points: List[Tuple[str, int, int]] = []
    seen_ids: Set[str] = set()
    seen_coords: Set[Vec2] = set()
    for i, item in enumerate(raw_points):
        if not isinstance(item, dict):
            raise ValidationError(f"point #{i} must be an object")
        pid = item.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValidationError(f"point #{i} needs a non-empty string id")
        if pid in seen_ids:
            raise ValidationError(f"duplicate point id: {pid!r}")
        x, y = item.get("x"), item.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int)
            or not isinstance(y, int)
        ):
            raise ValidationError(f"point {pid!r} coordinates must be integers")
        if (x, y) in seen_coords:
            raise ValidationError(
                f"duplicate coordinates for point {pid!r}: ({x}, {y})"
            )
        seen_ids.add(pid)
        seen_coords.add((x, y))
        points.append((pid, x, y))

    min_area = payload.get("min_cell_area")
    if isinstance(min_area, bool) or not isinstance(min_area, int):
        raise ValidationError("`min_cell_area` must be an integer")
    if not (MIN_AREA <= min_area <= MAX_AREA):
        raise ValidationError(
            f"`min_cell_area` must lie in [{MIN_AREA}, {MAX_AREA}], got {min_area}"
        )

    max_outliers = payload.get("max_outliers")
    if isinstance(max_outliers, bool) or not isinstance(max_outliers, int):
        raise ValidationError("`max_outliers` must be an integer")
    if not (0 <= max_outliers <= MAX_OUTLIERS):
        raise ValidationError(
            f"`max_outliers` must lie in [0, {MAX_OUTLIERS}], got {max_outliers}"
        )
    return points, min_area, max_outliers


def _describe(
    pid_points: List[Tuple[str, int, int]],
    H: Mat2,
    origin: Vec2,
) -> Optional[Dict[str, Any]]:
    """Membership audit of all points against one canonical lattice.

    Returns ``None`` unless at least three *input* points lie on the lattice
    and those are non-collinear.
    """
    (h, _), (r, q) = H
    ox, oy = origin
    retained: List[Dict[str, Any]] = []
    retained_coords: List[Vec2] = []
    outliers: List[str] = []
    for pid, x, y in pid_points:
        coord = member_coord(H, origin, (x, y))
        if coord is None:
            outliers.append(pid)
        else:
            retained.append(
                {"id": pid, "x": x, "y": y, "coord": [coord[0], coord[1]]}
            )
            retained_coords.append((x, y))

    if len(retained) < 3 or not _non_collinear(retained_coords):
        return None

    outliers.sort()
    return {
        "basis": {"b1": [h, r], "b2": [0, q]},
        "hnf": {"h": h, "r": r, "q": q},
        "origin": [ox, oy],
        "area": h * q,
        "retained": retained,
        "outliers": outliers,
        "outlier_count": len(outliers),
    }


def _public(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "basis": c["basis"],
        "hnf": c["hnf"],
        "origin": c["origin"],
        "area": c["area"],
        "retained": c["retained"],
        "outliers": c["outliers"],
        "outlier_count": c["outlier_count"],
        "retained_count": len(c["retained"]),
    }


def solve(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full audit and build the API response object."""
    points, min_area, max_outliers = validate(payload)
    n = len(points)
    coords = [(x, y) for _, x, y in points]

    seen_keys: Set[tuple] = set()
    candidates: List[Dict[str, Any]] = []

    def consider(remaining_idx: List[int]) -> Optional[Dict[str, Any]]:
        pts = [coords[i] for i in remaining_idx]
        if len(pts) < 3 or not _non_collinear(pts):
            return None
        H = _generated_lattice(pts)
        if H is None:
            return None
        origin = canonical_origin(H, pts[0])
        key = lattice_key(H, origin)
        if key in seen_keys:
            return None
        seen_keys.add(key)
        desc = _describe(points, H, origin)
        if desc is None:
            return None
        desc["key"] = key
        candidates.append(desc)
        return desc

    def better(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Lexicographic optimum: fewer outliers, then larger area, then
        smaller outlier-id sequence, then smaller canonical HNF key."""
        ka = (a["outlier_count"], -a["area"], tuple(a["outliers"]), a["key"])
        kb = (b["outlier_count"], -b["area"], tuple(b["outliers"]), b["key"])
        return ka < kb

    all_idx = list(range(n))
    best: Optional[Dict[str, Any]] = None

    # Deletion count k ascends.  A lattice whose *true* outlier count is o
    # is necessarily generated at level k=o (delete exactly its outliers);
    # any level-k key with fewer true outliers would already have appeared at
    # an earlier level, where seen_keys deduplicates it.  Once the first
    # feasible level is fully scanned, larger k cannot improve the optimum
    # (those lattices have strictly more outliers), so we stop.
    for k in range(0, max_outliers + 1):
        if k == 0:
            desc = consider(all_idx)
            if desc is not None and desc["area"] >= min_area and (
                best is None or better(desc, best)
            ):
                best = desc
        else:
            for removed in combinations(all_idx, k):
                removed_set = set(removed)
                remaining = [i for i in all_idx if i not in removed_set]
                desc = consider(remaining)
                if desc is None or desc["area"] < min_area:
                    continue
                if best is None or better(desc, best):
                    best = desc
        if best is not None:
            break

    input_echo = {
        "points": [{"id": pid, "x": x, "y": y} for pid, x, y in points],
        "min_cell_area": min_area,
        "max_outliers": max_outliers,
    }

    if best is not None:
        return {
            "feasible": True,
            "result": _public(best),
            "candidates_examined": len(seen_keys),
            "input": input_echo,
        }

    # No lattice within budget meets the area target.  Report the
    # largest-area witness actually attainable (exact, re-checkable), so the
    # failure is verifiable rather than asserted.
    witness = None
    reason = "no rank-2 lattice keeps three non-collinear points"
    if candidates:
        candidates.sort(
            key=lambda c: (
                -c["area"],
                c["outlier_count"],
                tuple(c["outliers"]),
                c["key"],
            )
        )
        witness = _public(candidates[0])
        if witness["area"] < min_area:
            reason = (
                f"within the outlier budget {max_outliers} the largest "
                f"attainable unit-cell area is {witness['area']}, below the "
                f"required minimum {min_area}"
            )
        else:
            reason = "no candidate keeps three non-collinear retained points"

    return {
        "feasible": False,
        "reason": reason,
        "witness": witness,
        "candidates_examined": len(seen_keys),
        "input": input_echo,
    }
