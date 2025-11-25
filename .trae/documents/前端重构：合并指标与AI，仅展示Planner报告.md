## 目标
- 保持左侧“对比功能区”不变：文件上传、双画布渲染、开始比较按钮与绘制逻辑维持现状。
- 右侧将“对比指标”和“AI 智能分析”合并为“Planner 报告”，仅展示后端 Planner 的最终输出蓝图列表。
- 对接后端 `/api/compare` 的 `ai_blueprints` 与 `diagnostic_report.report_id`；不再在 UI 中显示旧的指标与临时 AI 建议。

## 涉及文件
- `frontend/src/app/page.tsx`：界面重构、状态与类型调整、数据对接。
- 后端无需改动，仅消费接口返回：`backend/app.py:269` `/api/compare` 返回 `ai_blueprints` 与 `diagnostic_report`，Planner 生成逻辑在 `backend/planner/service.py:100-117`，蓝图结构在 `backend/planner/schema.py:5-12`。

## 数据对接
- 成功调用比较接口后，读取并保存：
  - `reportId = data.diagnostic_report?.report_id`
  - `blueprints = data.ai_blueprints`
- 取消对 `metrics` 与 `ai_suggestions` 的 UI 展示；保留现有绘图与比较触发逻辑。

## UI 改造
- 删除右侧两张卡片：
  - “对比指标”（`frontend/src/app/page.tsx:397-432`）
  - “AI 智能分析”（`frontend/src/app/page.tsx:433-458`）
- 新增一张卡片“Planner 报告”展示蓝图列表（不新建文件，直接在 `page.tsx` 中实现，沿用现有 `Card`、`Button`、`Input` 风格）：
  - 顶部显示 `reportId`（若有）。
  - 列表项字段：`plan_id`、`action_type`（彩色标识）、`target_file`、`confidence`、`location_hint`（简化显示 JSON 片段）、`reasoning`。
  - 当 `blueprints` 为空时，显示占位提示“无可用蓝图”。

## 类型与状态
- 在 `page.tsx` 定义 TS 类型：
  - `type Blueprint = { plan_id: string; target_file: string; confidence: string; action_type: string; location_hint: Record<string, any>; reasoning: string; parent_container_path?: string }`
- 新增状态：
  - `const [blueprints, setBlueprints] = useState<Blueprint[]>([])`
  - `const [reportId, setReportId] = useState<string>('')`
- 在 `compareDesigns` 成功分支中：
  - `setBlueprints(data.ai_blueprints || [])`
  - `setReportId(data.diagnostic_report?.report_id || '')`
  - 移除 `setAiSuggestion` 与 `metrics` 的使用（不再渲染这些内容）。

## 保留与兼容
- 左侧上传、画布绘制与“开始比较分析”按钮保持不变；不修改 `drawComponentsOnCanvas` 及相关调用。
- 后端的 `diagnostic_report`、`ai_blueprints` 已由 `/api/compare` 返回（`backend/app.py:367-392`）；无需后端改动。

## 验证
- 本地运行前端，上传两份 JSON，点击“开始比较分析”：
  - 左侧画布按原逻辑渲染；
  - 右侧仅出现“Planner 报告”卡片，列出蓝图；若为空显示占位文案；显示 `reportId`（若返回）。
- 观察网络响应，确保 `ai_blueprints` 被消费并渲染。

## 代码引用
- 前端比较触发：`frontend/src/app/page.tsx:228-283`
- 右侧旧卡片位置：`frontend/src/app/page.tsx:397-458`
- 后端接口返回：`backend/app.py:367-392`
- Planner 生成：`backend/planner/service.py:100-117`
- 蓝图结构定义：`backend/planner/schema.py:5-12`

确认后我将提交具体代码改动，仅修改 `page.tsx`，不新增文件。