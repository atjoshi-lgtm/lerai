import xml.etree.ElementTree as ET
import logging
import json
import re
from typing import Optional, Dict, Any
from pathlib import Path
import sys
from functools import lru_cache

logger = logging.getLogger(__name__)

VALID_REGION_GEO_CODES = {"NA", "LA", "APAC", "EMEA"}
REGION_GEO_SYNONYMS = {
    "north america": "NA",
    "na": "NA",
    "latin america": "LA",
    "latam": "LA",
    "la": "LA",
    "asia pacific": "APAC",
    "apac": "APAC",
    "europe middle east africa": "EMEA",
    "europe middle east and africa": "EMEA",
    "emea": "EMEA",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"
EXTRACTOR_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "leroy_override_entity_extractor_system_prompt.txt"
EXTRACTOR_USER_PROMPT_FILE = PROMPTS_DIR / "leroy_override_entity_extractor_user_prompt.txt"
EXTRACTOR_TOOL_SCHEMA_FILE = PROMPTS_DIR / "leroy_override_entity_extractor_tool.json"
EXTRACTOR_SETTINGS_FILE = PROMPTS_DIR / "leroy_override_entity_extractor_settings.json"

from openai_agent.openai_agent_client import responses


def _as_json(value: Any) -> str:
    """Best-effort pretty serialization for runtime-generated objects."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value)


def _load_prompt(prompt_path: Path) -> str:
    """Loads prompt text from disk and returns it as a string."""
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise ValueError(f"Prompt file not found: {prompt_path}") from exc


def _build_user_prompt(user_text: str, ticket_data: Dict[str, Any]) -> str:
    """Renders the user prompt template with request and optional Jira context."""
    template = _load_prompt(EXTRACTOR_USER_PROMPT_FILE)
    jira_context = json.dumps(ticket_data, indent=2) if ticket_data else "None"
    return (
        template
        .replace("{{USER_REQUEST}}", user_text)
        .replace("{{JIRA_TICKET_CONTEXT}}", jira_context)
    )


def _load_extractor_tool_schema() -> Dict[str, Any]:
    """Loads and validates the extractor function/tool schema from JSON."""
    try:
        schema = json.loads(EXTRACTOR_TOOL_SCHEMA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Extractor tool schema file not found: {EXTRACTOR_TOOL_SCHEMA_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in extractor tool schema: {EXTRACTOR_TOOL_SCHEMA_FILE}") from exc

    if not isinstance(schema, dict):
        raise ValueError("Extractor tool schema must be a JSON object.")
    if "name" not in schema or "parameters" not in schema:
        raise ValueError("Extractor tool schema must include 'name' and 'parameters'.")

    return schema


@lru_cache(maxsize=1)
def _load_extractor_settings() -> Dict[str, Any]:
    """Loads runtime settings for the extractor LLM call."""
    try:
        settings = json.loads(EXTRACTOR_SETTINGS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Extractor settings file not found: {EXTRACTOR_SETTINGS_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in extractor settings: {EXTRACTOR_SETTINGS_FILE}") from exc

    if not isinstance(settings, dict):
        raise ValueError("Extractor settings must be a JSON object.")

    if "model" not in settings:
        raise ValueError("Extractor settings must include 'model'.")

    if "temperature" not in settings:
        raise ValueError("Extractor settings must include 'temperature'.")

    return settings

def parse_jira_xml(xml_string: str) -> dict:
    """Parses a Jira XML export and returns the core ticket details."""
    if not xml_string or not xml_string.strip():
        return {}
    
    try:
        root = ET.fromstring(xml_string)
        item = root.find('.//item')
        if item is None:
            logger.warning("No <item> found in Jira XML.")
            return {}
            
        # Clean up HTML/XML tags from description if necessary, or pass raw to LLM
        return {
            "Ticket-id": item.findtext('key', default="").strip(),
            "summary": item.findtext('summary', default="").strip(),
            "description": item.findtext('description', default="").strip()
        }
    except ET.ParseError as e:
        logger.error(f"Failed to parse Jira XML: {e}")
        return {}


def _extract_ticket_id_from_text(text: str) -> Optional[str]:
    """Extracts a JIRA-style ticket id (e.g. LEROYOPS-61) from free-form text."""
    if not text:
        return None
    match = re.search(r"\b([A-Z]+-\d+)\b", text)
    return match.group(1) if match else None


def _normalize_region_geo_code(value: str) -> Optional[str]:
    """Maps free-form geo names/codes to strict Region-geo values."""
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    upper = cleaned.upper()
    if upper in VALID_REGION_GEO_CODES:
        return upper

    normalized_key = re.sub(r"[\s_-]+", " ", cleaned).strip().lower()
    return REGION_GEO_SYNONYMS.get(normalized_key)


def _normalize_geographical_scope(geo_scope: Dict[str, Any]) -> Dict[str, Any]:
    """Applies deterministic normalization for geographical scope values."""
    if not isinstance(geo_scope, dict):
        return geo_scope

    if "Region-metro" in geo_scope and geo_scope["Region-metro"]:
        geo_scope["Region-metro"] = [
            m.strip().replace(" ", "_") if isinstance(m, str) else m
            for m in geo_scope["Region-metro"]
        ]

    if "Region-geo" in geo_scope and geo_scope["Region-geo"]:
        normalized_geo_vals = []
        for raw in geo_scope["Region-geo"]:
            if isinstance(raw, str):
                mapped = _normalize_region_geo_code(raw)
                normalized_geo_vals.append(mapped or raw)
            else:
                normalized_geo_vals.append(raw)
        geo_scope["Region-geo"] = normalized_geo_vals

    if "Region-default" in geo_scope and geo_scope["Region-default"]:
        raw_default_vals = geo_scope["Region-default"]
        inferred_geo_vals = []
        normalized_default = []

        for raw in raw_default_vals:
            if not isinstance(raw, str):
                continue

            cleaned = raw.strip()
            if not cleaned:
                continue

            if cleaned.lower() in {"default", "all", "global", "worldwide", "everywhere"}:
                normalized_default.append("default")
                continue

            mapped_geo = _normalize_region_geo_code(cleaned)
            if mapped_geo:
                inferred_geo_vals.append(mapped_geo)

        if inferred_geo_vals and not normalized_default:
            geo_scope.pop("Region-default", None)
            existing_geo = geo_scope.get("Region-geo", [])
            if not isinstance(existing_geo, list):
                existing_geo = []
            combined = existing_geo + inferred_geo_vals
            geo_scope["Region-geo"] = list(dict.fromkeys(combined))
        elif normalized_default:
            geo_scope["Region-default"] = ["default"]

    return geo_scope
    
def validate_extraction(data: Dict[str, Any]) -> tuple[bool, str]:
    """Ensures the LLM adhered to the strict LeRoy constraints."""
    geo_scope = data.get("Geographical-Scope", {})
    directive = data.get("Override-Directive", {})
    
    if len([k for k, v in geo_scope.items() if v is not None]) != 1:
        return False, "Validation Error: Must provide exactly ONE geographical scope."
        
    if len([k for k, v in directive.items() if v is not None]) != 1:
        return False, "Validation Error: Must provide exactly ONE override directive."
        
    return True, "Valid"

def extract_intent(user_text: str, xml_string: Optional[str] = None) -> Dict[str, Any]:
    """Calls the LLM to extract structured intent from the user request and Jira XML."""
    
    # 1. Parse XML if provided
    ticket_data = parse_jira_xml(xml_string) if xml_string else {}
    logger.info("Parsed Jira ticket data:\n%s", _as_json(ticket_data))
    
    # 2. Build the messages payload using externalized prompt templates
    system_prompt = _load_prompt(EXTRACTOR_SYSTEM_PROMPT_FILE)
    user_content = _build_user_prompt(user_text, ticket_data)
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    # Intentionally avoid logging prompt/message content.
    logger.info(
        "Prepared extractor request metadata:\n%s",
        _as_json(
            {
                "message_count": len(messages),
                "message_roles": [m.get("role") for m in messages],
                "has_ticket_context": bool(ticket_data),
            }
        ),
    )
    
    # 3. Call the Azure OpenAI client
    try:
        extractor_tool = _load_extractor_tool_schema()
        extractor_tool_name = extractor_tool["name"]
        extractor_settings = _load_extractor_settings()

        r = responses(
            messages=messages,
            model=extractor_settings["model"],
            temperature=extractor_settings["temperature"],
            functions=[extractor_tool],
            tool_choice={
                "type": extractor_settings.get("tool_choice_type", "function"),
                "function": {"name": extractor_tool_name},
            }
        )
        logger.info("Received extractor response:\n%s", _as_json(r))
        
        # 4. Extract and validate the tool call arguments
        tool_calls = r["choices"][0]["message"].get("tool_calls")
        logger.info("Parsed tool calls:\n%s", _as_json(tool_calls))
        if not tool_calls:
            raise ValueError("LLM failed to return a structured tool call.")
            
        extracted_data = json.loads(tool_calls[0]["function"]["arguments"])
        logger.info("Extracted tool-call arguments:\n%s", _as_json(extracted_data))

        # Prefer deterministic ticket extraction from user text/Jira context.
        user_ticket_id = _extract_ticket_id_from_text(user_text)
        jira_ticket_id = _extract_ticket_id_from_text(ticket_data.get("Ticket-id", ""))
        llm_ticket_id = extracted_data.get("Ticket-id", "")
        if isinstance(llm_ticket_id, str):
            llm_ticket_id = llm_ticket_id.strip()
        else:
            llm_ticket_id = ""

        final_ticket_id = user_ticket_id or jira_ticket_id or llm_ticket_id
        logger.info(
            "Resolved ticket id candidates:\n%s",
            _as_json(
                {
                    "user_ticket_id": user_ticket_id,
                    "jira_ticket_id": jira_ticket_id,
                    "llm_ticket_id": llm_ticket_id,
                    "final_ticket_id": final_ticket_id,
                }
            ),
        )
        if final_ticket_id and re.fullmatch(r"[A-Z]+-\d+", final_ticket_id):
            extracted_data["Ticket-id"] = final_ticket_id
        else:
            extracted_data.pop("Ticket-id", None)
        
        # --- Deterministic Normalization ---
        geo_scope = extracted_data.get("Geographical-Scope", {})
        extracted_data["Geographical-Scope"] = _normalize_geographical_scope(geo_scope)
        logger.info("Normalized extraction payload:\n%s", _as_json(extracted_data))
        is_valid, validation_msg = validate_extraction(extracted_data)
        logger.info(
            "Extraction validation result:\n%s",
            _as_json({"is_valid": is_valid, "validation_msg": validation_msg}),
        )
        if not is_valid:
            raise ValueError(f"Extracted data is invalid: {validation_msg}\nData: {extracted_data}")
            
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error during intent extraction: {e}")
        raise

if __name__ == "__main__":
    # Setup basic logging to see what's happening during the test
    logging.basicConfig(level=logging.INFO)
    
    # Mock Jira XML based on LEROYOPS-61
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="0.92">
    <channel>
        <item>
            <key id="6143392">LEROYOPS-61</key>
            <summary>Remove mm2 from LRs in Germany</summary>
            <description>We're removing mm2 from LRs across the board. In this ops ticket we will remove them from Germany.</description>
        </item>
    </channel>
    </rss>
    """
    
    print("--- Test 1: With XML and User Text ---")
    user_query_1 = "Please generate the override to remove mm2 from Germany based on this ticket."
    try:
        result_1 = extract_intent(user_query_1, mock_xml)
        print("Success! Extracted Intent:")
        print(json.dumps(result_1, indent=2))
    except Exception as e:
        print(f"Test 1 Failed: {e}")
        
    print("\n--- Test 2: Natural Language Only ---")
    user_query_2 = "Set the disk quota for map w48 to 50TB in the New York metro. Ticket is LEROYOPS-99."
    try:
        result_2 = extract_intent(user_query_2)
        print("Success! Extracted Intent:")
        print(json.dumps(result_2, indent=2))
    except Exception as e:
        print(f"Test 2 Failed: {e}")