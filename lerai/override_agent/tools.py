from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomlkit
from langchain_core.tools import tool

from lerai.overrides_pipeline.conflict_detector import detect_conflicts
from lerai.overrides_pipeline.toml_generator import build_toml_string, validate_stanza


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDE_TOML_PATH = PROJECT_ROOT / "override.toml"
OVERRIDE_SCHEMA_PATH = PROJECT_ROOT / "override_schema.json"

_SCOPE_KEYS = {
    "Region-geo",
    "Region-country",
    "Region-state",
    "Region-city",
    "Region-metro",
    "Region-default",
}
_META_KEYS = {"Ticket-id", "Start-time", "End-time", "Mapnames"}


def _load_override_toml_read_only() -> str:
    """Reads override.toml in read-only mode; never writes to disk."""
    if not OVERRIDE_TOML_PATH.exists():
        return ""
    return OVERRIDE_TOML_PATH.read_text(encoding="utf-8")


def _load_override_schema() -> dict[str, Any]:
    with OVERRIDE_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _intent_from_record(record: dict[str, Any]) -> dict[str, Any]:
    geo_scope: dict[str, Any] = {}
    override_directive: dict[str, Any] = {}

    for key, value in record.items():
        if key in _SCOPE_KEYS:
            geo_scope[key] = value
        elif key not in _META_KEYS:
            override_directive[key] = value

    return {
        "Ticket-id": record.get("Ticket-id"),
        "Start-time": record.get("Start-time"),
        "End-time": record.get("End-time"),
        "Mapnames": record.get("Mapnames", []),
        "Geographical-Scope": geo_scope,
        "Override-Directive": override_directive,
    }


def _intent_from_toml(toml_text: str) -> dict[str, Any]:
    doc = tomlkit.parse(toml_text)
    records = doc.get("override-records", [])
    if not records:
        raise ValueError("No [[override-records]] stanza found in the provided TOML.")
    return _intent_from_record(dict(records[0]))


@tool
def detect_override_conflicts(proposed_toml: str) -> dict[str, Any]:
    """Read override.toml and detect stanza conflicts against the proposed TOML stanza."""
    try:
        new_intent = _intent_from_toml(proposed_toml)
        current_toml = _load_override_toml_read_only()

        if not current_toml:
            return {
                "has_conflict": False,
                "message": "override.toml was not found; conflict detection skipped.",
                "conflicting_tickets": [],
                "conflicting_records": [],
            }

        has_conflict, message, conflicting_records = detect_conflicts(new_intent, current_toml)
        ticket_ids = [record.get("Ticket-id", "UNKNOWN") for record in conflicting_records]
        return {
            "has_conflict": has_conflict,
            "message": message,
            "conflicting_tickets": ticket_ids,
            "conflicting_records": conflicting_records,
        }
    except Exception as exc:
        return {
            "has_conflict": False,
            "message": f"Conflict detection failed: {exc}",
            "conflicting_tickets": [],
            "conflicting_records": [],
        }


@tool
def generate_and_validate_toml(intent_json: str) -> dict[str, Any]:
    """Generate TOML from a JSON intent payload and validate it against override_schema.json."""
    try:
        intent = json.loads(intent_json)
        toml_text = build_toml_string(intent)
        schema = _load_override_schema()
        validate_stanza(toml_text, schema)
        return {
            "ok": True,
            "toml": toml_text,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "toml": "",
            "error": str(exc),
        }


SUPERVISOR_TOOLS = [
    generate_and_validate_toml,
    detect_override_conflicts,
]
