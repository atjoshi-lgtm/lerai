import unittest

from openai_agent.openai_agent_client import _build_payload


class OpenAIAgentClientPayloadTests(unittest.TestCase):
    def test_build_payload_converts_functions_to_tools(self):
        functions = [
            {
                "name": "lookup",
                "description": "Look up data.",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

        payload = _build_payload(
            messages=[{"role": "user", "content": "hello"}],
            functions=functions,
            function_call="auto",
        )

        self.assertNotIn("functions", payload)
        self.assertNotIn("function_call", payload)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["tools"], [{"type": "function", "function": functions[0]}])

    def test_build_payload_honors_model_and_generation_controls(self):
        payload = _build_payload(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4.1",
            temperature=0,
            top_p=0.1,
            seed=123,
            max_completion_tokens=42,
        )

        self.assertEqual(payload["model"], "gpt-4.1")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["top_p"], 0.1)
        self.assertEqual(payload["seed"], 123)
        self.assertEqual(payload["max_completion_tokens"], 42)

    def test_build_payload_converts_named_function_choice(self):
        payload = _build_payload(
            messages=[{"role": "user", "content": "hello"}],
            functions=[{"name": "lookup", "parameters": {"type": "object"}}],
            function_call={"name": "lookup"},
        )

        self.assertEqual(
            payload["tool_choice"],
            {"type": "function", "function": {"name": "lookup"}},
        )


if __name__ == "__main__":
    unittest.main()
