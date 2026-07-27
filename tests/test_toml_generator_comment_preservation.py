import unittest

import tomlkit

from lerai.overrides_pipeline.toml_generator import execute_ast_update


class TomlGeneratorCommentPreservationTests(unittest.TestCase):
    def test_delete_preserves_adjacent_comments(self):
        original = """# top comment A
[[override-records]]
# comment on seed record
Ticket-id = "SEED"
Mapnames = ["seed"]
Region-number = [0]
Access-control = "allowed"

[[override-records]]
# comment on first record
Ticket-id = "A"
Mapnames = ["x"]
Region-number = [1]
Access-control = "must-exclude"

# comment before second record
[[override-records]]
Ticket-id = "B"
Mapnames = ["y"]
Region-number = [2]
Access-control = "allowed"
"""

        doc = tomlkit.parse(original)
        updated = execute_ast_update(
            doc,
            target_intents=[
                {
                    "Ticket-id": "A",
                    "Mapnames": ["x"],
                    "Region-number": [1],
                    "Access-control": "must-exclude",
                }
            ],
            new_intents=[],
            conflict_rules={
                "scope_keys": [
                    "Region-default",
                    "Region-geo",
                    "Region-country",
                    "Region-metro",
                    "Region-number",
                ],
                "metadata_keys": ["Ticket-id", "Start-time", "End-time", "Mapnames"],
            },
        )

        rendered = tomlkit.dumps(updated)
        self.assertIn("# top comment A", rendered)
        self.assertIn("# comment on seed record", rendered)
        self.assertIn("# comment on first record", rendered)
        self.assertIn("# comment before second record", rendered)
        self.assertIn('Ticket-id = "SEED"', rendered)
        self.assertIn('Ticket-id = "B"', rendered)
        self.assertNotIn('Ticket-id = "A"', rendered)
        self.assertIn(
            "# comment before second record\n[[override-records]]\nTicket-id = \"B\"",
            rendered,
        )
        self.assertNotIn(
            "[[override-records]]\n# comment before second record\nTicket-id = \"B\"",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()