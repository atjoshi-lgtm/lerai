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


if __name__ == "__main__":
    unittest.main()
