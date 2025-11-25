## 目标
在匹配结果基础上实现语义级 Diff：全局偏移校正、容忍度阈值过滤与动态文本识别，输出结构化诊断报告，避免噪点并标注严重性。

## 集成点
- 新增模块：`backend/differ.py`，实现 `UISemanticDiffer`（纯标准库）。
- 路由扩展：`/api/compare` 在完成匹配后调用 Diff 引擎，响应新增 `diagnostic_report` 字段（含 global calibration 与 issues）。

## 设计要点
- L1 全局偏移：取匹配对的 `Δy` 像素中位数，作为 `global_offset_y`，用于位置对比时的修正（不更改原数据）。
- L2 容忍度：
  - 位置容忍：`pos_threshold_px`（默认 5px）。
  - 尺寸容忍：`size_abs_threshold_px`（默认 2px）与 `size_threshold_pct`（默认 5%）。
  - 相对坐标对比，转换到像素判断。
- L3 文本语义：
  - 完全匹配通过；
  - 动态字段正则库：`currency/time/date/number`，命中则 `DYNAMIC_CONTENT`（忽略）；
  - 相似度阈值：≥0.8 标记 `TEXT_TYPO`（minor），否则 `TEXT_MISMATCH`（major）。
- 结构差异：
  - Missing：`button/input/text` → `critical`；装饰类小面积元素 → `minor`；其他 → `major`。
  - Added：小面积 → `minor`；其他 → `major`。

## 输出结构
- `diagnostic_report`：
  - `report_id`、`global_calibration.y_offset_px`
  - `issues`：[TEXT_*、LAYOUT_SHIFT_*, MISSING_WIDGET, ADDED_WIDGET]

## 验证
- 用当前示例数据验证：按钮缺失应输出 `MISSING_WIDGET`（critical）；新增 `text`/`image`按面积分级；匹配的 `header/card`布局在阈值内不报错。