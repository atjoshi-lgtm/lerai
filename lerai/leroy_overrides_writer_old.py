#!/usr/bin/env python3
"""
leroy_overrides_writer.py
- Orchestrates the LeRoy overrides generation pipeline.
- Extracts intent, checks for conflicts, and safely generates a validated TOML stanza.
"""

import sys
import argparse
import logging
import json
from pathlib import Path
from typing import Optional
from functools import lru_cache

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PROMPTS_DIR = PROJECT_ROOT / "lerai" / "prompts"
WRITER_RESPONSE_TEMPLATES_FILE = PROMPTS_DIR / "leroy_override_writer_response_templates.json"
CONFLICT_RULES_FILE = PROMPTS_DIR / "leroy_override_conflict_rules.json"
LOG_FILE_PATH = PROJECT_ROOT / "leroy_override_pipeline.log"

from lerai.logging_utils import redact_value
from lerai.overrides_pipeline.entity_extractor import extract_intent
from lerai.overrides_pipeline.conflict_detector import detect_conflicts
from lerai.overrides_pipeline.toml_generator import build_toml_string, validate_stanza

logger = logging.getLogger(__name__)


def _as_json(value: object) -> str:
    """Best-effort pretty serialization for runtime-generated objects."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value)


def configure_pipeline_logging() -> None:
    """Configures human-readable file logging for direct script runs."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s\n%(message)s\n")
    )
    root_logger.addHandler(file_handler)


@lru_cache(maxsize=1)
def _load_json_file(file_path: Path) -> dict:
    """Loads and validates that a JSON file contains an object."""
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Required JSON file not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in file: {file_path}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {file_path}")

    return payload


@lru_cache(maxsize=1)
def _load_writer_response_templates() -> dict:
    """Loads response templates used by the override writer."""
    templates = _load_json_file(WRITER_RESPONSE_TEMPLATES_FILE)
    required = [
        "hard_conflict",
        "warning_note",
        "success",
        "error",
    ]
    missing = [key for key in required if key not in templates]
    if missing:
        raise ValueError(
            "Missing writer response templates: " + ", ".join(missing)
        )
    return templates


@lru_cache(maxsize=1)
def _load_no_conflict_message() -> str:
    """Loads the canonical no-conflict message from conflict rules."""
    conflict_rules = _load_json_file(CONFLICT_RULES_FILE)
    messages = conflict_rules.get("messages", {})
    no_conflict = messages.get("no_conflict")
    if not isinstance(no_conflict, str) or not no_conflict:
        raise ValueError("Conflict rules must define messages.no_conflict")
    return no_conflict


def _render_template(template_key: str, **kwargs: str) -> str:
    """Renders a named response template with placeholder values."""
    template = _load_writer_response_templates()[template_key]
    return template.format(**kwargs)

def load_schema() -> dict:
    """Loads the authoritative JSON schema for validation."""
    schema_path = PROJECT_ROOT / "override_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    return schema

def load_current_toml() -> str:
    """Loads the current production TOML to check for conflicts."""
    toml_path = PROJECT_ROOT / "override.toml"
    if not toml_path.exists():
        logger.warning("override.toml not found. Proceeding without conflict detection.")
        return ""
    with open(toml_path, "r", encoding="utf-8") as f:
        toml_content = f.read()
    return toml_content

def write_toml(user_question: str, xml_string: Optional[str] = None) -> str: 
    """
    Pipeline orchestrator:
    1. Extract intent
    2. Check conflicts
    3. Generate TOML
    4. Validate against schema
    5. Format Webex response
    """
    try:
        # Step 1: Extract Intent
        logger.info("Extracting intent from user request...")
        intent = extract_intent(user_question, xml_string)
        logger.info("Intent extraction complete:\n%s", _as_json(intent))
        
        # Step 2: Detect Conflicts
        logger.info("Checking for conflicts against current override.toml...")
        current_toml = load_current_toml()
        schema = load_schema()
        
        conflict_warning = ""
        no_conflict_message = _load_no_conflict_message()
        if current_toml:
            has_conflict, msg, records = detect_conflicts(intent, current_toml)
            logger.info(
                "Conflict detection result:\n%s",
                _as_json(
                    {
                        "has_conflict": has_conflict,
                        "message": msg,
                        "record_count": len(records),
                    }
                ),
            )
            if has_conflict or msg != no_conflict_message:
                # Surface all conflict/warning messages as non-blocking warnings
                conflict_warning = _render_template("warning_note", warning_message=msg)
                logger.info("Conflict warning generated:\n%s", _as_json({"conflict_warning": conflict_warning}))
        
        # Step 3 & 4: Generate and Validate TOML
        logger.info("Building and validating TOML stanza...")
        toml_out = build_toml_string(intent)
        logger.info("Generated TOML stanza text was created successfully")
        validate_stanza(toml_out, schema)
        logger.info("TOML validation complete")
        
        # Step 5: Format the final Webex Response
        final_response = _render_template(
            "success",
            conflict_warning=conflict_warning,
            toml_stanza=toml_out,
        )
        logger.info("Rendered final response text successfully")
        return final_response

    except Exception as exc:
        logger.error("Override pipeline failed", extra={"error": redact_value(str(exc))})
        return _render_template("error", error_message=str(exc))

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Leroy override TOML stanza")
    parser.add_argument(
        "user_question",
        nargs="?",
        default="I'd like to remove mm2 from all the US large regions. Ticket is LEROYOPS-99.",
        help="Ticket/request description to convert into a TOML override stanza",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    configure_pipeline_logging()
    args = _parse_args(sys.argv[1:])
    try:
        # Test the end-to-end pipeline
        output = write_toml(args.user_question)
        print(output)
        logger.info("Manual override writer output generated")
    except Exception as exc:
        print(f"Critical error: {exc}", file=sys.stderr)
        sys.exit(1)