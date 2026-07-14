from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import AzureChatOpenAI

from .state import OverrideAgentState
from .tools import SUPERVISOR_TOOLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"
SUPERVISOR_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "override_agent_supervisor_system_prompt.txt"


def _load_supervisor_system_prompt() -> str:
     return SUPERVISOR_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()


def _get_azure_api_version() -> str:
    """Extract api-version from endpoint query string; fallback to legacy default."""
    endpoint = os.getenv("AZURE_OPENAI_URL", "")
    if endpoint:
        parsed = urlparse(endpoint)
        query = parse_qs(parsed.query)
        api_version = query.get("api-version", [""])[0]
        if api_version:
            return api_version
    return "2023-05-15"


def _build_proxy_base_url(full_url: str) -> str | None:
    """Derive base URL for chat.completions from full proxy URL, if present."""
    if not full_url:
        return None

    parsed = urlparse(full_url)
    path = parsed.path or ""

    if "/chat/completions" in path:
        path = path.split("/chat/completions", 1)[0]

    if not path:
        return None

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _build_azure_deployment(full_url: str) -> str | None:
    """Extract deployment name from URL path when using /deployments/<name>/..."""
    if not full_url:
        return None

    parsed = urlparse(full_url)
    path = parsed.path or ""
    marker = "/deployments/"
    if marker not in path:
        return None

    tail = path.split(marker, 1)[1]
    deployment = tail.split("/", 1)[0].strip()
    return deployment or None


def _build_http_client(timeout_seconds: float) -> httpx.Client:
    verify_setting: str | bool = os.getenv("REQUESTS_CA_BUNDLE") or True
    return httpx.Client(verify=verify_setting, timeout=timeout_seconds)


def _build_supervisor_llm() -> AzureChatOpenAI:
    """Creates an AzureChatOpenAI model configured for this environment."""
    azure_url = os.getenv("AZURE_OPENAI_URL", "")
    timeout_seconds = float(os.getenv("AZURE_OPENAI_TIMEOUT", 30))
    model = os.getenv("AZURE_OPENAI_MODEL", "GPT-5.2")
    api_version = _get_azure_api_version()

    # Keep requested mapping while also supporting full proxy-style URLs.
    base_url = _build_proxy_base_url(azure_url)
    deployment = _build_azure_deployment(azure_url)

    llm_kwargs: dict[str, Any] = {
        "model": model,
        "azure_deployment": deployment,
        "api_key": os.getenv("AZURE_API_KEY"),
        "api_version": api_version,
        "timeout": timeout_seconds,
        "default_query": {"api-version": api_version},
        "http_client": _build_http_client(timeout_seconds),
        "validate_base_url": False,
        "default_headers": {
            "user-id": os.getenv("AZURE_USER_ID", ""),
            "app-name": os.getenv("AZURE_APP_NAME", ""),
        },
        "temperature": 0,
    }

    if base_url:
        llm_kwargs["base_url"] = base_url
    else:
        llm_kwargs["azure_endpoint"] = azure_url

    return AzureChatOpenAI(**llm_kwargs)


def _extract_latest_conflict_report(messages: list[Any]) -> dict[str, Any] | str:
    """Returns the latest conflict tool payload for state tracking."""
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue

        if message.name != "detect_override_conflicts":
            continue

        content = message.content
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )

        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content

        return str(content)

    return ""


def _extract_latest_draft(messages: list[Any]) -> str:
    """Returns the latest generated TOML payload for state tracking."""
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue

        if message.name != "generate_and_validate_toml":
            continue

        content = message.content
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )

        if isinstance(content, str):
            try:
                payload = json.loads(content)
                if isinstance(payload, dict):
                    return str(payload.get("toml", ""))
            except json.JSONDecodeError:
                return ""

    return ""


def supervisor_node(state: OverrideAgentState) -> OverrideAgentState:
    """Primary Supervisor node for the override workflow."""
    llm = _build_supervisor_llm().bind_tools(SUPERVISOR_TOOLS)

    prior_messages = state.get("messages", [])
    system_prompt = _load_supervisor_system_prompt()
    response = llm.invoke([SystemMessage(content=system_prompt), *prior_messages])

    updates: OverrideAgentState = {"messages": [response]}

    combined_messages = [*prior_messages, response]
    latest_conflict = _extract_latest_conflict_report(combined_messages)
    if latest_conflict:
        updates["conflict_report"] = latest_conflict

    latest_draft = _extract_latest_draft(combined_messages)
    if latest_draft:
        updates["draft_toml"] = latest_draft

    return updates


def should_continue(state: OverrideAgentState) -> str:
    """Route to tools when tool calls are present; otherwise stop and wait for user/app."""
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"

    return "end"


def build_initial_input(user_text: str, jira_xml: str | None = None) -> OverrideAgentState:
    """Helper to seed graph input for an incoming Webex message."""
    content = user_text.strip()
    if jira_xml:
        content = f"{content}\n\nJIRA_XML_CONTEXT:\n{jira_xml.strip()}"
    return {"messages": [HumanMessage(content=content)]}
