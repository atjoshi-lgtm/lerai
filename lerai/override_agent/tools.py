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
_PROJECT_ROOT = PROJECT_ROOT
DATA_DIR = pathlib.Path(PROJECT_ROOT) / "lerai" / "data"
OVERRIDE_TOML_PATH = PROJECT_ROOT / "override.toml"
OVERRIDE_SCHEMA_PATH = PROJECT_ROOT / "override_schema.json"
SCHEMA_PATH = _PROJECT_ROOT / "lerai" / "prompts" / "leroy_override_entity_extractor_tool.json"


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
def lookup_infrastructure_data(target_output: str, source_value: str) -> str:
    """Use this tool to look up infrastructure mappings. It automatically handles normalization (spaces to underscores), aliases (airport codes), and hierarchical joins.
    - target_output: What you want to find (must be one of: 'regions', 'metros', 'countries').
    - source_value: The known entity you are searching with (e.g., 'France', 'FR', 'LAX', 'New York', 'EMEA').
    The tool will automatically figure out if the source is a geo, country, airport code, or metro, and traverse the hierarchy to return the target."""
    def normalize(s: str) -> str:
        return (s or "").strip().lower().replace(" ", "_")

    def unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    def load_csv_rows(file_name: str) -> list[dict[str, str]]:
        csv_path = DATA_DIR / file_name
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    kind = normalize(target_output)
    source_norm = normalize(source_value)

    if kind not in {"regions", "metros", "countries"}:
        return "Invalid target_output. Use one of: regions, metros, countries."
    if not source_norm:
        return "Please provide a non-empty source_value to search."

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

    try:
        geo_country_rows = load_csv_rows("geo_country.csv")
        country_metro_rows = load_csv_rows("country_metro.csv")
        metro_region_rows = load_csv_rows("metro_region.csv")

        geo_matches = [
            (row.get("country") or "").strip().upper()
            for row in geo_country_rows
            if normalize(row.get("geo") or "") == source_norm
        ]
        countries_from_geo = unique(geo_matches)

        if countries_from_geo:
            if kind == "countries":
                return f"Found countries for {source_value}: {', '.join(countries_from_geo)}"

            country_norm_set = {normalize(code) for code in countries_from_geo}
            metros_from_geo = unique(
                [
                    normalize((row.get("metro_area") or "").strip())
                    for row in country_metro_rows
                    if normalize((row.get("country") or "").strip()) in country_norm_set
                ]
            )

            if kind == "metros":
                if metros_from_geo:
                    return f"Found metros in {source_value}: {', '.join(metros_from_geo)}"
                return f"No metros found in {source_value}."

            metro_norm_set = set(metros_from_geo)
            regions_from_geo = unique(
                [
                    (row.get("region") or "").strip()
                    for row in metro_region_rows
                    if normalize((row.get("metro") or row.get("metro_area") or "").strip()) in metro_norm_set
                ]
            )
            if regions_from_geo:
                return f"Found regions for {source_value}: {', '.join(regions_from_geo)}"
            return f"No regions found for {source_value}."

        country_codes_from_data = {
            normalize((row.get("country") or "").strip()): (row.get("country") or "").strip().upper()
            for row in country_metro_rows
            if (row.get("country") or "").strip()
        }
        for row in geo_country_rows:
            country_code = (row.get("country") or "").strip()
            if country_code:
                country_codes_from_data[normalize(country_code)] = country_code.upper()

        resolved_country_code = country_codes_from_data.get(source_norm)
        if not resolved_country_code:
            alias_code = country_aliases.get(source_norm)
            if alias_code:
                resolved_country_code = country_codes_from_data.get(alias_code, alias_code.upper())

        if resolved_country_code:
            if kind == "countries":
                return f"Found countries for {source_value}: {resolved_country_code}"

            metros_from_country = unique(
                [
                    normalize((row.get("metro_area") or "").strip())
                    for row in country_metro_rows
                    if normalize((row.get("country") or "").strip()) == normalize(resolved_country_code)
                ]
            )

            if kind == "metros":
                if metros_from_country:
                    return f"Found metros in {source_value}: {', '.join(metros_from_country)}"
                return f"No metros found in {source_value}."

            metro_norm_set = set(metros_from_country)
            regions_from_country = unique(
                [
                    (row.get("region") or "").strip()
                    for row in metro_region_rows
                    if normalize((row.get("metro") or row.get("metro_area") or "").strip()) in metro_norm_set
                ]
            )
            if regions_from_country:
                return f"Found regions for {source_value}: {', '.join(regions_from_country)}"
            return f"No regions found for {source_value}."

        metro_or_airport_matches = [
            row
            for row in country_metro_rows
            if normalize((row.get("metro_area") or "").strip()) == source_norm
            or normalize((row.get("airport_code") or "").strip()) == source_norm
        ]

        if metro_or_airport_matches:
            canonical_metros = unique(
                [normalize((row.get("metro_area") or "").strip()) for row in metro_or_airport_matches]
            )
            countries_from_metro = unique(
                [
                    (row.get("country") or "").strip().upper()
                    for row in metro_or_airport_matches
                    if (row.get("country") or "").strip()
                ]
            )

            if kind == "countries":
                if countries_from_metro:
                    return f"Found countries for {source_value}: {', '.join(countries_from_metro)}"
                return f"No countries found for {source_value}."

            if kind == "metros":
                return f"Found metros in {source_value}: {', '.join(canonical_metros)}"

            metro_norm_set = set(canonical_metros)
            regions_from_metro = unique(
                [
                    (row.get("region") or "").strip()
                    for row in metro_region_rows
                    if normalize((row.get("metro") or row.get("metro_area") or "").strip()) in metro_norm_set
                ]
            )
            if regions_from_metro:
                return f"Found regions for {source_value}: {', '.join(regions_from_metro)}"
            return f"No regions found for {source_value}."

        return (
            f"No infrastructure mapping found for {source_value}. "
            "Try a geo (e.g., EMEA), country code/name (e.g., FR, France), airport code (e.g., LAX), or metro name (e.g., New York)."
        )

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


SUPERVISOR_TOOLS = [
    extract_override_intent,
    detect_override_conflicts,
    generate_and_validate_toml,
    search_leroy_documentation,
    lookup_infrastructure_data,
    get_unique_infrastructure_values,
    lookup_directive_schema,
]