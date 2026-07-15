from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from lerai.overrides_pipeline.conflict_detector import detect_conflicts, find_invalid_mapnames
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
        invalid_mapnames = find_invalid_mapnames(new_intent)
        warnings: list[str] = []
        if invalid_mapnames:
            warnings.append(
                "Invalid map name(s) provided: "
                + ", ".join(invalid_mapnames)
                + ". These map names are not present in lerai/data/maps.csv."
            )
        
        # Catch extraction errors before running detection
        if "error" in new_intent:
            message = new_intent["error"]
            if warnings:
                message = f"{message} Warning: {' '.join(warnings)}"
            return {
                "has_conflict": False,
                "message": message,
                "conflicts": [],
                "warnings": warnings,
                "invalid_mapnames": invalid_mapnames,
            }
            
        current_toml = _load_override_toml_read_only()

        if not current_toml:
            message = "override.toml was not found; conflict detection skipped."
            if warnings:
                message = f"{message} Warning: {' '.join(warnings)}"
            return {
                "has_conflict": False,
                "message": message,
                "conflicts": [],
                "warnings": warnings,
                "invalid_mapnames": invalid_mapnames,
            }

        # Call the upgraded semantic conflict detector
        found_conflicts = detect_conflicts(new_intent, current_toml)

        status_message = (
            f"Detected {len(found_conflicts)} potential conflict(s)."
            if found_conflicts
            else "No conflicts detected. Safe to proceed."
        )
        if warnings:
            status_message = f"{status_message} Warning: {' '.join(warnings)}"
        
        if found_conflicts:
            return {
                "has_conflict": True,
                "conflicts": found_conflicts,
                "message": status_message,
                "warnings": warnings,
                "invalid_mapnames": invalid_mapnames,
            }
        else:
            return {
                "has_conflict": False,
                "message": status_message,
                "conflicts": [],
                "warnings": warnings,
                "invalid_mapnames": invalid_mapnames,
            }

    except Exception as exc:
        return {
            "has_conflict": False,
            "message": f"Conflict detection failed: {exc}",
            "conflicts": [],
            "warnings": [],
            "invalid_mapnames": [],
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