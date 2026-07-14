import tomlkit
import logging
import json
from typing import Dict, Any, Tuple, List, Optional
from pathlib import Path
from functools import lru_cache
import csv
from lerai.netarch.netarch import fetch_metro_region_mapping

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"
CONFLICT_RULES_FILE = PROMPTS_DIR / "leroy_override_conflict_rules.json"

class GeographicalTaxonomy:
    """
    Dynamically loads and evaluates hierarchical relationships for LeRoy override scopes.
    Hierarchy (0 is broadest, 4 is narrowest):
    0: Region-default -> 1: Region-geo -> 2: Region-country -> 3: Region-metro -> 4: Region-number
    """

    HIERARCHY = {
        "Region-default": 0,
        "Region-geo": 1,
        "Region-country": 2,
        "Region-metro": 3,
        "Region-number": 4
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        
        # Mappings built from CSVs
        self.region_to_metro = {}
        self.metro_to_country = {}
        self.country_to_geo = {}

        self._load_csv_data()

    def _load_csv_data(self):
        """Reads the CSV files directly from disk on every instantiation."""
        try:
            # 1. Load Region-number -> Region-metro
            metro_region_path = self.data_dir / "metro_region.csv"
            # fetch_metro_region_mapping(output_path=metro_region_path)  # Ensure the latest mapping is fetched and saved as CSV
            if metro_region_path.exists():
                with open(metro_region_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Ensure we map string-to-string for easy comparisons
                        self.region_to_metro[str(row["region"]).strip()] = str(row["metro_area"]).strip()

            # 2. Load Region-metro -> Region-country
            country_metro_path = self.data_dir / "country_metro.csv"
            if country_metro_path.exists():
                with open(country_metro_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Entity extractor converts metro spaces to underscores, so we do it here too
                        metro_normalized = str(row["metro_area"]).strip().replace(" ", "_")
                        
                        # BUG FIX: This was incorrectly assigned to self.country_to_geo
                        self.metro_to_country[metro_normalized] = str(row["country"]).strip()

            # 3. Load Region-country -> Region-geo
            geo_country_path = self.data_dir / "geo_country.csv"
            if geo_country_path.exists():
                with open(geo_country_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.country_to_geo[str(row["country"]).strip()] = str(row["geo"]).strip()

        except Exception as e:
            logger.error(f"Failed to load taxonomy CSVs: {e}")

    def _get_ancestor(self, value: str, current_level: int, target_level: int) -> Optional[str]:
        """Translates a narrow scope value UP the hierarchy to the target level."""
        if current_level == target_level:
            return value
        if target_level == 0:
            return "default"

        current_val = str(value).strip()
        curr_lvl = current_level

        # Roll up the hierarchy one step at a time until we hit the target level
        while curr_lvl > target_level:
            if curr_lvl == 4:
                current_val = self.region_to_metro.get(current_val)
            elif curr_lvl == 3:
                current_val = self.metro_to_country.get(current_val)
            elif curr_lvl == 2:
                current_val = self.country_to_geo.get(current_val)

            if not current_val:
                return None  # Mapping gap; cannot traverse further
            curr_lvl -= 1

        return current_val

    def compare_scopes(self, scope_1_key: str, scope_1_vals: List, scope_2_key: str, scope_2_vals: List) -> str:
        """
        Determines the hierarchical relationship between two scopes.
        Returns: EXACT_MATCH, SCOPE_1_IS_BROADER, SCOPE_1_IS_NARROWER, or NO_OVERLAP.
        """
        lvl1 = self.HIERARCHY.get(scope_1_key)
        lvl2 = self.HIERARCHY.get(scope_2_key)

        if lvl1 is None or lvl2 is None:
            return "NO_OVERLAP"

        # Cast everything to strings for safe set operations
        s1_set = set(str(v).strip() for v in scope_1_vals)
        s2_set = set(str(v).strip() for v in scope_2_vals)

        # Scenario A: Same level (e.g., US vs US, or DE vs US)
        if lvl1 == lvl2:
            intersection = s1_set.intersection(s2_set)
            return "EXACT_MATCH" if intersection else "NO_OVERLAP"

        # Scenario B: Scope 1 is broader (e.g., Geo vs Country)
        elif lvl1 < lvl2:
            # Check if any narrow item in Scope 2 rolls up to a broad item in Scope 1
            for v2 in s2_set:
                ancestor = self._get_ancestor(v2, lvl2, lvl1)
                if ancestor and ancestor in s1_set:
                    return "SCOPE_1_IS_BROADER"
            return "NO_OVERLAP"

        # Scenario C: Scope 1 is narrower (e.g., Metro vs Geo)
        else:
            # Check if any narrow item in Scope 1 rolls up to a broad item in Scope 2
            for v1 in s1_set:
                ancestor = self._get_ancestor(v1, lvl1, lvl2)
                if ancestor and ancestor in s2_set:
                    return "SCOPE_1_IS_NARROWER"
            return "NO_OVERLAP"
        
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

def compare_directives(dir_1_key: str, dir_1_val: Any, dir_2_key: str, dir_2_val: Any) -> str:
    """
    Compares two override directives to determine their relationship.
    Currently only supports 'Access-control'.
    Returns: SAME, OPPOSITE, or UNSUPPORTED.
    """
    # If the directive keys don't match, they aren't directly competing in the same vector
    if dir_1_key != dir_2_key:
        return "UNSUPPORTED"

    if dir_1_key == "Access-control":
        # Valid values are "must-include", "must-exclude", "allowed"
        val_1 = str(dir_1_val).strip().lower()
        val_2 = str(dir_2_val).strip().lower()
        
        if val_1 == val_2:
            return "SAME"
        else:
            return "OPPOSITE"
            
    return "UNSUPPORTED"

def detect_conflicts(new_intent: Dict[str, Any], toml_content: str) -> List[Dict[str, Any]]:
    """
    Parses the TOML string and checks for hierarchical/semantic conflicts against the new intent.
    Returns a list of structured conflict dictionaries.
    """
    # Initialize the taxonomy (Assumes data/ is at the project root)
    data_dir = PROJECT_ROOT / "lerai" / "data"
    taxonomy = GeographicalTaxonomy(data_dir=data_dir)

    try:
        doc = tomlkit.parse(toml_content)
    except Exception as e:
        logger.error(f"Failed to parse TOML: {e}")
        return [{"conflict_type": "PARSE_ERROR", "message": f"Error parsing existing TOML: {e}"}]

    records = doc.get("override-records", [])
    
    new_geo_dict = new_intent.get("Geographical-Scope", {})
    new_dir_dict = new_intent.get("Override-Directive", {})
    new_maps = new_intent.get("Mapnames", [])
    
    if not new_geo_dict or not new_dir_dict:
        return [{"conflict_type": "INVALID_INTENT", "message": "Missing scope or directive in intent."}]

    new_geo_key = list(new_geo_dict.keys())[0]
    new_geo_vals = new_geo_dict[new_geo_key]
    new_dir_key = list(new_dir_dict.keys())[0]
    new_dir_val = new_dir_dict[new_dir_key]
    
    found_conflicts = []

    for record in records:
        rec_geo_key, rec_geo_vals = get_record_scope(record)
        rec_dir_key = get_record_directive(record)
        rec_dir_val = record.get(rec_dir_key)
        rec_maps = record.get("Mapnames", [])
        rec_ticket = record.get("Ticket-id", "UNKNOWN")

        # 1. Check Mapname Collision
        # Empty maps array implies an LR-level rule (applies to all maps)
        map_collision = False
        partial_map_overlap = False
        
        if not new_maps and not rec_maps:
            map_collision = True
        elif not new_maps or not rec_maps:
            map_collision = True # One applies to all maps, the other applies to specific maps (collision)
        else:
            intersection = set(new_maps) & set(rec_maps)
            if intersection:
                map_collision = True
                if set(new_maps) != set(rec_maps):
                    partial_map_overlap = True

        if not map_collision:
            continue # Maps don't intersect, no conflict possible with this record

        # 2. Check Geographical and Directive Relationships
        scope_relation = taxonomy.compare_scopes(new_geo_key, new_geo_vals, rec_geo_key, rec_geo_vals)
        dir_relation = compare_directives(new_dir_key, new_dir_val, rec_dir_key, rec_dir_val)

        if scope_relation == "NO_OVERLAP" or dir_relation == "UNSUPPORTED":
            continue

        # 3. Categorize the Conflict
        conflict_type = None
        message = ""

        if scope_relation == "EXACT_MATCH" and dir_relation == "OPPOSITE":
            conflict_type = "DIRECT_COLLISION"
            message = f"Hard collision: Exactly contradicts existing rule in {rec_ticket}."
            
        elif scope_relation == "SCOPE_1_IS_BROADER" and dir_relation == "OPPOSITE":
            conflict_type = "INEFFECTIVE"
            message = f"Ineffective rule: Your broader rule will be overridden by the narrower existing rule in {rec_ticket}."
            
        elif scope_relation == "SCOPE_1_IS_NARROWER" and dir_relation == "OPPOSITE":
            conflict_type = "CARVE_OUT"
            message = f"Carve-out: Your narrow rule punches a hole in the broader existing policy from {rec_ticket}."
            
        elif scope_relation == "SCOPE_1_IS_BROADER" and dir_relation == "SAME":
            conflict_type = "DEAD_CODE"
            message = f"Dead code: Your new broader rule makes the narrower existing rule in {rec_ticket} obsolete."
            
        if partial_map_overlap and conflict_type:
            conflict_type = "PARTIAL_OVERLAP"
            message += f" Note: This only applies to the overlapping maps: {list(intersection)}."

        if conflict_type:
            found_conflicts.append({
                "conflict_type": conflict_type,
                "ticket_id": rec_ticket,
                "message": message,
                "record": record
            })

    return found_conflicts

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