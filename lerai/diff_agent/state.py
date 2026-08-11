from typing import TypedDict

from langchain_core.messages import BaseMessage


class DiffAgentState(TypedDict):
	messages: list[BaseMessage]
	composite_token: str
	promotion_token: str
	toml_diff: str
	raw_csv_diff_response: dict
	filtered_csv_changes: dict
	is_pipeline_healthy: bool
	error_message: str | None
	final_report: str
