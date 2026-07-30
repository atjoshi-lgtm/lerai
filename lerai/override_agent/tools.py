from __future__ import annotations

import csv
import json
import pathlib
from pathlib import Path
from typing import Any

import tomlkit
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt

from lerai.override_agent.knowledge_base import search_leroy_knowledge_base
from lerai.git_workspace import TransientGitWorkspace
from lerai.overrides_pipeline.conflict_detector import detect_conflicts, find_invalid_mapnames
from lerai.overrides_pipeline.toml_generator import (
    build_toml_string,
    execute_ast_update,
    validate_stanza,
)
from lerai.overrides_pipeline.entity_extractor import extract_intent

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PROJECT_ROOT = PROJECT_ROOT
DATA_DIR = pathlib.Path(PROJECT_ROOT) / "lerai" / "data"
OVERRIDE_SCHEMA_PATH = PROJECT_ROOT / "override_schema.json"
SCHEMA_PATH = _PROJECT_ROOT / "lerai" / "prompts" / "leroy_override_entity_extractor_tool.json"


def _load_override_toml_read_only(workspace_path: str) -> str:
    """Reads override.toml in read-only mode; never writes to disk."""
    if not workspace_path:
        raise ValueError("workspace_path is required but was not provided.")

    toml_path = Path(workspace_path) / "override.toml"
    if not toml_path.exists():
        raise FileNotFoundError(
            f"override.toml not found in cloned workspace: {workspace_path}"
        )
    return toml_path.read_text(encoding="utf-8")


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
def detect_override_conflicts(intent_json: str, config: RunnableConfig) -> dict[str, Any]:
    """
    STEP 3 TOOL. Pass the JSON string output from extract_override_intent here.
    Reads override.toml and detects if this new intent conflicts with live records.
    """
    try:
        workspace_path = config.get("configurable", {}).get("workspace_path")
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
            
        current_toml = _load_override_toml_read_only(workspace_path)

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
    STEP 2 TOOL. Pass the JSON string output from extract_override_intent here.
    Generates the final TOML code and validates it against the schema.
    Run this before conflict detection so the full draft is available at approval time.
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
def lookup_infrastructure_data(target_output: str, source_value: str) -> str:
    """Use this tool to look up infrastructure mappings via a flat in-memory table.
    - target_output: What you want to find (must be one of: 'geos', 'countries', 'metros', 'regions').
    - source_value: One or more known entities, comma-separated (e.g., 'France, FR, LAX')."""
    def normalize(s: str) -> str:
        return (s or "").strip().lower().replace(" ", "_")

    def load_csv_rows(file_name: str) -> list[dict[str, str]]:
        csv_path = DATA_DIR / file_name
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    kind = normalize(target_output)
    if kind not in {"geos", "countries", "metros", "regions"}:
        return "Invalid target_output. Use one of: geos, countries, metros, regions."

    # Lightweight country aliases for common natural-language inputs.
    country_aliases = {
        "france": "fr",
        "united_states": "us",
        "united_states_of_america": "us",
        "usa": "us",
        "uk": "gb",
        "united_kingdom": "gb",
        "great_britain": "gb",
        "germany": "de",
        "spain": "es",
        "italy": "it",
        "canada": "ca",
        "australia": "au",
        "india": "in",
        "japan": "jp",
        "china": "cn",
        "brazil": "br",
    }

    source_items = [(part or "").strip() for part in (source_value or "").split(",")]
    valid_source_items = [item for item in source_items if item]
    if not valid_source_items:
        return "Please provide a non-empty source_value to search."

    try:
        geo_country_rows = load_csv_rows("geo_country.csv")
        country_metro_rows = load_csv_rows("country_metro.csv")
        metro_region_rows = load_csv_rows("metro_region.csv")

        geos_by_country: dict[str, list[str]] = {}
        for row in geo_country_rows:
            country = (row.get("country") or "").strip()
            geo = (row.get("geo") or "").strip()
            if not country:
                continue
            geos_by_country.setdefault(country, [])
            if geo and geo not in geos_by_country[country]:
                geos_by_country[country].append(geo)

        metros_by_country: dict[str, list[dict[str, str]]] = {}
        for row in country_metro_rows:
            country = (row.get("country") or "").strip()
            if not country:
                continue
            metro_entry = {
                "metro_area": (row.get("metro_area") or "").strip(),
                "airport_code": (row.get("airport_code") or "").strip(),
            }
            metros_by_country.setdefault(country, []).append(metro_entry)

        regions_by_metro: dict[str, list[str]] = {}
        for row in metro_region_rows:
            metro = (row.get("metro_area") or row.get("metro") or "").strip()
            region = (row.get("region") or "").strip()
            if not metro:
                continue
            regions_by_metro.setdefault(metro, [])
            if region and region not in regions_by_metro[metro]:
                regions_by_metro[metro].append(region)

        all_countries = set(geos_by_country.keys()) | set(metros_by_country.keys())

        flat_table: list[dict[str, str]] = []
        for country in all_countries:
            country_geos = geos_by_country.get(country, [""]) or [""]
            country_metros = metros_by_country.get(country, [{"metro_area": "", "airport_code": ""}])

            for geo in country_geos:
                for metro_entry in country_metros:
                    metro_area = metro_entry.get("metro_area", "")
                    airport_code = metro_entry.get("airport_code", "")
                    metro_regions = regions_by_metro.get(metro_area, [""]) if metro_area else [""]

                    for region in metro_regions:
                        flat_table.append(
                            {
                                "geo": geo,
                                "country": country,
                                "metro_area": metro_area,
                                "airport_code": airport_code,
                                "region": region,
                            }
                        )

        target_column = {
            "geos": "geo",
            "countries": "country",
            "metros": "metro_area",
            "regions": "region",
        }[kind]

        formatted_results: list[str] = []
        for raw_item in valid_source_items:
            normalized_item = normalize(raw_item)
            resolved_item = country_aliases.get(normalized_item, normalized_item)

            item_results: set[str] = set()
            for row in flat_table:
                searchable_values = {
                    normalize(row.get("geo", "")),
                    normalize(row.get("country", "")),
                    normalize(row.get("metro_area", "")),
                    normalize(row.get("airport_code", "")),
                    normalize(row.get("region", "")),
                }
                if resolved_item in searchable_values:
                    target_value = (row.get(target_column) or "").strip()
                    if target_value:
                        item_results.add(target_value)

            if item_results:
                sorted_results = sorted(item_results)
                formatted_results.append(f"{raw_item} -> {', '.join(sorted_results)}")
            else:
                formatted_results.append(f"{raw_item} -> No mapping found")

        return "\n".join(formatted_results)

    except Exception as exc:
        return f"Infrastructure lookup is currently unavailable: {exc}"


@tool
def get_unique_infrastructure_values(entity_type: str) -> str:
    """Use this tool to get a comprehensive list of all active entity types in the LeROY network. Valid entity_types are 'geos', 'countries', and 'metros'. Use this to discover what data actually exists before attempting to filter or group them."""
    kind = (entity_type or "").strip().lower()
    if kind not in {"geos", "countries", "metros"}:
        return "Invalid entity_type. Use one of: geos, countries, metros."

    try:
        if kind in {"geos", "countries"}:
            file_path = DATA_DIR / "geo_country.csv"
            with file_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                column = "geo" if kind == "geos" else "country"
                values = sorted(
                    {
                        (row.get(column) or "").strip()
                        for row in reader
                        if (row.get(column) or "").strip()
                    }
                )
            return ", ".join(values) if values else f"No {kind} found."

        file_path = DATA_DIR / "country_metro.csv"
        with file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            values = sorted(
                {
                    (row.get("metro_area") or "").strip()
                    for row in reader
                    if (row.get("metro_area") or "").strip()
                }
            )
        return ", ".join(values) if values else "No metros found."
    except Exception as exc:
        return f"Failed to load infrastructure values: {exc}"


@tool
def lookup_directive_schema(directive_name: str) -> str:
    """Use this tool to find the exact structural limitations, allowed enum values, data types, and min/max bounds for a specific override directive (e.g., 'Quota-pct', 'Access-control'). Do NOT guess constraints; use this tool."""
    name = (directive_name or "").strip()
    if not name:
        return "Please provide a non-empty directive_name."

    try:
        with SCHEMA_PATH.open("r", encoding="utf-8") as f:
            schema = json.load(f)

        directives = (
            schema.get("parameters", {})
            .get("properties", {})
            .get("Override-Directive", {})
            .get("properties", {})
        )

        if not isinstance(directives, dict):
            return "Directive schema structure is invalid or missing 'Override-Directive.properties'."

        lower_to_actual = {str(key).lower(): key for key in directives.keys()}
        matched_key = lower_to_actual.get(name.lower())
        if not matched_key:
            return f"Directive '{directive_name}' does not exist in the schema."

        return json.dumps(directives[matched_key], indent=2)
    except Exception as exc:
        return f"Failed to load directive schema: {exc}"


def _load_conflict_rules() -> dict[str, Any]:
    """Loads the LeROY override conflict rules JSON from the prompts directory."""
    rules_path = _PROJECT_ROOT / "lerai" / "prompts" / "leroy_override_conflict_rules.json"
    with rules_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@tool
def apply_override_to_workspace(
    new_intents_json: str, target_intents_json: str, config: RunnableConfig
) -> dict[str, Any]:
    """
    STEP 6 TOOL. Use this tool ONLY after the user explicitly approves the deployment of the override.
    Reads the live override.toml from the workspace, nukes any target records, appends one or more
    new intents, and saves the file back to disk.

    `new_intents_json` accepts either:
    - A single JSON object (backward-compatible), or
    - A JSON list of objects for multi-stanza append.
    """
    def _flatten_intent(intent: dict[str, Any]) -> dict[str, Any]:
        """Flattens nested JSON payloads into a flat dictionary for TOML."""
        flat = {}
        for k, v in intent.items():
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    flat[sub_k] = sub_v
            else:
                flat[k] = v
        return flat

    def _parse_payload(payload_str: str) -> list[dict[str, Any]]:
        """
        Robustly parses a payload string that may be JSON or TOML, with optional Markdown wrapping.
        
        Returns:
            list[dict[str, Any]]: A list of parsed records.
            
        Raises:
            ValueError: If the payload cannot be parsed as JSON or TOML.
        """
        # Handle empty or None payloads
        if not payload_str or not payload_str.strip():
            return []
        
        # Strip Markdown code block wrappers
        cleaned = payload_str.strip()
        lines = cleaned.split('\n')
        
        # Remove opening code block marker (e.g., ```json, ```toml, ```)
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        
        # Remove closing code block marker
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        
        cleaned = '\n'.join(lines).strip()
        
        if not cleaned:
            return []
        
        # Try parsing as JSON first
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return [parsed]
            elif isinstance(parsed, list):
                return parsed
            else:
                raise ValueError(
                    f"Expected JSON object or array, got {type(parsed).__name__}"
                )
        except json.JSONDecodeError:
            pass
        
        # Fall back to TOML parsing
        try:
            doc = tomlkit.parse(cleaned)
            if "override-records" not in doc:
                raise ValueError(
                    "TOML payload missing required 'override-records' key"
                )
            
            records = doc["override-records"]
            if not isinstance(records, list):
                raise ValueError(
                    f"Expected 'override-records' to be an array, got {type(records).__name__}"
                )
            
            # Convert tomlkit objects to standard Python dicts
            result = []
            for record in records:
                if hasattr(record, 'items'):
                    result.append(dict(record))
                else:
                    result.append(record)
            return result
        except Exception as toml_exc:
            raise ValueError(
                f"Failed to parse payload as JSON or TOML: {toml_exc}"
            )

    try:
        raw_new_intents = _parse_payload(new_intents_json)
        
        # FIX 1: ONLY flatten the new intents so they don't write as nested TOML
        new_intents = [_flatten_intent(intent) for intent in raw_new_intents]

        raw_target_intents = _parse_payload(target_intents_json)

        # FIX 2: Apply _flatten_intent() to extracted items before appending
        target_intents = []
        for item in raw_target_intents:
            if isinstance(item, dict) and "record" in item:
                extracted = item["record"]
            else:
                extracted = item
            target_intents.append(_flatten_intent(extracted))

        workspace_path = config.get("configurable", {}).get("workspace_path")
        if not workspace_path or not Path(workspace_path).is_dir():
            raise ValueError(
                f"Invalid or missing workspace_path: {workspace_path!r}"
            )

        toml_path = Path(workspace_path) / "override.toml"
        if not toml_path.exists():
            raise FileNotFoundError(
                f"override.toml not found in workspace: {workspace_path}"
            )

        doc = tomlkit.parse(toml_path.read_text(encoding="utf-8"))
        conflict_rules = _load_conflict_rules()

        doc = execute_ast_update(doc, target_intents, new_intents, conflict_rules)

        toml_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

        return {
            "ok": True,
            "message": "Successfully applied updates to workspace override.toml.",
        }
    except Exception as exc:
        return {"ok": False, "error": f"Failed to apply overrides to disk: {exc}"}


@tool
def commit_and_push_workspace(
    ticket_id: str, commit_message: str, config: RunnableConfig
) -> dict[str, Any]:
    """
    STEP 7 TOOL. Use this tool ONLY after successfully applying the override to the workspace.
    Commits the file changes and pushes them to the remote repository.
    """
    try:
        workspace_path = config.get("configurable", {}).get("workspace_path")
        if not workspace_path or not Path(workspace_path).is_dir():
            raise ValueError(
                f"Invalid or missing workspace_path: {workspace_path!r}"
            )

        workspace = TransientGitWorkspace(local_path=workspace_path)
        workspace.commit(
            user_name="LeRAI Bot",
            user_email="lerai-bot@akamai.com",
            ticket_id=ticket_id,
            commit_message=commit_message,
        )
        git_diff = workspace.get_head_diff()
        workspace.push()

        return {
            "ok": True,
            "message": "Successfully committed and pushed changes to remote repository.",
            "diff": git_diff,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Failed to commit and push: {exc}"}


@tool
def request_deployment_approval(stanzas_to_add: str, stanzas_to_delete: str, message: str = "") -> str:
    """
    STEP 4 TOOL. You MUST use this tool after you finish drafting the TOML and resolving conflicts,
    and BEFORE you call apply_override_to_workspace.
    It shows the user the exact changes and pauses execution to wait for their approval or feedback.
    Use the `message` parameter to pass any warnings, conflict notes, or questions to the user.
    """
    parts: list[str] = []

    if message and message.strip():
        parts.append(f"### 💬 Agent Message:\n{message}\n")

    if stanzas_to_delete and stanzas_to_delete.strip():
        parts.append(
            f"### 🚨 To Be Deleted (Nuked):\n```toml\n{stanzas_to_delete}\n```\n"
        )

    parts.append(f"### 🆕 To Be Added:\n```toml\n{stanzas_to_add}\n```\n")

    parts.append(
        '**Do you approve these changes for deployment?**'
        ' (Reply "Yes" to deploy, or tell me what to change)'
    )

    markdown_string = "\n".join(parts)
    user_response = interrupt(markdown_string)
    return user_response

SUPERVISOR_TOOLS = [
    extract_override_intent,
    detect_override_conflicts,
    generate_and_validate_toml,
    search_leroy_documentation,
    lookup_infrastructure_data,
    get_unique_infrastructure_values,
    lookup_directive_schema,
    request_deployment_approval,
    apply_override_to_workspace,
    commit_and_push_workspace,
]