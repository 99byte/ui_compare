import uuid


class UISemanticBuilder:
    """UI 语义图构建器

    将原始检测框与文本等信息转化为结构化的语义图，
    补充几何信息、页面分区、父子层级关系等，供后续匹配与差异分析使用。
    """
    def __init__(self, image_width, image_height, source_type="runtime"):
        """初始化语义图构建器

        参数:
        - image_width: 图像宽度（像素）
        - image_height: 图像高度（像素）
        - source_type: 来源类型标记，如 "design" 或 "runtime"
        """
        self.width = max(1, int(image_width))
        self.height = max(1, int(image_height))
        self.source_type = source_type

    def _generate_id(self):
        """生成节点唯一 ID"""
        return f"node_{uuid.uuid4().hex[:8]}"

    def _calculate_geometry(self, box):
        """根据绝对坐标框计算几何属性（绝对/相对/中心/面积/宽高）"""
        x1, y1, x2, y2 = box
        w = max(0, int(x2) - int(x1))
        h = max(0, int(y2) - int(y1))
        area = w * h
        iw = self.width
        ih = self.height
        return {
            "abs": [int(x1), int(y1), int(x2), int(y2)],
            "rel": [round(int(x1) / iw, 4), round(int(y1) / ih, 4), round(int(x2) / iw, 4), round(int(y2) / ih, 4)],
            "center": [round((int(x1) + w / 2) / iw, 4), round((int(y1) + h / 2) / ih, 4)],
            "area": area,
            "width": w,
            "height": h,
        }

    def _assign_zone(self, rel_y_center):
        """根据相对中心的 Y 值划分页面区域"""
        if rel_y_center < 0.15:
            return "header"
        if rel_y_center > 0.85:
            return "footer"
        return "body"

    def _is_contained(self, parent_geom, child_geom, threshold=0.90):
        """判断子节点是否绝大部分被父节点包含

        参数:
        - parent_geom: 父几何属性
        - child_geom: 子几何属性
        - threshold: 交并比相对于子面积的阈值
        """
        px1, py1, px2, py2 = parent_geom["abs"]
        cx1, cy1, cx2, cy2 = child_geom["abs"]
        ix1 = max(px1, cx1)
        iy1 = max(py1, cy1)
        ix2 = min(px2, cx2)
        iy2 = min(py2, cy2)
        if ix2 <= ix1 or iy2 <= iy1:
            return False
        intersection_area = (ix2 - ix1) * (iy2 - iy1)
        child_area = child_geom["area"]
        if child_area == 0:
            return False
        return (intersection_area / child_area) >= threshold

    def build(self, raw_detections):
        """从原始检测结果生成语义图

        参数:
        - raw_detections: 列表，每项包含 box/label/conf/text/ocr_conf

        返回:
        - dict: 语义图，包含 meta 与 elements
        """
        processed_nodes = []
        for item in raw_detections:
            geom = self._calculate_geometry(item["box"])
            node = {
                "id": self._generate_id(),
                "type": {
                    "label": item.get("label", "unknown"),
                    "conf": float(item.get("conf", 0.0)),
                },
                "geometry": geom,
                "content": {
                    "text": item.get("text"),
                    "ocr_conf": float(item.get("ocr_conf", 0.0)),
                },
                "topology": {
                    "zone": self._assign_zone(geom["center"][1]),
                    "parent_id": None,
                    "layer_level": 0,
                    "children": [],
                },
                "_area": geom["area"],
            }
            processed_nodes.append(node)

        sorted_indices = sorted(range(len(processed_nodes)), key=lambda k: processed_nodes[k]["_area"], reverse=True)

        for i in range(len(sorted_indices)):
            child_idx = sorted_indices[i]
            child = processed_nodes[child_idx]
            best_parent_idx = None
            for j in range(i - 1, -1, -1):
                parent_candidate_idx = sorted_indices[j]
                parent_candidate = processed_nodes[parent_candidate_idx]
                if self._is_contained(parent_candidate["geometry"], child["geometry"]):
                    best_parent_idx = parent_candidate_idx
                    break
            if best_parent_idx is not None:
                parent = processed_nodes[best_parent_idx]
                child["topology"]["parent_id"] = parent["id"]
                child["topology"]["layer_level"] = parent["topology"]["layer_level"] + 1
                parent["topology"]["children"].append(child["id"])

        final_nodes = []
        for node in processed_nodes:
            del node["_area"]
            final_nodes.append(node)

        return {
            "meta": {
                "source": self.source_type,
                "resolution": [self.width, self.height],
                "node_count": len(final_nodes),
            },
            "elements": final_nodes,
        }
