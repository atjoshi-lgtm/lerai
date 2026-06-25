import os
import subprocess
from typing import Optional

import urllib.request
import urllib.error
import sys
import os
import ssl
from openai_agent.openai_agent_client import chat_completion

BASE = os.environ.get("FOOTPRINT_API_BASE_URL")
cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")
CERT_ARG = (cert_path, key_path)
VERIFY_ARG = True


# ==============================
# Configuration
# ==============================

LOG_ERRORS_URL = os.environ.get("LOG_ERRORS_URL")

def fetch_log_errors_via_http(timeout=60) -> str:

    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    
    req = urllib.request.Request(
        LOG_ERRORS_URL,
        headers={
            "User-Agent": "log_error_summary/1.0",
            "Accept": "text/plain,*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
            # If your endpoint returns HTML, you may need to parse/strip.
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            return body
    except urllib.error.HTTPError as e:
        # e.code, e.read() often contain useful details
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP error {e.code} fetching log errors: {detail[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching log errors: {e}")

# ==============================
# OpenAI summarization
# ==============================

def summarize_log_errors(raw_log_output: str) -> str:
    """
    Given raw lines like:
      /path/file.log:[timestamp] ERROR - ...
    ask OpenAI to produce a concise summary.
    """
    if not raw_log_output.strip():
        return "No ERROR lines found in the last 12 hours for the specified DAG/task."

    # To avoid extremely long prompts, you could truncate here if needed.
    # For now, we'll send full content. If it gets too big, we can clip.
    prompt = (
        "You are analyzing Airflow log ERROR lines for a specific DAG.\n"
        "Each line typically has the format:\n"
        "[timestamp] {module:line} ERROR - message\n\n"
        "Please do the following:\n"
        "1. Group repeated errors and mention how many times they appear. In case of no data or invalid maprule inputs, show a list of which regions have this problem.\n"
        "3. Highlight which tasks/DAG attempts are failing.\n"
        "Here are the ERROR lines:\n\n"
        f"{raw_log_output}\n"
    )

    resp = chat_completion(
        messages=[
            {
                "role": "system",
                "content": "You are an SRE assistant summarizing Airflow errors for engineers.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
    )
    return resp["choices"][0]["message"]["content"].strip()


# ==============================
# High-level function
# ==============================

def get_airflow_error_summary () -> str:
    try:
        raw_logs = fetch_log_errors_via_http()
        summary = summarize_log_errors(raw_logs)
        return summary
    except Exception as e:
        raise RuntimeError(f"Error: {e}")

if __name__ == "__main__":
	print (get_airflow_error_summary())

