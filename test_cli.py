#!/usr/bin/env python3
"""Local CLI harness for the LangGraph override agent (no Webex dependencies)."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from datetime import datetime
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

try:
    from override_agent.graph import get_compiled_graph
except ModuleNotFoundError:
    from lerai.override_agent.graph import get_compiled_graph

try:
    from git_workspace import TransientGitWorkspace
except ModuleNotFoundError:
    from lerai.git_workspace import TransientGitWorkspace

os.makedirs("logs/test_cli", exist_ok=True)
_log_filename = os.path.join("logs/test_cli", f"override_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    filename=_log_filename,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Suppress verbose third-party debug output that produces unreadable single-line dumps
for _noisy_logger in ("httpx", "httpcore", "openai", "openai._base_client"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _print_new_messages(result: dict[str, Any], seen_messages: set[str]) -> None:
    """Logs AI messages, tool calls, and tool results that haven't been seen yet."""
    messages = result.get("messages", [])
    
    for msg in messages:
        # Skip if we already printed this message in a previous turn
        msg_id = getattr(msg, "id", str(id(msg)))
        if msg_id in seen_messages:
            continue
        seen_messages.add(msg_id)

        msg_type = getattr(msg, "type", None)

        # 1. Handle AI Messages and Tool Calls
        if msg_type == "ai":
            # Log any tool calls the AI decided to make
            tool_calls = getattr(msg, "tool_calls", [])
            for tc in tool_calls:
                logger.info("[Tool Called: %s] Arguments: %s", tc.get("name"), tc.get("args"))

            # Print standard AI conversational text
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                text_parts = [str(part["text"]) for part in content if isinstance(part, dict) and "text" in part]
                rendered = "\n".join(text_parts)
            else:
                rendered = str(content)

            if rendered.strip():
                logger.info("[Assistant] %s", rendered)
                print(f"\n### 🤖 Assistant:\n{rendered}\n")

        # 2. Handle Tool Results (Optional, but great for debugging)
        elif msg_type == "tool":
            content = getattr(msg, "content", "")
            # Truncate long tool outputs so it doesn't flood the log
            truncated = str(content)[:300] + ("..." if len(str(content)) > 300 else "")
            logger.debug("[Tool Result (%s)] %s", getattr(msg, "name", "unknown"), truncated)


def _print_interrupts(graph, config, result) -> bool:
    """Checks if the graph is currently interrupted and prints the interrupt payload."""
    state = graph.get_state(config)
    
    # Check if there are active tasks with interrupts
    if state.tasks:
        for task in state.tasks:
            if getattr(task, "interrupts", None):
                for intr in task.interrupts:
                    diff_payload = getattr(intr, "value", str(intr))
                    print("\n")
                    print("⚠️  ACTION REQUIRED: APPROVAL REQUEST")
                    # print("=" * 50)
                    print(diff_payload)
                    print("\n")
                return True

    # Fallback check on result if state tasks aren't populated
    if isinstance(result, dict) and "__interrupt__" in result:
        print("\n⚠️  [Graph Interrupted / Paused]")
        return True

    return False


def main() -> int:
    graph = get_compiled_graph()
    
    # logger.info(graph.get_graph(xray=True).draw_mermaid())
    # Generate a unique thread ID every time the script is executed
    request_uuid = uuid.uuid4().hex
    workspace_path = f"/tmp/leroy_config_test_{request_uuid}"
    thread_id = f"cli_test_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id, "workspace_path": workspace_path}}

    required_env = [
        "AZURE_OPENAI_URL",
        "AZURE_API_KEY",
        "AZURE_USER_ID",
        "AZURE_APP_NAME",
    ]
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        logger.error("Missing required environment variables: %s", missing)
        print("Missing required environment variables:")
        for name in missing:
            print(f"- {name}")
        return 1

    logger.info("Override Agent CLI session started (thread_id=%s)", thread_id)
    print(f"Override Agent CLI (Session: {thread_id})")
    print("Type 'exit' or 'quit' to stop.")

    is_interrupted = False
    seen_messages: set[str] = set()

    workspace = TransientGitWorkspace(local_path=workspace_path)
    workspace.clone()

    try:
        while True:
            try:
                user_text = input("\n### 👤 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                return 0

            if user_text.lower() in {"exit", "quit"}:
                print("Exiting.")
                return 0

            if not user_text:
                continue

            try:
                if is_interrupted:
                    result = graph.invoke(Command(resume=user_text), config=config)
                else:
                    result = graph.invoke({"messages": [HumanMessage(content=user_text)]}, config=config)

                _print_new_messages(result, seen_messages)
                is_interrupted = _print_interrupts(graph, config, result)

            except Exception as exc:
                logger.error("Error invoking graph: %s", exc, exc_info=True)
                print(f"\n❌ Error invoking graph: {exc}\n")
    finally:
        shutil.rmtree(workspace_path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())