"""LangGraph nodes for diff_agent_v2."""

from __future__ import annotations

import json
import logging
import os
import shutil
import textwrap
import uuid
from pathlib import Path

from lerai.git_workspace import TransientGitWorkspace
from openai_agent.openai_agent_client import chat_completion

from .state import DiffAgentState
from .utils import (
    inject_geography,
    load_geography_mapping,
    QUOTA_THRESHOLD,
    load_map_translations,
    read_blc,
    read_fcs,
    split_structure_and_quota_diffs,
    translate_diff_maps,
)


logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "diff_analyst_v2_system_prompt.txt"


def _format_llm_messages_for_log(messages: list[dict]) -> str:
    """Return a readable, indented log representation of the LLM request."""
    formatted_blocks: list[str] = []
    for message in messages:
        role = message.get("role", "unknown")
        content = message.get("content")

        if isinstance(content, str):
            try:
                json_content = json.loads(content)
            except json.JSONDecodeError:
                json_content = None

            if isinstance(json_content, (dict, list)):
                rendered_content = json.dumps(json_content, indent=2, ensure_ascii=False)
            else:
                rendered_content = content
        else:
            rendered_content = json.dumps(content, indent=2, ensure_ascii=False)

        formatted_blocks.append(f"role: {role}\ncontent:\n{textwrap.indent(rendered_content, '  ')}")

    return "\n\n".join(formatted_blocks)


def ingest_and_diff_data(state: DiffAgentState) -> dict:
    """Clone required repos, compute diffs, and return state updates."""
    _ = state

    logger.info("Starting ingest_and_diff_data")

    config_repo_url = os.environ["LEROY_CONFIG_REPO_URL"]
    offline_csv_repo_url = os.environ["LEROY_OFFLINE_CSV_REPO_URL"]
    prod_csv_repo_url = os.environ["LEROY_PROD_CSV_REPO_URL"]
    git_ssh_key_path = os.environ["LEROY_GIT_SSH_KEY_PATH"]
    git_branch = os.environ["LEROY_GIT_BRANCH"]
    override_toml_relative_path = os.environ["LEROY_OVERRIDE_TOML_RELATIVE_PATH"]

    base_temp_dir = Path("/tmp/diff_agent_v2") / str(uuid.uuid4())
    config_repo_path = base_temp_dir / "config"
    offline_repo_path = base_temp_dir / "offline"
    prod_repo_path = base_temp_dir / "prod"

    try:
        logger.info("Initializing transient workspaces under %s", base_temp_dir)
        config_workspace = TransientGitWorkspace(
            repo_url=config_repo_url,
            local_path=config_repo_path,
            ssh_key_path=git_ssh_key_path,
            branch=git_branch,
        )
        offline_workspace = TransientGitWorkspace(
            repo_url=offline_csv_repo_url,
            local_path=offline_repo_path,
            ssh_key_path=git_ssh_key_path,
        )
        prod_workspace = TransientGitWorkspace(
            repo_url=prod_csv_repo_url,
            local_path=prod_repo_path,
            ssh_key_path=git_ssh_key_path,
        )

        logger.info("Cloning config, offline, and prod repositories")
        config_workspace.clone()
        offline_workspace.clone()
        prod_workspace.clone()

        logger.info("Extracting override.toml diff from config repo")
        override_toml_diff = config_workspace.get_diff_against_branch(
            file_path=override_toml_relative_path,
        )

        offline_blc = read_blc(offline_repo_path / "blc.csv")
        prod_blc = read_blc(prod_repo_path / "blc.csv")
        blc_structure_diffs, _ = split_structure_and_quota_diffs(
            offline_blc,
            prod_blc,
            "blc",
        )

        offline_fcs = read_fcs(offline_repo_path / "fcs.csv")
        prod_fcs = read_fcs(prod_repo_path / "fcs.csv")
        fcs_structure_diffs, fcs_quota_diffs = split_structure_and_quota_diffs(
            offline_fcs,
            prod_fcs,
            "fcs",
            QUOTA_THRESHOLD,
        )

        map_dict = load_map_translations(DATA_DIR)
        geo_dict = load_geography_mapping(DATA_DIR)
        translate_diff_maps(blc_structure_diffs, map_dict, "item")
        translate_diff_maps(fcs_structure_diffs, map_dict, "item")
        translate_diff_maps(fcs_quota_diffs, map_dict, "map_identifier")
        inject_geography(blc_structure_diffs, geo_dict)
        inject_geography(fcs_structure_diffs, geo_dict)
        inject_geography(fcs_quota_diffs, geo_dict)

        logger.info(
            "ingest_and_diff_data complete (override_diff_len=%d, blc_structure=%d, fcs_structure=%d, fcs_quota=%d)",
            len(override_toml_diff),
            len(blc_structure_diffs),
            len(fcs_structure_diffs),
            len(fcs_quota_diffs),
        )

        return {
            "override_toml_diff": override_toml_diff,
            "blc_structure_diffs": blc_structure_diffs,
            "fcs_structure_diffs": fcs_structure_diffs,
            "fcs_quota_diffs": fcs_quota_diffs,
        }
    except Exception as e:
        logger.error("ingest_and_diff_data failed: %s", e, exc_info=True)
        raise
    finally:
        logger.info("Cleaning up transient workspace: %s", base_temp_dir)
        shutil.rmtree(base_temp_dir, ignore_errors=True)


def analyze_and_correlate(state: DiffAgentState) -> dict:
    """Generate final report by correlating all diff artifacts with the LLM."""
    logger.info("Starting analyze_and_correlate")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    user_payload = {
        "override_toml_diff": state.get("override_toml_diff", ""),
        "blc_structure_diffs": state.get("blc_structure_diffs", []),
        "fcs_structure_diffs": state.get("fcs_structure_diffs", []),
        "fcs_quota_diffs": state.get("fcs_quota_diffs", []),
    }
    user_payload_str = json.dumps(user_payload, indent=2)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload_str},
    ]

    logger.info("LLM payload:\n%s", _format_llm_messages_for_log(messages))
    response = chat_completion(messages=messages, temperature=0.0)
    report_text = ""
    try:
        report_text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.error("Unexpected chat_completion response shape: %s", response)

    logger.info("analyze_and_correlate complete (report_len=%d)", len(report_text))
    return {"final_report": report_text}
