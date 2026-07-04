import tomlkit
import logging
from typing import Dict, Any, Tuple, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Define the keys that represent metadata or scope, so we can isolate the directive
SCOPE_KEYS = {"Region-default", "Region-geo", "Region-country", "Region-metro", "Region-number"}
META_KEYS = {"Ticket-id", "Start-time", "End-time", "Mapnames"} | SCOPE_KEYS

def get_record_scope(record: Dict) -> Tuple[str, List[Any]]:
    """Extracts the geographical scope key and value from a TOML record."""
    for key in SCOPE_KEYS:
        if key in record:
            val = record[key]
            # Normalize to list for easy intersection testing
            return key, val if isinstance(val, list) else [val]
    return "", []

def get_record_directive(record: Dict) -> str:
    """Extracts the specific override directive (e.g., Access-control, Quota-tb) from a TOML record."""
    for key in record.keys():
        if key not in META_KEYS:
            return key
    return ""

def detect_conflicts(new_intent: Dict[str, Any], toml_content: str) -> Tuple[bool, str, List[Dict]]:
    """
    Parses the TOML string and checks for literal conflicts against the new intent.
    Returns (has_conflict, warning_message, conflicting_records).
    """
    try:
        doc = tomlkit.parse(toml_content)
    except Exception as e:
        logger.error(f"Failed to parse TOML: {e}")
        return False, f"Error parsing existing TOML: {e}", []

    records = doc.get("override-records", [])
    
    # Unpack the structured new intent
    new_geo_dict = new_intent.get("Geographical-Scope", {})
    new_dir_dict = new_intent.get("Override-Directive", {})
    new_maps = new_intent.get("Mapnames", [])
    
    if not new_geo_dict or not new_dir_dict:
        return False, "Invalid intent structure: Missing scope or directive.", []

    new_geo_key = list(new_geo_dict.keys())[0]
    new_geo_vals = new_geo_dict[new_geo_key]
    new_dir_key = list(new_dir_dict.keys())[0]
    
    conflicting_records = []

    for record in records:
        rec_geo_key, rec_geo_vals = get_record_scope(record)
        rec_dir_key = get_record_directive(record)
        rec_maps = record.get("Mapnames", [])
        
        # 1. Check Geographical Collision
        geo_collision = (rec_geo_key == new_geo_key) and bool(set(rec_geo_vals) & set(new_geo_vals))
        
        # 2. Check Directive Collision
        dir_collision = (rec_dir_key == new_dir_key)
        
        # 3. Check Mapname Collision (If both lack mapnames, it's an LR-level collision)
        if not new_maps and not rec_maps:
            map_collision = True
        else:
            map_collision = bool(set(rec_maps) & set(new_maps))
            
        if geo_collision and dir_collision and map_collision:
            conflicting_records.append(record)

    if conflicting_records:
        conflict_tickets = [rec.get('Ticket-id', 'UNKNOWN') for rec in conflicting_records]
        msg = (
            f"Conflict detected! Your request overlaps exactly with existing records "
            f"from ticket(s): {', '.join(conflict_tickets)}. You must manually remove "
            f"the old stanzas before adding this new one."
        )
        return True, msg, conflicting_records

    # We do not block for broader/deeper hierarchy warnings, but we can return a friendly heads-up
    if new_geo_key in ["Region-geo", "Region-country"]:
        return False, f"Note: You are setting a broad {new_geo_key} rule. Ensure it doesn't conflict with deeper, region-specific topology overrides.", []

    return False, "No conflicts detected. Safe to proceed.", []

if __name__ == "__main__":
    # Local Verification Block
    logging.basicConfig(level=logging.INFO)
    
    # Assuming override.toml is in the root directory (3 levels up from this file)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    toml_path = PROJECT_ROOT / "override.toml"
    
    if not toml_path.exists():
        print(f"Test failed: Could not find {toml_path}")
    else:
        with open(toml_path, "r", encoding="utf-8") as f:
            toml_content = f.read()
            
        print("--- Test 1: Simulating an Exact Conflict (LEROYOPS-61) ---")
        # Creating a mock intent that directly collides with LEROYOPS-61 in the provided TOML
        conflict_intent = {
            "Ticket-id": "LEROYOPS-999",
            "Mapnames": ["mm2", "w4"], 
            "Geographical-Scope": {"Region-country": ["DE"]},
            "Override-Directive": {"Access-control": "allowed"}
        }
        
        has_conflict, msg, records = detect_conflicts(conflict_intent, toml_content)
        print(f"Has Conflict: {has_conflict}")
        print(f"Message: {msg}")
        
        print("\n--- Test 2: Simulating a Safe, New Rule ---")
        # Creating a mock intent that touches the same region but a DIFFERENT mapname
        safe_intent = {
            "Ticket-id": "LEROYOPS-1000",
            "Mapnames": ["brand_new_map"], 
            "Geographical-Scope": {"Region-country": ["DE"]},
            "Override-Directive": {"Access-control": "must-exclude"}
        }
        
        has_conflict2, msg2, records2 = detect_conflicts(safe_intent, toml_content)
        print(f"Has Conflict: {has_conflict2}")
        print(f"Message: {msg2}")