import ast
import json
import logging
from pathlib import Path
import os

from lerai.csv_env_diff import fetch_offline_prod_diff
from lerai.git_workspace import TransientGitWorkspace
from openai_agent.openai_agent_client import chat_completion

from .state import DiffAgentState
from .utils import process_all_diffs

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
ANALYST_SYSTEM_PROMPT = (_PROMPTS_DIR / "diff_analyst_system_prompt.txt").read_text(
	encoding="utf-8"
).strip()
logger = logging.getLogger(__name__)


def ingest_and_filter_node(state: DiffAgentState) -> dict:
	try:
		logger.info("Starting ingest_and_filter_node")
		workspace = TransientGitWorkspace()
		target_branch = os.environ.get("LEROY_PRODUCTION_GIT_BRANCH", "origin/master")
		try:
			toml_diff = workspace.get_diff_against_branch(target_branch=target_branch)
		except Exception:
			logger.warning("Falling back to HEAD-only diff extraction", exc_info=True)
			toml_diff = workspace.get_head_diff()
		toml_timestamps = workspace.get_override_file_timestamps(target_branch=target_branch)

		raw_response = fetch_offline_prod_diff()
		raw_response = json.loads(raw_response)

		if raw_response.get("returncode") != 0:
			raise RuntimeError(
				f"Diff script failed (returncode={raw_response.get('returncode')}) stderr: {raw_response.get('stderr', '').strip()}"
			)

		stdout = raw_response.get("stdout", "")
		stdout_dict = ast.literal_eval(stdout)

		token = stdout_dict.get("token", "")
		diffs = stdout_dict.get("diffs", {})
		blc_meta = diffs.get("blc.csv", {})
		if not isinstance(blc_meta, dict):
			blc_meta = {}

		toml_source = {
			"file": "override.toml",
			"repository": workspace.repo_url or "Unknown",
			"offline_branch": workspace.branch or "HEAD",
			"production_branch": target_branch,
		}
		csv_source = {
			"file": "blc.csv",
			"offline_repository": blc_meta.get("offline_repository")
			or blc_meta.get("offline_repo")
			or "Unknown",
			"offline_branch": blc_meta.get("offline_branch") or "Unknown",
			"production_repository": blc_meta.get("production_repository")
			or blc_meta.get("production_repo")
			or "Unknown",
			"production_branch": blc_meta.get("production_branch") or "Unknown",
		}
		csv_timestamps = {
			"offline": blc_meta.get("offline_last_modified", "Unknown"),
			"production": blc_meta.get("production_last_modified", "Unknown"),
		}
		filtered_changes = process_all_diffs(diffs)
		logger.info(
			"Ingestion complete (token_present=%s, diff_files=%d, toml_offline_ts=%s, toml_production_ts=%s, csv_offline_ts=%s, csv_production_ts=%s)",
			bool(token),
			len(filtered_changes),
			toml_timestamps.get("offline_last_modified", "Unknown"),
			toml_timestamps.get("production_last_modified", "Unknown"),
			csv_timestamps["offline"],
			csv_timestamps["production"],
		)

		return {
			"toml_diff": toml_diff,
			"raw_csv_diff_response": raw_response,
			"filtered_csv_changes": filtered_changes,
			"promotion_token": token,
			"source_context": {
				"toml": toml_source,
				"csv": csv_source,
			},
			"timestamps": {
				"toml": toml_timestamps,
				"csv": csv_timestamps,
			},
			"is_pipeline_healthy": True,
			"error_message": None,
		}
	except Exception as e:
		logger.error("ingest_and_filter_node failed: %s", e, exc_info=True)
		return {
			"toml_diff": "",
			"raw_csv_diff_response": {},
			"filtered_csv_changes": {},
			"promotion_token": "",
			"source_context": {"toml": {}, "csv": {}},
			"timestamps": {"toml": {}, "csv": {}},
			"is_pipeline_healthy": False,
			"error_message": str(e),
		}


def analyze_and_correlate_node(state: DiffAgentState) -> dict:
	if not state.get("is_pipeline_healthy"):
		logger.warning("Pipeline unhealthy; skipping LLM correlation")
		return {
			"final_report": f"⚠️ **Pipeline Validation Failed**\n\n```text\n{state.get('error_message')}\n```"
		}

	csv_changes = json.dumps(state["filtered_csv_changes"], indent=2)
	source_context = state.get("source_context", {})
	user_message = f"SOURCE CONTEXT:\n{json.dumps(source_context, indent=2)}\n\nTIMESTAMPS:\n{json.dumps(state.get('timestamps', {}), indent=2)}\n\nTOML DIFF:\n{state['toml_diff']}\n\nFILTERED CSV CHANGES:\n{csv_changes}"

	try:
		logger.info("Starting analyze_and_correlate_node")
		resp = chat_completion(
			messages=[
				{"role": "system", "content": ANALYST_SYSTEM_PROMPT},
				{"role": "user", "content": user_message},
			]
		)
		response_text = resp["choices"][0]["message"]["content"].strip()
		toml_source = source_context.get("toml", {}) if isinstance(source_context, dict) else {}
		csv_source = source_context.get("csv", {}) if isinstance(source_context, dict) else {}
		source_summary = (
			"## 🔎 Source Repositories\n"
			f"- TOML (`override.toml`): repo=`{toml_source.get('repository', 'Unknown')}`, "
			f"offline_branch=`{toml_source.get('offline_branch', 'Unknown')}`, "
			f"production_branch=`{toml_source.get('production_branch', 'Unknown')}`\n"
			f"- CSV (`{csv_source.get('file', 'blc.csv')}` metadata source): "
			f"offline_repo=`{csv_source.get('offline_repository', 'Unknown')}`, "
			f"offline_branch=`{csv_source.get('offline_branch', 'Unknown')}`, "
			f"production_repo=`{csv_source.get('production_repository', 'Unknown')}`, "
			f"production_branch=`{csv_source.get('production_branch', 'Unknown')}`"
		)
		response_text = f"{source_summary}\n\n{response_text}"
		token = state.get("promotion_token", "")
		if token:
			response_text += f"\n\n---\n**To promote this output, run:**\n`/promote @<approver_name> {token}`"
		logger.info("LLM correlation complete (report_len=%d)", len(response_text))
		return {"final_report": response_text}
	except Exception as e:
		logger.error("analyze_and_correlate_node failed: %s", e, exc_info=True)
		return {"final_report": f"⚠️ **LLM Analysis Failed**\n\n{str(e)}"}
