from typing import TypedDict

from langchain_core.messages import BaseMessage


class DiffAgentState(TypedDict):
	messages: list[BaseMessage]
	promotion_token: str
	source_context: dict
	toml_diff: str
	raw_csv_diff_response: dict
	filtered_csv_changes: dict
	is_pipeline_healthy: bool
	error_message: str | None
	final_report: str
	timestamps: dict
