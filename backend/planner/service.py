import os
import json
import uuid
from typing import List, Dict, Any, Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .schema import ModificationBlueprint
from .tools import search_codebase, list_files
from .agent import make_executor, AGENT_AVAILABLE

def _index_elements(elements: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """按 id 建立元素索引"""
    return {e.get("id"): e for e in elements if isinstance(e, dict) and e.get("id")}

def _distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """计算两元素中心点的欧氏距离（归一化）"""
    ca = a.get("geometry", {}).get("center") or [0.0, 0.0]
    cb = b.get("geometry", {}).get("center") or [0.0, 0.0]
    dx = float(ca[0]) - float(cb[0])
    dy = float(ca[1]) - float(cb[1])
    return (dx * dx + dy * dy) ** 0.5

def build_issue_context(elements: List[Dict[str, Any]], node_id: Optional[str]) -> Dict[str, Any]:
    """构建问题上下文信息

    返回与目标节点相关的父容器角色与近邻文本，用于定位代码位置。
    """
    idx = _index_elements(elements or [])
    node = idx.get(node_id) if node_id else None
    parent_role = None
    sibling_text = []
    if node:
        pid = node.get("topology", {}).get("parent_id")
        parent = idx.get(pid) if pid else None
        if parent:
            parent_role = (parent.get("type", {}).get("label") or "")
            sib_ids = parent.get("topology", {}).get("children") or []
            sibs = [idx.get(s) for s in sib_ids if idx.get(s) and idx.get(s).get("id") != node.get("id")]
            sibs = sorted(sibs, key=lambda s: _distance(node, s))
            for s in sibs[:3]:
                t = (s.get("content", {}).get("text") or "").strip()
                if t:
                    sibling_text.append(t)
    return {"sibling_text": sibling_text, "parent_role": parent_role}

class LangChainPlanner:
    """基于 LangChain 的修改蓝图规划器

    负责调用工具型代理，根据诊断问题与上下文生成 ModificationBlueprint。
    在依赖缺失或执行失败时，回退到规则驱动的方案。
    """
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0):
        """初始化规划器并构建代理执行器"""
        tools = []
        tools.append(search_codebase)
        tools.append(list_files)
        model = model or os.getenv("LLM_MODEL") or "gpt-4o"
        self.executor = make_executor(tools, model=model, temperature=temperature)

    def _fallback(self, issue: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """在代理不可用或失败时的回退策略，生成保守的蓝图"""
        pid = uuid.uuid4().hex[:8]
        t = issue.get("type") or "UNKNOWN"
        role = issue.get("widget_role") or "component"
        target_file = ""
        confidence = "low"
        action_type = "MODIFY_STYLE"
        location_hint = {}
        if t == "TEXT_MISMATCH":
            action_type = "MODIFY_TEXT"
            actual = (issue.get("actual") or "").strip()
            location_hint = {"search_text": actual or issue.get("expected") or ""}
            sr = search_codebase(location_hint.get("search_text") or "")
            first = sr.splitlines()[0] if isinstance(sr, str) and sr else ""
            if ":" in first:
                target_file = first.split(":", 1)[0]
            confidence = "low"
        elif t == "MISSING_WIDGET":
            action_type = "ADD_COMPONENT"
            location_hint = {"component_name": role, "anchors": ctx or {}}
            confidence = "low"
        else:
            action_type = "MODIFY_STYLE"
            location_hint = {"component_name": role}
            confidence = "low"
        return ModificationBlueprint(
            plan_id=f"plan_{pid}",
            target_file=target_file,
            confidence=confidence,
            action_type=action_type,
            location_hint=location_hint,
            reasoning="rule-based fallback",
            parent_container_path=None,
        ).dict()

    def plan(self, issue_json: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """根据单条问题与上下文生成修改蓝图"""
        user_input = (
            "请分析以下 UI 问题并生成修改蓝图：\n" +
            json.dumps({"issue": issue_json, "context": context}, ensure_ascii=False)
            + "\n最终回答必须严格符合 ModificationBlueprint 的 JSON 结构。"
        )
        if self.executor is None:
            return self._fallback(issue_json, context)
        try:
            result = self.executor.invoke({"diagnostic_report": user_input})
            out = result.get("output") if isinstance(result, dict) else None
            if isinstance(out, str) and out.strip():
                data = json.loads(out)
                return data
        except Exception:
            pass
        return self._fallback(issue_json, context)

def _save_blueprints(out_path: str, report_id: str, blueprints: List[Dict[str, Any]]):
    """将蓝图结果保存为 JSON 文件"""
    payload = {"report_id": report_id, "blueprints": blueprints}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", required=True)
    args = parser.parse_args()
    p = os.path.abspath(args.diagnostic)
    with open(p, "r", encoding="utf-8") as f:
        diag = json.load(f)
    issues = diag.get("issues") or []
    elements = diag.get("elements") or []
    report_id = diag.get("report_id") or uuid.uuid4().hex[:8]
    planner = LangChainPlanner()
    blueprints = []
    for it in issues:
        ctx = build_issue_context(elements, it.get("node_id"))
        bp = planner.plan(it, ctx)
        blueprints.append(bp)
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    out_dir = os.path.join(root_dir, 'output')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'step4_blueprints_{uuid.uuid4().hex[:8]}.json')
    _save_blueprints(out_path, report_id, blueprints)
    print(out_path)
