import xml.etree.ElementTree as ET
import logging
import json
from typing import Optional, Dict, Any
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai_agent.openai_agent_client import responses

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
    
# We define the strict schema the LLM must populate.
# openai_agent_client expects the inner function schema and wraps it as a tool.
EXTRACTOR_TOOL = {
    "name": "extract_leroy_override_intent",
    "description": "Extracts configuration parameters for a LeRoy override based on a user request and Jira ticket.",
    "parameters": {
        "type": "object",
        "properties": {
            "Ticket-id": {"type": "string", "description": "Jira ticket ID (e.g., LEROYOPS-61)."},
            "Mapnames": {"type": "array", "items": {"type": "string"}, "description": "List of maprules."},
            "Geographical-Scope": {
                "type": "object",
                "description": "Exactly ONE geographical scope.",
                "properties": {
                    "Region-default": {"type": "array", "items": {"type": "string"}},
                    "Region-geo": {"type": "array", "items": {"type": "string"}},
                    "Region-country": {"type": "array", "items": {"type": "string"}},
                    "Region-metro": {"type": "array", "items": {"type": "string"}},
                    "Region-number": {"type": "array", "items": {"type": "integer"}}
                }
            },
            "Override-Directive": {
                "type": "object",
                "description": "Exactly ONE override directive and its corresponding value.",
                "properties": {
                    "Access-control": {"type": "string", "enum": ["must-include", "must-exclude", "allowed"]},
                    "Quota-tb": {"type": "array", "items": {"type": "number"}},
                    "Traffic-multiplier": {"type": "number"},
                    "BLC-only": {"type": "boolean"},
                    "LR-disk-capacity-tb": {"type": "number"}
                    # Note: Add remaining directives from the schema here
                }
            },
            "Start-time": {"type": "integer", "description": "Unix epoch start time if specified."},
            "End-time": {"type": "integer", "description": "Unix epoch end time if specified."}
        },
        "required": ["Ticket-id", "Geographical-Scope", "Override-Directive"]
    }
}

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
    
    # 2. Build the messages payload
    system_prompt = (
        "You are an expert configuration assistant for the LeRoy system. "
        "Extract the exact configuration values requested by the user. "
        "Map natural language locations to the correct geographical scopes "
        "(e.g., 'Germany' -> Region-country: ['DE'], 'US' -> Region-country: ['US']). "
        "Ensure you only output exactly ONE override directive and ONE geographical scope."
    )
    
    user_content = f"User Request: {user_text}\n"
    if ticket_data:
        user_content += f"Jira Ticket Context:\n{json.dumps(ticket_data, indent=2)}\n"
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    # 3. Call the Azure OpenAI client
    try:
        r = responses(
            messages=messages,
            model="gpt-5.2", # From your original script
            temperature=0,
            functions=[EXTRACTOR_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_leroy_override_intent"}}
        )
        
        # 4. Extract and validate the tool call arguments
        tool_calls = r["choices"][0]["message"].get("tool_calls")
        if not tool_calls:
            raise ValueError("LLM failed to return a structured tool call.")
            
        extracted_data = json.loads(tool_calls[0]["function"]["arguments"])
        
        is_valid, validation_msg = validate_extraction(extracted_data)
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