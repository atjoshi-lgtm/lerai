#!/usr/bin/env python3
"""
leroy_overrides_writer.py
- Sends overrides schema and ticket description to chatgpt and asks to write an overrides stanza
"""

import os
import sys
import argparse
import csv
import re
import tempfile
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai_agent.openai_agent_client import responses
from lerai.logging_utils import redact_value


PROMPTS_DIR = Path(__file__).parent / "prompts"
logger = logging.getLogger(__name__)


webex_thread_chatgpt_history = {}


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def load_schema() -> str:
    # folder = dataiku.Folder("jh542TwD")
    # with folder.get_download_stream("override_schema.json") as f:
    #     schema_text = f.read()
    #     if isinstance(schema_text, bytes):
    #         schema_text = schema_text.decode("utf-8")
    # return schema_text
    with open(PROJECT_ROOT / "override_schema.json", "r", encoding="utf-8") as f:
        schema_text = f.read()
    return schema_text

#        schema = json.loads(f.read())
#        return schema

def ask_chatgpt_to_write_overrides(schema: str, userquetion: str) -> str:
    
    defaultprompt = "leroy_overrides_writer_prompt.txt"
    prompt = load_prompt(defaultprompt)
    prompt += "\nThe toml schema is:\n"
    prompt += schema 
    prompt += "\nThe ticket description is:\n"
    prompt += userquetion 
    prompt += "\n"

    logger.debug("Override writer prompt built", extra={"prompt": redact_value(prompt)})
    msg = [{"role": "user", "content": prompt}]
    r = responses(
        messages=msg,
        model="gpt-5.2",
        temperature=0,
    )

    resp = r["choices"][0]["message"]["content"]
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        if "output_text" in resp:
            return str(resp["output_text"])
        if "stdout" in resp:
            return str(resp["stdout"])
    return str(resp)

def write_toml (userquestion: str = ""): 
    schema = load_schema()
    ret = ask_chatgpt_to_write_overrides (schema, userquestion)
    return ret


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Leroy override TOML stanza")
    parser.add_argument(
        "user_question",
        nargs="?",
        default="I'd like to remove mm2 from all the US large regions",
        help="Ticket/request description to convert into a TOML override stanza",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    try:
        x = write_toml(args.user_question)
        print(x)
        logger.info("Manual override writer output generated", extra={"output": redact_value(x)})
    except Exception as exc:
        logger.error("Manual override writer run failed", extra={"error": redact_value(str(exc))})
        print(f"Error running leroy_overrides_writer: {exc}", file=sys.stderr)
        sys.exit(1)
