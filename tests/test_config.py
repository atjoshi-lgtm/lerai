import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lerai.config import (
    ConfigError,
    bool_env,
    int_env,
    json_env,
    optional_env,
    require_cert_pair,
    require_existing_file_env,
    required_env,
)


class ConfigHelperTests(unittest.TestCase):
    def test_required_env_returns_present_value(self):
        with patch.dict("os.environ", {"LERAI_TEST_VALUE": "present"}, clear=True):
            self.assertEqual(required_env("LERAI_TEST_VALUE"), "present")

    def test_required_env_rejects_missing_value(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ConfigError):
                required_env("LERAI_TEST_VALUE")

    def test_optional_env_returns_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(optional_env("LERAI_TEST_VALUE", "fallback"), "fallback")

    def test_int_env_uses_default_and_minimum(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(int_env("LERAI_TEST_INT", 10, minimum=1), 10)

    def test_int_env_rejects_invalid_integer(self):
        with patch.dict("os.environ", {"LERAI_TEST_INT": "abc"}, clear=True):
            with self.assertRaises(ConfigError):
                int_env("LERAI_TEST_INT", 10)

    def test_int_env_rejects_value_below_minimum(self):
        with patch.dict("os.environ", {"LERAI_TEST_INT": "0"}, clear=True):
            with self.assertRaises(ConfigError):
                int_env("LERAI_TEST_INT", 10, minimum=1)

    def test_bool_env_parses_true_and_false(self):
        with patch.dict("os.environ", {"LERAI_TEST_BOOL": "yes"}, clear=True):
            self.assertTrue(bool_env("LERAI_TEST_BOOL"))
        with patch.dict("os.environ", {"LERAI_TEST_BOOL": "off"}, clear=True):
            self.assertFalse(bool_env("LERAI_TEST_BOOL", default=True))

    def test_bool_env_rejects_invalid_value(self):
        with patch.dict("os.environ", {"LERAI_TEST_BOOL": "maybe"}, clear=True):
            with self.assertRaises(ConfigError):
                bool_env("LERAI_TEST_BOOL")

    def test_json_env_parses_json(self):
        with patch.dict("os.environ", {"LERAI_TEST_JSON": json.dumps({"name": "value"})}, clear=True):
            self.assertEqual(json_env("LERAI_TEST_JSON"), {"name": "value"})

    def test_json_env_rejects_invalid_json(self):
        with patch.dict("os.environ", {"LERAI_TEST_JSON": "{"}, clear=True):
            with self.assertRaises(ConfigError):
                json_env("LERAI_TEST_JSON")

    def test_require_existing_file_env(self):
        with tempfile.NamedTemporaryFile() as temp_file:
            with patch.dict("os.environ", {"LERAI_TEST_FILE": temp_file.name}, clear=True):
                self.assertEqual(require_existing_file_env("LERAI_TEST_FILE"), temp_file.name)

    def test_require_existing_file_env_rejects_missing_file(self):
        missing_path = str(Path(tempfile.gettempdir()) / "lerai-missing-config-test-file")
        with patch.dict("os.environ", {"LERAI_TEST_FILE": missing_path}, clear=True):
            with self.assertRaises(ConfigError):
                require_existing_file_env("LERAI_TEST_FILE")

    def test_require_cert_pair(self):
        with tempfile.NamedTemporaryFile() as cert_file, tempfile.NamedTemporaryFile() as key_file:
            with patch.dict("os.environ", {"CERT_PATH": cert_file.name, "KEY_PATH": key_file.name}, clear=True):
                self.assertEqual(require_cert_pair(), (cert_file.name, key_file.name))


if __name__ == "__main__":
    unittest.main()
