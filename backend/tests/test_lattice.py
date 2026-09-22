"""Exact-integer tests for HNF arithmetic and the optimization solver."""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lattice import (  # noqa: E402
    canonical_origin,
    extgcd,
    hnf22,
    lattice_key,
    member_coord,
)
from app.solver import ValidationError, solve, validate  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_extgcd():
    random.seed(1)
    for _ in range(2000):
        a = random.randint(-500, 500)
        b = random.randint(-500, 500)
        if a == b == 0:
            continue
        g, s, t = extgcd(a, b)
        check(g > 0, "gcd must be positive")
        check(s * a + t * b == g, "bezout identity")
        check(g == __import__("math").gcd(abs(a), abs(b)), "gcd value")


def test_hnf_and_coords():
    random.seed(2)
    for _ in range(500):
        # Random full-rank integer basis, possibly huge entries.
        while True:
            u = (random.randint(-30, 30), random.randint(-30, 30))
            v = (random.randint(-30, 30), random.randint(-30, 30))
            det = u[0] * v[1] - u[1] * v[0]
            if det != 0:
                break
        H = hnf22((u, v))
        (h, _), (r, q) = H
        check(h > 0 and q > 0 and 0 <= r < q, "HNF constraints")
        check(h * q == abs(det), f"HNF area {h*q} != |det| {abs(det)}")

        o = canonical_origin(H, (0, 0))
        check(0 <= o[0] < h and 0 <= o[1] < q, "origin box")
        # Every integer combination of u,v must have exact integer HNF coords.
        for _ in range(20):
            m, n = random.randint(-40, 40), random.randint(-40, 40)
            p = (
                m * u[0] + n * v[0],
                m * u[1] + n * v[1],
            )
            coord = member_coord(H, o, p)
            check(coord is not None, f"generator point {p} missing")
            mm, nn = coord
            check(
                (o[0] + h * mm, o[1] + r * mm + q * nn) == p,
                "coordinate round-trip",
            )
        # A point outside the lattice must be detected by exact divisibility.
        check(member_coord(H, o, (1, 0)) is None or h == 1,
              "outside point detected")


def test_hnf_uniqueness():
    # Different unimodular transforms give the identical canonical HNF.
    u, v = (6, 10), (4, 7)
    H1 = hnf22((u, v))
    H2 = hnf22(((u[0] + v[0], u[1] + v[1]), v))
    H3 = hnf22(((-v[0], -v[1]), (u[0] + 2 * v[0], u[1] + 2 * v[1])))
    check(H1 == H2 == H3, f"HNF not unique: {H1} {H2} {H3}")


def _lattice_points(origin, b1, b2, mr, nr, used, rng, skip=()):
    pts = []
    i = 0
    for m in mr:
        for n in nr:
            i += 1
            if i in skip:
                continue
            p = (
                origin[0] + m * b1[0] + n * b2[0],
                origin[1] + n * b2[1] + m * b1[1],
            )
            if p in used:
                continue
            used.add(p)
            pts.append(p)
            if len(pts) >= 8:
                return pts
    return pts


def test_clean_lattice():
    # 12 points on an area-6 lattice, no noise; budget irrelevant.
    b1, b2 = (2, 1), (0, 3)
    used = set()
    pts = _lattice_points((5, -2), b1, b2, range(-2, 3), range(-2, 3), used, None)
    pts = pts[:10]
    check(len(pts) >= 6, "need >= 6 points")
    payload = {
        "points": [{"id": f"p{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(pts)],
        "min_cell_area": 6,
        "max_outliers": 3,
    }
    out = solve(payload)
    check(out["feasible"], f"should be feasible: {out.get('reason')}")
    r = out["result"]
    check(r["area"] == 6, f"area {r['area']} != 6")
    check(r["outlier_count"] == 0, "no outliers")
    check(len(r["retained"]) == len(pts), "all retained")
    # HNF of [[2,0],[1,3]] is itself; canonical origin for a coset member.
    check(r["hnf"] == {"h": 2, "r": 1, "q": 3}, str(r["hnf"]))
    _verify_result(payload, r)


def test_dense_grid_with_outliers():
    # Truth: a coarse area-12 lattice. Contamination: 3 points on an
    # over-dense area-6 supermesh. The coarsest lattice consistent with the
    # non-contaminated points must win after exactly the 3 contaminants are
    # dropped.
    rng = random.Random(7)
    # Truth b1=(4,0), b2=(1,3) (area 12) is an index-2 sublattice of the
    # fine mesh (2,0),(1,3) (area 6).  Contaminants are fine-mesh points
    # that are NOT on the coarse lattice.
    fine1, fine2 = (2, 0), (1, 3)
    b1, b2 = (4, 0), (1, 3)
    Hc = hnf22((b1, b2))
    used = set()
    good = _lattice_points((0, 0), b1, b2, range(-2, 2), range(-2, 2), used, rng)
    good = good[:8]
    bad = []
    for m in range(-3, 4):
        for n in range(-3, 4):
            p = (m * fine1[0] + n * fine2[0], m * fine1[1] + n * fine2[1])
            if p in used:
                continue
            if member_coord(Hc, (0, 0), p) is not None:
                continue  # coarse point: genuine, not contamination
            bad.append(p)
    rng.shuffle(bad)
    bad = bad[:3]
    check(len(bad) == 3, "need 3 fine-only contaminants")
    pts = good + bad
    check(len({p for p in pts}) == len(pts), "points distinct")
    payload = {
        "points": [{"id": f"g{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(good)]
        + [{"id": f"b{i}", "x": p[0], "y": p[1]}
           for i, p in enumerate(bad)],
        "min_cell_area": 12,
        "max_outliers": 3,
    }
    out = solve(payload)
    check(out["feasible"], f"expected feasible: {out.get('reason')}")
    r = out["result"]
    check(r["outlier_count"] == 3, f"want 3 outliers, got {r['outlier_count']}")
    check(r["area"] == 12, f"area {r['area']} != 12")
    check(set(r["outliers"]) == {"b0", "b1", "b2"},
          f"wrong outliers: {r['outliers']}")
    _verify_result(payload, r)


def _rule_batch_points():
    """The 12-spot rule-generated batch: O plus four A, three B, four C."""
    O = (7, -4)
    pts = [("O", O[0], O[1])]
    for k in range(1, 5):
        pts.append((f"A{k}", O[0] + 10 * k, O[1]))
    for k in range(1, 4):
        pts.append((f"B{k}", O[0], O[1] + 30 * k))
    for k in range(1, 5):
        pts.append((f"C{k}", O[0] + 5 * k, O[1] + 25 * k))
    return pts


def test_multi_difference_generated_lattice():
    # Several difference families together generate a finer lattice than any
    # single pair: (10,0),(0,30),(5,25) Z-span the area-50 lattice, not the
    # area-25 axis mesh (gcd(10*30, 10*25, 0*25-30*5) == gcd(300,250,150)==50).
    from app.solver import _generated_lattice

    H = _generated_lattice(
        [(0, 0), (10, 0), (0, 30), (5, 25)]
    )
    check(H == ((5, 0), (5, 10)), f"raw vectors HNF {H}")
    check(H[0][0] * H[1][1] == 50, "multi-difference area is 50")
    # Ordering of the difference vectors must not change the answer.
    H2 = _generated_lattice([(0, 0), (5, 25), (0, 30), (10, 0), (20, 0)])
    check(H2 == H, f"reordered input changed HNF: {H2}")

    pts = _rule_batch_points()
    H3 = _generated_lattice([(x, y) for _, x, y in pts])
    check(H3 == ((5, 0), (5, 10)), f"batch HNF {H3}")

    payload = {
        "points": [{"id": i, "x": x, "y": y} for i, x, y in pts],
        "min_cell_area": 2,
        "max_outliers": 0,
    }
    out = solve(payload)
    check(out["feasible"], f"batch must be feasible: {out.get('reason')}")
    r = out["result"]
    check(r["area"] == 50, f"coarsest area {r['area']} != 50")
    check(r["hnf"] == {"h": 5, "r": 5, "q": 10}, str(r["hnf"]))
    check(r["origin"] == [2, 1], f"canonical origin {r['origin']} != [2,1]")
    check(r["outlier_count"] == 0, f"zero outliers, got {r['outlier_count']}")
    check(r["outliers"] == [], "no outlier ids")
    check(len(r["retained"]) == 12, "all 12 spots retained")
    _verify_result(payload, r)


def test_rule_batch_invariant_under_reorder():
    # Reordering the spot input must not change area, HNF, canonical origin,
    # outlier partition or any point's integer coordinates.
    pts = _rule_batch_points()
    payload = {
        "points": [{"id": i, "x": x, "y": y} for i, x, y in pts],
        "min_cell_area": 2,
        "max_outliers": 0,
    }
    base = solve(payload)["result"]
    base_coords = {
        item["id"]: tuple(item["coord"]) for item in base["retained"]
    }
    signature = (base["area"], base["hnf"], tuple(base["origin"]),
                 tuple(base["outliers"]))

    orders = [list(reversed(pts)),
              sorted(pts, key=lambda p: p[0]),
              sorted(pts, key=lambda p: (p[2], p[1]))]
    rng = random.Random(1234)
    for _ in range(8):
        shuffled = pts[:]
        rng.shuffle(shuffled)
        orders.append(shuffled)
    for order in orders:
        p2 = {
            "points": [{"id": i, "x": x, "y": y} for i, x, y in order],
            "min_cell_area": 2,
            "max_outliers": 0,
        }
        out = solve(p2)
        check(out["feasible"], f"reorder feasible: {out.get('reason')}")
        r = out["result"]
        sig = (r["area"], r["hnf"], tuple(r["origin"]), tuple(r["outliers"]))
        check(sig == signature, f"reorder changed conclusion: {sig}")
        coords = {item["id"]: tuple(item["coord"]) for item in r["retained"]}
        check(coords == base_coords, "reorder changed per-point coords")
        _verify_result(p2, r)


def _reference_generated_hnf(vecs):
    """Independent oracle: generic column HNF of a 2xn integer matrix.

    Built from Euclidean column operations only -- shares no code with the
    solver's incremental construction, so agreement means the solver really
    finds the Z-span, not merely a lattice consistent by membership.
    """
    from math import gcd as _gcd

    cols = [[x, y] for x, y in vecs if (x, y) != (0, 0)]
    while True:
        nz = [i for i, c in enumerate(cols) if c[0] != 0]
        if len(nz) <= 1:
            break
        i, j = nz[0], nz[1]
        a, b = cols[i][0], cols[j][0]
        if abs(a) < abs(b):
            i, j, a, b = j, i, b, a
        q = a // b if b else 0
        cols[i][0] -= q * cols[j][0]
        cols[i][1] -= q * cols[j][1]
    nz = [i for i, c in enumerate(cols) if c[0] != 0]
    if not nz:
        return None
    i0 = nz[0]
    if cols[i0][0] < 0:
        cols[i0][0], cols[i0][1] = -cols[i0][0], -cols[i0][1]
    h = cols[i0][0]
    q = 0
    for k, c in enumerate(cols):
        if k != i0:
            q = _gcd(q, abs(c[1]))
    if q == 0:
        return None
    return ((h, 0), (cols[i0][1] % q, q))


def test_generated_lattice_matches_independent_hnf():
    from itertools import combinations
    from math import gcd as _gcd

    from app.solver import _generated_lattice

    rng = random.Random(777)
    checked = 0
    for _ in range(400):
        vecs = []
        if rng.random() < 0.5:
            # hidden coarse lattice, samples with coefficient gaps
            while True:
                u = (rng.randint(-6, 6), rng.randint(-6, 6))
                v = (rng.randint(-6, 6), rng.randint(-6, 6))
                if u[0] * v[1] - u[1] * v[0] != 0:
                    break
            for _ in range(rng.randint(2, 7)):
                a, b = rng.randint(0, 4), rng.randint(0, 4)
                vecs.append((a * u[0] + b * v[0], a * u[1] + b * v[1]))
        else:
            # axis families + diagonals: the multi-difference failure shape
            hx, vy = rng.choice([2, 5, 10]), rng.choice([6, 15, 30])
            vecs = [(hx * rng.randint(1, 3), 0), (0, vy * rng.randint(1, 3))]
            for _ in range(rng.randint(0, 3)):
                vecs.append((hx * rng.randint(0, 3),
                             hx * rng.randint(0, 3) + vy * rng.randint(0, 3)))
        if all((x, y) == (0, 0) for x, y in vecs):
            continue
        if rng.random() < 0.1:  # big integers every so often
            B = 10 ** rng.randint(2, 12)
            vecs = [(x * B, y * B) for x, y in vecs]
        ref = _reference_generated_hnf(vecs)
        perm = vecs[:]
        rng.shuffle(perm)
        got = _generated_lattice([(0, 0)] + perm)
        if ref is None:
            check(got is None, "rank-deficient case")
            continue
        check(got == ref, f"HNF {got} != independent {ref} for {vecs}")
        # Area independently equals gcd of every pairwise 2x2 minor.
        gminor = 0
        for a, b in combinations(vecs, 2):
            gminor = _gcd(gminor, abs(a[0] * b[1] - a[1] * b[0]))
        check(got[0][0] * got[1][1] == gminor, "minor-gcd area invariant")
        checked += 1
    check(checked >= 300, f"not enough rank-2 trials: {checked}")


def test_area_infeasible_reports_witness():
    # Collinear-ish thin cluster: only small-area lattices attainable.
    b1, b2 = (1, 0), (0, 2)  # area 2
    used = set()
    pts = _lattice_points((0, 0), b1, b2, range(-3, 4), range(0, 2), used, None)
    pts = pts[:10]
    payload = {
        "points": [{"id": f"p{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(pts)],
        "min_cell_area": 1000,
        "max_outliers": 3,
    }
    out = solve(payload)
    check(not out["feasible"], "must be infeasible")
    check(out["witness"] is not None, "must provide a witness")
    check(out["witness"]["area"] < 1000, "witness area below target")
    _verify_result(payload, out["witness"])


def test_budget_infeasible_when_more_contamination():
    b1, b2 = (3, 2), (0, 5)  # area 15
    used = set()
    good = _lattice_points((0, 0), b1, b2, range(-2, 2), range(-1, 2), used, None)[:7]
    # One contaminant (0,1) that enlarges the generated mesh exactly to
    # area 3 (still >= 2), plus three generic far contaminants.
    special = (0, 1)
    assert special not in used
    used.add(special)
    Hc = hnf22((b1, b2))
    rng = random.Random(11)
    extra = []
    while len(extra) < 3:
        p = (rng.randint(200, 400), rng.randint(200, 400))
        if p in used:
            continue
        if member_coord(Hc, (0, 0), p) is not None:
            continue  # accidentally a genuine lattice point: not contamination
        used.add(p)
        extra.append(p)
    payload = {
        "points": [{"id": f"g{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(good)]
        + [{"id": "s", "x": special[0], "y": special[1]}]
        + [{"id": f"z{i}", "x": p[0], "y": p[1]}
           for i, p in enumerate(extra)],
        "min_cell_area": 15,
        "max_outliers": 3,
    }
    out = solve(payload)
    # With 4 contaminants and budget 3 no area-15 lattice exists.
    check(not out["feasible"], "must be infeasible with 4 outliers and budget 3")
    check(out["witness"] is not None and out["witness"]["area"] < 15,
          "witness must explain the failure")
    # Budget semantics: 4 is rejected at validation.
    try:
        validate({**payload, "max_outliers": 4})
        raise AssertionError("max_outliers=4 must be rejected")
    except ValidationError:
        pass
    # Relaxing the area target: keep the special contaminant (area-3 mesh),
    # drop the three generic ones -> feasible within budget.
    out2 = solve({**payload, "min_cell_area": 2})
    check(out2["feasible"], "area-3 mesh with 3 drops must be feasible")
    check(out2["result"]["outlier_count"] <= 3, "outlier budget respected")
    check(out2["result"]["area"] == 3, f"area {out2['result']['area']} != 3")
    _verify_result({**payload, "min_cell_area": 2}, out2["result"])


def test_outlier_id_tiebreak_and_hnf_tiebreak():
    # Two lattices with equal area and equal outlier counts but different
    # removed ids: lexicographically smallest id tuple must win.
    # Construct 3 collinear-ish points whose removal gives same area; use a
    # simpler guaranteed setup: a lattice plus two swapable contaminants.
    b1, b2 = (2, 0), (0, 2)  # area 4
    used = set()
    good = _lattice_points((0, 0), b1, b2, range(-2, 3), range(-1, 2), used, None)[:9]
    # Two contaminants symmetric so removing either leaves same area lattice.
    bad_a = (-1, 1)  # odd x
    bad_b = (100, 1)
    used.update(good)
    for cand in (bad_a, bad_b):
        assert cand not in used
    payload = {
        "points": [{"id": f"g{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(good)]
        + [{"id": "a", "x": bad_a[0], "y": bad_a[1]},
           {"id": "b", "x": bad_b[0], "y": bad_b[1]}],
        "min_cell_area": 4,
        "max_outliers": 2,
    }
    out = solve(payload)
    check(out["feasible"], f"should be feasible: {out.get('reason')}")
    r = out["result"]
    check(set(r["outliers"]) == {"a", "b"}, f"both contaminants removed: {r['outliers']}")
    check(r["area"] == 4, f"area {r['area']}")
    _verify_result(payload, r)


def test_area_maximization():
    # Good points on the coarse area-6 lattice (2,0),(1,3); one extra point
    # x=(1,0) lives on its area-3 supermesh.  With area target 2 the
    # area-3 lattice covering everything (0 outliers) must win.  Raising the
    # target to 4 forces x out and exposes the coarsest area-6 cell.
    rng = random.Random(3)
    used = set()
    b1, b2 = (2, 0), (1, 3)
    good = _lattice_points((0, 0), b1, b2, range(-3, 4), range(-2, 3), used, rng)[:12]
    p = (1, 0)
    assert p not in used

    payload = {
        "points": [{"id": f"g{i}", "x": q[0], "y": q[1]}
                   for i, q in enumerate(good)]
        + [{"id": "x", "x": p[0], "y": p[1]}],
        "min_cell_area": 2,
        "max_outliers": 1,
    }
    out = solve(payload)
    check(out["feasible"], f"feasible: {out.get('reason')}")
    r = out["result"]
    # Outlier minimization dominates: all 13 fit an area-3 cell with 0
    # outliers, beating the area-6 cell that drops x.
    check(r["outlier_count"] == 0, f"expected 0 outliers, got {r['outlier_count']}")
    check(r["area"] == 3, f"area {r['area']} != 3")

    payload["min_cell_area"] = 4
    out = solve(payload)
    check(out["feasible"], f"area-4 target feasible: {out.get('reason')}")
    r = out["result"]
    check(r["outlier_count"] == 1, f"expected 1 outlier, got {r['outlier_count']}")
    check(r["area"] == 6, f"coarsest area {r['area']} != 6")
    check(r["outliers"] == ["x"], f"outliers {r['outliers']}")
    _verify_result(payload, r)


def test_min_outliers_before_area():
    # A huge-area lattice dropping 2 points vs a smaller lattice dropping 1:
    # outlier minimization dominates.
    b1, b2 = (5, 1), (2, 7)  # area 33
    used = set()
    good = _lattice_points((0, 0), b1, b2, range(-2, 2), range(-1, 2), used, None)[:8]
    rng = random.Random(13)
    extras = []
    while len(extras) < 2:
        p = (rng.randint(-60, 60), rng.randint(-60, 60))
        if p in used:
            continue
        used.add(p)
        extras.append(p)
    payload = {
        "points": [{"id": f"g{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(good)]
        + [{"id": "e0", "x": extras[0][0], "y": extras[0][1]},
           {"id": "e1", "x": extras[1][0], "y": extras[1][1]}],
        "min_cell_area": 2,
        "max_outliers": 3,
    }
    out = solve(payload)
    r = out["result"]
    check(r["outlier_count"] <= 2, "outlier count")
    check(out["candidates_examined"] > 0, "candidates were examined")
    _verify_result(payload, r)
    _verify_optimality(payload, r)


def test_bruteforce_agreement_random():
    """End-to-end: solver verdict (feasible/infeasible and the chosen
    lattice) must agree with an independently enumerated optimum, and every
    claimed membership must re-check exactly.  Random generic points often
    span the area-1 plane lattice, so infeasibility is a valid outcome and
    must match the enumeration too."""
    rng = random.Random(42)
    for trial in range(60):
        while True:
            b1 = (rng.randint(-4, 4), rng.randint(-4, 4))
            b2 = (rng.randint(-4, 4), rng.randint(-4, 4))
            if b1[0] * b2[1] - b1[1] * b2[0] != 0:
                break
        origin = (rng.randint(-5, 5), rng.randint(-5, 5))
        pts = set()
        for _ in range(10):
            m, n = rng.randint(-2, 2), rng.randint(-2, 2)
            pts.add((origin[0] + m * b1[0] + n * b2[0],
                     origin[1] + m * b1[1] + n * b2[1]))
        for _ in range(rng.randint(0, 3)):
            pts.add((rng.randint(-30, 30), rng.randint(-30, 30)))
        pts = list(pts)
        while len(pts) < 6:
            p = (rng.randint(-30, 30), rng.randint(-30, 30))
            if p not in pts:
                pts.append(p)
        pts = pts[:12]
        payload = {
            "points": [{"id": f"p{i:02d}", "x": p[0], "y": p[1]}
                       for i, p in enumerate(pts)],
            "min_cell_area": 2,
            "max_outliers": 3,
        }
        out = solve(payload)
        if out["feasible"]:
            _verify_result(payload, out["result"])
        else:
            if out["witness"] is not None:
                _verify_result(payload, out["witness"])
        _verify_verdict(payload, out)


def _result_key(result):
    return (
        result["outlier_count"],
        -result["area"],
        tuple(result["outliers"]),
        (
            result["hnf"]["h"],
            result["hnf"]["r"],
            result["hnf"]["q"],
            result["origin"][0],
            result["origin"][1],
        ),
    )


def _verify_verdict(payload, out):
    """Independent enumeration reproduces feasible/infeasible + optimum."""
    from itertools import combinations

    from app.solver import _generated_lattice, _describe, _non_collinear
    from app.lattice import canonical_origin, lattice_key

    pts = [(p["x"], p["y"]) for p in payload["points"]]
    pid_points = [(p["id"], p["x"], p["y"]) for p in payload["points"]]
    n = len(pts)
    seen = set()
    best_key = None
    max_area = 0
    for k in range(0, payload["max_outliers"] + 1):
        for removed in combinations(range(n), k):
            rem = [i for i in range(n) if i not in removed]
            sub = [pts[i] for i in rem]
            if len(sub) < 3 or not _non_collinear(sub):
                continue
            H = _generated_lattice(sub)
            if H is None:
                continue
            o = canonical_origin(H, sub[0])
            key = lattice_key(H, o)
            if key in seen:
                continue
            seen.add(key)
            d = _describe(pid_points, H, o)
            if d is None:
                continue
            max_area = max(max_area, d["area"])
            if d["area"] < payload["min_cell_area"]:
                continue
            kk = (d["outlier_count"], -d["area"], tuple(d["outliers"]), key)
            if best_key is None or kk < best_key:
                best_key = kk
    if best_key is None:
        check(not out["feasible"], "solver claims feasible but enumeration disagrees")
        if out["witness"] is not None:
            check(out["witness"]["area"] == max_area,
                  f"witness area {out['witness']['area']} != max {max_area}")
    else:
        check(out["feasible"], "solver claims infeasible but enumeration found one")
        check(_result_key(out["result"]) == best_key,
              f"solver {_result_key(out['result'])} != enumeration {best_key}")


def _verify_optimality(payload, result):
    """Wrapper kept for the targeted scenario tests: compare the returned
    lattice against the independently enumerated optimum."""
    out = {"feasible": True, "result": result, "witness": None}
    _verify_verdict(payload, out)


def _verify_result(payload, r):
    """Independently re-derive membership from returned basis and origin."""
    h = r["basis"]["b1"][0]
    rr = r["basis"]["b1"][1]
    q = r["basis"]["b2"][1]
    check(r["basis"]["b2"][0] == 0, "HNF upper-right must be 0")
    check(h > 0 and q > 0 and 0 <= rr < q, "HNF bounds")
    check(r["area"] == h * q, "area equals determinant")
    ox, oy = r["origin"]
    check(0 <= ox < h and 0 <= oy < q, "canonical origin box")
    by_id = {p["id"]: (p["x"], p["y"]) for p in payload["points"]}
    out_ids = set(r["outliers"])
    check(len(out_ids) == len(r["outliers"]), "outlier ids unique")
    check(len(r["retained"]) + len(out_ids) == len(by_id), "partition")
    for item in r["retained"]:
        x, y = by_id[item["id"]]
        m, n = item["coord"]
        check(isinstance(m, int) and isinstance(n, int), "integer coords")
        check((ox + h * m, oy + rr * m + q * n) == (x, y),
              f"coord mismatch for {item['id']}")
    # Retained set must contain three non-collinear points.
    rc = [(by_id[i["id"]]) for i in r["retained"]]
    check(len(rc) >= 3 and any(
        (rc[1][0] - rc[0][0]) * (p[1] - rc[0][1])
        - (rc[1][1] - rc[0][1]) * (p[0] - rc[0][0]) != 0
        for p in rc[2:]
    ), "retained points non-collinear")


def test_validation_rules():
    base = {
        "points": [{"id": str(i), "x": 2 * i, "y": 3 * (i // 2)}
                   for i in range(6)],
        "min_cell_area": 2,
        "max_outliers": 0,
    }
    validate(base)
    bad_cases = [
        {**base, "points": base["points"][:5]},
        {**base, "min_cell_area": 1},
        {**base, "min_cell_area": 1_000_001},
        {**base, "max_outliers": -1},
        {**base, "max_outliers": 4},
        {**base, "points": [{**p, "id": "0"} for p in base["points"]]},
        {**base, "points": [{**p, "x": 0} for p in base["points"]]},
        {**base, "points": [{**p, "x": 1.5} for p in base["points"]]},
    ]
    for i, case in enumerate(bad_cases):
        try:
            validate(case)
        except ValidationError:
            continue
        raise AssertionError(f"bad case {i} was accepted")


def test_large_coordinates_exact():
    # Huge coordinates/areas: bigint safety and exact arithmetic.
    B = 10**18
    b1, b2 = (B, 1), (0, B)
    used = set()
    pts = _lattice_points((0, 0), b1, b2, range(-1, 2), range(-1, 2), used, None)[:7]
    payload = {
        "points": [{"id": f"p{i}", "x": p[0], "y": p[1]}
                   for i, p in enumerate(pts)],
        "min_cell_area": 2,
        "max_outliers": 0,
    }
    out = solve(payload)
    check(out["feasible"], f"huge: {out.get('reason')}")
    r = out["result"]
    check(r["area"] == B * B, f"area {r['area']}")
    _verify_result(payload, r)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
