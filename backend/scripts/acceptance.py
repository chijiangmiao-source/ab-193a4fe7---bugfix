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

    print("\n== 6. infeasible case: input retained + max-area witness ==")
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

    print("\n== 7. contract validation ==")
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

    print("\n== 8. exactness with 10^18-scale coordinates ==")
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
