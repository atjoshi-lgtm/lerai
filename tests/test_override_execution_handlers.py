from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tomlkit

from lerai.leroy_overrides_writer import (
    commit_override_changes,
    execute_offline_run,
    preview_override_diff,
)


class _FakeGraph:
    def __init__(self, values: dict | None = None):
        self.values = values or {}

    def get_state(self, config):
        return SimpleNamespace(values=dict(self.values), next=[])

    def update_state(self, config, values, as_node=None, task_id=None):
        self.values.update(values)
        return config


class OverrideExecutionHandlerTests(unittest.TestCase):
    def test_preview_override_diff_with_raw_toml_block_appends_draft_intent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            override_path = Path(tmp_dir) / "override.toml"
            override_path.write_text(
                '[[override-records]]\nTicket-id = "LEROYOPS-1"\nRegion-geo = ["NA"]\nMapnames = ["mm2"]\nAccess-control = "must-exclude"\n',
                encoding="utf-8",
            )
            graph = _FakeGraph()
            raw_toml = (
                "```toml\n"
                '[[override-records]]\n'
                'Ticket-id = "LEROYOPS-2"\n'
                'Region-country = ["DE"]\n'
                'Mapnames = ["mm2"]\n'
                'Access-control = "must-exclude"\n'
                "```"
            )

            with patch("lerai.leroy_overrides_writer.ensure_workspace"), patch(
                "lerai.leroy_overrides_writer.get_compiled_graph",
                return_value=graph,
            ), patch(
                "lerai.leroy_overrides_writer.get_override_toml_path",
                return_value=override_path,
            ), patch("lerai.leroy_overrides_writer.write_toml") as mock_write_toml:
                response = preview_override_diff("thread-1", raw_toml)

            self.assertFalse(mock_write_toml.called)
            self.assertTrue(response.startswith("```diff\n"))
            self.assertIn("+[[override-records]]", response)
            self.assertIn('+Region-country = ["DE"]', response)
            self.assertEqual(len(graph.values["draft_intents"]), 1)
            self.assertEqual(graph.values["draft_intents"][0]["action"], "add")
            self.assertEqual(graph.values["draft_intents"][0]["scope_key"], "Region-country")
            self.assertEqual(graph.values["draft_intents"][0]["directive"], "Access-control")

    def test_preview_override_diff_with_natural_language_routes_through_writer(self):
        graph = _FakeGraph()

        def _fake_write_toml(user_question, xml_string=None, force_route=None, thread_id=None, webex_message=None, webex_api=None):
            graph.values["draft_intents"] = [
                {
                    "action": "add",
                    "scope_key": "Region-geo",
                    "scope_value": ["NA"],
                    "directive": "Access-control",
                    "directive_value": "must-exclude",
                }
            ]
            return "ok"

        with tempfile.TemporaryDirectory() as tmp_dir:
            override_path = Path(tmp_dir) / "override.toml"
            override_path.write_text("", encoding="utf-8")

            with patch("lerai.leroy_overrides_writer.ensure_workspace"), patch(
                "lerai.leroy_overrides_writer.get_compiled_graph",
                return_value=graph,
            ), patch(
                "lerai.leroy_overrides_writer.get_override_toml_path",
                return_value=override_path,
            ), patch(
                "lerai.leroy_overrides_writer.write_toml",
                side_effect=_fake_write_toml,
            ) as mock_write_toml:
                response = preview_override_diff("thread-2", "Remove mm2 from North America.")

            self.assertTrue(mock_write_toml.called)
            self.assertIn("```diff", response)
            self.assertIn("+[[override-records]]", response)
            self.assertEqual(graph.values["draft_intents"][0]["scope_key"], "Region-geo")

    def test_commit_override_changes_writes_file_commits_and_clears_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            override_path = Path(tmp_dir) / "override.toml"
            override_path.write_text("", encoding="utf-8")
            graph = _FakeGraph(
                {
                    "draft_intents": [
                        {
                            "action": "add",
                            "scope_key": "Region-geo",
                            "scope_value": ["NA"],
                            "directive": "Access-control",
                            "directive_value": "must-exclude",
                        }
                    ]
                }
            )

            with patch("lerai.leroy_overrides_writer.ensure_workspace"), patch(
                "lerai.leroy_overrides_writer.get_compiled_graph",
                return_value=graph,
            ), patch(
                "lerai.leroy_overrides_writer.get_override_toml_path",
                return_value=override_path,
            ), patch(
                "lerai.leroy_overrides_writer.commit_and_push"
            ) as mock_commit_and_push, patch(
                "lerai.leroy_overrides_writer.get_latest_commit_hash",
                return_value="abc123",
            ):
                response = commit_override_changes("thread-3", "LEROYOPS-42")

            self.assertIn("LEROYOPS-42", response)
            self.assertIn("abc123", response)
            self.assertEqual(graph.values["draft_intents"], [])
            mock_commit_and_push.assert_called_once_with(
                "override.toml",
                commit_message="[LEROYOPS-42] Updated override.toml via LeRAI Webex Bot",
            )
            parsed = tomlkit.parse(override_path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["override-records"][0]["Region-geo"], ["NA"])
            self.assertEqual(parsed["override-records"][0]["Access-control"], "must-exclude")

    def test_execute_offline_run_includes_stdout_stderr_and_commit_hash(self):
        completed = subprocess.CompletedProcess(
            args=["python3", "compute_quota_offline.py"],
            returncode=0,
            stdout="offline stdout\n",
            stderr="offline stderr\n",
        )

        with patch(
            "lerai.leroy_overrides_writer.subprocess.run",
            return_value=completed,
        ) as mock_run, patch(
            "lerai.leroy_overrides_writer.get_latest_commit_hash",
            return_value="def456",
        ):
            response = execute_offline_run()

        mock_run.assert_called_once_with(
            ["python3", "compute_quota_offline.py"],
            capture_output=True,
            text=True,
        )
        self.assertIn("def456", response)
        self.assertIn("offline stdout", response)
        self.assertIn("offline stderr", response)


if __name__ == "__main__":
    unittest.main()