import unittest

from lerai.override_agent.tools import _compact_deploy_result


class CompactDeployResultTests(unittest.TestCase):
    def test_extracts_token_from_offline_diff_string(self):
        response = {
            "success": True,
            "returncode": 0,
            "offline_diff": "{'token': 'abc123', 'diffs': {'blc.csv': {'diff': '...'}}}",
        }

        compact = _compact_deploy_result(response)

        self.assertEqual(compact["ok"], True)
        self.assertEqual(compact["success"], True)
        self.assertEqual(compact["returncode"], 0)
        self.assertEqual(compact["offline_token"], "abc123")
        self.assertNotIn("offline_diff", compact)

    def test_handles_invalid_offline_diff_string(self):
        response = {
            "success": "true",
            "returncode": "0",
            "offline_diff": "not-a-dict",
        }

        compact = _compact_deploy_result(response)

        self.assertEqual(compact["ok"], True)
        self.assertEqual(compact["success"], True)
        self.assertEqual(compact["returncode"], "0")
        self.assertNotIn("offline_token", compact)


if __name__ == "__main__":
    unittest.main()
