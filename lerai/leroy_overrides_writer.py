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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lerai.logging_utils import redact_value
from lerai.overrides_pipeline.entity_extractor import extract_intent
from lerai.overrides_pipeline.conflict_detector import detect_conflicts
from lerai.overrides_pipeline.toml_generator import build_toml_string, validate_stanza

logger = logging.getLogger(__name__)

def load_schema() -> dict:
    """Loads the authoritative JSON schema for validation."""
    schema_path = PROJECT_ROOT / "override_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_current_toml() -> str:
    """Loads the current production TOML to check for conflicts."""
    toml_path = PROJECT_ROOT / "override.toml"
    if not toml_path.exists():
        logger.warning("override.toml not found. Proceeding without conflict detection.")
        return ""
    with open(toml_path, "r", encoding="utf-8") as f:
        return f.read()

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
        
        # Step 2: Detect Conflicts
        logger.info("Checking for conflicts against current override.toml...")
        current_toml = load_current_toml()
        schema = load_schema()
        
        conflict_warning = ""
        if current_toml:
            has_conflict, msg, records = detect_conflicts(intent, current_toml)
            if has_conflict:
                # If there's a hard conflict, stop and inform the user immediately
                return f"⚠️ **Conflict Detected** ⚠️\n\n{msg}\n\nPlease remove the conflicting stanza from `override.toml` before proceeding."
            elif msg != "No conflicts detected. Safe to proceed.":
                # Capture the non-blocking warning (like broad geo rules)
                conflict_warning = f"\n> **Note:** {msg}\n"
        
        # Step 3 & 4: Generate and Validate TOML
        logger.info("Building and validating TOML stanza...")
        toml_out = build_toml_string(intent)
        validate_stanza(toml_out, schema)
        
        # Step 5: Format the final Webex Response
        response = "✅ **Override Stanza Generated Successfully**\n"
        if conflict_warning:
            response += conflict_warning
            
        response += "\nPlease review the generated configuration below:\n\n"
        response += f"```toml\n{toml_out}\n```\n"
        response += "\n*If this looks correct, you may copy and paste it into `override.toml`.*"
        
        return response

    except Exception as exc:
        logger.error("Override pipeline failed", extra={"error": redact_value(str(exc))})
        return f"❌ **Error generating override:**\n\n`{str(exc)}`\n\nPlease check your input and try again."

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
    args = _parse_args(sys.argv[1:])
    try:
        # Test the end-to-end pipeline
        output = write_toml(args.user_question)
        print(output)
        logger.info("Manual override writer output generated")
    except Exception as exc:
        print(f"Critical error: {exc}", file=sys.stderr)
        sys.exit(1)