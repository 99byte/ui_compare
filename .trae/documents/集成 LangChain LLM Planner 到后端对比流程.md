## 目标
- 在现有 `/api/compare` 计算出 `diagnostic_report` 后，生成结构化的 AI 修改蓝图 `ModificationBlueprint`（每个 issue 一条）。
- 将蓝图随接口响应返回并落盘到 `output/step4_blueprints_<req_id>.json`，作为后续 Coder 自动修改的输入。

## 依赖与配置
- 安装依赖：`pip install langchain langchain-openai pydantic python-dotenv`
- 环境变量：`OPENAI_API_KEY`（可扩展 `OPENAI_BASE_URL` 适配私有或国内推理端点）
- 模型：默认 `gpt-4o`，回退 `gpt-3.5-turbo-0125`；温度 `0`，确保可重复与结构化输出。

## 目录与文件
- `backend/planner/schema.py`：定义 `ModificationBlueprint`（Pydantic）
- `backend/planner/tools.py`：实现 `search_codebase`、`list_files`（受限检索，默认根目录为仓库根）
- `backend/planner/agent.py`：创建 OpenAI Tools Agent，绑定工具与 Prompt，开启结构化输出
- `backend/planner/service.py`：封装 `LangChainPlanner.plan(issue_json, context)`；支持批量与 CLI
- `backend/app.py`：在生成 `diagnostic_report` 后，提取上下文，调用 Planner，返回 `ai_blueprints` 并写入 `output`
- 可选：`backend/tests/test_planner.py`（使用假模型/桩函数做回归验证）

## 输出结构
- `ModificationBlueprint` 字段：`plan_id`、`target_file`、`confidence`（high/medium/low）、`action_type`（MODIFY_TEXT/MODIFY_STYLE/ADD_COMPONENT）、`location_hint`（包含 `search_text` 或 `component_name`）、`reasoning`、`parent_container_path`（新增组件时可填）
- 批量包装：`{"report_id": ..., "blueprints": [ModificationBlueprint...]}`

## 工具实现
- `search_codebase(query: str) -> str`
  - 以 `grep -rn` 子进程实现；排除 `node_modules`、`.git`、`dist`、`*.json`；最多返回前 10 条命中。
  - 根路径：`PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))`
- `list_files(directory: str = "") -> str`
  - 返回目标目录（相对 `PROJECT_ROOT`）的文件/子目录列表，过滤隐藏项与 `node_modules`，最多 20 项。

## Agent 设计
- 通过 `create_openai_tools_agent` 绑定工具与 Prompt；使用 `Pydantic`/JSON Mode 强制结构化输出。
- System Prompt 策略：
  - `TEXT_MISMATCH`：优先搜索 `actual` 文本；命中路径语义筛选（如 `src/pages`、`components`）。
  - `MISSING_WIDGET`：不要搜缺失文本；改搜兄弟文本 `sibling_text` 或父容器 `parent_role`；`action_type=ADD_COMPONENT`。
  - `LAYOUT_SHIFT/SIZE_MISMATCH`：定位组件定义或样式文件；`action_type=MODIFY_STYLE`；`location_hint` 给出 `component_name` 或样式选择器。
- 输出通过 `.with_structured_output(ModificationBlueprint)` 或 `PydanticOutputParser` 保证 100% 返回 JSON。

## 上下文提取（从语义图补强 Issue）
- 设计图：`semantic_graph_design['elements']` 提供 `topology.parent_id` 与 `children`。
- 对每个 Issue：
  - 根据 `node_id` 在 `elements` 里取该节点的父节点 `parent_role = parent.type.label`。
  - 取同层兄弟节点中带文本的若干 `sibling_text`（如最多 3 个，按几何邻近排序）。
  - 形成 `context = { sibling_text: [...], parent_role: "..." }`；随 Issue 一并喂给 Agent。

## 与后端集成
- 位置：`backend/app.py:268` 生成 `diagnostic_report` 之后。
- 流程：
  - 遍历 `diagnostic_report['issues']`，对每条构造 `issue_json`（含 `type`、`severity`、`widget_role`、`expected`/`actual`、`node_id`、`context`）。
  - 调用 `LangChainPlanner.plan(issue_json)`，得到单条 `ModificationBlueprint`。
  - 汇总为 `ai_blueprints`，写入 `output/step4_blueprints_<req_id>.json`，并在接口响应增加 `ai_blueprints` 与 `outputs.step4_blueprints`。

## 回退与健壮性
- 模型不可用或返回不合规 JSON：
  - `TEXT_MISMATCH`：启用规则回退（搜索 `actual`，就近命中文件作为 `target_file`，`confidence=low`）。
  - `MISSING_WIDGET`：基于 `parent_role` 与页面目录启发生成 `ADD_COMPONENT`，`confidence=low`。
- 超时与速率：每次调用设置超时与重试（指数退避，最多 2 次），批量串行上限（如 30 条），超出走回退。

## 暴露接口与 CLI
- HTTP：保持 `/api/compare` 单一入口，增加返回字段 `ai_blueprints`；无需新增路由。
- CLI：`python backend/planner/service.py --diagnostic output/step3_diagnostic_<id>.json` 生成蓝图文件，便于离线验证。

## 测试与验证
- 单元测试：
  - 针对 `TEXT_MISMATCH` 与 `MISSING_WIDGET` 的上下文提取与规则回退。
- 集成测试：
  - 使用仓库中的示例 JSON（如 `1.json`）构造请求，验证 `step1/2/3/4` 文件均正确产出，响应包含 `ai_blueprints`。

## 安全与合规
- 不记录或回显 `OPENAI_API_KEY`；日志只保留必要的错误信息与输入哈希。
- 限制工具输出长度，避免将大段代码送入模型；仅返回路径+行号摘要。

## 交付物
- Planner 相关 4 个 Python 文件与 `app.py` 集成改动。
- `output/step4_blueprints_<req_id>.json` 新增产物。
- 基础测试用例与离线 CLI。

请确认以上集成方案；确认后我将按该方案落地到 `backend` 并完成联调与验证。