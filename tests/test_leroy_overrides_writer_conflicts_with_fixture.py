import json
import unittest
from pathlib import Path
from unittest.mock import patch

from lerai.leroy_overrides_writer import write_toml


class LeroyOverridesWriterConflictFixtureTests(unittest.TestCase):
    OVERRIDE_FIXTURE_FILE = Path(__file__).parent / "fixtures" / "override.toml"
    CONFLICT_CASES_FILE = Path(__file__).parent / "fixtures" / "leroy_overrides_writer_conflict_cases.json"

    @classmethod
    def setUpClass(cls):
        cls.override_toml_fixture = cls.OVERRIDE_FIXTURE_FILE.read_text(encoding="utf-8")
        cls.conflict_cases = json.loads(cls.CONFLICT_CASES_FILE.read_text(encoding="utf-8"))

    @classmethod
    def _conflict_case_by_query(cls, user_question: str) -> dict:
        for case in cls.conflict_cases:
            if case["query"] == user_question:
                return case
        raise AssertionError(f"No conflict fixture defined for query: {user_question}")

    @classmethod
    def _intent_for_query(cls, user_question: str, xml_string=None) -> dict:
        return cls._conflict_case_by_query(user_question)["intent"]

    def test_conflict_behavior_matches_fixture_expectations(self):
        with patch("lerai.leroy_overrides_writer.extract_intent", side_effect=self._intent_for_query), patch(
            "lerai.leroy_overrides_writer.load_current_toml", return_value=self.override_toml_fixture
        ):
            for case in self.conflict_cases:
                with self.subTest(query=case["query"]):
                    response = write_toml(case["query"])

                    expected = case["expected"]

                    for expected_text in expected.get("contains", []):
                        self.assertIn(expected_text, response)

                    for unexpected_text in expected.get("not_contains", []):
                        self.assertNotIn(unexpected_text, response)

                    if expected.get("is_error"):
                        self.assertIn("Error generating override", response)
                    else:
                        self.assertNotIn("Error generating override", response)

                    if expected.get("is_conflict"):
                        self.assertIn("Conflict Detected", response)
                    else:
                        self.assertNotIn("Conflict Detected", response)


if __name__ == "__main__":
    unittest.main()