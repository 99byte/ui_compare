## 背景与问题
- 当前 `README.md` 的后端安装指南假设依赖文件在 `backend/requirements.txt`，但实际依赖文件位于仓库根目录（见 README.md:19）。
- 项目已前后端分离（`backend/` + `frontend/`），但依赖与环境文件未按标准位置归档，且仓库包含本地 `venv/`，不符合通用最佳实践。

## 目标
- 采用更标准的国际化前后端分离组织结构（可演进为双仓），将后端依赖归档至后端目录，完善忽略规则，保持启动脚本一致，并更新 `README` 与目录结构说明。

## 新的目录组织（单仓，双仓友好）
- 根目录：保留 `frontend/` 与 `backend/`，并在后端目录内放置依赖文件；新增根 `.gitignore`。
```
ui_compare/
├─ backend/
│  ├─ app.py
│  ├─ matcher.py
│  ├─ differ.py
│  ├─ semantic_graph.py
│  └─ requirements.txt
├─ frontend/
│  ├─ package.json
│  ├─ src/ ...
│  └─ node_modules/ (被忽略)
├─ output/ (运行产物，被忽略)
├─ start.sh
├─ README.md
└─ .gitignore (新增)
```
- 可选后续：真正多仓时，将 `backend/`、`frontend/` 分离为两个 Git 仓库；当前结构已与多仓一致（顶层说明与各自独立安装/运行），迁移成本低。

## 具体改动
1. 移动依赖文件
   - 将根目录 `requirements.txt` 移动到 `backend/requirements.txt`，保持内容不变。
2. 新增根 `.gitignore`
   - 忽略：`/venv/`、`/output/`、`/frontend/node_modules/`、`**/__pycache__/`、`*.pyc`、`.DS_Store`、`.vercel/`。
3. 清理不应提交的本地环境
   - 从仓库移除已提交的 `venv/` 目录（开发者本地重建虚拟环境）。
4. 保持启动脚本
   - `start.sh` 无需变更，继续后端 5050 + 前端 3000 并行启动。
5. 更新根 `README.md`
   - 修正后端依赖安装位置；补充一键启动与手动启动指南；补充目录结构与端口说明。

## 更新后的 README 草案
### 项目结构
```
Backend: Python Flask API
Frontend: Next.js + TypeScript + shadcn/ui
```
```
ui_compare/
├─ backend/ (后端服务与依赖)
├─ frontend/ (前端应用与依赖)
├─ output/ (运行生成文件)
├─ start.sh (一键启动)
└─ .gitignore
```

### 后端安装与启动
```
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                # 运行在 http://localhost:5050
```
健康检查：`GET http://localhost:5050/health`

### 前端安装与启动
```
cd frontend
npm install
npm run dev                  # 运行在 http://localhost:3000
```
前端已默认请求后端 `http://localhost:5050/api/compare`（见 `frontend/src/app/page.tsx`）。

### 一键启动
```
bash start.sh
```
- 后端：`http://localhost:5050`
- 前端：`http://localhost:3000`

### 运行产物
- 后端比较 API 会将中间产物输出至根目录 `output/`（保持被忽略提交）。

### 推荐的多仓演进（可选）
- 后端仓库：`ui-compare-backend`（包含 `backend/` 内容与其 README）
- 前端仓库：`ui-compare-frontend`（包含 `frontend/` 内容与其 README）
- 用 `Docker Compose` 或 `Makefile`/脚本编排本地与 CI/CD。

## 实施步骤与验证
1. 移动依赖文件到 `backend/requirements.txt`。
2. 新增根 `.gitignore` 并提交，清理已提交的 `venv/`。
3. 本地验证：
   - 后端：
     ```
     cd backend
     python -m venv .venv && source .venv/bin/activate
     pip install -r requirements.txt
     python app.py
     curl http://localhost:5050/health
     ```
   - 前端：
     ```
     cd frontend
     npm install
     npm run dev
     ```
   - 联调：浏览器访问前端，上传两份 JSON，检查接口联通与 `output/` 生成。
4. 一键脚本验证：`bash start.sh`。

## 可选后续优化
- 用 `pyproject.toml` + `uv`/Poetry 管理后端依赖（锁版本、可复现）。
- 增加 `Dockerfile` 与 `docker-compose.yml` 简化多仓编排。
- 在前端使用环境变量（如 `NEXT_PUBLIC_API_BASE`）以支持非本地后端地址。