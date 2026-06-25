#!/usr/bin/env python3
"""
leroy_overrides_writer.py
- Sends overrides schema and ticket description to chatgpt and asks to write an overrides stanza
"""

import os
import sys
import csv
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import json

from openai_agent.openai_agent_client import responses


PROMPTS_DIR = Path(__file__).parent / "prompts"


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
    with open("override_schema.json", "r") as f:
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

    print ("******* prompt ********")
    print (prompt)
    print ("******* prompt ********")
    msg = [{"role": "user", "content": prompt}]
    r = responses(
        messages=msg,
        model="gpt-5.2",
        temperature=0,
    )
    
    resp = r['choices'][0]['message']['content']
    if "output_text" in resp:
        return resp["output_text"]
    elif "stdout" in resp:
        return resp["stdout"]
    else:
        return str(resp)

def write_toml (userquestion: str = ""): 
    schema = load_schema()
    ret = ask_chatgpt_to_write_overrides (schema, userquestion)
    return ret


if __name__ == "__main__":

    x = write_toml("I'd like to remove mm2 from all the US large regions")
    print (x)
