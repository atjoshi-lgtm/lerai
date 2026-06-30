import json
import unittest

from lerai.query2_variance_addition import handle_response as handle_variance_response
from lerai.quota_exceed import handle_response as handle_quota_response


class Query2VarianceResponseTests(unittest.TestCase):
    def test_variance_empty_result_is_quiet_when_silent(self):
        response = json.dumps(
            {
                "returncode": 0,
                "stdout": "[['region', 'regionname', 'vsize_limit']]",
                "stderr": "",
            }
        )

        self.assertEqual(handle_variance_response(response, silent=True), "")

    def test_variance_formats_regions_that_need_updates(self):
        response = json.dumps(
            {
                "returncode": 0,
                "stdout": "[['region', 'regionname', 'vsize_limit'], ['123', 'Example LR', 100]]",
                "stderr": "",
            }
        )

        result = handle_variance_response(response, silent=False)

        self.assertIn("123", result)
        self.assertIn("Example LR", result)


class QuotaResponseTests(unittest.TestCase):
    def test_quota_empty_result_is_quiet_when_silent(self):
        response = json.dumps(
            {
                "returncode": 0,
                "stdout": "[['region', 'regionname', 'vsize_limit']]",
                "stderr": "",
            }
        )

        self.assertEqual(handle_quota_response(response, silent=True), "")

    def test_quota_formats_region_quota_exceedance(self):
        response = json.dumps(
            {
                "returncode": 0,
                "stdout": "[['physregion', 'fp_config_name', 'objcount_max', 'objectlimit', 'objcount', 'objcount_quota'], ['123', 'fp-config', 10, 20, 105, 100]]",
                "stderr": "",
            }
        )

        result = handle_quota_response(response, silent=False)

        self.assertIn("LR 123", result)
        self.assertIn("fp-config", result)
        self.assertIn("105", result)
        self.assertIn("100", result)


if __name__ == "__main__":
    unittest.main()
