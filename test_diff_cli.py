#!/usr/bin/env python3
"""Local CLI harness for the Diff Analyst LangGraph agent (no Webex dependencies)."""

from __future__ import annotations

from datetime import datetime
import logging
import os
import sys
import uuid


os.makedirs("logs/test_cli", exist_ok=True)
_log_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_info_log = os.path.join("logs/test_cli", f"diff_agent_{_log_ts}.log")
_debug_log = os.path.join("logs/test_cli", f"diff_agent_{_log_ts}.debug.log")

_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_info_handler = logging.FileHandler(_info_log)
_info_handler.setLevel(logging.INFO)
_info_handler.setFormatter(_fmt)
_debug_handler = logging.FileHandler(_debug_log)
_debug_handler.setLevel(logging.DEBUG)
_debug_handler.setFormatter(_fmt)

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_info_handler)
_root_logger.addHandler(_debug_handler)

for _noisy_logger in ("httpx", "httpcore", "openai", "openai._base_client"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> int:
	if len(sys.argv) < 2:
		print("Usage: python test_diff_cli.py <composite_token>")
		return 1

	provided_token = sys.argv[1]

	thread_id = f"diff_cli_{uuid.uuid4().hex[:8]}"
	config = {"configurable": {"thread_id": thread_id}}
	logger.info("Diff Analyst CLI session started (thread_id=%s)", thread_id)
	logger.info("Log files: info=%s debug=%s", _info_log, _debug_log)

	required_env_vars = [
		"AZURE_OPENAI_URL",
		"AZURE_API_KEY",
		"AZURE_USER_ID",
		"AZURE_APP_NAME",
	]
	missing_env_vars = [var for var in required_env_vars if not os.environ.get(var)]

	if missing_env_vars:
		logger.error("Missing required environment variables: %s", missing_env_vars)
		print("Missing required environment variables:")
		for var in missing_env_vars:
			print(f"- {var}")
		return 1

	print("🚀 Triggering Diff Analyst Agent...")
	try:
		from lerai.diff_agent.graph import get_compiled_graph
	except Exception as exc:
		logger.error("Failed to import Diff Analyst graph: %s", exc, exc_info=True)
		print(f"\n❌ Error importing Diff Analyst graph: {exc}\n")
		return 1

	try:
		logger.info("Compiling Diff Analyst graph")
		graph = get_compiled_graph()
		logger.info("Invoking Diff Analyst graph")
		result = graph.invoke({"messages": [], "composite_token": provided_token}, config=config)
	except Exception as exc:
		logger.error("Error invoking Diff Analyst graph: %s", exc, exc_info=True)
		print(f"\n❌ Error invoking Diff Analyst graph: {exc}\n")
		return 1

	final_report = result.get("final_report", "No report generated.")
	logger.info(
		"Diff Analyst graph invocation completed (state_keys=%s, final_report_len=%d)",
		sorted(result.keys()),
		len(final_report),
	)

	print("\n" + "=" * 80)
	print(final_report)
	return 0


if __name__ == "__main__":
	sys.exit(main())
