import unittest
from unittest.mock import patch

from lerai.promote import (
    create_approval_token,
    decode_approval_token,
    parse_promote_message,
)


class PromoteParserTests(unittest.TestCase):
    def test_parse_approver_equals_token_equals(self):
        approver, token = parse_promote_message("/promote approver=Bruce token=abc123")

        self.assertEqual(approver, "Bruce")
        self.assertEqual(token, "abc123")

    def test_parse_ask_name_token(self):
        approver, token = parse_promote_message("/promote ask Bruce token abc123")

        self.assertEqual(approver, "Bruce")
        self.assertEqual(token, "abc123")

    def test_parse_name_token_colon(self):
        approver, token = parse_promote_message("/promote Bruce, token: abc123")

        self.assertEqual(approver, "Bruce")
        self.assertEqual(token, "abc123")

    def test_parse_unknown_format(self):
        approver, token = parse_promote_message("please promote this whenever possible")

        self.assertIsNone(approver)
        self.assertIsNone(token)


class PromotionTokenTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ",
            {
                "PROMOTION_TOKEN_SECRET": "test-secret",
                "PROMOTION_TOKEN_TTL_SECONDS": "3600",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_signed_token_round_trip(self):
        with patch("lerai.promote.time.time", return_value=1000):
            token = create_approval_token("alice@example.com", "bob@example.com", "room-1", "original-token")

        with patch("lerai.promote.time.time", return_value=1200):
            decoded = decode_approval_token(token)

        self.assertEqual(decoded["sender"], "alice@example.com")
        self.assertEqual(decoded["approver"], "bob@example.com")
        self.assertEqual(decoded["webex_space"], "room-1")
        self.assertEqual(decoded["original_token"], "original-token")
        self.assertEqual(decoded["timestamp"], "1000")

    def test_tampered_token_is_rejected(self):
        with patch("lerai.promote.time.time", return_value=1000):
            token = create_approval_token("alice@example.com", "bob@example.com", "room-1", "original-token")

        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        with patch("lerai.promote.time.time", return_value=1200):
            self.assertIsNone(decode_approval_token(tampered))

    def test_expired_token_is_rejected(self):
        with patch("lerai.promote.time.time", return_value=1000):
            token = create_approval_token("alice@example.com", "bob@example.com", "room-1", "original-token")

        with patch("lerai.promote.time.time", return_value=5000):
            self.assertIsNone(decode_approval_token(token))

    def test_missing_secret_blocks_token_creation(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                create_approval_token("alice@example.com", "bob@example.com", "room-1", "original-token")


if __name__ == "__main__":
    unittest.main()
