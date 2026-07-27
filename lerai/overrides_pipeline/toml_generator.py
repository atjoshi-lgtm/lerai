import tomlkit
import jsonschema
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _as_json(value: Any) -> str:
    """Best-effort pretty serialization for runtime-generated objects."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value)


def _normalize_scalar(value: Any) -> Any:
    """Coerces a single (possibly ``tomlkit``) scalar into a comparable Python value.

    String-like values are stripped and lower-cased so that hidden ``tomlkit``
    formatting artifacts (surrounding whitespace, casing) never cause a false
    negative during set comparison. Non-string scalars are unwrapped to their
    native Python representation and returned untouched.

    Args:
        value: A raw Python scalar or a ``tomlkit`` item wrapping one.

    Returns:
        A hashable, comparison-safe Python value.
    """
    # ``tomlkit`` items subclass their native Python counterparts, but call
    # ``unwrap()`` when available to guarantee we operate on raw values.
    if hasattr(value, "unwrap"):
        try:
            value = value.unwrap()
        except Exception:
            pass
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _to_comparison_set(values: Any) -> frozenset:
    """Builds a normalized, order-independent set from a list-like value.

    Args:
        values: A ``tomlkit`` array, Python list, or lone scalar.

    Returns:
        A ``frozenset`` of normalized scalars suitable for equality comparison.
    """
    if values is None:
        return frozenset()
    if not isinstance(values, list):
        values = [values]
    return frozenset(_normalize_scalar(v) for v in values)


def _extract_record_profile(
    node: Any,
    scope_keys: List[str],
    metadata_keys: List[str],
) -> Tuple[Optional[str], frozenset, Optional[str], frozenset]:
    """Extracts a comparison profile from a single override-record node.

    The node is unwrapped to raw Python values before inspection so that no
    ``tomlkit`` object equality is ever performed downstream.

    Args:
        node: A ``tomlkit`` table (or dict-like) representing one record.
        scope_keys: The ordered list of recognized geographical scope keys.
        metadata_keys: The list of non-directive metadata keys (e.g. Ticket-id).

    Returns:
        A tuple of ``(scope_key, scope_value_set, directive_key, mapname_set)``.
        ``scope_key`` and ``directive_key`` are ``None`` when absent.
    """
    raw: Dict[str, Any] = node.unwrap() if hasattr(node, "unwrap") else dict(node)

    # Scope: the first recognized scope key present in the node.
    scope_key: Optional[str] = None
    scope_value_set: frozenset = frozenset()
    for key in scope_keys:
        if key in raw:
            scope_key = key
            scope_value_set = _to_comparison_set(raw[key])
            break

    # Directive: the sole key that is neither a scope nor a metadata key.
    excluded = set(scope_keys) | set(metadata_keys)
    directive_key: Optional[str] = None
    for key in raw.keys():
        if key not in excluded:
            directive_key = key
            break

    # Mapnames: default to an empty collection when the record is LR-level.
    mapname_set = _to_comparison_set(raw.get("Mapnames", []))

    return scope_key, scope_value_set, directive_key, mapname_set


def execute_ast_update(
    doc: tomlkit.TOMLDocument,
    target_intents: List[Dict[str, Any]],
    new_intents: List[Dict[str, Any]],
    conflict_rules: Dict[str, Any],
) -> tomlkit.TOMLDocument:
    """Performs a deterministic "Nuke and Append" mutation on a TOML document.

    Every override-record that exactly matches one of ``target_intents`` is
    deleted in place, after which each item in ``new_intents`` is appended as a
    fresh record.
    The Array of Tables is walked backwards so that in-place deletions never
    invalidate the indices of records still pending inspection.

    A record is considered a match only when its scope key, scope values (as a
    set), directive key, and Mapnames (as a set) are all identical to the
    target intent. Scope values and Mapnames are compared as sets of stripped,
    lower-cased strings to neutralize ``tomlkit`` formatting differences.

    Args:
        doc: The parsed ``tomlkit`` document to mutate.
        target_intents: Records the caller wants removed. Each is a flat mapping
            shaped like a live record (scope key, directive key, Mapnames, ...).
        new_intents: The replacement record(s) to append. Each record's keys
            (including metadata such as ``Ticket-id`` and ``Start-time``) are
            copied verbatim.
        conflict_rules: Configuration providing ``scope_keys`` and
            ``metadata_keys`` used to classify each key within a record.

    Returns:
        The same ``doc`` instance, mutated in place and returned for chaining.
    """
    scope_keys: List[str] = conflict_rules.get("scope_keys", [])
    metadata_keys: List[str] = conflict_rules.get("metadata_keys", [])

    records = doc.get("override-records")
    if records is None:
        logger.warning(
            "No 'override-records' array found in document; skipping nuke phase."
        )
    else:
        # Pre-compute the comparison profiles of every target intent once.
        target_profiles = [
            _extract_record_profile(intent, scope_keys, metadata_keys)
            for intent in target_intents
        ]

        # Iterate backwards so that ``del`` never shifts an unvisited index.
        for i in range(len(records) - 1, -1, -1):
            live_scope_key, live_scope_vals, live_dir_key, live_maps = (
                _extract_record_profile(records[i], scope_keys, metadata_keys)
            )

            for (
                tgt_scope_key,
                tgt_scope_vals,
                tgt_dir_key,
                tgt_maps,
            ) in target_profiles:
                is_match = (
                    live_scope_key == tgt_scope_key
                    and live_scope_vals == tgt_scope_vals
                    and live_dir_key == tgt_dir_key
                    and live_maps == tgt_maps
                )
                if is_match:
                    logger.debug(
                        "Nuking override-record at index %d "
                        "(scope=%s, values=%s, directive=%s, mapnames=%s).",
                        i,
                        live_scope_key,
                        sorted(str(v) for v in live_scope_vals),
                        live_dir_key,
                        sorted(str(v) for v in live_maps),
                    )
                    del doc["override-records"][i]
                    break  # Record nuked; advance to the next index.

    # Append phase: materialize each intent as a fresh table.
    records = doc.get("override-records")
    if records is None:
        records = tomlkit.aot()
        doc.append("override-records", records)

    for intent in new_intents:
        new_record = tomlkit.table()
        for key, value in intent.items():
            new_record[key] = value
        records.append(new_record)

    logger.debug(
        "Appended %d new override-record(s):\n%s",
        len(new_intents),
        _as_json(new_intents),
    )
    return doc

def build_toml_string(intent: Dict[str, Any]) -> str:
    """
    Programmatically builds a TOML string from the structured intent dictionary.
    """
    doc = tomlkit.document()
    
    # Create an Array of Tables (AOT) to represent [[override-records]]
    aot = tomlkit.aot()
    record = tomlkit.table()
    logger.info("Building TOML from intent:\n%s", _as_json(intent))
    
    # 1. Add Metadata
    if intent.get("Ticket-id"):
        record["Ticket-id"] = intent["Ticket-id"]
    if "Start-time" in intent:
        record["Start-time"] = intent["Start-time"]
    if "End-time" in intent:
        record["End-time"] = intent["End-time"]
    if "Mapnames" in intent and intent["Mapnames"]:
        record["Mapnames"] = intent["Mapnames"]
        
    # 2. Add Geographical Scope
    geo_dict = intent.get("Geographical-Scope", {})
    logger.info("Geographical scope object:\n%s", _as_json(geo_dict))
    for key, value in geo_dict.items():
        record[key] = value
        
    # 3. Add Override Directive
    dir_dict = intent.get("Override-Directive", {})
    logger.info("Override directive object:\n%s", _as_json(dir_dict))
    for key, value in dir_dict.items():
        record[key] = value
        
    aot.append(record)
    doc.append("override-records", aot)

    toml_output = tomlkit.dumps(doc)
    logger.info("Built TOML record object:\n%s", _as_json(record))
    return toml_output

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
        logger.info(
            "Prepared record for schema validation:\n%s",
            _as_json(clean_record),
        )
        
        jsonschema.validate(instance=clean_record, schema=schema_dict)
        logger.info("Schema validation passed for record:\n%s", _as_json(clean_record))
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