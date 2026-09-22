import React, { useMemo } from 'react';

// Renders the exact integer lattice returned by the backend as an SVG
// overlay: unit-cell grid lines in canonical HNF basis, retained points
// (green) with their integer (m,n) labels and outliers (red rings).
//
// Every grid vertex is reconstructed in data coordinates with
// p = origin + m*b1 + n*b2 (all integers), then projected to SVG space.
export default function LatticeOverlay({ result, allPoints }) {
  const geometry = useMemo(() => buildGeometry(result, allPoints), [result, allPoints]);

  if (!geometry) return null;
  const { vbW, vbH, project, gridLines, vertices, retained, outliers, originSvg } = geometry;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="lattice-svg"
      role="img"
      aria-label="晶格叠加图"

    >
      {/* Unit-cell grid: lines along b1 (fixed n) and b2 (fixed m) */}
      <g>
        {gridLines.map((line, i) => (
          <line
            key={i}
            x1={line.a.x}
            y1={line.a.y}
            x2={line.b.x}
            y2={line.b.y}
            className={line.kind === 'b1' ? 'grid-line grid-line-b1' : 'grid-line grid-line-b2'}
          />
        ))}
      </g>

      {/* Grid vertices inside the view window (faint dots) */}
      {vertices.map((v, i) => (
        <circle key={`v${i}`} cx={v.x} cy={v.y} r={1.6} className="grid-vertex" />
      ))}

      {/* Canonical coset origin */}
      <circle cx={originSvg.x} cy={originSvg.y} r={5} className="origin-dot" />
      <text x={originSvg.x + 7} y={originSvg.y - 6} className="origin-label">
        o=({result.origin[0]},{result.origin[1]})
      </text>

      {/* Retained spots */}
      {retained.map((p) => (
        <g key={`r${p.id}`}>
          <circle cx={p.sx} cy={p.sy} r={6} className="retained-dot" />
          <text x={p.sx + 8} y={p.sy - 7} className="point-label">
            {p.id} ({p.coord[0]},{p.coord[1]})
          </text>
        </g>
      ))}

      {/* Outliers */}
      {outliers.map((p) => (
        <g key={`o${p.id}`}>
          <circle cx={p.sx} cy={p.sy} r={7} className="outlier-ring" />
          <line x1={p.sx - 5} y1={p.sy - 5} x2={p.sx + 5} y2={p.sy + 5} className="outlier-cross" />
          <line x1={p.sx - 5} y1={p.sy + 5} x2={p.sx + 5} y2={p.sy - 5} className="outlier-cross" />
          <text x={p.sx + 9} y={p.sy - 8} className="outlier-label">
            {p.id} 离群
          </text>
        </g>
      ))}
    </svg>
  );
}

function buildGeometry(result, allPoints) {
  if (!result) return null;
  const b1 = result.basis.b1; // [h, r]
  const b2 = result.basis.b2; // [0, q]
  const h = b1[0];
  const r = b1[1];
  const q = b2[1];
  const origin = result.origin;

  const retainedById = new Map(result.retained.map((p) => [p.id, p]));
  const outlierIds = new Set(result.outliers);

  const plotted = allPoints
    .filter((p) => retainedById.has(p.id) || outlierIds.has(p.id))
    .map((p) => ({ id: p.id, x: Number(p.x), y: Number(p.y) }));
  if (plotted.length === 0) return null;

  const xs = plotted.map((p) => p.x);
  const ys = plotted.map((p) => p.y);
  const minX = Math.min(...xs, origin[0]);
  const maxX = Math.max(...xs, origin[0]);
  const minY = Math.min(...ys, origin[1]);
  const maxY = Math.max(...ys, origin[1]);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const pad = 0.12;
  const wLo = minX - pad * spanX - 4;
  const wHi = maxX + pad * spanX + 4;
  const yLoData = minY - pad * spanY - 4;
  const yHiData = maxY + pad * spanY + 4;

  const vbW = wHi - wLo;
  const vbH = yHiData - yLoData;
  const project = (x, y) => ({ x: x - wLo, y: yHiData - y }); // y flip

  // Integer (m,n) range whose lattice points cover the window.
  // x = ox + h*m  =>  m in [(wLo-ox)/h, (wHi-ox)/h]
  const mLo = Math.floor((wLo - origin[0]) / h) - 1;
  const mHi = Math.ceil((wHi - origin[0]) / h) + 1;
  // y = oy + r*m + q*n; bound n using extreme m values.
  const nFor = (m, yv) => (yv - origin[1] - r * m) / q;
  const nCandidates = [mLo, mHi].flatMap((m) => [
    Math.floor(nFor(m, yLoData)) - 1,
    Math.ceil(nFor(m, yHiData)) + 1
  ]);
  const nLo = Math.min(...nCandidates);
  const nHi = Math.max(...nCandidates);

  const latticePoint = (m, n) => ({
    x: origin[0] + h * m,
    y: origin[1] + r * m + q * n,
    m,
    n
  });

  const inWindow = (p) =>
    p.x >= wLo - h && p.x <= wHi + h && p.y >= yLoData - q && p.y <= yHiData + q;

  const gridLines = [];
  const vertices = [];
  for (let n = nLo; n <= nHi; n++) {
    let prev = null;
    for (let m = mLo; m <= mHi; m++) {
      const p = latticePoint(m, n);
      if (inWindow(p)) {
        vertices.push(project(p.x, p.y));
        if (prev) gridLines.push({ a: project(prev.x, prev.y), b: project(p.x, p.y), kind: 'b1' });
        prev = p;
      } else {
        prev = null;
      }
    }
  }
  for (let m = mLo; m <= mHi; m++) {
    let prev = null;
    for (let n = nLo; n <= nHi; n++) {
      const p = latticePoint(m, n);
      if (inWindow(p)) {
        if (prev) gridLines.push({ a: project(prev.x, prev.y), b: project(p.x, p.y), kind: 'b2' });
        prev = p;
      } else {
        prev = null;
      }
    }
  }

  const retained = result.retained.map((p) => {
    const s = project(Number(p.x), Number(p.y));
    return { ...p, sx: s.x, sy: s.y };
  });
  const outliers = plotted
    .filter((p) => outlierIds.has(p.id))
    .map((p) => {
      const s = project(p.x, p.y);
      return { ...p, sx: s.x, sy: s.y };
    });

  return {
    vbW,
    vbH,
    project,
    gridLines,
    vertices,
    retained,
    outliers,
    originSvg: project(origin[0], origin[1])
  };
}
