// Typed access to the real backend audit API.  All numeric values are
// serialized as JSON numbers; the backend performs exact integer
// arithmetic, so coordinates must not pass through any float formatting.

export async function fetchHealth() {
  const res = await fetch('/health');
  if (!res.ok) throw new Error(`health check failed: HTTP ${res.status}`);
  return res.json();
}

export async function postAudit({ points, minCellArea, maxOutliers }) {
  const body = {
    points: points.map((p) => ({ id: p.id, x: Number(p.x), y: Number(p.y) })),
    min_cell_area: Number(minCellArea),
    max_outliers: Number(maxOutliers)
  };
  const res = await fetch('/api/audit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const detail =
      data && (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data));
    throw new Error(detail || `审计请求失败：HTTP ${res.status}`);
  }
  return data;
}
