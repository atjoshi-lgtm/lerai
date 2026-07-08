from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class OverrideAgentState(TypedDict, total=False):
    """State container for the override supervisor workflow."""

    messages: Annotated[list[AnyMessage], add_messages]
    draft_toml: str
    conflict_report: dict[str, Any] | str
