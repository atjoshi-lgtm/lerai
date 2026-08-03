from __future__ import annotations

import atexit
import sqlite3
import threading

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from lerai.override_agent.graph import _open_checkpoint_connection, CHECKPOINT_DB_PATH
from .nodes import supervisor_node, should_continue
from .state import CplexAgentState
from .tools import CPLEX_TOOLS

_GRAPH_LOCK = threading.Lock()
_SQLITE_CONN: sqlite3.Connection | None = None
_COMPILED_GRAPH = None


def _build_graph_builder() -> StateGraph:
    graph_builder = StateGraph(CplexAgentState)

    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("tools", ToolNode(CPLEX_TOOLS))

    graph_builder.add_edge(START, "supervisor")
    graph_builder.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )
    graph_builder.add_edge("tools", "supervisor")
    return graph_builder


def _close_checkpoint_connection() -> None:
    global _SQLITE_CONN
    if _SQLITE_CONN is not None:
        _SQLITE_CONN.close()
        _SQLITE_CONN = None


atexit.register(_close_checkpoint_connection)


def get_compiled_graph():
    """Builds a singleton compiled graph backed by the shared SQLite checkpointer."""
    global _SQLITE_CONN, _COMPILED_GRAPH

    with _GRAPH_LOCK:
        if _COMPILED_GRAPH is not None:
            return _COMPILED_GRAPH

        _SQLITE_CONN = _open_checkpoint_connection()
        checkpointer = SqliteSaver(_SQLITE_CONN)
        graph_builder = _build_graph_builder()
        _COMPILED_GRAPH = graph_builder.compile(checkpointer=checkpointer)
        return _COMPILED_GRAPH
