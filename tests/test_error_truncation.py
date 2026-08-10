import os
import unittest
from unittest.mock import patch

from lerai.error_truncation import (
    ABSOLUTE_MAX_ERROR_TEXT_CHARS,
    DEFAULT_ERROR_TEXT_MAX_CHARS,
    get_error_text_max_chars,
    truncate_with_marker,
)


class ErrorTruncationTests(unittest.TestCase):
    def test_uses_default_when_env_missing_or_invalid(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LERAI_ERROR_TEXT_MAX_CHARS", None)
            self.assertEqual(get_error_text_max_chars(), DEFAULT_ERROR_TEXT_MAX_CHARS)

        with patch.dict(os.environ, {"LERAI_ERROR_TEXT_MAX_CHARS": "invalid"}, clear=False):
            self.assertEqual(get_error_text_max_chars(), DEFAULT_ERROR_TEXT_MAX_CHARS)

    def test_caps_env_limit_at_absolute_max(self):
        oversized = str(ABSOLUTE_MAX_ERROR_TEXT_CHARS * 10)
        with patch.dict(os.environ, {"LERAI_ERROR_TEXT_MAX_CHARS": oversized}, clear=False):
            self.assertEqual(get_error_text_max_chars(), ABSOLUTE_MAX_ERROR_TEXT_CHARS)

    def test_truncate_with_marker_uses_env_limit(self):
        with patch.dict(os.environ, {"LERAI_ERROR_TEXT_MAX_CHARS": "10"}, clear=False):
            value = "abcdefghijklmnopqrstuvwxyz"
            clipped = truncate_with_marker(value, "sample")

        self.assertTrue(clipped.startswith("abcdefghij"))
        self.assertIn("[TRUNCATED field=sample", clipped)
        self.assertIn("shown_chars=10", clipped)


if __name__ == "__main__":
    unittest.main()
