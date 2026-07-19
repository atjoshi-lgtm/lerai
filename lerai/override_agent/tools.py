from __future__ import annotations

import csv
import json
import pathlib
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from lerai.override_agent.knowledge_base import search_leroy_knowledge_base
from lerai.overrides_pipeline.conflict_detector import detect_conflicts, find_invalid_mapnames
from lerai.overrides_pipeline.toml_generator import build_toml_string, validate_stanza
from lerai.overrides_pipeline.entity_extractor import extract_intent

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = pathlib.Path(PROJECT_ROOT) / "lerai" / "data"
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


@tool
def search_leroy_documentation(query: str) -> str:
    """Use this tool to search the LeRoy manuals when the user asks a conceptual question about override directives, safety rules, architecture, constraints, or configurations.
    IMPORTANT: Provide short, natural language questions for your query (e.g., 'What is the maximum allowed value for Quota-pct?') rather than a list of keywords."""
    return search_leroy_knowledge_base(query)


@tool
def lookup_infrastructure_data(search_type: str, value: str) -> str:
    """Use this tool to look up exact infrastructure mappings. 
    Valid search_types are: 'map' (to check if a map shortname exists), 'region' (to find metros for a region ID), and 'metro' (to find region IDs for a metro)."""
    kind = (search_type or "").strip().lower()
    needle = (value or "").strip()

    if kind not in {"map", "region", "metro"}:
        return "Invalid search_type. Use one of: map, region, metro."

    if not needle:
        return "Please provide a non-empty value to search."

    try:
        if kind == "map":
            maps_path = DATA_DIR / "maps.csv"
            with maps_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    shortname = (row.get("shortname") or "").strip().lower()
                    if shortname == needle.lower():
                        return f"Map '{needle}' is a valid mapname."
            return f"Map '{needle}' not found."

        metro_region_path = DATA_DIR / "metro_region.csv"
        with metro_region_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if kind == "region":
                metros: list[str] = []
                for row in reader:
                    region = (row.get("region") or "").strip()
                    metro = (row.get("metro") or row.get("metro_area") or "").strip()
                    if region == needle and metro and metro not in metros:
                        metros.append(metro)

                if not metros:
                    return f"No metros found for region '{needle}'."
                return f"Region '{needle}' maps to metros: {', '.join(metros)}."

            regions: list[str] = []
            for row in reader:
                metro = (row.get("metro") or row.get("metro_area") or "").strip()
                region = (row.get("region") or "").strip()
                if metro.lower() == needle.lower() and region and region not in regions:
                    regions.append(region)

            if not regions:
                return f"No regions found for metro '{needle}'."
            return f"Metro '{needle}' maps to regions: {', '.join(regions)}."

    except Exception as exc:
        return f"Infrastructure lookup is currently unavailable: {exc}"


SUPERVISOR_TOOLS = [
    extract_override_intent,
    detect_override_conflicts,
    generate_and_validate_toml,
    search_leroy_documentation,
    lookup_infrastructure_data,
]