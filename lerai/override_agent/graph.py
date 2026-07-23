from __future__ import annotations

import atexit
import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .nodes import discard_node, drafting_specialist, knowledge_specialist, semantic_router
from .state import OverrideAgentState
from .tools import DRAFTING_TOOLS, KNOWLEDGE_TOOLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINT_DB_PATH = PROJECT_ROOT / "lerai_checkpoints.db"

_GRAPH_LOCK = threading.Lock()
_SQLITE_CONN: sqlite3.Connection | None = None
_COMPILED_GRAPH = None


def _build_graph_builder() -> StateGraph:
    graph_builder = StateGraph(OverrideAgentState)

    graph_builder.add_node("router", semantic_router)
    graph_builder.add_node("knowledge", knowledge_specialist)
    graph_builder.add_node("drafting", drafting_specialist)
    graph_builder.add_node("discard", discard_node)
    graph_builder.add_node("knowledge_tools", ToolNode(KNOWLEDGE_TOOLS))
    graph_builder.add_node("drafting_tools", ToolNode(DRAFTING_TOOLS))

    graph_builder.add_edge(START, "router")

    def route_decision(state: OverrideAgentState) -> str:
        return state.get("router_decision", "drafting")

    graph_builder.add_conditional_edges(
        "router",
        route_decision,
        {"knowledge": "knowledge", "drafting": "drafting", "discard": "discard"},
    )

    def tools_condition(state: OverrideAgentState) -> str:
        messages = state.get("messages", [])
        if messages and getattr(messages[-1], "tool_calls", None):
            return "tools"
        return END

    graph_builder.add_conditional_edges(
        "knowledge", tools_condition, {"tools": "knowledge_tools", END: END}
    )
    graph_builder.add_conditional_edges(
        "drafting", tools_condition, {"tools": "drafting_tools", END: END}
    )

    graph_builder.add_edge("knowledge_tools", "knowledge")
    graph_builder.add_edge("drafting_tools", "drafting")
    graph_builder.add_edge("discard", END)

    return graph_builder


def _open_checkpoint_connection() -> sqlite3.Connection:
    """Opens a process-wide SQLite connection tuned for concurrent access."""
    conn = sqlite3.connect(
        CHECKPOINT_DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _close_checkpoint_connection() -> None:
    global _SQLITE_CONN
    if _SQLITE_CONN is not None:
        _SQLITE_CONN.close()
        _SQLITE_CONN = None


atexit.register(_close_checkpoint_connection)


def build_override_agent_graph():
    """Backwards-compatible alias for getting the compiled override graph."""
    return get_compiled_graph()


def get_compiled_graph():
    """Builds a singleton compiled graph backed by a persistent SQLite checkpointer."""
    global _SQLITE_CONN, _COMPILED_GRAPH

    with _GRAPH_LOCK:
        if _COMPILED_GRAPH is not None:
            return _COMPILED_GRAPH

        _SQLITE_CONN = _open_checkpoint_connection()
        checkpointer = SqliteSaver(_SQLITE_CONN)
        graph_builder = _build_graph_builder()
        _COMPILED_GRAPH = graph_builder.compile(checkpointer=checkpointer)
        return _COMPILED_GRAPH


def invoke_override_agent(app, state: OverrideAgentState, thread_id: str):
    """Invoke helper that persists conversations by thread_id (e.g., Webex conversation id)."""
    return app.invoke(
        state,
        config={"configurable": {"thread_id": thread_id}},
    )
