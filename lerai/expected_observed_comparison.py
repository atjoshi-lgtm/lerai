#!/usr/bin/env python3
"""
expected_observed_comparison.py

- Reads expected CSV: region,map,offload_expected
- Reads observed CSV: region,map,offload,gbps
- Outer joins on (region,map)
- Filters rows: gbps > 10 AND (offload/offload_expected) < 0.9
- Writes joined CSV and prints a bullet summary by map
"""

import os
import sys
import csv
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import urllib.request
import urllib.error
import ssl
import logging
from openai_agent.openai_agent_client import responses
from openai_agent.openai_agent_client import chat_completion
from lerai.logging_utils import redact_value


logger = logging.getLogger(__name__)


BASE = os.environ.get("FOOTPRINT_API_BASE_URL")
cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")
CERT_ARG = (cert_path, key_path)
VERIFY_ARG = True


ExpectedRow = Tuple[str, str, Optional[float]]              # (region, map, expected_offload)
ObservedRow = Tuple[str, str, Optional[float], Optional[float]]  # (region, map, observed_offload, gbps)
JoinedRow = Tuple[str, str, Optional[float], Optional[float], Optional[float]]  # (region, map, expected, observed, gbps)

EXPECTED_OBSERVED_URL = os.environ.get("EXPECTED_OBSERVED_URL")

PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")

def fetch_expected_observed_via_http(timeout=60) -> str:
    
    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    req = urllib.request.Request(
        EXPECTED_OBSERVED_URL,
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
            #print ("expected-observed-diff is")
            #print (body)
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
def ask_chatgpt_to_summarize_expected_observed_diff(s: str) -> str:
    if not s.strip():
        return "Empty diff found."

    prompt1 = load_prompt("expected_observed_summary_prompt.txt")
    prompt = f"{prompt1}:\n\n{s}\n"

#    print ("prompt is")
#    print (prompt)
    try:
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
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")


def run_offload_analysis_workflow(): 
    logger.info("Fetching expected-observed data")
    x = fetch_expected_observed_via_http()
    logger.info("Summarizing expected-observed data with LLM")
    return ask_chatgpt_to_summarize_expected_observed_diff(x)



if __name__ == "__main__":
    logger.info("Manual expected-observed summary generated", extra={"summary": redact_value(run_offload_analysis_workflow())}) 
