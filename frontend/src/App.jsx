import React, { useEffect, useMemo, useRef, useState } from 'react';
import { postAudit, fetchHealth } from './api.js';
import LatticeOverlay from './LatticeOverlay.jsx';
import { SAMPLE_POINTS, SAMPLE_AREA, SAMPLE_OUTLIERS } from './sampleData.js';

// Every audit request and response is tracked with a monotone id so that a
// stale in-flight or previously displayed result can never be shown after
// the input changes ("不得沿用旧图或旧结论").
let requestSeq = 0;

export default function App() {
  const [points, setPoints] = useState(() => SAMPLE_POINTS.map((p) => ({ ...p })));
  const [minArea, setMinArea] = useState(String(SAMPLE_AREA));
  const [maxOutliers, setMaxOutliers] = useState(String(SAMPLE_OUTLIERS));
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState({ checked: false, ok: false, detail: '' });

  // Serialized form of the exact inputs that produced `response`.
  const [auditedSignature, setAuditedSignature] = useState(null);
  const pendingSeq = useRef(0);

  const inputProblem = useMemo(() => validateInputs(points, minArea, maxOutliers),
    [points, minArea, maxOutliers]);

  const currentSignature = useMemo(
    () => signatureFor(points, minArea, maxOutliers),
    [points, minArea, maxOutliers]
  );

  // A result is stale as soon as the editor diverges from the inputs that
  // produced it.  While stale the overlay/conclusion are hidden until a
  // fresh audit confirms them again.
  const resultStale = response !== null && auditedSignature !== currentSignature;

  useEffect(() => {
    let alive = true;
    fetchHealth()
      .then((d) => alive && setHealth({ checked: true, ok: true, detail: d.status || 'ok' }))
      .catch((e) => alive && setHealth({ checked: true, ok: false, detail: String(e.message || e) }));
    return () => {
      alive = false;
    };
  }, []);

  async function runAudit() {
    if (inputProblem) {
      setError(inputProblem);
      return;
    }
    const seq = ++requestSeq;
    pendingSeq.current = seq;
    setLoading(true);
    setError(null);
    try {
      const data = await postAudit({
        points: points.map((p) => ({ id: p.id, x: parseInt(p.x, 10), y: parseInt(p.y, 10) })),
        minCellArea: parseInt(minArea, 10),
        maxOutliers: parseInt(maxOutliers, 10)
      });
      if (pendingSeq.current !== seq) return; // superseded by a newer request
      setResponse(data);
      setAuditedSignature(signatureFor(points, minArea, maxOutliers));
    } catch (e) {
      if (pendingSeq.current !== seq) return;
      setError(String(e.message || e));
      setResponse(null);
      setAuditedSignature(null);
    } finally {
      if (pendingSeq.current === seq) setLoading(false);
    }
  }

  function updatePoint(index, field, value) {
    setPoints((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
  }

  function addPoint() {
    setPoints((prev) => {
      const used = new Set(prev.map((p) => p.id));
      let k = prev.length;
      let id = `p${k}`;
      while (used.has(id)) id = `p${++k}`;
      return [...prev, { id, x: '0', y: '0' }];
    });
  }

  function removePoint(index) {
    setPoints((prev) => prev.filter((_, i) => i !== index));
  }

  function resetSample() {
    setPoints(SAMPLE_POINTS.map((p) => ({ ...p })));
    setMinArea(String(SAMPLE_AREA));
    setMaxOutliers(String(SAMPLE_OUTLIERS));
  }

  const result = response && response.feasible ? response.result : null;
  const witness = response && !response.feasible ? response.witness : null;
  const numericPoints = useMemo(
    () => points.map((p) => ({ id: p.id, x: Number(p.x), y: Number(p.y) })),
    [points]
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1>倒易晶格审计台</h1>
        <div className={`health ${health.ok ? 'health-ok' : health.checked ? 'health-bad' : ''}`}>
          后端健康检查：{health.checked ? (health.ok ? `正常（${health.detail}）` : `不可达（${health.detail}）`) : '检测中…'}
        </div>
      </header>

      <div className="layout">
        <section className="panel editor-panel">
          <h2>斑点输入（整数像素坐标）</h2>
          <div className="params">
            <label>
              最小晶胞面积
              <input
                type="number"
                min="2"
                max="1000000"
                step="1"
                value={minArea}
                onChange={(e) => setMinArea(e.target.value)}
              />
            </label>
            <label>
              离群上限
              <select value={maxOutliers} onChange={(e) => setMaxOutliers(e.target.value)}>
                {[0, 1, 2, 3].map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="point-table-wrap">
            <table className="point-table">
              <thead>
                <tr><th>标识</th><th>x</th><th>y</th><th></th></tr>
              </thead>
              <tbody>
                {points.map((p, i) => (
                  <tr key={i}>
                    <td>
                      <input value={p.id} onChange={(e) => updatePoint(i, 'id', e.target.value)} aria-label={`点 ${i + 1} 标识`} />
                    </td>
                    <td>
                      <input type="number" step="1" value={p.x} onChange={(e) => updatePoint(i, 'x', e.target.value)} aria-label={`点 ${p.id} x`} />
                    </td>
                    <td>
                      <input type="number" step="1" value={p.y} onChange={(e) => updatePoint(i, 'y', e.target.value)} aria-label={`点 ${p.id} y`} />
                    </td>
                    <td>
                      <button className="btn-small" onClick={() => removePoint(i)} disabled={points.length <= 6} title="至少保留 6 个点">
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="editor-actions">
            <button className="btn-small" onClick={addPoint} disabled={points.length >= 60}>+ 增加点</button>
            <button className="btn-small" onClick={resetSample}>恢复样例</button>
            <span className="point-count">{points.length} 个点</span>
          </div>

          <button className="btn-primary" onClick={runAudit} disabled={loading || !!inputProblem}>
            {loading ? '审计中…' : '执行审计'}
          </button>
          {inputProblem && <div className="inline-error">{inputProblem}</div>}
          {error && <div className="inline-error">{error}</div>}
        </section>

        <section className="panel view-panel">
          <h2>审计结果</h2>
          {resultStale && (
            <div className="stale-banner">
              输入已修改：以下图/结论对应旧输入，已停止展示。请重新执行审计。
            </div>
          )}
          {!response && !loading && !error && (
            <p className="hint">编辑左侧斑点后点击「执行审计」，结果将由后端精确整数运算给出。</p>
          )}

          {response && !resultStale && result && (
            <SuccessView result={result} examined={response.candidates_examined} points={numericPoints} />
          )}
          {response && !resultStale && !result && (
            <FailureView response={response} points={numericPoints} />
          )}
        </section>
      </div>
    </div>
  );
}

function SuccessView({ result, examined, points }) {
  return (
    <div>
      <div className="verdict verdict-ok">
        存在达标晶格：面积（基矩阵行列式绝对值）= <strong>{result.area}</strong>，
        离群点 <strong>{result.outlier_count}</strong> 个，保留 <strong>{result.retained_count}</strong> 个点
        <span className="muted">（检查候选晶格 {examined} 个）</span>
      </div>
      <div className="meta-grid">
        <div>
          <div className="meta-title">基矩阵（列向量，HNF）</div>
          <pre className="matrix">{`⎡ ${result.basis.b1[0]}  ${result.basis.b2[0]} ⎤\n⎣ ${result.basis.b1[1]}  ${result.basis.b2[1]} ⎦`}</pre>
        </div>
        <div>
          <div className="meta-title">规范余类原点 o</div>
          <pre className="matrix">({result.origin[0]}, {result.origin[1]})</pre>
          <div className="meta-title">规范 Hermite 标准形</div>
          <pre className="matrix">h={result.hnf.h}, r={result.hnf.r}, q={result.hnf.q}</pre>
        </div>
      </div>
      <div className="svg-wrap">
        <LatticeOverlay result={result} allPoints={points} />
      </div>
      <RetainedTable result={result} />
    </div>
  );
}

function FailureView({ response, points }) {
  return (
    <div>
      <div className="verdict verdict-bad">
        离群上限 {response.input.max_outliers} 内不存在面积 ≥ {response.input.min_cell_area} 的晶格。
      </div>
      <p className="reason">{response.reason}</p>
      {response.witness ? (
        <div>
          <div className="verdict verdict-witness">
            可核验的最大面积见证：面积 = <strong>{response.witness.area}</strong>，
            离群 {response.witness.outlier_count} 个。
            输入已原样保留，可据此复算。
          </div>
          <div className="meta-grid">
            <div>
              <div className="meta-title">见证晶格基（HNF）</div>
              <pre className="matrix">{`⎡ ${response.witness.basis.b1[0]}  ${response.witness.basis.b2[0]} ⎤\n⎣ ${response.witness.basis.b1[1]}  ${response.witness.basis.b2[1]} ⎦`}</pre>
            </div>
            <div>
              <div className="meta-title">余类原点</div>
              <pre className="matrix">({response.witness.origin[0]}, {response.witness.origin[1]})</pre>
            </div>
          </div>
          <div className="svg-wrap svg-wrap-witness">
            <LatticeOverlay result={response.witness} allPoints={points} />
          </div>
          <RetainedTable result={response.witness} witness />
        </div>
      ) : (
        <p className="reason">不存在保留三个不共线点的秩-2 晶格，无法给出见证。</p>
      )}
    </div>
  );
}

function RetainedTable({ result, witness = false }) {
  return (
    <details className="coord-details" open>
      <summary>{witness ? '见证晶格逐点整数坐标' : '保留点逐点整数坐标 p = o + m·b1 + n·b2'}</summary>
      <table className="coord-table">
        <thead>
          <tr><th>标识</th><th>像素 (x,y)</th><th>整数坐标 (m,n)</th><th>状态</th></tr>
        </thead>
        <tbody>
          {result.retained.map((p) => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>({p.x}, {p.y})</td>
              <td>({p.coord[0]}, {p.coord[1]})</td>
              <td className="status-ok">保留</td>
            </tr>
          ))}
          {result.outliers.map((id) => (
            <tr key={id}>
              <td>{id}</td>
              <td>—</td>
              <td>—</td>
              <td className="status-bad">离群</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function validateInputs(points, minArea, maxOutliers) {
  if (points.length < 6 || points.length > 60) return '点数必须在 6 至 60 之间';
  const ids = new Set();
  const coords = new Set();
  for (const p of points) {
    if (!p.id.trim()) return '存在空标识';
    if (ids.has(p.id)) return `标识重复：${p.id}`;
    if (!/^[+-]?\d+$/.test(String(p.x).trim()) || !/^[+-]?\d+$/.test(String(p.y).trim())) {
      return `点 ${p.id} 的坐标必须是整数`;
    }
    const key = `${p.x}|${p.y}`;
    if (coords.has(key)) return `点 ${p.id} 坐标重复 (${p.x}, ${p.y})`;
    coords.add(key);
    ids.add(p.id);
  }
  if (!/^\d+$/.test(String(minArea).trim())) return '最小面积必须为正整数';
  const a = Number(minArea);
  if (a < 2 || a > 1_000_000) return '最小晶胞面积必须在 2 至 1000000 之间';
  const k = Number(maxOutliers);
  if (!Number.isInteger(k) || k < 0 || k > 3) return '离群上限必须在 0 至 3 之间';
  return null;
}

function signatureFor(points, minArea, maxOutliers) {
  return JSON.stringify({
    points: points.map((p) => [p.id, String(p.x), String(p.y)]),
    a: String(minArea),
    k: String(maxOutliers)
  });
}
