from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import AzureChatOpenAI

from .state import OverrideAgentState
from .tools import DRAFTING_TOOLS, KNOWLEDGE_TOOLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"

logger = logging.getLogger(__name__)


def _serialize_message(message: Any) -> dict[str, Any]:
    """Convert LangChain messages into a log-friendly payload."""
    payload: dict[str, Any] = {
        "type": getattr(message, "type", message.__class__.__name__),
        "content": getattr(message, "content", ""),
    }

    name = getattr(message, "name", None)
    if name:
        payload["name"] = name

    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = tool_calls

    invalid_tool_calls = getattr(message, "invalid_tool_calls", None)
    if invalid_tool_calls:
        payload["invalid_tool_calls"] = invalid_tool_calls

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if additional_kwargs:
        payload["additional_kwargs"] = additional_kwargs

    response_metadata = getattr(message, "response_metadata", None)
    if response_metadata:
        payload["response_metadata"] = response_metadata

    usage_metadata = getattr(message, "usage_metadata", None)
    if usage_metadata:
        payload["usage_metadata"] = usage_metadata

    return payload


def _decode_nested_json(value: Any, max_depth: int = 5) -> Any:
    """Recursively decode JSON-looking strings into structured objects for logging."""
    if max_depth <= 0:
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{":
            try:
                parsed = json.loads(stripped)
                return _decode_nested_json(parsed, max_depth=max_depth - 1)
            except json.JSONDecodeError:
                return value
        return value

    if isinstance(value, list):
        return [_decode_nested_json(item, max_depth=max_depth) for item in value]

    if isinstance(value, dict):
        return {
            key: _decode_nested_json(item, max_depth=max_depth)
            for key, item in value.items()
        }

    return value


def _pretty_payload(value: Any) -> str:
    """Return a consistently formatted JSON string for log readability."""
    normalized = _decode_nested_json(value)
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def _log_llm_request(messages: list[Any]) -> None:
    logger.debug(
        "[LLM Request Payload] %s",
        _pretty_payload([_serialize_message(message) for message in messages]),
    )


def _log_llm_response(message: Any) -> None:
    logger.debug(
        "[LLM Response Payload] %s",
        _pretty_payload(_serialize_message(message)),
    )


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


def _extract_latest_intents(messages: list[Any]) -> list[dict] | None:
    for message in reversed(messages):
        if getattr(message, "type", None) != "tool":
            continue

        name = getattr(message, "name", None)
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )

        if not isinstance(content, str):
            continue

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue

        if name == "extract_override_intent":
            if isinstance(parsed, dict) and "error" not in parsed:
                return [parsed]

        if name == "update_draft_intents":
            if isinstance(parsed, dict) and parsed.get("ok") and "draft_intents" in parsed:
                draft_intents = parsed.get("draft_intents")
                if isinstance(draft_intents, list):
                    return draft_intents

    return None


class RouteDecision(TypedDict):
    destination: Annotated[
        Literal["knowledge", "drafting", "discard"],
        {"description": "The specialist to route the user to."},
    ]


def semantic_router(state: OverrideAgentState) -> OverrideAgentState:
    """Classifies the user's intent and sets router_decision."""
    if state.get("router_decision"):
        # Command layer already selected a deterministic route.
        return {}

    llm = _build_supervisor_llm().with_structured_output(RouteDecision)
    messages = state.get("messages", [])
    system_prompt = (
        "You are a router. If the user asks a question about LeRoy rules or infrastructure, "
        "output 'knowledge'. If they want to build, edit, or check an override, output 'drafting'. "
        "If they want to cancel, scrap, or clear the plan, output 'discard'."
    )
    request_messages = [SystemMessage(content=system_prompt), *messages]
    _log_llm_request(request_messages)
    decision: RouteDecision = llm.invoke(request_messages) # type: ignore
    return {"router_decision": decision["destination"]}


def knowledge_specialist(state: OverrideAgentState) -> OverrideAgentState:
    """Answers questions about LeRoy documentation and infrastructure data."""
    llm = _build_supervisor_llm().bind_tools(KNOWLEDGE_TOOLS)
    messages = state.get("messages", [])
    system_prompt = (
        "You are an expert on LeRoy override rules, documentation, and infrastructure data. "
        "Use your tools to look up information and answer the user's question accurately."
    )
    request_messages = [SystemMessage(content=system_prompt), *messages]
    _log_llm_request(request_messages)
    response = llm.invoke(request_messages)
    _log_llm_response(response)
    return {"messages": [response]}


def drafting_specialist(state: OverrideAgentState) -> OverrideAgentState:
    """Builds and validates override intent plans using TOML drafting tools."""
    llm = _build_supervisor_llm().bind_tools(DRAFTING_TOOLS)
    messages = state.get("messages", [])
    # system_prompt = (
    #     "You are a TOML drafting expert for LeRoy overrides. "
    #     "Strictly use your tools to extract intents, update the draft plan, and detect conflicts. "
    #     "Never fabricate values; always run tools to build or modify the intent list."
    # )
    system_prompt_path = PROMPTS_DIR / "override_agent_supervisor_system_prompt.txt"
    system_prompt = system_prompt_path.read_text()
    request_messages = [SystemMessage(content=system_prompt), *messages]
    _log_llm_request(request_messages)
    response = llm.invoke(request_messages)
    _log_llm_response(response)

    updates: OverrideAgentState = {"messages": [response]}
    combined_messages = [*messages, response]
    latest_conflict = _extract_latest_conflict_report(combined_messages)
    if latest_conflict:
        updates["conflict_report"] = latest_conflict

    latest_intents = _extract_latest_intents(state.get("messages", []))
    if latest_intents is not None:
        updates["draft_intents"] = latest_intents
    return updates


def discard_node(state: OverrideAgentState) -> OverrideAgentState:
    """Clears the draft plan without calling the LLM."""
    return {
        "draft_intents": [],
        "messages": [AIMessage(content="I have cleared the draft plan. How else can I help you?")],
    }


def build_initial_input(
    user_text: str,
    jira_xml: str | None = None,
    force_route: str | None = None,
) -> OverrideAgentState:
    """Helper to seed graph input for an incoming Webex message."""
    content = user_text.strip()
    if jira_xml:
        content = f"{content}\n\nJIRA_XML_CONTEXT:\n{jira_xml.strip()}"

    state: OverrideAgentState = {"messages": [HumanMessage(content=content)]}
    if force_route:
        state["router_decision"] = force_route
    return state
