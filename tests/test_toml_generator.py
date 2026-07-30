import unittest

import tomlkit

from lerai.overrides_pipeline.toml_generator import execute_ast_update


class TomlGeneratorNormalizationTests(unittest.TestCase):
    def test_execute_ast_update_deletes_record_with_mixed_type_target_intent(self):
        original = """[[override-records]]
Ticket-id = "TEST-1"
Mapnames = ["mm2"]
Region-number = ["50535", "50565"]
Access-control = "must-exclude"
"""

        doc = tomlkit.parse(original)

        target_intents = [
            {
                "Ticket-id": "TEST-1",
                "Mapnames": [" MM2 "],
                "Region-number": [50535, "  50565  "],
                "Access-control": "must-exclude",
            }
        ]

        conflict_rules = {
            "scope_keys": ["Region-number"],
            "metadata_keys": ["Ticket-id"],
        }

        updated = execute_ast_update(
            doc=doc,
            target_intents=target_intents,
            new_intents=[],
            conflict_rules=conflict_rules,
        )

        records = updated.get("override-records")
        self.assertIsNotNone(records)
        self.assertEqual(len(records), 0)


if __name__ == "__main__":
    unittest.main()