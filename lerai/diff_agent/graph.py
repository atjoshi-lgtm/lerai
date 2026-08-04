from langgraph.graph import END, START, StateGraph

from .nodes import analyze_and_correlate_node, ingest_and_filter_node
from .state import DiffAgentState


def get_compiled_graph():
	workflow = StateGraph(DiffAgentState)

	workflow.add_node("ingest_and_filter", ingest_and_filter_node)
	workflow.add_node("analyze_and_correlate", analyze_and_correlate_node)

	workflow.add_edge(START, "ingest_and_filter")
	workflow.add_edge("ingest_and_filter", "analyze_and_correlate")
	workflow.add_edge("analyze_and_correlate", END)

	return workflow.compile()
