import unittest
from unittest.mock import patch

import lerai.DP_AMA as dp_ama


class DPAMAStateTests(unittest.TestCase):
    def test_module_no_longer_exposes_dplist_global(self):
        self.assertFalse(hasattr(dp_ama, "dplist_save"))

    def test_summarize_uses_passed_dpinfo_without_fetching(self):
        with patch("lerai.DP_AMA.fetch_dp_info") as mock_fetch, patch(
            "lerai.DP_AMA.ask_chatgpt_to_summarize_dps", return_value="summary"
        ) as mock_ask:
            result = dp_ama.summarize_dps("question", dpinfo="request scoped data")

        self.assertEqual(result, "summary")
        mock_fetch.assert_not_called()
        mock_ask.assert_called_once_with("request scoped data", "question")

    def test_create_candidate_uses_passed_dpinfo_without_fetching(self):
        with patch("lerai.DP_AMA.fetch_dp_info") as mock_fetch, patch(
            "lerai.DP_AMA.ask_chatgpt_to_create_candidate_answer", return_value="candidate"
        ) as mock_ask:
            result = dp_ama.create_dp_candiate_answer("question", dpinfo="request scoped data")

        self.assertEqual(result, "candidate")
        mock_fetch.assert_not_called()
        mock_ask.assert_called_once_with("request scoped data", "question")

    def test_verify_uses_passed_dpinfo_without_fetching(self):
        with patch("lerai.DP_AMA.fetch_dp_info") as mock_fetch, patch(
            "lerai.DP_AMA.ask_chatgpt_to_verify_candidate_answer", return_value="verified"
        ) as mock_ask:
            result = dp_ama.verify_dp_candiate_answer(
                "question",
                "candidate",
                dpinfo="request scoped data",
            )

        self.assertEqual(result, "verified")
        mock_fetch.assert_not_called()
        mock_ask.assert_called_once_with("request scoped data", "question", "candidate")

    def test_verify_fetches_dpinfo_when_not_provided(self):
        with patch("lerai.DP_AMA.fetch_dp_info", return_value="fresh data") as mock_fetch, patch(
            "lerai.DP_AMA.ask_chatgpt_to_verify_candidate_answer", return_value="verified"
        ) as mock_ask:
            result = dp_ama.verify_dp_candiate_answer("question", "candidate")

        self.assertEqual(result, "verified")
        mock_fetch.assert_called_once_with()
        mock_ask.assert_called_once_with("fresh data", "question", "candidate")


if __name__ == "__main__":
    unittest.main()
