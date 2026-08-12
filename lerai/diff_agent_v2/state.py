"""State schema for the diff_agent_v2 in-memory pipeline."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class DiffAgentState(TypedDict):
    """Typed state shared across diff_agent_v2 graph nodes."""

    messages: Annotated[list, add_messages]
    blc_structure_diffs: list[dict[str, str]]
    fcs_structure_diffs: list[dict[str, str]]
    fcs_quota_diffs: list[dict[str, float | str]]
    override_toml_diff: str
    final_report: str
