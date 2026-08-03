from __future__ import annotations

from pathlib import Path

from langchain_core.messages import SystemMessage

from lerai.override_agent.nodes import _build_supervisor_llm, should_continue, build_initial_input
from .state import CplexAgentState
from .tools import CPLEX_TOOLS

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SYSTEM_PROMPT = (
    PROJECT_ROOT / "lerai" / "prompts" / "cplex_agent_system_prompt.txt"
).read_text(encoding="utf-8").strip()


def supervisor_node(state: CplexAgentState) -> CplexAgentState:
    llm = _build_supervisor_llm().bind_tools(CPLEX_TOOLS)
    messages = [SystemMessage(content=_SYSTEM_PROMPT)] + list(state["messages"])
    response = llm.invoke(messages)
    return {"messages": [response]}
