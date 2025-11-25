import json
from planner.service import build_issue_context, LangChainPlanner

def test_context_extraction_minimal():
    elements = [
        {
            "id": "p1",
            "type": {"label": "container"},
            "geometry": {"center": [0.5, 0.5]},
            "topology": {"parent_id": None, "children": ["a", "b"]},
            "content": {"text": None},
        },
        {
            "id": "a",
            "type": {"label": "text"},
            "geometry": {"center": [0.4, 0.5]},
            "topology": {"parent_id": "p1", "children": []},
            "content": {"text": "合计: ¥100"},
        },
        {
            "id": "b",
            "type": {"label": "button"},
            "geometry": {"center": [0.6, 0.5]},
            "topology": {"parent_id": "p1", "children": []},
            "content": {"text": "去下单"},
        },
    ]
    ctx = build_issue_context(elements, "b")
    assert "parent_role" in ctx
    assert isinstance(ctx.get("sibling_text"), list)

def test_planner_fallback_text_mismatch():
    planner = LangChainPlanner()
    issue = {
        "type": "TEXT_MISMATCH",
        "severity": "major",
        "widget_role": "submit_button",
        "actual": "去下单",
        "expected": "立即下单",
    }
    bp = planner.plan(issue, {"sibling_text": ["合计: ¥100"], "parent_role": "container"})
    assert isinstance(bp, dict)
    assert bp.get("action_type") == "MODIFY_TEXT"
