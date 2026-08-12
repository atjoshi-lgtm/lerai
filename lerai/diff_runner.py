import logging

from lerai.diff_agent.graph import get_compiled_graph
from lerai.diff_agent_v2.graph import get_compiled_graph as get_compiled_graph_v2


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


def run_diff_agent_v2(message: str, webex_message=None) -> str:
	logger.info("Invoking Diff Analyst v2 agent")
	graph = get_compiled_graph_v2()
	result = graph.invoke(
		{
			"messages": [],
			"blc_structure_diffs": [],
			"fcs_structure_diffs": [],
			"fcs_quota_diffs": [],
			"override_toml_diff": "",
			"final_report": "",
		}
	)
	final_report = result.get("final_report", "Error: No report generated.")
	logger.info(
		"Diff Analyst v2 agent completed (state_keys=%s, final_report_len=%d)",
		sorted(result.keys()),
		len(final_report),
	)
	return final_report
