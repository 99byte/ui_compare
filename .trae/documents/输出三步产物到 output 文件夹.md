## 目标
在每次调用“开始对比”时，将三步产物分别落盘到项目根目录的 `output/`：
- 步骤一：两份语义图（设计、运行）
- 步骤二：匹配器结果（matches/missing/added）
- 步骤三：语义级诊断报告（diagnostic_report）
并在响应中返回文件路径，便于核对。

## 改动点
- 路由 `/api/compare`：在现有生成 `semantic_graph_*`、`matching`、`diagnostic_report` 后，创建 `output/` 目录并写入 JSON 文件，文件名带请求ID（短 UUID）。
- 响应新增 `outputs` 字段，包含三步文件的绝对路径（或相对项目根路径）。

## 文件命名
- `step1_design_<id>.json`
- `step1_runtime_<id>.json`
- `step2_matching_<id>.json`
- `step3_diagnostic_<id>.json`

## 验证
- 使用现有示例请求触发写入，检查 `output/` 生成四个文件，内容与响应对象一致。

## 兼容
- 不改变现有返回结构；仅新增文件写入与路径字段。