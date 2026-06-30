import json
import os
from pathlib import Path


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def int_env(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "":
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ConfigError(f"Environment variable {name} must be an integer") from exc

    if minimum is not None and value < minimum:
        raise ConfigError(f"Environment variable {name} must be >= {minimum}")
    return value


def bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "":
        return default

    normalized = raw_value.lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"Environment variable {name} must be a boolean")


def json_env(name: str, default=None):
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Environment variable {name} must contain valid JSON") from exc


def require_existing_file_env(name: str) -> str:
    value = required_env(name)
    path = Path(value)
    if not path.is_file():
        raise ConfigError(f"Environment variable {name} points to a missing file: {value}")
    return value


def require_cert_pair(cert_var: str = "CERT_PATH", key_var: str = "KEY_PATH") -> tuple[str, str]:
    return require_existing_file_env(cert_var), require_existing_file_env(key_var)
