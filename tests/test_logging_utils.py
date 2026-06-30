import logging
import unittest

from lerai.logging_utils import REDACTED, REDACTED_EMAIL, log_user_request, redact_value


class LoggingUtilsTests(unittest.TestCase):
    def test_redacts_sensitive_mapping_keys(self):
        value = redact_value({"token": "abc123", "nested": {"api_key": "secret"}, "safe": "ok"})

        self.assertEqual(value["token"], REDACTED)
        self.assertEqual(value["nested"]["api_key"], REDACTED)
        self.assertEqual(value["safe"], "ok")

    def test_redacts_email_addresses(self):
        self.assertEqual(redact_value("from alice@example.com"), f"from {REDACTED_EMAIL}")

    def test_redacts_inline_secret_assignments(self):
        self.assertEqual(redact_value("token=abc123 api_key:xyz"), f"token={REDACTED} api_key:{REDACTED}")

    def test_redacts_bearer_and_signed_tokens(self):
        text = "Authorization: Bearer abc.def.ghi approval=v2.payload.signature"

        redacted = redact_value(text)

        self.assertNotIn("abc.def.ghi", redacted)
        self.assertNotIn("v2.payload.signature", redacted)
        self.assertIn(REDACTED, redacted)

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
