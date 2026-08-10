from __future__ import annotations

import ast
import logging
import os
from typing import Any, Tuple

import requests

from lerai.logging_utils import redact_value

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT_SECONDS = 900.0


def _log_api_request(method: str, url: str, payload: dict[str, Any] | None = None) -> None:
    redacted_url = redact_value(url)
    redacted_payload = redact_value(payload) if payload is not None else None
    logger.info(
        "Override API request method=%s url=%s payload=%s",
        method,
        redacted_url,
        redacted_payload,
        extra={
            "method": method,
            "url": redacted_url,
            "payload": redacted_payload,
        },
    )


def _log_api_response(response: requests.Response, payload: Any | None = None) -> None:
    payload_value = redact_value(payload) if payload is not None else None
    raw_body_preview = None
    if payload is None:
        raw_body_preview = redact_value(response.text[:2000])

    logger.info(
        "Override API response status=%s url=%s reason=%s payload=%s raw_body_preview=%s",
        response.status_code,
        redact_value(response.url),
        redact_value(response.reason),
        payload_value,
        raw_body_preview,
        extra={
            "status_code": response.status_code,
            "url": redact_value(response.url),
            "reason": redact_value(response.reason),
            "payload": payload_value,
            "raw_body_preview": raw_body_preview,
        },
    )


def _safe_json_payload(response: requests.Response) -> Any | None:
    try:
        return response.json()
    except ValueError:
        return None


def _coerce_success_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _looks_like_offline_result(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in ("success", "returncode", "offline_run_errors", "offline_run_log", "stdout")
    )


def _build_upstream_failure_message(payload: dict[str, Any]) -> str:
    errors = payload.get("offline_run_errors")
    if isinstance(errors, list):
        error_text = "; ".join(str(item) for item in errors if item is not None)
    elif errors is None:
        error_text = ""
    else:
        error_text = str(errors)

    returncode = payload.get("returncode")
    if error_text:
        return f"Offline override failed upstream (returncode={returncode}): {error_text}"
    return f"Offline override failed upstream (returncode={returncode})."


def _request_certs() -> Tuple[str, str]:
    cert_path = os.environ.get("CERT_PATH")
    key_path = os.environ.get("KEY_PATH")
    if not cert_path or not key_path:
        raise ValueError("CERT_PATH and KEY_PATH environment variables are required")
    return cert_path, key_path


def fetch_override_and_token() -> tuple[str, str]:
    """Fetch the current override body and optimistic concurrency token."""
    override_token_url = os.environ.get("OVERRIDE_TOKEN_URL")
    if not override_token_url:
        raise ValueError("OVERRIDE_TOKEN_URL environment variable is required")

    cert = _request_certs()
    _log_api_request("GET", override_token_url)

    try:
        response = requests.get(override_token_url, cert=cert, timeout=300)
        _log_api_response(response, payload=_safe_json_payload(response))
        response.raise_for_status()

        payload = response.json()
        stdout = payload.get("stdout", "")
        if not isinstance(stdout, str):
            raise TypeError("override token response field 'stdout' must be a string")

        parsed_stdout = ast.literal_eval(stdout.strip())
        if not isinstance(parsed_stdout, dict):
            raise TypeError("override token stdout must parse to a dictionary")

        token = parsed_stdout.get("token")
        override_body = parsed_stdout.get("override")
        if not isinstance(token, str) or not isinstance(override_body, str):
            raise TypeError("override token stdout must contain string 'token' and 'override' fields")

        logger.info(
            "Parsed override token payload",
            extra={
                "token": redact_value(token),
                "override_length": len(override_body),
            },
        )
        return token, override_body

    except (requests.RequestException, ValueError, TypeError, SyntaxError) as exc:
        logger.exception(
            "Failed to fetch override token payload from override endpoint",
            extra={"error": redact_value(str(exc))},
        )
        raise


def submit_offline_override(updated_toml: str, base_token: str) -> dict[str, Any]:
    """Submit an updated override TOML along with base token for concurrency validation."""
    run_offline_override_url = os.environ.get("RUN_OFFLINE_OVERRIDE_URL")
    if not run_offline_override_url:
        raise ValueError("RUN_OFFLINE_OVERRIDE_URL environment variable is required")

    cert = _request_certs()
    raw_timeout = os.environ.get("RUN_OFFLINE_OVERRIDE_TIMEOUT_SEC")
    timeout_seconds = DEFAULT_HTTP_TIMEOUT_SECONDS
    if raw_timeout is not None:
        try:
            parsed_timeout = float(raw_timeout)
            if parsed_timeout > 0:
                timeout_seconds = parsed_timeout
        except ValueError:
            pass
    request_payload = {
        "updated_toml": updated_toml,
        "base_token": base_token,
    }
    _log_api_request("POST", run_offline_override_url, payload=request_payload)

    try:
        response = requests.post(
            run_offline_override_url,
            json=request_payload,
            cert=cert,
            timeout=timeout_seconds,
        )
        _log_api_response(response, payload=_safe_json_payload(response))
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("offline override response payload must be a dictionary")

        stdout_value = payload.get("stdout")
        parsed_stdout: dict[str, Any]

        if isinstance(stdout_value, str) and stdout_value.strip():
            try:
                maybe_parsed = ast.literal_eval(stdout_value.strip())
            except (ValueError, SyntaxError) as exc:
                if _looks_like_offline_result(payload):
                    raise ValueError(_build_upstream_failure_message(payload)) from exc
                raise
            if not isinstance(maybe_parsed, dict):
                raise TypeError("offline override stdout must parse to a dictionary")
            parsed_stdout = maybe_parsed
        elif _looks_like_offline_result(payload):
            # Some endpoints return the final structured result directly (without stdout wrapping).
            parsed_stdout = payload
        else:
            raise TypeError("offline override response is missing parseable stdout payload")

        if not _coerce_success_flag(parsed_stdout.get("success", True)):
            raise ValueError(_build_upstream_failure_message(parsed_stdout))

        logger.info(
            "Parsed offline override response payload",
            extra={"parsed_stdout": redact_value(parsed_stdout)},
        )
        return parsed_stdout

    except (requests.RequestException, ValueError, TypeError, SyntaxError) as exc:
        logger.exception(
            "Failed to submit offline override payload to endpoint",
            extra={"error": redact_value(str(exc))},
        )
        raise
