import re
import uuid


class UISemanticDiffer:
    """UI 语义差异分析器

    用于对设计阶段与运行时阶段的语义图匹配结果进行深入分析，
    识别文本差异、布局位移、尺寸不一致以及新增/缺失组件等问题，
    并生成可供后续修复与规划使用的诊断报告。
    """
    def __init__(self, config=None):
        """初始化差异分析器

        参数:
        - config: 可选的配置字典，包含布局与文本分析的阈值与规则。

        说明:
        若未提供，则使用内置的默认阈值与动态文本匹配规则。
        """
        self.config = config or {
            "layout": {
                "pos_threshold_px": 5,
                "size_abs_threshold_px": 2,
                "size_threshold_pct": 0.05,
            },
            "text": {
                "typo_threshold": 0.8,
                "dynamic_patterns": {
                    "currency": r"^[¥$￥]\s*\d+(?:\.\d+)?$",
                    "time": r"^\d{1,2}:\d{2}$",
                    "date": r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$",
                    "number": r"^\d+$",
                },
            },
        }

    def _median(self, arr):
        """计算数组的中位数

        参数:
        - arr: 数值列表

        返回:
        - float: 中位数，空列表返回 0.0
        """
        n = len(arr)
        if n == 0:
            return 0.0
        s = sorted(arr)
        m = n // 2
        if n % 2 == 1:
            return float(s[m])
        return float((s[m - 1] + s[m]) / 2.0)

    def _global_offset_y(self, matches, h_px):
        """估计全局的 Y 方向偏移量（归一化）

        通过匹配对中设计与运行时元素的中心点，估计整体的垂直偏移。

        参数:
        - matches: 匹配列表，每项含 design/runtime 的几何信息
        - h_px: 屏幕高度像素，用于归一化

        返回:
        - float: 归一化的 Y 方向偏移量
        """
        if not matches or h_px <= 0:
            return 0.0
        diffs = []
        for m in matches:
            yd = float(m["design"]["geometry"]["center"][1]) * h_px
            yr = float(m["runtime"]["geometry"]["center"][1]) * h_px
            diffs.append(yr - yd)
        med = self._median(diffs)
        return med / max(h_px, 1.0)

    def _text_dynamic(self, a, b):
        """判断两段文本是否都符合同类动态模式

        适用于金额、时间、日期、纯数字等动态变化内容，
        若两者均匹配同一正则模式，则视为动态一致。

        参数:
        - a: 文本 A
        - b: 文本 B

        返回:
        - bool: 是否属于同类动态文本
        """
        pats = self.config["text"]["dynamic_patterns"]
        for _, p in pats.items():
            if re.match(p, a or "") and re.match(p, b or ""):
                return True
        return False

    def _text_diff(self, d, r):
        """分析文本差异

        参数:
        - d: 设计阶段节点
        - r: 运行时阶段节点

        返回:
        - dict|None: 差异信息字典；若无差异返回 None；
          动态文本返回 severity=ignore；其他情况返回具体差异类型与期望/实际文本。
        """
        ta = (d.get("content", {}).get("text") or "").strip()
        tb = (r.get("content", {}).get("text") or "").strip()
        if ta == tb:
            return None
        if self._text_dynamic(ta, tb):
            return {"type": "DYNAMIC_CONTENT", "severity": "ignore"}
        if not ta or not tb:
            return {"type": "TEXT_MISMATCH", "severity": "major", "expected": ta, "actual": tb}
        la = len(ta)
        lb = len(tb)
        if la == 0 or lb == 0:
            return {"type": "TEXT_MISMATCH", "severity": "major", "expected": ta, "actual": tb}
        common = 0
        da = {}
        for ch in ta:
            da[ch] = da.get(ch, 0) + 1
        for ch in tb:
            if da.get(ch, 0) > 0:
                common += 1
                da[ch] -= 1
        sim = common / float(max(la, lb))
        if sim >= float(self.config["text"]["typo_threshold"]):
            return {"type": "TEXT_TYPO", "severity": "minor", "expected": ta, "actual": tb, "similarity": sim}
        return {"type": "TEXT_MISMATCH", "severity": "major", "expected": ta, "actual": tb}

    def _layout_diff(self, d, r, w_px, h_px, offset_y):
        """分析布局与尺寸差异

        参数:
        - d: 设计阶段节点
        - r: 运行时阶段节点
        - w_px: 屏幕宽度像素
        - h_px: 屏幕高度像素
        - offset_y: 全局 Y 方向偏移（归一化）

        返回:
        - list[dict]: 差异问题列表（位移与尺寸不一致）
        """
        cd = d.get("geometry", {}).get("center") or [0.0, 0.0]
        cr = r.get("geometry", {}).get("center") or [0.0, 0.0]
        dx = (float(cr[0]) - float(cd[0])) * w_px
        dy = (float(cr[1]) - float(cd[1]) - float(offset_y)) * h_px
        pos_thr = float(self.config["layout"]["pos_threshold_px"])
        issues = []
        if abs(dx) > pos_thr:
            issues.append({"type": "LAYOUT_SHIFT_X", "severity": "major", "delta_px": round(dx, 1), "direction": "right" if dx > 0 else "left"})
        if abs(dy) > pos_thr:
            issues.append({"type": "LAYOUT_SHIFT_Y", "severity": "major", "delta_px": round(dy, 1), "direction": "down" if dy > 0 else "up"})
        rd = d.get("geometry", {}).get("rel") or [0.0, 0.0, 0.0, 0.0]
        rr = r.get("geometry", {}).get("rel") or [0.0, 0.0, 0.0, 0.0]
        wd = (float(rd[2]) - float(rd[0])) * w_px
        hd = (float(rd[3]) - float(rd[1])) * h_px
        wr = (float(rr[2]) - float(rr[0])) * w_px
        hr = (float(rr[3]) - float(rr[1])) * h_px
        dw = abs(wr - wd)
        dh = abs(hr - hd)
        size_abs = float(self.config["layout"]["size_abs_threshold_px"])
        size_pct = float(self.config["layout"]["size_threshold_pct"])
        tw = max(size_abs, wd * size_pct)
        th = max(size_abs, hd * size_pct)
        if dw > tw:
            issues.append({"type": "SIZE_MISMATCH_W", "severity": "major", "delta_px": round(wr - wd, 1), "direction": "expand" if wr > wd else "shrink"})
        if dh > th:
            issues.append({"type": "SIZE_MISMATCH_H", "severity": "major", "delta_px": round(hr - hd, 1), "direction": "expand" if hr > hd else "shrink"})
        return issues

    def _area_px(self, node, w_px, h_px):
        """计算节点面积（像素）

        参数:
        - node: 节点对象
        - w_px: 屏幕宽度像素
        - h_px: 屏幕高度像素

        返回:
        - float: 面积像素值
        """
        rel = node.get("geometry", {}).get("rel") or [0.0, 0.0, 0.0, 0.0]
        aw = max(0.0, float(rel[2]) - float(rel[0])) * w_px
        ah = max(0.0, float(rel[3]) - float(rel[1])) * h_px
        return aw * ah

    def _severity_for_missing(self, node, screen_area_px):
        """缺失组件的严重等级评估"""
        t = (node.get("type", {}).get("label") or "").lower()
        if t in ("button", "input", "text"):
            return "critical"
        area = screen_area_px and self._area_px(node, 1.0, 1.0) or 0.0
        if screen_area_px and area < screen_area_px * 0.01:
            return "minor"
        return "major"

    def _severity_for_added(self, node, screen_area_px):
        """新增组件的严重等级评估"""
        area = screen_area_px and self._area_px(node, 1.0, 1.0) or 0.0
        if screen_area_px and area < screen_area_px * 0.01:
            return "minor"
        return "major"

    def analyze(self, match_results, design_meta=None, runtime_meta=None):
        """对匹配结果进行全面差异分析

        参数:
        - match_results: 匹配输出，包含 matches/missing/added
        - design_meta: 设计阶段元信息（包含分辨率）
        - runtime_meta: 运行时阶段元信息（包含分辨率）

        返回:
        - dict: 诊断报告，含报告 ID、全局校准信息与问题清单
        """
        dw = 0
        dh = 0
        if isinstance(design_meta, dict):
            res = design_meta.get("resolution")
            if isinstance(res, list) and len(res) == 2:
                dw = int(res[0])
                dh = int(res[1])
        if dw <= 0 or dh <= 0:
            if isinstance(runtime_meta, dict):
                res = runtime_meta.get("resolution")
                if isinstance(res, list) and len(res) == 2:
                    dw = int(res[0])
                    dh = int(res[1])
        if dw <= 0:
            dw = 1
        if dh <= 0:
            dh = 1
        offset_norm = self._global_offset_y(match_results.get("matches", []), dh)
        issues = []
        for m in match_results.get("matches", []):
            d = m.get("design")
            r = m.get("runtime")
            ti = self._text_diff(d, r)
            if ti and ti.get("severity") != "ignore":
                ti["node_id"] = d.get("id")
                ti["widget_role"] = d.get("type", {}).get("label")
                issues.append(ti)
            li = self._layout_diff(d, r, dw, dh, offset_norm)
            for it in li:
                it["node_id"] = d.get("id")
                it["widget_role"] = d.get("type", {}).get("label")
                issues.append(it)
        screen_area_px = float(dw * dh)
        for miss in match_results.get("missing", []):
            sev = self._severity_for_missing(miss, screen_area_px)
            issues.append({"type": "MISSING_WIDGET", "severity": sev, "node_id": miss.get("id"), "widget_role": miss.get("type", {}).get("label")})
        for add in match_results.get("added", []):
            sev = self._severity_for_added(add, screen_area_px)
            issues.append({"type": "ADDED_WIDGET", "severity": sev, "node_id": add.get("id"), "widget_role": add.get("type", {}).get("label")})
        return {
            "report_id": f"diff_{uuid.uuid4().hex[:8]}",
            "global_calibration": {"y_offset_px": round(offset_norm * dh, 1)},
            "issues": issues,
        }
