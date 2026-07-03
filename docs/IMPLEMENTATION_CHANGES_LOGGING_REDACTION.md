# Implementation Changes: Structured Logging and Redaction

This file documents the no-server logging hardening pass. It records what changed, why it changed, and how it was validated without access to a running Webex bot, MySQL database, Azure OpenAI endpoint, LeROY endpoint, or internal HTTP services.

## Scope

This pass replaced active high-risk `print()` calls with Python `logging` calls and added a shared redaction helper for values that may contain secrets or personally identifiable information.

The goal was not to redesign observability end to end. The goal was to stop raw user input, tokens, prompts, response bodies, and internal identifiers from being emitted through direct console prints.

## Files Changed

- `lerai/logging_utils.py`
- `tests/test_logging_utils.py`
- `lerai/lerai_commands.py`
- `lerai/promote.py`
- `lerai/scheduled_jobs.py`
- `lerai/FD_AMA.py`
- `lerai/leroy_overrides_writer.py`
- `lerai/csv_env_diff.py`
- `lerai/expected_observed_comparison.py`
- `lerai/DP_AMA.py`
- `lerai/lerai_main.py`
- `lerai/log_error_summary.py`

## What Changed

### 1. Added shared redaction helpers

`lerai/logging_utils.py` now provides:

| Helper | Purpose |
| --- | --- |
| `redact_value(value)` | Redacts sensitive values from strings, mappings, and sequences before logging. |
| `log_user_request(logger, command, message, activity)` | Logs command entry with redacted user email and message content. |
| `configure_default_logging(level)` | Configures a default logging handler when the process has not configured one yet. |

`redact_value()` currently redacts:

- email addresses,
- bearer tokens,
- signed promotion-token-like values,
- inline `token=...`, `secret=...`, `api_key=...`, `authorization=...`, `cert_path=...`, and `key_path=...` patterns,
- sensitive mapping keys such as `token`, `secret`, `api_key`, `cert_path`, and `key_path`.

### Why This Changed

Many existing debug prints emitted raw operational data. Some examples were user messages, approval tokens, Webex access tokens, prompts sent to LLMs, and upstream response bodies. Those values can contain secrets or production context and should not be printed directly.

### 2. Replaced command-router request prints

`lerai/lerai_commands.py` now uses `log_user_request()` in command `pre_execute()` methods instead of printing:

```text
[USER REQUEST] User: ... | Command: ... | Message: ...
```

The override writer command now logs redacted `message`, `attachment_actions`, and `activity` values instead of printing the whole request object.

### Why This Changed

Command entry logs are useful, but raw Webex messages and activity payloads can include tokens, internal identifiers, or PII. The new helper preserves the event while redacting sensitive content.

### 3. Replaced promotion workflow prints

`lerai/promote.py` now logs promotion-agent stdout/stderr and routing information through `logger.info()` with redaction.

Connection failures now use `logger.exception()` instead of `print()`.

### Why This Changed

The promotion path is production-action code. It previously printed LeROY stdout/stderr and Webex space information directly. That information may include operational details and should go through redaction before entering logs.

### 4. Replaced scheduled job prints

`lerai/scheduled_jobs.py` now uses logger calls for:

- missing environment variables,
- daily job start events,
- daily job failures.

The previous offload job printed the Webex token and space id. The replacement does not log the token and redacts the space id.

### Why This Changed

Scheduled jobs run unattended, so their logs are likely to be retained or scraped by external systems. Tokens and space ids should not be printed directly.

### 5. Replaced LLM prompt and response debug prints

`lerai/FD_AMA.py` and `lerai/leroy_overrides_writer.py` now use `logger.debug()` for prompts, messages, tool calls, tool outputs, and final content. Values are passed through `redact_value()` before logging.

### Why This Changed

LLM prompts and tool outputs may contain user text, internal schemas, operational data, and generated configuration. Debugging remains possible, but raw prompt dumps are no longer printed to stdout.

### 6. Replaced service workflow and manual CLI prints

The following modules now use logger calls instead of active prints:

- `lerai/csv_env_diff.py`
- `lerai/expected_observed_comparison.py`
- `lerai/DP_AMA.py`
- `lerai/lerai_main.py`
- `lerai/log_error_summary.py`

Manual `__main__` paths now log generated summaries or outputs through redaction.

## Tests Added

### `tests/test_logging_utils.py`

Covers:

- sensitive mapping key redaction,
- email redaction,
- inline secret assignment redaction,
- bearer token redaction,
- signed approval-token-like value redaction.

## Validation Performed

Focused validation commands run during this pass:

```bash
python3 -m unittest tests.test_logging_utils
python3 -m py_compile lerai/lerai_commands.py lerai/promote.py lerai/scheduled_jobs.py
python3 -m py_compile lerai/FD_AMA.py lerai/leroy_overrides_writer.py lerai/csv_env_diff.py lerai/expected_observed_comparison.py lerai/DP_AMA.py lerai/lerai_main.py
python3 -m py_compile lerai/log_error_summary.py
```

A scan for active Python `print()` calls was also run during this pass and found no uncommented matches at that time.

Current repository state includes manual CLI `print()` usage in `lerai/leroy_overrides_writer.py` under the `__main__` path. These calls are for direct CLI output and are not part of Webex command handling.

## Remaining Follow-Up Work

1. Decide which log fields should become stable production observability fields.
2. Add request correlation ids at command entry and pass them into downstream workflows.
3. Review user-facing error strings that still include raw exception text.
4. Configure logging format and handlers explicitly in the deployment environment.
