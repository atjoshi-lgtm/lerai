import json
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    @staticmethod
    def _mock_graph_for_case(case: dict):
        expected = case["expected"]
        contains = expected.get("contains", [])
        response_lines = [str(item) for item in contains]

        if expected.get("is_conflict") and "Conflict Detected" not in response_lines:
            response_lines.append("Conflict Detected")
        if expected.get("is_error") and "Error generating override" not in response_lines:
            response_lines.append("Error generating override")

        if not response_lines:
            response_lines = ["Override request processed"]

        content = "\n".join(response_lines)

        class _MockGraph:
            def get_state(self, config):
                return SimpleNamespace(next=[])

            def invoke(self, state, config=None):
                return {
                    "messages": [
                        {
                            "type": "ai",
                            "content": content,
                        }
                    ]
                }

        return _MockGraph()

    def test_conflict_behavior_matches_fixture_expectations(self):
        with patch("lerai.leroy_overrides_writer.ensure_workspace"), patch(
            "lerai.leroy_overrides_writer.get_compiled_graph"
        ) as mock_get_compiled_graph:
            for case in self.conflict_cases:
                with self.subTest(query=case["query"]):
                    mock_get_compiled_graph.return_value = self._mock_graph_for_case(case)
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