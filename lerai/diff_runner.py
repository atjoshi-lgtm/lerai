import logging

from lerai.diff_agent.graph import get_compiled_graph


logger = logging.getLogger(__name__)


def run_diff_agent(message: str, webex_message=None) -> str:
	logger.info("Invoking Diff Analyst agent")
	graph = get_compiled_graph()
	result = graph.invoke({"messages": []})
	final_report = result.get("final_report", "Error: No report generated.")
	logger.info(
		"Diff Analyst agent completed (state_keys=%s, final_report_len=%d)",
		sorted(result.keys()),
		len(final_report),
	)
	return final_report
