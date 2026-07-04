import tomlkit
import jsonschema
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

def build_toml_string(intent: Dict[str, Any]) -> str:
    """
    Programmatically builds a TOML string from the structured intent dictionary.
    """
    doc = tomlkit.document()
    
    # Create an Array of Tables (AOT) to represent [[override-records]]
    aot = tomlkit.aot()
    record = tomlkit.table()
    
    # 1. Add Metadata
    if "Ticket-id" in intent:
        record["Ticket-id"] = intent["Ticket-id"]
    if "Start-time" in intent:
        record["Start-time"] = intent["Start-time"]
    if "End-time" in intent:
        record["End-time"] = intent["End-time"]
    if "Mapnames" in intent and intent["Mapnames"]:
        record["Mapnames"] = intent["Mapnames"]
        
    # 2. Add Geographical Scope
    geo_dict = intent.get("Geographical-Scope", {})
    for key, value in geo_dict.items():
        record[key] = value
        
    # 3. Add Override Directive
    dir_dict = intent.get("Override-Directive", {})
    for key, value in dir_dict.items():
        record[key] = value
        
    aot.append(record)
    doc.append("override-records", aot)
    
    return tomlkit.dumps(doc)

def validate_stanza(toml_string: str, schema_dict: Dict[str, Any]) -> bool:
    """
    Parses the generated TOML and strictly validates it against the JSON schema.
    Raises ValueError if it fails.
    """
    try:
        doc = tomlkit.parse(toml_string)
        records = doc.get("override-records", [])
        if not records:
            raise ValueError("No override-records found in generated TOML.")
            
        # Convert tomlkit internal objects to native Python dict for jsonschema
        record = records[0]
        clean_record = json.loads(json.dumps(record))
        
        jsonschema.validate(instance=clean_record, schema=schema_dict)
        return True
        
    except jsonschema.exceptions.ValidationError as e:
        logger.error(f"Schema validation failed: {e.message}")
        raise ValueError(f"Generated TOML violates strict schema: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected validation error: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Assuming override_schema.json is in the root directory
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    schema_path = PROJECT_ROOT / "override_schema.json"
    
    if not schema_path.exists():
        print(f"Test failed: Could not find {schema_path}")
    else:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
            
        print("--- Test 1: Building and Validating a Proper Stanza ---")
        mock_intent = {
            "Ticket-id": "LEROYOPS-61",
            "Mapnames": ["mm2"],
            "Geographical-Scope": {"Region-country": ["DE"]},
            "Override-Directive": {"Access-control": "must-exclude"}
        }
        
        try:
            # Build it
            toml_out = build_toml_string(mock_intent)
            print("Generated TOML:\n")
            print(toml_out)
            
            # Validate it
            validate_stanza(toml_out, schema)
            print("Validation: SUCCESS (Schema approved)")
        except Exception as e:
            print(f"Test Failed: {e}")