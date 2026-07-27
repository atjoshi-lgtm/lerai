import unittest
from pathlib import Path

from lerai.overrides_pipeline.conflict_detector import detect_conflicts


class ConflictDetectorObjectCountTests(unittest.TestCase):
    def test_object_count_quota_conflicts_with_existing_mm3_override(self):
        toml_content = Path(__file__).resolve().parent.parent / "override.toml"
        existing_toml = toml_content.read_text(encoding="utf-8")

        intent = {
            "Mapnames": ["mm3"],
            "Geographical-Scope": {"Region-number": [53419]},
            "Override-Directive": {"Object-count-quota-pct": [30]},
        }

        conflicts = detect_conflicts(intent, existing_toml)
        ticket_ids = {conflict["ticket_id"] for conflict in conflicts}

        self.assertIn("LEROYOPS-49", ticket_ids)
        self.assertTrue(
            any(
                conflict["ticket_id"] == "LEROYOPS-49"
                and conflict["conflict_type"] == "DIRECT_COLLISION"
                for conflict in conflicts
            )
        )


if __name__ == "__main__":
    unittest.main()