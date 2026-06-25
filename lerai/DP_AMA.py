#!/usr/bin/env python3
"""
DP_AMA.py

- Reads from netarch DB the details of all the DPs for LRs. 
- Sends user question and the DP details to chatgpt to answer. 
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

from netarch_queries import query_LR_DP
from mysql_client import run_mysql_query

from openai_agent.openai_agent_client import responses

global dplist_save


PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")

def ask_chatgpt_to_summarize_dps(dpinfo: str, userquetion: str = "") -> str:
    
    defaultprompt = "dp_default_prompt.txt"
    userprompt = "dp_user_prompt.txt"
    prompt_tail = "dp_prompt_tail.txt"

    if not userquetion or not userquetion.strip():
        prompt = load_prompt(defaultprompt)
    else:
        prompt = load_prompt(userprompt)
        prompt += "\n"
        prompt += userquetion 
        prompt += "\n"

    prompt_tail = load_prompt(prompt_tail)
    prompt = prompt + dpinfo + prompt_tail

    msg = [{"role": "user", "content": prompt}]
    r = responses(
        messages=msg,
        model="gpt-4.1",
        temperature=0,
    )
    
    resp = r['choices'][0]['message']['content']
    if "output_text" in resp:
        return resp["output_text"]
    elif "stdout" in resp:
        return resp["stdout"]
    else:
        return str(resp)

def ask_chatgpt_to_create_candidate_answer(dpinfo: str, userquetion: str = "") -> str:
    
    defaultpromptfile = "dp_proof_prompt.txt"
    prompt_tail = "dp_proof_tail_prompt.txt"

    prompt = load_prompt(defaultpromptfile)
    prompt += "\n"
    prompt += userquetion 
    prompt += "\n"
    prompt_tail = load_prompt(prompt_tail)
    prompt = prompt + dpinfo + prompt_tail

    msg = [{"role": "user", "content": prompt}]
    r = responses(
        messages=msg,
        model="gpt-4.1",
        temperature=0,
    )
    resp = r['choices'][0]['message']['content']
    if "output_text" in resp:
        return resp["output_text"]
    elif "stdout" in resp:
        return resp["stdout"]
    else:
        return str(resp)

def ask_chatgpt_to_verify_candidate_answer(dpinfo: str, userquetion: str = "", candidate_answer: str = "") -> str:
    
    defaultpromptfile = "dp_proof_check_prompt.txt"
    prompt_tail = "dp_proof_check_tail_prompt.txt"

    prompt_tail = load_prompt(prompt_tail)
    prompt = load_prompt(defaultpromptfile)
    prompt += "\n\n\nThe question that was asked:\n"
    prompt += userquetion 
    prompt += "\n\n\nThe candidate answer and its proof that you gave:\n"
    prompt += candidate_answer
    prompt += "\n\n\nThe input data that was provided:\n"
    prompt += dpinfo 
    prompt += prompt_tail

    msg = [{"role": "user", "content": prompt}]
    r = responses(
        messages=msg,
        model="gpt-4.1",
        temperature=0,
    )
    resp = r['choices'][0]['message']['content']
    if "output_text" in resp:
        return resp["output_text"]
    elif "stdout" in resp:
        return resp["stdout"]
    else:
        return str(resp)


def summarize_dps (userquestion: str = ""): 
    global dplist_save
    dplist_save = run_mysql_query(query_LR_DP)
    return ask_chatgpt_to_summarize_dps(dplist_save,userquestion)

def create_dp_candiate_answer(userquestion: str = ""):
    global dplist_save
    dplist_save = run_mysql_query(query_LR_DP)
    return ask_chatgpt_to_create_candidate_answer(dplist_save,userquestion)

def verify_dp_candiate_answer(userquestion: str, candidate_answer: str):
    #return "Skipping verification"
    global dplist_save
    return ask_chatgpt_to_verify_candidate_answer(dplist_save,userquestion,candidate_answer)


if __name__ == "__main__":
    #print(summarize_dps( "which ecors have active LR DPs?")) 
    question = "give me statistics of days in different status across all the DPs"
    ca = create_dp_candiate_answer(question)
    ver = verify_dp_candiate_answer(question, ca)

    print (ca)
    print ("----- Verification ----")
    print (ver)
