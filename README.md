# 倒易晶格审计台（Diffraction Lattice Audit）

从电子衍射图提取的整数像素斑点中，用**精确整数运算**找出最粗的整数仿射晶格：
先最少化离群点数，再最大化基矩阵行列式绝对值（晶胞面积），
再以离群标识序列、规范 Hermite 标准形依次裁决。后端返回基矩阵、
规范余类原点以及每个保留点的整数坐标，全部可独立复算。

## 目录结构

```
backend/            FastAPI 服务（精确整数求解器）
  app/lattice.py    HNF / 扩展欧几里得 / 余类原点 / 逐点整数坐标（纯整数）
  app/solver.py     枚举删除 0..K 个点的生成格，按裁决次序求最优
  app/main.py       /health 与 POST /api/audit
  tests/            13 个纯标准库测试（含对拍独立全枚举的最优性验证）
  scripts/acceptance.py  compose verify 一次性验收脚本
frontend/           React + Vite 单页应用（SVG 晶格叠加）
  src/LatticeOverlay.jsx 用返回的整数基/原点重建网格、保留点、离群点
docker-compose.yml  backend + web + 一次性 verify 服务
```

## 运行

```bash
# 构建并启动（前端宿主机端口可用 FRONTEND_PORT 覆盖，默认 8080）
docker compose up -d --build

# 浏览器打开 http://localhost:8080
# 后端接口文档 http://localhost:8000 仅在容器网络内；通过 web 反代访问：
#   GET  http://localhost:8080/health
#   POST http://localhost:8080/api/audit
FRONTEND_PORT=9000 docker compose up -d   # 自定义宿主机端口
```

健康检查：`backend` 与 `web` 均在 Dockerfile 中声明 HEALTHCHECK；
web 的健康检查经 nginx 反代打到后端 `/health`。

## 一次性验收服务

`verify` 服务启动后自行退出，**以退出码报告结果**（0 通过，非 0 失败）：

```bash
docker compose build verify
docker compose run verify        # 退出码即验收结论
# 或随栈一起启动后查看：
docker compose up --build verify
docker inspect -f '{{.State.ExitCode}}' lattice-audit-verify
```

验收内容：13 个精确整数单元测试 → 后端 HTTP 健康 → nginx 静态页与反代 →
污染网格场景（面积 12、恰 3 个离群点 b0/b1/b2）→ 代理同请求结论一致 →
不可行时的最大面积见证可复算 → 输入契约 422 → 10^18 坐标精确性。

## 接口

`POST /api/audit`

```json
{
  "points": [{"id": "g0", "x": -4, "y": 0}],
  "min_cell_area": 12,
  "max_outliers": 3
}
```

- 6–60 个点；`id` 非空字符串且唯一；`x,y` 为整数且坐标不重复；
  `min_cell_area ∈ [2, 10^6]`；`max_outliers ∈ [0,3]`。
- 成功：`feasible=true`，`result` 含列向量基 `basis.b1/b2`（HNF）、
  规范余类原点 `origin`、`area`、每个保留点的整数坐标 `coord=(m,n)`
  （满足 `p == origin + m*b1 + n*b2`）以及排序后的离群标识。
- 失败：`feasible=false`，原样回显 `input`，并给出上限内**可核验的
  最大面积见证** `witness`（同样含基、原点与逐点整数坐标）。

任何候选至少保留三个不共线点；否则被拒绝。

## 正确性要点

- 任意保留点集 `T` 的**生成格**（基点加所有差向量的 Z-张成，HNF 由
  2×2 子式 gcd 决定）是包含 `T` 的最小格，即面积最大的格；因此最优解必为
  删除至多 K 个点后某个剩余集的生成格。枚举全部 `Σ C(n,k) (k≤3)` 删除集
  （n=60 时 34,221 个）即完备无遗漏。
- 全部运算为 Python 任意精度整数（HNF、扩展 gcd、整除判定、余类原点
  规范化），坐标 10^18、面积 10^36 亦精确。
- 前端在成功审计后若修改任意点（含离群点）或参数，旧图与旧结论立即失效
  （签名比对 + 置顶提示），必须重新审计后才显示新结果。

## 本地开发（无 Docker）

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000
# 前端
cd frontend && npm install && npm run dev   # vite 已配置 /api、/health 代理
```
