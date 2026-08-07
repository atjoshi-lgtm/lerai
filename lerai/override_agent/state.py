from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class OverrideAgentState(TypedDict, total=False):
    """State container for the override supervisor workflow."""

    messages: Annotated[list[AnyMessage], add_messages]
    base_override_token: str
    live_override_toml: str
    # Single-stanza preview from generate_and_validate_toml; distinct from the merged draft_toml.
    generated_stanza_toml: str
    draft_toml: str
    conflict_report: dict[str, Any] | str
