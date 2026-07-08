#!/usr/bin/env python3
"""Local CLI harness for the LangGraph override agent (no Webex dependencies)."""

from __future__ import annotations

import os
import sys
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

try:
    # Preferred import path per request.
    from override_agent.graph import get_compiled_graph
except ModuleNotFoundError:
    # Fallback for this repository layout.
    from lerai.override_agent.graph import get_compiled_graph


def _print_ai_messages(result: dict[str, Any]) -> None:
    """Print only AI messages from graph outputs for readability in terminal."""
    messages = result.get("messages", [])
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type != "ai":
            continue

        content = getattr(msg, "content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(str(part["text"]))
                else:
                    text_parts.append(str(part))
            rendered = "\n".join(p for p in text_parts if p)
        else:
            rendered = str(content)

        if rendered.strip():
            print("\nAssistant:\n")
            print(rendered)
            print()


def _print_interrupts(result: dict[str, Any]) -> bool:
    """Print interrupt payloads when graph returns __interrupt__."""
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return False

    print("\nGraph interrupt detected:\n")
    for item in interrupts:
        print(item)
    print("\nReply with your resolution to continue.\n")
    return True


def main() -> int:
    graph = get_compiled_graph()
    thread_id = "terminal_test_1"
    config = {"configurable": {"thread_id": thread_id}}

    required_env = [
        "AZURE_OPENAI_URL",
        "AZURE_API_KEY",
        "AZURE_USER_ID",
        "AZURE_APP_NAME",
    ]
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        print("Missing required environment variables:")
        for name in missing:
            print(f"- {name}")
        return 1

    print("Override Agent CLI")
    print("Type 'exit' or 'quit' to stop.")

    is_first_turn = True
    is_interrupted = False

    while True:
        try:
            user_text = input("\nYou: ").strip()
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

            _print_ai_messages(result)
            is_interrupted = _print_interrupts(result)

            if is_first_turn:
                is_first_turn = False
        except Exception as exc:
            print(f"\nError invoking graph: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
