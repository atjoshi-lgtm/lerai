import json
import unittest
from unittest.mock import patch

from lerai.override_agent.tools import detect_override_conflicts
from lerai.overrides_pipeline.conflict_detector import find_invalid_mapnames


class MapnameValidationTests(unittest.TestCase):
    def test_find_invalid_mapnames_returns_only_unknown_values(self):
        intent = {"Mapnames": ["mm2", "INVALID_MAP", "W4", "unknown-map"]}

        invalid = find_invalid_mapnames(intent)

        self.assertEqual(invalid, ["INVALID_MAP", "unknown-map"])

    def test_detect_override_conflicts_warns_when_mapname_invalid(self):
        intent_json = json.dumps(
            {
                "Ticket-id": "LEROYOPS-123",
                "Mapnames": ["mm2", "INVALID_MAP"],
                "Geographical-Scope": {"Region-country": ["DE"]},
                "Override-Directive": {"Access-control": "must-exclude"},
            }
        )

        with patch("lerai.override_agent.tools._load_override_toml_read_only", return_value=""):
            response = detect_override_conflicts.invoke({"intent_json": intent_json})

        self.assertFalse(response["has_conflict"])
        self.assertIn("invalid_mapnames", response)
        self.assertEqual(response["invalid_mapnames"], ["INVALID_MAP"])
        self.assertTrue(response["warnings"])
        self.assertIn("Invalid map name(s) provided: INVALID_MAP", response["message"])

    def test_detect_override_conflicts_has_no_warning_for_valid_maps(self):
        intent_json = json.dumps(
            {
                "Ticket-id": "LEROYOPS-124",
                "Mapnames": ["mm2", "W4"],
                "Geographical-Scope": {"Region-country": ["DE"]},
                "Override-Directive": {"Access-control": "must-exclude"},
            }
        )

        with patch("lerai.override_agent.tools._load_override_toml_read_only", return_value=""):
            response = detect_override_conflicts.invoke({"intent_json": intent_json})

        self.assertFalse(response["has_conflict"])
        self.assertEqual(response["invalid_mapnames"], [])
        self.assertEqual(response["warnings"], [])
        self.assertNotIn("Invalid map name", response["message"])


if __name__ == "__main__":
    unittest.main()
