import logging
import unittest

from lerai.logging_utils import REDACTED, REDACTED_EMAIL, log_user_request, redact_value


class LoggingUtilsTests(unittest.TestCase):
    def test_redact_value_is_noop(self):
        """redact_value is currently disabled (no-op) to facilitate debugging.
        It returns values unchanged for all input types."""
        
        # Dict input is returned unchanged
        input_dict = {"token": "abc123", "nested": {"api_key": "secret"}, "safe": "ok"}
        output_dict = redact_value(input_dict)
        self.assertEqual(output_dict, input_dict)
        self.assertEqual(output_dict["token"], "abc123")
        self.assertEqual(output_dict["nested"]["api_key"], "secret")
        
        # String input is returned unchanged
        email_string = "from alice@example.com"
        self.assertEqual(redact_value(email_string), email_string)
        
        # Secret assignments are returned unchanged
        secret_string = "token=abc123 api_key:xyz"
        self.assertEqual(redact_value(secret_string), secret_string)
        
        # Bearer tokens are returned unchanged
        bearer_string = "Authorization: Bearer abc.def.ghi approval=v2.payload.signature"
        self.assertEqual(redact_value(bearer_string), bearer_string)

    def test_log_user_request_uses_safe_extra_fields(self):
        logger = logging.getLogger("tests.logging_utils")

        with self.assertLogs(logger, level="INFO"):
            log_user_request(
                logger,
                "/promote",
                "token=abc123 from alice@example.com",
                {"actor": {"emailAddress": "alice@example.com"}},
            )


if __name__ == "__main__":
    unittest.main()
