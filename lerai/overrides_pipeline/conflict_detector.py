import tomlkit
import logging
import json
from typing import Dict, Any, Tuple, List
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"
CONFLICT_RULES_FILE = PROMPTS_DIR / "leroy_override_conflict_rules.json"


def _as_json(value: Any) -> str:
    """Best-effort pretty serialization for runtime-generated objects."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value)


@lru_cache(maxsize=1)
def _load_conflict_rules() -> Dict[str, Any]:
    """Loads conflict detection keys and message templates from JSON."""
    try:
        rules = json.loads(CONFLICT_RULES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Conflict rules file not found: {CONFLICT_RULES_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in conflict rules file: {CONFLICT_RULES_FILE}") from exc

    if not isinstance(rules, dict):
        raise ValueError("Conflict rules must be a JSON object.")

    required_keys = ["scope_keys", "metadata_keys", "warning_scope_keys", "messages"]
    missing = [key for key in required_keys if key not in rules]
    if missing:
        raise ValueError(f"Conflict rules missing required keys: {', '.join(missing)}")

    return rules

def get_record_scope(record: Dict) -> Tuple[str, List[Any]]:
    """Extracts the geographical scope key and value from a TOML record."""
    rules = _load_conflict_rules()
    scope_keys = set(rules["scope_keys"])

    for key in scope_keys:
        if key in record:
            val = record[key]
            # Normalize to list for easy intersection testing
            return key, val if isinstance(val, list) else [val]
    return "", []

def get_record_directive(record: Dict) -> str:
    """Extracts the specific override directive (e.g., Access-control, Quota-tb) from a TOML record."""
    rules = _load_conflict_rules()
    scope_keys = set(rules["scope_keys"])
    meta_keys = set(rules["metadata_keys"]) | scope_keys

    for key in record.keys():
        if key not in meta_keys:
            return key
    return ""

def detect_conflicts(new_intent: Dict[str, Any], toml_content: str) -> Tuple[bool, str, List[Dict]]:
    """
    Parses the TOML string and checks for literal conflicts against the new intent.
    Returns (has_conflict, warning_message, conflicting_records).
    """
    rules = _load_conflict_rules()
    messages = rules["messages"]
    warning_scope_keys = set(rules["warning_scope_keys"])

    try:
        doc = tomlkit.parse(toml_content)
    except Exception as e:
        logger.error(f"Failed to parse TOML: {e}")
        return False, messages["parse_error"].format(error=e), []

    records = doc.get("override-records", [])
    logger.info("Parsed current override records count=%s", len(records))
    
    # Unpack the structured new intent
    new_geo_dict = new_intent.get("Geographical-Scope", {})
    new_dir_dict = new_intent.get("Override-Directive", {})
    new_maps = new_intent.get("Mapnames", [])
    logger.info("Parsed new intent for conflict check:\n%s", _as_json(new_intent))
    
    if not new_geo_dict or not new_dir_dict:
        return False, messages["invalid_intent"], []

    new_geo_key = list(new_geo_dict.keys())[0]
    new_geo_vals = new_geo_dict[new_geo_key]
    new_dir_key = list(new_dir_dict.keys())[0]
    logger.info(
        "Derived intent comparison keys:\n%s",
        _as_json(
            {
                "new_geo_key": new_geo_key,
                "new_geo_vals": new_geo_vals,
                "new_dir_key": new_dir_key,
                "new_maps": new_maps,
            }
        ),
    )
    
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

        # logger.info(
        #     "Computed conflict comparison:\n%s",
        #     _as_json(
        #         {
        #             "rec_geo_key": rec_geo_key,
        #             "rec_geo_vals": rec_geo_vals,
        #             "rec_dir_key": rec_dir_key,
        #             "rec_maps": rec_maps,
        #             "geo_collision": geo_collision,
        #             "dir_collision": dir_collision,
        #             "map_collision": map_collision,
        #         }
        #     ),
        # )
            
        if geo_collision and dir_collision and map_collision:
            conflicting_records.append(record)

    if conflicting_records:
        conflict_tickets = [rec.get('Ticket-id', 'UNKNOWN') for rec in conflicting_records]
        msg = messages["literal_conflict"].format(tickets=", ".join(conflict_tickets))
        logger.info(
            "Literal conflicts detected:\n%s",
            _as_json(
                {
                    "conflicting_record_count": len(conflicting_records),
                    "conflict_tickets": conflict_tickets,
                    "message": msg,
                }
            ),
        )
        return True, msg, conflicting_records

    # We do not block for broader/deeper hierarchy warnings, but we can return a friendly heads-up
    if new_geo_key in warning_scope_keys:
        warning_msg = messages["broad_scope_warning"].format(scope_key=new_geo_key)
        logger.info("Broad-scope warning emitted:\n%s", _as_json({"warning_message": warning_msg}))
        return False, warning_msg, []

    logger.info("No conflicts detected:\n%s", _as_json({"message": messages["no_conflict"]}))
    return False, messages["no_conflict"], []

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