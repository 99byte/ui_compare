## 范围
完成“新版方案的第一步”：将输入的两份原始 JSON（YOLO/OCR 扁平检测或旧结构）统一转换为增强版 Schema，并在转换过程中重建 UI 空间层级（父子关系、zone、center、归一化坐标）。暂不做匹配与差异判定，确保后续步骤有干净一致的输入。

## 文件与入口
- 后端入口：`backend/app.py:/api/compare`（`backend/app.py:160-205`）。
- 现有旧解析：`normalize_to_components()`（`backend/app.py:125-158`）。
- 计划：新增 `semantic_graph.py`（或在 `app.py` 内先内联）实现 `UISemanticBuilder`；路由在读入 `design_json`、`code_json` 后分别构建 `semantic_graph_design` 与 `semantic_graph_runtime`，并在响应中返回两份增强版 Schema 供前端或后续管线使用。

## 行为调整
- 删除/废弃旧版组件列表方案：不再基于 `normalize_to_components()` 直接产生扁平 `components`，改为：
  - 若输入已是增强版 Schema（含 `meta/elements`）：校验与补全（归一化、zone、center、缺失字段）。
  - 若输入是扁平检测：使用 `UISemanticBuilder.build(raw_detections)` 生成增强版 Schema。
- 路由响应新增：`semantic_graph_design`、`semantic_graph_runtime` 字段（含 `meta`、`elements`）。保留现有 `metrics`、`comparison_result` 字段以防前端尚未切换，但标注为即将废弃。

## 算法与实现要点
- 采用您提供的 `UISemanticBuilder` 实现：
  - 归一化：`geometry.rel`、`center`、`abs`、`area/width/height`。
  - 分区：`_assign_zone()` 基于 `center.y` 切片 `header/body/footer`。
  - 层级重建：面积降序 + 倒序查找最小父容器，使用 `IoC ≥ 0.90` 判定包含，生成 `parent_id`、`layer_level` 与父节点 `children`。
- 输入宽高获取策略：
  - 优先采用增强版 `meta.resolution`；
  - 否则尝试根 bounds 或通过所有框的 `max(x2), max(y2)` 估算画布大小（避免除 0）。
- ID 策略：默认 `uuid`；可选位置哈希保证稳定性（后续可按需切换）。

## API 合约
- 请求：无需变更字段名，仍使用 `design_json`、`code_json`，但对旧输入进行自动转换。
- 响应：
```json
{
  "success": true,
  "semantic_graph_design": {"meta":{...}, "elements":[...]},
  "semantic_graph_runtime": {"meta":{...}, "elements":[...]},
  "metrics": { ... },
  "comparison_result": { ... } // 过渡期兼容
}
```
- 后续步骤将改为仅基于两份 `semantic_graph` 继续分桶、候选筛选与匹配。

## 代码改动点
- 新增：`UISemanticBuilder` 类（按参考实现），封装为模块或临时内联。
- 修改：`/api/compare` 的输入处理分支：
  - 判断输入是否为增强版 Schema；否则调用 `UISemanticBuilder.build()`。
  - 将旧的 `normalize_to_components()` 标记为兼容回退，不再参与主流程。
- 不触动：现有 `ComponentComparator` 与指标/建议逻辑暂时保留，便于对比与验证；完成后续步骤将逐步替换。

## 验证
- 用参考示例与 2 套实际 YOLO 输出验证层级重建：
  - `Card > Button > Text` 的直接父子关系正确；
  - `Header` 元素不误认为 `Body` 的父节点；
  - 子元素轻微溢出仍能判定包含（`IoC≥0.90`）。
- 检查归一化与 `center`、`zone` 是否合理，`node_count` 与输入规模一致。

## 交付
- 提交后端改动（新增构建器与路由转换逻辑），返回两份增强版 Schema；前端可先展示树状结构或保留旧视图，下一步再接入对比管线。