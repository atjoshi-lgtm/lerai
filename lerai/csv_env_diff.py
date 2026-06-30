import os
import sys
import csv
import shutil
import difflib
import tempfile
import subprocess
import datetime
import json
import urllib.request
import urllib.error
import ssl
import logging
from pathlib import Path
from openai_agent.openai_agent_client import responses
from openai_agent.openai_agent_client import chat_completion
from lerai.logging_utils import redact_value


logger = logging.getLogger(__name__)

BASE = os.environ.get("FOOTPRINT_API_BASE_URL")
cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")
CERT_ARG = (cert_path, key_path)
VERIFY_ARG = True

PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


OFFLINE_PROD_DIFF_ERRORS_URL = os.environ.get("OFFLINE_PROD_DIFF_ERRORS_URL")

def fetch_offline_prod_diff(timeout=30) -> str:
    
    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    req = urllib.request.Request(
        OFFLINE_PROD_DIFF_ERRORS_URL,
        headers={
            "User-Agent": "LeRAI/1.0",
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
# OpenAI summarization helper
# ==============================
def summarize_diff_with_openai(file_diffs):
    """
    file_diffs: dict {filename: diff_text}
    Returns a combined natural-language summary from OpenAI.
    """

    parts = []
    prompt1 = load_prompt("offline_prod_prompt.txt")
    parts.append(prompt1)    
    parts.append(file_diffs)    
    prompt = "\n".join(parts)

    try:

        resp = chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are an SRE assistant summarizing csv file diffs.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")



# ==============================
# High-level entry point
# ==============================
def compare_offline_vs_production(check_staleness_only=False, stale_hours=36):
    raw = fetch_offline_prod_diff()
    try:
        response = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse diff response as JSON: {e}\nRaw: {raw[:200]}")
    
    if response.get("returncode") != 0:
        raise RuntimeError(
            f"Diff script failed (returncode={response['returncode']})\n"
            f"stderr: {response.get('stderr', '').strip()}"
        )
    
    stderr = response.get("stderr", "").strip()
    if stderr:
        logger.warning("Diff script returned stderr", extra={"stderr": redact_value(stderr)})
    
    stdout = response.get("stdout", "")
    if not stdout.strip():
        raise RuntimeError("Diff script returned empty output")

    #print (stdout)
    return summarize_diff_with_openai(stdout)
    

# ==============================
# Optional: CLI usage for testing
# ==============================

if __name__ == "__main__":
    """
    Simple CLI test:
    - Ensure your SSH agent is running and has the Bitbucket key loaded:
        eval "$(ssh-agent -s)"
        ssh-add /path/to/your/key
    - Ensure OPENAI_API_KEY is set.
    - Run: python csv_env_diff.py
    """
    try:
        result = compare_offline_vs_production()
        logger.info("Diff summary generated", extra={"summary": redact_value(result)})
    except Exception as e:
        logger.exception("CSV diff CLI error")
