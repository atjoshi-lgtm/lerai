import unittest
from unittest.mock import MagicMock, patch

from lerai.api_clients.override_api import submit_offline_override


class SubmitOfflineOverrideTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ",
            {
                "RUN_OFFLINE_OVERRIDE_URL": "https://example.test/run_offline_override",
                "CERT_PATH": "/tmp/test.crt",
                "KEY_PATH": "/tmp/test.key",
            },
            clear=True,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    @patch("lerai.api_clients.override_api.requests.post")
    def test_uses_default_timeout_when_env_not_set(self, mock_post):
        response = MagicMock()
        response.json.return_value = {"stdout": "{'ok': True}"}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        submit_offline_override("[[override-records]]", "token-1")

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 900.0)

    @patch("lerai.api_clients.override_api.requests.post")
    def test_uses_env_timeout_when_set(self, mock_post):
        with patch.dict("os.environ", {"RUN_OFFLINE_OVERRIDE_TIMEOUT_SEC": "900"}):
            response = MagicMock()
            response.json.return_value = {"stdout": "{'ok': True}"}
            response.raise_for_status.return_value = None
            mock_post.return_value = response

            submit_offline_override("[[override-records]]", "token-2")

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 900.0)

    @patch("lerai.api_clients.override_api.requests.post")
    def test_falls_back_to_default_for_invalid_env_timeout(self, mock_post):
        with patch.dict("os.environ", {"RUN_OFFLINE_OVERRIDE_TIMEOUT_SEC": "invalid"}):
            response = MagicMock()
            response.json.return_value = {"stdout": "{'ok': True}"}
            response.raise_for_status.return_value = None
            mock_post.return_value = response

            submit_offline_override("[[override-records]]", "token-3")

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 900.0)

    @patch("lerai.api_clients.override_api.requests.post")
    def test_raises_upstream_error_for_structured_failure_payload(self, mock_post):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": False,
            "returncode": 1,
            "offline_run_errors": [
                "An error occurred: FCS API returned status code 500 with message: <html>"
            ],
            "offline_run_log": "...",
        }
        mock_post.return_value = response

        with self.assertRaisesRegex(
            ValueError,
            r"Offline override failed upstream \(returncode=1\)\. An error occurred: FCS API returned status code 500",
        ):
            submit_offline_override("[[override-records]]", "token-4")

    @patch("lerai.api_clients.override_api.requests.post")
    def test_returns_structured_success_payload_without_stdout(self, mock_post):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "returncode": 0,
            "offline_diff": {"token": "abc123"},
        }
        mock_post.return_value = response

        parsed = submit_offline_override("[[override-records]]", "token-5")

        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["returncode"], 0)

    @patch("lerai.api_clients.override_api.requests.post")
    def test_raises_upstream_error_and_preserves_message_when_no_offline_run_errors(self, mock_post):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": False,
            "returncode": 1,
            "message": "Error: Cmd('git') failed due to: exit code(128)\\n  cmdline: git push --porcelain -- origin\\n  stderr: 'fatal: remote error: Insufficient permissions'",
        }
        mock_post.return_value = response

        with self.assertRaises(ValueError) as ctx:
            submit_offline_override("[[override-records]]", "token-6")

        self.assertIn("Offline override failed upstream (returncode=1).", str(ctx.exception))
        self.assertIn("Error: Cmd('git') failed due to: exit code(128)", str(ctx.exception))
        self.assertIn("message=Error: Cmd('git') failed due to: exit code(128)", str(ctx.exception))

    @patch("lerai.api_clients.override_api.requests.post")
    def test_raises_upstream_error_and_preserves_stderr_and_log(self, mock_post):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": False,
            "returncode": 2,
            "stderr": "fatal: Could not read from remote repository.",
            "offline_run_log": "line1\\nline2",
        }
        mock_post.return_value = response

        with self.assertRaises(ValueError) as ctx:
            submit_offline_override("[[override-records]]", "token-7")

        self.assertIn("Offline override failed upstream (returncode=2).", str(ctx.exception))
        self.assertIn("stderr=fatal: Could not read from remote repository.", str(ctx.exception))
        self.assertIn("offline_run_log=line1\\nline2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
