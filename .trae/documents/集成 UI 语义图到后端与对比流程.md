## 目标
- 将“UI 语义图 (UI Semantic Graph)”纳入后端处理管线，输出归一化坐标、显式置信度、空间拓扑（父子层级）。
- 在现有比较接口的基础上，先重建层级，再进行分桶与局部匹配，提升匹配精度与鲁棒性。

## 数据模型
- 输入支持两类：
  - Raw Detection List：`[{label, box:[x1,y1,x2,y2], conf, text?}]`
  - 现有组件：`[{id, type, bounding_box:{x,y,width,height}, text?, confidence?}]`
- 输出：
  - `meta:{source,resolution:[w,h],node_count}`
  - `elements:[{id,type:{label,conf},geometry:{abs,rel,center,area,width,height},content:{text,ocr_conf},topology:{zone,parent_id,layer_level}}]`

## 核心算法
- 层级重建：
  - 面积降序排序；对每个节点倒序查找第一个满足 IoC≥0.90 的“最小父容器”。
  - 计算 `layer_level`、`parent_id`、`children` 并分配 `zone`（header/body/footer）。
- 分桶与匹配：
  - 先匹配“容器层”（如 `card`, `container`, `panel`），依据类型、zone 与 IoU/相似度。
  - 在已匹配容器对内做二分图匹配，综合 IoU、类型/标签相似度、文本相似度与层级惩罚。
  - 未匹配容器与叶子节点分别统计，产出更可解释的差异列表。

## 后端改造
- 新增模块：`backend/semantic_graph.py`，实现 `UISemanticBuilder`（支持两种输入形态，统一到 `box:[x1,y1,x2,y2]`）。
- 在比较流程中插入层级重建：
  - 读取 `design_json` 与 `code_json`，沿用解析逻辑 `normalize_to_components`（backend/app.py:125）。
  - 将 `components` 转换为 builder 输入（`[x,y,x+w,y+h]`），构建两份语义图。
  - 容器优先匹配 → 容器内子元素匹配 → 组装 enriched diff。
- 新增接口：
  - `POST /api/semantic-graph`：返回单份语义图（便于调试与前端可视化）。
  - 扩展现有 `POST /api/compare`：增加 `semantic_graph_design` 与 `semantic_graph_code` 和分桶匹配结果。

## API 契约
- `POST /api/semantic-graph`
  - 请求：`{ data, width?, height?, source?: 'runtime'|'design' }`（若为 components，自动解析；若为 raw detections 需携带分辨率或在 meta 中提供）
  - 响应：语义图 JSON（含 `meta` 与 `elements`）。
- `POST /api/compare`
  - 请求不变：`{ design_json, code_json }`
  - 响应新增：
    - `semantic_graph_design`, `semantic_graph_code`
    - `bucketed_matches:[{parent_pair:{design_id,code_id}, children_matches:[...]}]`
    - 现有 `metrics`/`comparison_result` 保持兼容。

## 前端适配
- 维持现有画布渲染；新增可选开关：
  - 显示容器层描边与 zone 颜色分级。
  - 按容器对查看匹配结果（仅渲染某父容器的 children）。
- 支持从 `semantic_graph_*` 中读取 `rel` 坐标进行归一化绘制（保持一屏展示逻辑不变）。

## 验证与测试
- 单元测试（pytest）：
  - IoC 包含判定阈值与抖动容忍（±1px）
  - 多层嵌套场景：`Body > Card > Button/Text`，确保选取最小父容器。
  - 边界用例：零面积、交集为空、部分越界。
- 端到端测试：
  - 用 `sample_design.json` / `sample_code.json` 生成语义图与对比结果，检查指标与可视化。

## 性能与鲁棒性
- 层级构建 O(N^2)，在 N<500 场景可接受；必要时可加网格索引提前剪枝。
- IoC 阈值与 zone 分桶参数化，接口支持覆盖默认值。
- 统一坐标归一化，避免分辨率差异导致的匹配偏差。

## 代码对接参考
- 现有解析：`backend/app.py:125 normalize_to_components`
- 比较入口：`backend/app.py:160 compare_designs`
- IoU 用于匹配；IoC 仅用于层级包含判定（二者并行且互不替代）。

## 交付与回滚
- 以增量方式引入新模块与新接口；`/api/compare` 响应保持向后兼容。
- 新增开关位控制是否启用分桶匹配；问题时可降级回当前 IOU 流程。
