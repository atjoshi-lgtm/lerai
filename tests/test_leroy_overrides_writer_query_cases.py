import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tomlkit

from lerai.leroy_overrides_writer import write_toml


def _extract_toml_block(response_text: str) -> str:
    match = re.search(r"```toml\n(.*?)\n```", response_text, re.DOTALL)
    if not match:
        raise AssertionError(f"Expected TOML code fence in response. Response was:\n{response_text}")
    return match.group(1).strip()


def _canonical_toml(toml_text: str) -> str:
    return tomlkit.dumps(tomlkit.parse(toml_text)).strip()


class LeroyOverridesWriterQueryCasesTests(unittest.TestCase):
    FIXTURE_FILE = Path(__file__).parent / "fixtures" / "leroy_overrides_writer_query_cases.json"

    @classmethod
    def _query_cases(cls) -> list[dict]:
        return json.loads(cls.FIXTURE_FILE.read_text(encoding="utf-8"))

    @staticmethod
    def _intent_for_query(user_question: str, xml_string=None) -> dict:
        for case in LeroyOverridesWriterQueryCasesTests._query_cases():
            if case["query"] == user_question:
                return case["intent"]
        raise AssertionError(f"No test fixture defined for query: {user_question}")

    @staticmethod
    def _mock_graph_for_case(case: dict):
        class _MockGraph:
            def get_state(self, config):
                return SimpleNamespace(next=[])

            def invoke(self, state, config=None):
                return {
                    "messages": [
                        {
                            "type": "ai",
                            "content": f"```toml\n{case['expected_toml'].strip()}\n```",
                        }
                    ]
                }

        return _MockGraph()

    def test_query_cases_match_expected_toml(self):
        with patch("lerai.leroy_overrides_writer.ensure_workspace"), patch(
            "lerai.leroy_overrides_writer.get_compiled_graph"
        ) as mock_get_compiled_graph:
            for case in self._query_cases():
                with self.subTest(query=case["query"]):
                    mock_get_compiled_graph.return_value = self._mock_graph_for_case(case)
                    response = write_toml(case["query"])
                    self.assertIsInstance(response, str)

                    generated_toml = _extract_toml_block(response)
                    expected_toml = case["expected_toml"].strip()

                    self.assertEqual(_canonical_toml(generated_toml), _canonical_toml(expected_toml))


if __name__ == "__main__":
    unittest.main()