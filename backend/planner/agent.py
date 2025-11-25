import os
from typing import List, Optional

AGENT_AVAILABLE = True
HAVE_AGENT_API = True
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.tools import Tool
    try:
        from langchain.agents import AgentExecutor, create_openai_tools_agent
    except Exception:
        HAVE_AGENT_API = False
except Exception:
    AGENT_AVAILABLE = False
    HAVE_AGENT_API = False

def system_prompt_text() -> str:
    """返回代理的系统提示词

    角色设定为资深前端架构师，指导模型如何利用工具与策略生成修改蓝图。
    """
    return (
        "你是资深前端架构师，任务是根据 UI 诊断报告定位需要修改的代码文件。\n"
        "工具: search_codebase, list_files。\n"
        "策略: TEXT_MISMATCH 搜索 actual；MISSING_WIDGET 搜索 sibling_text 或 parent_role；\n"
        "LAYOUT/SIZE 定位样式或组件定义；输出严格为 ModificationBlueprint JSON。"
    )

def make_executor(tools: List, model: Optional[str] = None, temperature: float = 0.0):
    """创建使用工具的代理执行器

    参数:
    - tools: 可用工具列表
    - model: LLM 模型名称
    - temperature: 采样温度

    返回:
    - AgentExecutor 或 None（当依赖不可用时）
    """
    if not AGENT_AVAILABLE:
        return None
    model = model or os.getenv("LLM_MODEL") or "gpt-4o"
    base = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    if base:
        os.environ["OPENAI_BASE_URL"] = base
        os.environ["OPENAI_API_BASE"] = base
    llm = ChatOpenAI(model=model, temperature=temperature)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt_text()),
        ("user", "{diagnostic_report}"),
    ])
    if HAVE_AGENT_API:
        lc_tools = []
        for t in tools:
            lc_tools.append(Tool(name=getattr(t, "__name__", "tool"), description="project helper", func=t))
        agent = create_openai_tools_agent(llm, lc_tools, prompt)
        return AgentExecutor(agent=agent, tools=lc_tools, verbose=False)
    class SimpleExecutor:
        def __init__(self, llm, prompt):
            self.llm = llm
            self.prompt = prompt
        def invoke(self, inputs):
            msgs = self.prompt.format_messages(diagnostic_report=inputs.get("diagnostic_report", ""))
            res = self.llm.invoke(msgs)
            txt = getattr(res, "content", "")
            return {"output": txt}
    return SimpleExecutor(llm, prompt)
