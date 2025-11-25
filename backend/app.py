from flask import Flask, request, jsonify
from flask_cors import CORS
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return None
import json
import os
from io import BytesIO
import base64
import uuid
from semantic_graph import UISemanticBuilder
from matcher import UIFuzzyMatcher
from differ import UISemanticDiffer
from planner.service import LangChainPlanner, build_issue_context

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

class ComponentComparator:
    """组件集合比较器

    基于组件的边界框，计算两集合的匹配关系与统计指标，
    并生成简单的建议。主要用于示例比较逻辑。
    """
    def __init__(self):
        """初始化比较器，设置匹配阈值（IoU >= 0.8 认为匹配）"""
        self.match_threshold = 0.8
    
    def calculate_iou(self, box1, box2):
        """计算两个边界框的 IoU 值"""
        x1 = max(box1['x'], box2['x'])
        y1 = max(box1['y'], box2['y'])
        x2 = min(box1['x'] + box1['width'], box2['x'] + box2['width'])
        y2 = min(box1['y'] + box1['height'], box2['y'] + box2['height'])
        
        if x2 < x1 or y2 < y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = box1['width'] * box1['height']
        area2 = box2['width'] * box2['height']
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def compare_components(self, design_components, code_components):
        """比较两组组件并返回匹配结果与统计信息"""
        matches = []
        unmatched_design = []
        unmatched_code = []
        
        # Create copies to track unmatched components
        remaining_code = code_components.copy()
        
        for design_comp in design_components:
            best_match = None
            best_iou = 0
            
            for i, code_comp in enumerate(remaining_code):
                iou = self.calculate_iou(design_comp['bounding_box'], code_comp['bounding_box'])
                if iou > best_iou and iou >= self.match_threshold:
                    best_iou = iou
                    best_match = i
            
            if best_match is not None:
                matches.append({
                    'design_component': design_comp,
                    'code_component': remaining_code[best_match],
                    'iou': best_iou
                })
                remaining_code.pop(best_match)
            else:
                unmatched_design.append(design_comp)
        
        unmatched_code = remaining_code
        
        return {
            'matches': matches,
            'unmatched_design': unmatched_design,
            'unmatched_code': unmatched_code,
            'total_design_components': len(design_components),
            'total_code_components': len(code_components),
            'matched_components': len(matches),
            'unmatched_design_count': len(unmatched_design),
            'unmatched_code_count': len(unmatched_code)
        }
    
    def generate_metrics(self, comparison_result):
        """根据比较结果生成简化的统计指标"""
        total_components = comparison_result['total_design_components'] + comparison_result['total_code_components']
        matched_components = comparison_result['matched_components']
        
        match_rate = (matched_components / max(comparison_result['total_design_components'], 
                                             comparison_result['total_code_components'])) * 100 if max(comparison_result['total_design_components'], comparison_result['total_code_components']) > 0 else 0
        
        completeness = (matched_components / total_components) * 100 if total_components > 0 else 0
        
        return {
            'difference_count': comparison_result['unmatched_design_count'] + comparison_result['unmatched_code_count'],
            'match_rate': round(match_rate, 1),
            'total_components': comparison_result['total_design_components'],
            'completeness': round(completeness, 1)
        }
    
    def generate_ai_suggestions(self, comparison_result):
        """基于比较结果生成改进建议（示例）"""
        suggestions = []
        
        if comparison_result['unmatched_design_count'] > 0:
            suggestions.append(f"发现 {comparison_result['unmatched_design_count']} 个设计组件未在代码中找到对应实现，建议检查这些组件是否被遗漏或实现方式不同。")
        
        if comparison_result['unmatched_code_count'] > 0:
            suggestions.append(f"发现 {comparison_result['unmatched_code_count']} 个代码组件未在设计中找到对应组件，建议确认是否为新增功能或设计遗漏。")
        
        if comparison_result['matched_components'] > 0:
            avg_iou = sum(match['iou'] for match in comparison_result['matches']) / comparison_result['matched_components'] if comparison_result['matched_components'] > 0 else 0
            if avg_iou < 0.9:
                suggestions.append(f"匹配组件的平均重叠率为 {avg_iou:.1%}，建议优化组件定位和尺寸精度。")
        
        if not suggestions:
            suggestions.append("组件匹配度较高，设计实现一致性良好。")
        
        return suggestions

comparator = ComponentComparator()

def parse_bounds(bounds_str):
    """解析字符串格式的 bounds，返回 {x,y,width,height}

    参数:
    - bounds_str: 类似 "[x1,y1][x2,y2]" 或包含四个整数的字符串
    返回 None 表示解析失败
    """
    try:
        nums = [int(n) for n in __import__("re").findall(r"-?\d+", str(bounds_str))]
        if len(nums) >= 4:
            x1, y1, x2, y2 = nums[:4]
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            return {"x": x1, "y": y1, "width": w, "height": h}
    except Exception:
        pass
    return None

def normalize_to_components(data):
    """从原始层级数据抽取为组件列表

    识别字典节点的 attributes/bounds/type/text 等信息并生成统一格式。
    """
    result = []
    idx = 0

    def rec(node):
        nonlocal idx
        if isinstance(node, dict):
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else None
            if attrs:
                bounds = attrs.get("bounds")
                bb = parse_bounds(bounds) if isinstance(bounds, str) else None
                t = attrs.get("type") or "component"
                if bb and t != "root" and bb["width"] > 0 and bb["height"] > 0:
                    comp_id = attrs.get("accessibilityId") or attrs.get("hashcode") or str(idx)
                    idx += 1
                    comp = {
                        "id": str(comp_id),
                        "type": t,
                        "bounding_box": bb
                    }
                    txt = attrs.get("text")
                    if isinstance(txt, str) and txt:
                        comp["text"] = txt
                    result.append(comp)
            children = node.get("children")
            if isinstance(children, list):
                for c in children:
                    rec(c)
        elif isinstance(node, list):
            for it in node:
                rec(it)

    rec(data)
    return result

def is_enhanced_schema(obj):
    """判断对象是否为增强语义图结构（包含 meta/elements）"""
    return isinstance(obj, dict) and isinstance(obj.get("meta"), dict) and isinstance(obj.get("elements"), list)

def extract_raw_detections_from_list(data):
    """从简单列表结构提取原始检测项

    每项需包含 box=[x1,y1,x2,y2]，可选 label/conf/text/ocr_conf
    """
    out = []
    if isinstance(data, list):
        for it in data:
            box = it.get("box")
            if isinstance(box, (list, tuple)) and len(box) >= 4:
                out.append({
                    "label": it.get("label", "unknown"),
                    "box": [box[0], box[1], box[2], box[3]],
                    "conf": it.get("conf", 0.0),
                    "text": it.get("text"),
                    "ocr_conf": it.get("ocr_conf", 0.0),
                })
    return out

def extract_raw_detections_from_tree(data):
    """从树形结构（含 children/attributes）提取原始检测项"""
    out = []
    def rec(node):
        if isinstance(node, dict):
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else None
            if attrs:
                bounds = attrs.get("bounds")
                bb = parse_bounds(bounds) if isinstance(bounds, str) else None
                t = attrs.get("type") or attrs.get("label") or "unknown"
                if bb and t != "root" and bb["width"] > 0 and bb["height"] > 0:
                    x1 = bb["x"]
                    y1 = bb["y"]
                    x2 = x1 + bb["width"]
                    y2 = y1 + bb["height"]
                    out.append({
                        "label": t,
                        "box": [x1, y1, x2, y2],
                        "conf": 0.0,
                        "text": attrs.get("text"),
                        "ocr_conf": 0.0,
                    })
            children = node.get("children")
            if isinstance(children, list):
                for c in children:
                    rec(c)
        elif isinstance(node, list):
            for it in node:
                rec(it)
    rec(data)
    return out

def infer_resolution_from_graph_or_boxes(obj, raw_detections):
    """推断分辨率

    优先从增强语义图的 meta.resolution 获取；
    其次取检测框的最大 x2/y2；最后尝试解析树根 bounds。
    """
    if is_enhanced_schema(obj):
        res = obj.get("meta", {}).get("resolution")
        if isinstance(res, list) and len(res) == 2:
            return int(res[0]) or 1, int(res[1]) or 1
    max_x2 = 1
    max_y2 = 1
    for it in raw_detections:
        box = it.get("box")
        if isinstance(box, (list, tuple)) and len(box) >= 4:
            max_x2 = max(max_x2, int(box[2]))
            max_y2 = max(max_y2, int(box[3]))
    if max_x2 > 1 and max_y2 > 1:
        return max_x2, max_y2
    if isinstance(obj, dict):
        attrs = obj.get('attributes') if isinstance(obj.get('attributes'), dict) else None
        if attrs and isinstance(attrs.get('bounds'), str):
            bb = parse_bounds(attrs.get('bounds'))
            if bb:
                return max(1, int(bb['width'])), max(1, int(bb['height']))
    return 1, 1

@app.route('/api/compare', methods=['POST'])
def compare_designs():
    """设计与运行时对比入口

    请求体:
    - design_json: 设计端原始/增强数据（字符串或对象）
    - code_json: 运行时原始/增强数据（字符串或对象）

    流程:
    - 规范化输入为语义图
    - 模糊匹配得到 matches/missing/added
    - 差异分析生成诊断报告与蓝图
    - 返回各阶段产物路径与汇总数据
    """
    try:
        data = request.json
        design_json = data.get('design_json')
        code_json = data.get('code_json')
        
        if not design_json or not code_json:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        design_data = json.loads(design_json) if isinstance(design_json, str) else design_json
        code_data = json.loads(code_json) if isinstance(code_json, str) else code_json

        design_raw = []
        runtime_raw = []
        if is_enhanced_schema(design_data):
            semantic_graph_design = design_data
        else:
            design_raw = extract_raw_detections_from_list(design_data) if isinstance(design_data, list) else extract_raw_detections_from_tree(design_data)
            dw, dh = infer_resolution_from_graph_or_boxes(design_data, design_raw)
            builder_d = UISemanticBuilder(dw, dh, "design")
            semantic_graph_design = builder_d.build(design_raw)
        if is_enhanced_schema(code_data):
            semantic_graph_runtime = code_data
        else:
            runtime_raw = extract_raw_detections_from_list(code_data) if isinstance(code_data, list) else extract_raw_detections_from_tree(code_data)
            rw, rh = infer_resolution_from_graph_or_boxes(code_data, runtime_raw)
            builder_r = UISemanticBuilder(rw, rh, "runtime")
            semantic_graph_runtime = builder_r.build(runtime_raw)

        matcher = UIFuzzyMatcher()
        matching = matcher.run(semantic_graph_design, semantic_graph_runtime)
        differ = UISemanticDiffer()
        diagnostic_report = differ.analyze(matching, semantic_graph_design.get('meta'), semantic_graph_runtime.get('meta'))
        req_id = uuid.uuid4().hex[:8]
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        out_root = os.path.join(root_dir, 'output')
        os.makedirs(out_root, exist_ok=True)
        folder_id = diagnostic_report.get('report_id') or req_id
        out_dir = os.path.join(out_root, folder_id)
        os.makedirs(out_dir, exist_ok=True)
        p_step1_design = os.path.join(out_dir, 'step1_design.json')
        p_step1_runtime = os.path.join(out_dir, 'step1_runtime.json')
        p_step2 = os.path.join(out_dir, 'step2_matching.json')
        p_step3 = os.path.join(out_dir, 'step3_diagnostic.json')
        p_step4 = os.path.join(out_dir, 'step4_blueprints.json')
        try:
            with open(p_step1_design, 'w', encoding='utf-8') as f:
                json.dump(semantic_graph_design, f, ensure_ascii=False, indent=2)
            with open(p_step1_runtime, 'w', encoding='utf-8') as f:
                json.dump(semantic_graph_runtime, f, ensure_ascii=False, indent=2)
            with open(p_step2, 'w', encoding='utf-8') as f:
                json.dump(matching, f, ensure_ascii=False, indent=2)
            with open(p_step3, 'w', encoding='utf-8') as f:
                json.dump(diagnostic_report, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        planner = LangChainPlanner()
        ai_blueprints = []
        for it in diagnostic_report.get('issues', []):
            ctx = build_issue_context(semantic_graph_design.get('elements', []), it.get('node_id'))
            bp = planner.plan(it, ctx)
            ai_blueprints.append(bp)
        if not ai_blueprints:
            ai_blueprints.append({
                'plan_id': f"plan_{uuid.uuid4().hex[:8]}",
                'target_file': '',
                'confidence': 'high',
                'action_type': 'NO_ACTION',
                'location_hint': {},
                'reasoning': '设计与实现一致，无需修改',
                'parent_container_path': None,
            })
        try:
            with open(p_step4, 'w', encoding='utf-8') as f:
                json.dump({
                    'report_id': diagnostic_report.get('report_id'),
                    'blueprints': ai_blueprints
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        metrics = {
            'difference_count': len(matching.get('missing', [])) + len(matching.get('added', [])),
            'match_rate': 0,
            'total_components': semantic_graph_design.get('meta', {}).get('node_count', 0),
            'completeness': 0,
        }
        comparison_result = {
            'matches': [],
            'unmatched_design': matching.get('missing', []),
            'unmatched_code': matching.get('added', []),
            'total_design_components': semantic_graph_design.get('meta', {}).get('node_count', 0),
            'total_code_components': semantic_graph_runtime.get('meta', {}).get('node_count', 0),
            'matched_components': len(matching.get('matches', [])),
            'unmatched_design_count': len(matching.get('missing', [])),
            'unmatched_code_count': len(matching.get('added', [])),
        }
        suggestions = []
        
        return jsonify({
            'success': True,
            'metrics': metrics,
            'comparison_result': comparison_result,
            'ai_suggestions': suggestions,
            'ai_blueprints': ai_blueprints,
            'semantic_graph_design': semantic_graph_design,
            'semantic_graph_runtime': semantic_graph_runtime,
            'matching': {
                'matches': [{
                    'design_id': it['design'].get('id'),
                    'runtime_id': it['runtime'].get('id'),
                    'cost': it['cost']
                } for it in matching.get('matches', [])],
                'missing': [it.get('id') for it in matching.get('missing', [])],
                'added': [it.get('id') for it in matching.get('added', [])]
            },
            'diagnostic_report': diagnostic_report,
            'outputs': {
                'dir': out_dir,
                'step1_design': p_step1_design,
                'step1_runtime': p_step1_runtime,
                'step2_matching': p_step2,
                'step3_diagnostic': p_step3,
                'step4_blueprints': p_step4
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """图片上传示例接口（当前未处理图像）"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        image_file = request.files['image']
        # For now, just return success without processing
        # In a real implementation, you'd process the image here
        
        return jsonify({
            'success': True,
            'message': 'Image uploaded successfully',
            'filename': image_file.filename
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)
