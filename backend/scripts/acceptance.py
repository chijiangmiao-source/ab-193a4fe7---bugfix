#!/usr/bin/env python3
"""One-shot acceptance check for the compose stack.

Runs:
  1. the pure-stdlib exact-arithmetic unit tests;
  2. HTTP acceptance checks against the running backend and the
     nginx-served frontend (including the nginx -> backend proxy);
  3. an independent exact re-verification of every returned lattice
     membership and the optimum on the standard contamination scenario.

Exits 0 only when everything passes; any failure -> exit 1, so the
`verify` compose service reports the result by its exit code and stops.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
WEB_URL = os.environ.get("WEB_URL", "http://web:80")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def http_get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def http_post(url, payload, timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


SAMPLE_POINTS = [
    {"id": "g0", "x": -4, "y": 0}, {"id": "g1", "x": 0, "y": 0},
    {"id": "g2", "x": 4, "y": 0}, {"id": "g3", "x": 8, "y": 0},
    {"id": "g4", "x": -3, "y": 3}, {"id": "g5", "x": 1, "y": 3},
    {"id": "g6", "x": 5, "y": 3}, {"id": "g7", "x": -1, "y": -3},
    {"id": "g8", "x": 3, "y": -3}, {"id": "g9", "x": 2, "y": 6},
    {"id": "b0", "x": -2, "y": 0}, {"id": "b1", "x": 2, "y": 0},
    {"id": "b2", "x": 1, "y": -3},
]


# Rule-generated audit batch: base O=(7,-4), A_k = O+k*(10,0) (k=1..4),
# B_k = O+k*(0,30) (k=1..3), C_k = O+k*(5,25) (k=1..4).  The difference
# vectors together generate a strictly coarser area-50 lattice (HNF
# h=5,r=5,q=10, canonical origin (2,1)) than any single pair suggests.
def rule_batch_points():
    ox, oy = 7, -4
    pts = [{"id": "O", "x": ox, "y": oy}]
    pts += [{"id": f"A{k}", "x": ox + 10 * k, "y": oy} for k in range(1, 5)]
    pts += [{"id": f"B{k}", "x": ox, "y": oy + 30 * k} for k in range(1, 4)]
    pts += [
        {"id": f"C{k}", "x": ox + 5 * k, "y": oy + 25 * k}
        for k in range(1, 5)
    ]
    return pts


RULE_POINTS = rule_batch_points()


def verify_coarse_audit(data, points, label, expect_reversed=False):
    """Exact checks for the rule-generated batch via a live API response."""
    check(data["feasible"] is True, f"[{label}] scenario is feasible")
    r = data["result"]
    check(r["area"] == 50, f"[{label}] coarsest cell area is 50 "
                           f"(got {r['area']})")
    check(r["hnf"] == {"h": 5, "r": 5, "q": 10},
          f"[{label}] canonical HNF is h=5,r=5,q=10 (got {r['hnf']})")
    check(r["basis"] == {"b1": [5, 5], "b2": [0, 10]},
          f"[{label}] basis columns are (5,5) and (0,10) (got {r['basis']})")
    check(r["origin"] == [2, 1],
          f"[{label}] canonical coset origin is (2,1) (got {r['origin']})")
    check(r["outlier_count"] == 0,
          f"[{label}] zero outliers (got {r['outlier_count']})")
    check(r["outliers"] == [], f"[{label}] no outlier ids (got {r['outliers']})")
    check(r["retained_count"] == 12,
          f"[{label}] all 12 spots retained (got {r['retained_count']})")
    by_id = {p["id"]: p for p in points}
    check({p["id"] for p in r["retained"]} == set(by_id),
          f"[{label}] retained ids are exactly the 12 input ids")
    verify_membership(r, points, label)
    if expect_reversed:
        check(r["retained"][0]["id"] == "C4",
              f"[{label}] echo preserves the reversed input order")



def verify_membership(result, points, label):
    """Independently re-derive every point from basis + integer coords."""
    h, r = result["basis"]["b1"]
    z, q = result["basis"]["b2"]
    ox, oy = result["origin"]
    check(z == 0, f"[{label}] HNF upper-right entry is 0")
    check(h > 0 and q > 0 and 0 <= r < q, f"[{label}] HNF bounds hold")
    check(result["area"] == h * q, f"[{label}] area equals h*q exactly")
    check(0 <= ox < h and 0 <= oy < q, f"[{label}] canonical origin box")
    by_id = {p["id"]: (p["x"], p["y"]) for p in points}
    out = set(result["outliers"])
    check(len(out) + len(result["retained"]) == len(by_id),
          f"[{label}] retained + outliers partition the input")
    non_collinear = 0
    for item in result["retained"]:
        x, y = by_id[item["id"]]
        m, n = item["coord"]
        check(isinstance(m, int) and isinstance(n, int),
              f"[{label}] {item['id']} has integer coordinates")
        check((ox + h * m, oy + r * m + q * n) == (x, y),
              f"[{label}] {item['id']}: o + m*b1 + n*b2 == pixel point")
    rc = [by_id[i["id"]] for i in result["retained"]]
    p0, p1 = rc[0], rc[1]
    check(
        any((p1[0] - p0[0]) * (p[1] - p0[1]) - (p1[1] - p0[1]) * (p[0] - p0[0]) != 0
            for p in rc[2:]),
        f"[{label}] retained points contain three non-collinear points",
    )


def main():
    print("== 1. exact-arithmetic unit tests ==")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "test_lattice.py")],
        cwd=ROOT,
    )
    check(proc.returncode == 0, "unit test suite exit code 0")

    print("\n== 2. backend HTTP checks ==")
    status, body = http_get(f"{BACKEND_URL}/health")
    check(status == 200 and '"ok"' in body, "backend /health responds ok")

    print("\n== 3. frontend serving and reverse proxy ==")
    status, body = http_get(f"{WEB_URL}/")
    check(status == 200 and 'id="root"' in body, "nginx serves the SPA shell")
    status, body = http_get(f"{WEB_URL}/health")
    check(status == 200 and '"ok"' in body, "nginx proxies /health to backend")

    print("\n== 4. audit: contaminated mesh -> coarsest area-12 cell ==")
    status, data = http_post(
        f"{BACKEND_URL}/api/audit",
        {"points": SAMPLE_POINTS, "min_cell_area": 12, "max_outliers": 3},
    )
    check(status == 200, "audit endpoint HTTP 200")
    check(data["feasible"] is True, "scenario is feasible")
    r = data["result"]
    check(r["area"] == 12, f"coarsest cell area is 12 (got {r['area']})")
    check(r["outlier_count"] == 3, f"exactly 3 outliers (got {r['outlier_count']})")
    check(r["outliers"] == ["b0", "b1", "b2"],
          f"outlier ids are b0,b1,b2 (got {r['outliers']})")
    check(r["retained_count"] == 10, "all 10 genuine spots retained")
    verify_membership(r, SAMPLE_POINTS, "success")

    print("\n== 5. same request through the nginx proxy ==")
    status, data2 = http_post(
        f"{WEB_URL}/api/audit",
        {"points": SAMPLE_POINTS, "min_cell_area": 12, "max_outliers": 3},
    )
    check(status == 200 and data2["feasible"] and data2["result"]["area"] == 12,
          "proxied audit returns the identical conclusion")

    print("\n== 6. audit: multi-difference batch -> coarsest area-50 cell ==")
    status, data = http_post(
        f"{BACKEND_URL}/api/audit",
        {"points": RULE_POINTS, "min_cell_area": 2, "max_outliers": 0},
    )
    check(status == 200, "rule-batch audit HTTP 200")
    verify_coarse_audit(data, RULE_POINTS, "area-50")

    print("\n== 7. same batch with reversed entry order (proxy) ==")
    reversed_points = list(reversed(RULE_POINTS))
    status, data = http_post(
        f"{WEB_URL}/api/audit",
        {"points": reversed_points, "min_cell_area": 2, "max_outliers": 0},
    )
    check(status == 200, "reordered audit through nginx HTTP 200")
    # Conclusion is order-independent; the retained echo keeps input order.
    verify_coarse_audit(data, reversed_points, "area-50-reordered",
                        expect_reversed=True)

    print("\n== 8. regression: clean area-6 lattice, zero outliers ==")
    clean6 = [
        {"id": f"p{i}", "x": 5 + 2 * m, "y": -2 + m + 3 * n}
        for i, (m, n) in enumerate(
            [(m, n) for n in range(-1, 2) for m in range(-2, 3)][:10]
        )
    ]
    status, data = http_post(
        f"{BACKEND_URL}/api/audit",
        {"points": clean6, "min_cell_area": 6, "max_outliers": 3},
    )
    check(status == 200 and data["feasible"], "area-6 batch feasible")
    r = data["result"]
    check(r["area"] == 6, f"area-6 cell retained (got {r['area']})")
    check(r["hnf"] == {"h": 2, "r": 1, "q": 3}, f"area-6 HNF (got {r['hnf']})")
    check(r["outlier_count"] == 0, f"zero area-6 outliers (got {r['outlier_count']})")
    verify_membership(r, clean6, "area-6")

    print("\n== 9. infeasible case: input retained + max-area witness ==")
    tight = [
        {"id": f"p{i}", "x": i - 4, "y": 2 * ((i - 4) % 2)} for i in range(10)
    ]
    status, data = http_post(
        f"{BACKEND_URL}/api/audit",
        {"points": tight, "min_cell_area": 1000, "max_outliers": 3},
    )
    check(status == 200 and data["feasible"] is False, "request is infeasible")
    check(data["witness"] is not None, "a verifiable witness is returned")
    check(data["witness"]["area"] < 1000, "witness area is below the target")
    check(len(data["input"]["points"]) == 10, "the full input is echoed back")
    verify_membership(data["witness"], tight, "witness")

    print("\n== 10. contract validation ==")
    bad_payloads = [
        ({"points": SAMPLE_POINTS[:5], "min_cell_area": 2, "max_outliers": 0},
         "fewer than 6 points rejected"),
        ({"points": SAMPLE_POINTS, "min_cell_area": 1, "max_outliers": 0},
         "min_cell_area < 2 rejected"),
        ({"points": SAMPLE_POINTS, "min_cell_area": 1_000_001, "max_outliers": 0},
         "min_cell_area > 1e6 rejected"),
        ({"points": SAMPLE_POINTS, "min_cell_area": 12, "max_outliers": 4},
         "max_outliers > 3 rejected"),
    ]
    for payload, label in bad_payloads:
        status, _ = http_post(f"{BACKEND_URL}/api/audit", payload)
        check(status == 422, label)

    print("\n== 11. exactness with 10^18-scale coordinates ==")
    B = 10**18
    # 8 points on the area B^2 lattice (B,0),(0,B).
    big = [{"id": f"p{i}", "x": B * m, "y": B * n}
           for i, (m, n) in enumerate(
               [(-1, -1), (0, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (-1, 1), (1, 1)])]
    status, data = http_post(
        f"{BACKEND_URL}/api/audit",
        {"points": big, "min_cell_area": 2, "max_outliers": 0},
    )
    check(status == 200 and data["feasible"], "huge-coordinate case feasible")
    check(data["result"]["area"] == B * B, f"area is exactly B^2={B*B}")
    verify_membership(data["result"], big, "bigint")

    print()
    if failures:
        print(f"ACCEPTANCE FAILED: {len(failures)} check(s) failed")
        return 1
    print("ACCEPTANCE PASSED: all checks succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
