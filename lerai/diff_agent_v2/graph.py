"""Graph assembly for diff_agent_v2."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import analyze_and_correlate, ingest_and_diff_data
from .state import DiffAgentState


def get_compiled_graph():
    """Build and compile the diff_agent_v2 execution graph."""
    builder = StateGraph(DiffAgentState)
    builder.add_node("ingest_and_diff_data", ingest_and_diff_data)
    builder.add_node("analyze_and_correlate", analyze_and_correlate)

    builder.add_edge(START, "ingest_and_diff_data")
    builder.add_edge("ingest_and_diff_data", "analyze_and_correlate")
    builder.add_edge("analyze_and_correlate", END)

    return builder.compile()
