import logging
import re
from collections.abc import Mapping, Sequence


REDACTED = "[REDACTED]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cert",
    "cert_path",
    "key",
    "key_path",
    "password",
    "secret",
    "token",
}

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
BEARER_RE = re.compile(r"\bBearer\s+[^\s,;]+", re.IGNORECASE)
PROMOTION_TOKEN_RE = re.compile(r"\bv\d+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
KEY_VALUE_SECRET_RE = re.compile(
    r"\b(token|secret|api[_-]?key|authorization|cert[_-]?path|key[_-]?path)\s*([:=])\s*([^\s,;]+)",
    re.IGNORECASE,
)


def _is_sensitive_key(key):
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEYS)


def redact_value(value):
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]

    if value is None:
        return None

    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    text = BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = PROMOTION_TOKEN_RE.sub(REDACTED, text)
    text = KEY_VALUE_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text)
    text = EMAIL_RE.sub(REDACTED_EMAIL, text)
    return text


def log_user_request(logger, command, message, activity):
    actor = activity.get("actor", {}) if isinstance(activity, Mapping) else {}
    logger.info(
        "User request received",
        extra={
            "command": command,
            "user_email": redact_value(actor.get("emailAddress", "Unknown")),
            "request_message": redact_value(message or "None"),
        },
    )


def configure_default_logging(level=logging.INFO):
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
