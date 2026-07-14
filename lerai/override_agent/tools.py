from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from lerai.overrides_pipeline.conflict_detector import detect_conflicts
from lerai.overrides_pipeline.toml_generator import build_toml_string, validate_stanza
from lerai.overrides_pipeline.entity_extractor import extract_intent

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDE_TOML_PATH = PROJECT_ROOT / "override.toml"
OVERRIDE_SCHEMA_PATH = PROJECT_ROOT / "override_schema.json"


def _load_override_toml_read_only() -> str:
    """Reads override.toml in read-only mode; never writes to disk."""
    if not OVERRIDE_TOML_PATH.exists():
        return ""
    return OVERRIDE_TOML_PATH.read_text(encoding="utf-8")


def _load_override_schema() -> dict[str, Any]:
    with OVERRIDE_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@tool
def extract_override_intent(synthesized_request: str) -> str:
    """
    STEP 1 TOOL. ALWAYS use this tool FIRST. 
    You must pass a FULLY RESOLVED, context-rich natural language request here. 
    If the user provides a short follow-up (e.g., 'change it to 80%'), you MUST 
    synthesize it with the previous context (e.g., 'change quota to 80% for map w5 in region 50565') 
    before passing it to this tool.
    
    Returns a JSON string of the extracted LeROY intent.
    """
    try:
        intent_dict = extract_intent(synthesized_request)
        return json.dumps(intent_dict)
    except Exception as exc:
        return json.dumps({"error": f"Failed to extract intent: {exc}"})


@tool
def detect_override_conflicts(intent_json: str) -> dict[str, Any]:
    """
    STEP 2 TOOL. Pass the JSON string output from extract_override_intent here.
    Reads override.toml and detects if this new intent conflicts with live records.
    """
    try:
        new_intent = json.loads(intent_json)
        
        # Catch extraction errors before running detection
        if "error" in new_intent:
            return {"has_conflict": False, "message": new_intent["error"]}
            
        current_toml = _load_override_toml_read_only()

        if not current_toml:
            return {
                "has_conflict": False,
                "message": "override.toml was not found; conflict detection skipped.",
            }

        has_conflict, message, conflicting_records = detect_conflicts(new_intent, current_toml)
        return {
            "has_conflict": has_conflict,
            "message": message,
        }
    except Exception as exc:
        return {
            "has_conflict": False,
            "message": f"Conflict detection failed: {exc}",
        }


@tool
def generate_and_validate_toml(intent_json: str) -> dict[str, Any]:
    """
    STEP 3 TOOL. Pass the JSON string output from extract_override_intent here.
    Generates the final TOML code and validates it against the schema.
    Use this only after resolving any conflicts.
    """
    try:
        intent = json.loads(intent_json)
        
        if "error" in intent:
            return {"ok": False, "toml": "", "error": intent["error"]}
            
        toml_text = build_toml_string(intent)
        schema = _load_override_schema()
        validate_stanza(toml_text, schema)
        return {
            "ok": True,
            "toml": toml_text,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "toml": "",
            "error": str(exc),
        }


SUPERVISOR_TOOLS = [
    extract_override_intent,
    detect_override_conflicts,
    generate_and_validate_toml,
]