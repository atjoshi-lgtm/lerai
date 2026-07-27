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


def _extract_comment_lines(node: Any) -> list[str]:
    """Extracts comment-only lines from a TOML record while preserving order."""
    if not hasattr(node, "as_string"):
        return []

    comment_lines: list[str] = []
    for line in node.as_string().splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            comment_lines.append(line.rstrip())
    return comment_lines


def _set_leading_comments(node: Any, comment_lines: list[str]) -> None:
    """Prepends comment lines to a TOML record's leading trivia."""
    if not comment_lines or not hasattr(node, "trivia"):
        return

    existing_comment = getattr(node.trivia, "comment", "")
    combined_lines = [line for line in comment_lines if line.strip()]
    if existing_comment:
        combined_lines.extend(
            line.rstrip() for line in str(existing_comment).splitlines() if line.strip()
        )

    if not combined_lines:
        return

    node.trivia.comment = "\n".join(combined_lines)
    node.trivia.comment_ws = "\n"


def _set_trailing_comments(node: Any, comment_lines: list[str]) -> None:
    """Appends comment lines after a TOML table body, before the next table."""
    if not comment_lines:
        return

    combined_lines = [line for line in comment_lines if line.strip()]

    if not combined_lines:
        return

    comment_block = "\n".join(combined_lines)

    if hasattr(node, "add"):
        table_value = getattr(node, "value", None)
        body = getattr(table_value, "body", None)
        if isinstance(body, list) and body:
            last_entry = body[-1]
            if isinstance(last_entry, tuple) and len(last_entry) == 2 and last_entry[0] is None:
                raw_tail = last_entry[1]
                tail_text = (
                    raw_tail.as_string() if hasattr(raw_tail, "as_string") else str(raw_tail)
                )
                if not tail_text.strip():
                    body.pop()

        # Insert raw whitespace/comment text into the table body so comments
        # stay above the following [[override-records]] header.
        node.add(tomlkit.ws("\n" + comment_block + "\n"))
        return

    if hasattr(node, "trivia"):
        existing_trail = getattr(node.trivia, "trail", "")
        trail_prefix = str(existing_trail)
        if trail_prefix and not trail_prefix.endswith("\n"):
            trail_prefix += "\n"
        node.trivia.trail = trail_prefix + comment_block


def _transfer_deleted_record_comments(records: Any, index: int) -> None:
    """Moves comment/whitespace body entries from a soon-to-be-deleted record.

    `tomlkit` stores inter-stanza comment blocks as `key=None` body items on the
    preceding table. If we delete that table directly, those comments vanish.
    This helper moves those raw entries to the nearest surviving table first.
    """
    if index < 0 or index >= len(records):
        return

    record = records[index]
    value = getattr(record, "value", None)
    body = getattr(value, "body", None)
    if not isinstance(body, list):
        return

    transferred_entries = [entry for entry in body if isinstance(entry, tuple) and len(entry) == 2 and entry[0] is None]
    if not transferred_entries:
        return

    if index > 0:
        previous = records[index - 1]
        prev_value = getattr(previous, "value", None)
        prev_body = getattr(prev_value, "body", None)
        if isinstance(prev_body, list):
            prev_body.extend(transferred_entries)
            return

    # Fallback: if there is no previous record (deleted first record), attach
    # the comments to the next record's leading trivia.
    if index + 1 < len(records):
        next_record = records[index + 1]
        comment_lines: list[str] = []
        for _, item in transferred_entries:
            text = item.as_string() if hasattr(item, "as_string") else str(item)
            for line in str(text).splitlines():
                if line.lstrip().startswith("#"):
                    comment_lines.append(line.rstrip())
        _set_leading_comments(next_record, comment_lines)


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

        # Iterate backwards so index positions stay valid while deleting.
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
                    _transfer_deleted_record_comments(records, i)
                    del doc["override-records"][i]
                    break

    # Append phase: materialize each intent as a fresh table.
    records = doc.get("override-records")
    if records is None:
        records = tomlkit.aot()
        doc.append("override-records", records)

    for intent in new_intents:
        new_record = tomlkit.table()
        for key, value in intent.items():
            new_record[key] = value
        new_record.add(tomlkit.nl())
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