## 目标

* 解析根目录 `1.json` 的生产级层级结构，提取所有组件的矩形框与类型。

* 后端在 `/api/compare` 中删除旧版实现，只支持生产版本：旧版 `{components: [...]}` 与新版（生产）`{attributes, children}`。

* 返回标准化组件列表与屏幕尺寸，使前端能按手机屏幕长宽设置画布并正确渲染组件。

## 生产 JSON Schema 要点

* 顶层：`attributes.bounds` 为字符串，形如 `[x1,y1][x2,y2]`，表示整机屏幕范围，例如 `"[0,0][1260,2720]"`。

* 层级：`children` 为递归子节点；每个节点都有 `attributes.type`（如 `Scroll/Column/Row/Text/Button`）与 `attributes.bounds`。

* 文本、可交互信息在 `attributes.text/clickable` 等字段中。

## 后端改造（`backend/app.py`）

* 引入 `parse_bounds(bounds_str)`：将如 `"[52,150][895,226]"` 转为 `{x:52,y:150,width:843,height:76}`。

* 引入 `normalize_to_components(obj)`：

  * 深度遍历 `children`，对存在 `attributes.bounds` 的节点生成标准组件：`{id,type,bounding_box,confidence?,text?}`；`id`优先用`attributes.accessibilityId/hashcode`，否则用遍历序号。

  * 过滤掉 `type=root` 节点；其余包含容器与叶子组件，确保画布完整可视化。

* `/api/compare`（src: `backend/app.py:113-141`）逻辑更新：

  * 若输入是字符串先 `json.loads`；

  * 从设计侧顶层 `attributes.bounds` 解析出 `screen_width/screen_height`，随响应一起返回；

  * 保留现有 IoU 匹配与指标生成，输出结构不变，新增 `screen:{width,height}` 字段。

## 前端适配（`frontend/src/app/page.tsx`）

* 更新 `extractComponents`（src: `frontend/src/app/page.tsx:83-120`）：

  * 支持生产 schema：遍历 `children`，读取 `attributes.bounds/type`，生成标准化组件；

  * 读取顶层 `attributes.bounds` 并保存屏幕尺寸到状态（如 `designScreen` / `codeScreen`）。

* 更新 `drawComponentsOnCanvas`（src: `frontend/src/app/page.tsx:122-167`）：

  * 接收可选 `screenWidth/screenHeight`；若提供则直接设定 `canvas.width/height` 为屏幕长宽并按原始坐标绘制；若未提供则回退到当前缩放方案；

  * 保持匹配和未匹配组件的不同样式描边。

* 在比较后渲染处（src: `frontend/src/app/page.tsx:200-220`）：

  * 使用后端返回 `screen` 设置两个画布尺寸再绘制匹配/未匹配。

## 验证方案

* 使用 `根目录/1.json` 作为设计侧输入，检查：

  * 后端能正确标准化为组件列表（包含大量 `Text/Button/...`）且返回 `screen: {width:1260,height:2720}`；

  * 前端上传后立即在画布展示所有组件框；点击“开始比较”后按匹配/未匹配分色渲染；

  * 大文件（\~565KB）递归解析性能正常。

## 边界与兼容

* 非法或缺失 `bounds` 的节点跳过；宽高为 0 的节点不计入。

* 不继续兼容旧版 `{components}` 输入

* 不泄露任何与密钥相关信息，保持现有 CORS 与错误处理。

请确认上述方案，确认后我将实现并联调前后端，确保画布按屏幕尺寸渲染并正确显示组件。
