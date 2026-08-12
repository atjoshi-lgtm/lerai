#!/usr/bin/env python3
"""Local CLI harness to unit-test diff_agent_v2 ingest node behavior."""

from __future__ import annotations

from datetime import datetime
import logging
import os
import sys

os.makedirs("logs/test_diffv2_cli", exist_ok=True)
_log_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_info_log = os.path.join("logs/test_diffv2_cli", f"diffv2_agent_{_log_ts}.log")
_debug_log = os.path.join("logs/test_diffv2_cli", f"diffv2_agent_{_log_ts}.debug.log")

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
    logger.info("Diff v2 ingest CLI session started")
    logger.info("Log files: info=%s debug=%s", _info_log, _debug_log)

    required_env_vars = [
        "LEROY_CONFIG_REPO_URL",
        "LEROY_OFFLINE_CSV_REPO_URL",
        "LEROY_PROD_CSV_REPO_URL",
        "LEROY_GIT_SSH_KEY_PATH",
        "LEROY_GIT_BRANCH",
        "LEROY_OVERRIDE_TOML_RELATIVE_PATH",
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

    try:
        from lerai.diff_agent_v2.graph import get_compiled_graph
        from lerai.diff_agent_v2.state import DiffAgentState
    except Exception as exc:
        logger.error("Failed to import diff_agent_v2 symbols: %s", exc, exc_info=True)
        print(f"\nError importing diff_agent_v2 symbols: {exc}\n")
        return 1

    state: DiffAgentState = {
        "messages": [],
        "blc_structure_diffs": [],
        "fcs_structure_diffs": [],
        "fcs_quota_diffs": [],
        "override_toml_diff": "",
        "final_report": "",
    }

    try:
        logger.info("Compiling diff_agent_v2 graph")
        graph = get_compiled_graph()
        logger.info("Invoking diff_agent_v2 graph")
        result = graph.invoke(state)
    except Exception as exc:
        logger.error("Error invoking diff_agent_v2 graph: %s", exc, exc_info=True)
        print(f"\nError invoking diff_agent_v2 graph: {exc}\n")
        return 1

    final_report = result.get("final_report", "No report generated.")

    logger.info(
        "diff_agent_v2 graph invocation completed (state_keys=%s, final_report_len=%d)",
        sorted(result.keys()),
        len(final_report),
    )

    print("=" * 80)
    print(final_report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
