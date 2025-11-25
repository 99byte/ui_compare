import math


class UIFuzzyMatcher:
    """UI 模糊匹配器

    在设计语义图与运行时语义图之间进行元素级匹配，
    综合几何位置、形状比例、文本相似度与类型兼容度计算成本，
    采用匈牙利算法得到最优匹配，并输出匹配、缺失与新增列表。
    """
    def __init__(self, config=None):
        """初始化匹配器

        参数:
        - config: 匹配权重与阈值配置，未提供则使用默认值
        """
        self.config = config or {
            "weights": {"geo": 0.4, "shape": 0.2, "text": 0.3, "type": 0.1},
            "thresholds": {"match_cutoff": 0.65},
        }
        self.soft_pairs = {("button", "text"), ("icon", "image"), ("input", "text")}

    def _center(self, node):
        """获取节点中心点坐标（归一化）"""
        c = node.get("geometry", {}).get("center") or [0.0, 0.0]
        return float(c[0]), float(c[1])

    def _rel(self, node):
        """获取节点相对坐标框 [x1,y1,x2,y2]（归一化）"""
        r = node.get("geometry", {}).get("rel") or [0.0, 0.0, 0.0, 0.0]
        return float(r[0]), float(r[1]), float(r[2]), float(r[3])

    def _shape_ar(self, node):
        """计算节点宽高比"""
        g = node.get("geometry", {})
        w = float(g.get("width", 0.0))
        h = float(g.get("height", 1.0))
        return w / max(h, 1.0)

    def _iou_rel(self, a, b):
        """计算两个相对框的 IoU"""
        ax1, ay1, ax2, ay2 = self._rel(a)
        bx1, by1, bx2, by2 = self._rel(b)
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        a_area = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
        b_area = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
        union = a_area + b_area - inter
        if union <= 0:
            return 0.0
        return inter / union

    def _text(self, node):
        """提取节点文本内容（字符串）"""
        t = node.get("content", {}).get("text")
        return "" if t is None else str(t)

    def _seq_similarity(self, a, b):
        """简单序列相似度估计（近似 LCS 计数比）"""
        if a == b:
            return 1.0
        la = len(a)
        lb = len(b)
        if la == 0 and lb == 0:
            return 1.0
        lcs = 0
        da = {}
        for i, ch in enumerate(a):
            da.setdefault(ch, []).append(i)
        for j, ch in enumerate(b):
            if ch in da:
                lcs += 1
        return max(0.0, min(1.0, lcs / max(la, lb)))

    def _calc_geo_cost(self, a, b, y_offset=0.0):
        """几何成本: 距离 + 1-IoU"""
        ax, ay = self._center(a)
        bx, by = self._center(b)
        by = by + y_offset
        dx = ax - bx
        dy = ay - by
        dist = math.sqrt(dx * dx + dy * dy)
        dist_cost = min(dist * 2.0, 1.0)
        iou = self._iou_rel(a, b)
        return dist_cost + (1.0 - iou)

    def _calc_shape_cost(self, a, b):
        """形状成本: 宽高比差值裁剪到 [0,1]"""
        ar_a = self._shape_ar(a)
        ar_b = self._shape_ar(b)
        return min(abs(ar_a - ar_b), 1.0)

    def _calc_text_cost(self, a, b):
        """文本成本: 1-相似度；空文本一致成本为 0"""
        ta = self._text(a)
        tb = self._text(b)
        if not ta and not tb:
            return 0.0
        if bool(ta) != bool(tb):
            return 1.0
        sim = self._seq_similarity(ta, tb)
        return 1.0 - sim

    def _calc_type_cost(self, a, b):
        """类型成本: 完全一致为 0；软兼容对给定较低成本"""
        la = (a.get("type", {}).get("label") or "").lower()
        lb = (b.get("type", {}).get("label") or "").lower()
        if la == lb:
            return 0.0
        pair = tuple(sorted((la, lb)))
        if pair in self.soft_pairs:
            return 0.3
        return 1.0

    def _compute_cost_matrix(self, A, B, y_offset=0.0):
        """构建成本矩阵

        参数:
        - A: 设计元素列表
        - B: 运行时元素列表
        - y_offset: Y 方向偏移校正

        返回:
        - list[list[float]]: 成本矩阵
        """
        n = len(A)
        m = len(B)
        w = self.config["weights"]
        M = [[0.0 for _ in range(m)] for _ in range(n)]
        for i in range(n):
            ai = A[i]
            for j in range(m):
                bj = B[j]
                c_geo = self._calc_geo_cost(ai, bj, y_offset)
                c_shape = self._calc_shape_cost(ai, bj)
                c_text = self._calc_text_cost(ai, bj)
                c_type = self._calc_type_cost(ai, bj)
                M[i][j] = w["geo"] * c_geo + w["shape"] * c_shape + w["text"] * c_text + w["type"] * c_type
        return M

    def _hungarian(self, cost):
        """匈牙利算法求最小成本匹配

        参数:
        - cost: 方阵或通过填充得到的成本矩阵

        返回:
        - list[tuple[int,int]]: 匹配下标对 (i,j)
        """
        n = len(cost)
        m = len(cost[0]) if n > 0 else 0
        size = max(n, m)
        INF = 1e9
        pad = [[INF for _ in range(size)] for _ in range(size)]
        for i in range(size):
            for j in range(size):
                if i < n and j < m:
                    pad[i][j] = cost[i][j]
        u = [0.0] * (size + 1)
        v = [0.0] * (size + 1)
        p = [0] * (size + 1)
        way = [0] * (size + 1)
        for i in range(1, size + 1):
            p[0] = i
            j0 = 0
            minv = [INF] * (size + 1)
            used = [False] * (size + 1)
            while True:
                used[j0] = True
                i0 = p[j0]
                j1 = 0
                delta = INF
                for j in range(1, size + 1):
                    if not used[j]:
                        cur = pad[i0 - 1][j - 1] - u[i0] - v[j]
                        if cur < minv[j]:
                            minv[j] = cur
                            way[j] = j0
                        if minv[j] < delta:
                            delta = minv[j]
                            j1 = j
                for j in range(0, size + 1):
                    if used[j]:
                        u[p[j]] += delta
                        v[j] -= delta
                    else:
                        minv[j] -= delta
                j0 = j1
                if p[j0] == 0:
                    break
            while True:
                j1 = way[j0]
                p[j0] = p[j1]
                j0 = j1
                if j0 == 0:
                    break
        assignment = []
        for j in range(1, size + 1):
            if p[j] != 0 and p[j] - 1 < n and j - 1 < m and cost[p[j] - 1][j - 1] < INF / 2:
                assignment.append((p[j] - 1, j - 1))
        return assignment

    def _bucket(self, elements, zone):
        """按页面区域过滤元素（header/body/footer）"""
        return [e for e in elements if (e.get("topology", {}).get("zone") or "") == zone]

    def _y_offset(self, A, B):
        """估计 A 与 B 在 Y 方向的平均偏移量"""
        if not A or not B:
            return 0.0
        ya = sum(self._center(a)[1] for a in A) / len(A)
        yb = sum(self._center(b)[1] for b in B) / len(B)
        return ya - yb

    def match_bucket(self, A, B):
        """对同一区域的两组元素进行匹配，返回三元组

        返回:
        - matched: 匹配对列表，每项包含 design/runtime/cost
        - missing: 设计中缺失的元素列表
        - added: 运行时新增的元素列表
        """
        if not A:
            return [], A, B
        if not B:
            return [], A, B
        yoff = self._y_offset(A, B)
        M = self._compute_cost_matrix(A, B, yoff)
        pairs = self._hungarian(M)
        cutoff = float(self.config["thresholds"]["match_cutoff"])
        matched = []
        mi = set()
        mj = set()
        for i, j in pairs:
            c = M[i][j]
            if c <= cutoff:
                matched.append({"design": A[i], "runtime": B[j], "cost": float(c)})
                mi.add(i)
                mj.add(j)
        missing = [A[i] for i in range(len(A)) if i not in mi]
        added = [B[j] for j in range(len(B)) if j not in mj]
        return matched, missing, added

    def run(self, design_graph, runtime_graph):
        """对完整语义图进行分区匹配并汇总结果"""
        res = {"matches": [], "missing": [], "added": []}
        zones = ["header", "body", "footer"]
        for z in zones:
            da = self._bucket(design_graph.get("elements", []), z)
            rb = self._bucket(runtime_graph.get("elements", []), z)
            m, miss, add = self.match_bucket(da, rb)
            res["matches"].extend(m)
            res["missing"].extend(miss)
            res["added"].extend(add)
        return res
