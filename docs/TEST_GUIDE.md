# Test Guide

This document explains the current no-server test suite: what each test file checks, why those checks matter, and how to run the tests locally.

The tests are intentionally designed to run without a Webex bot server, MySQL database, Azure OpenAI endpoint, LeROY endpoint, Query2 endpoint, or internal HTTP services. They focus on pure functions, parser behavior, configuration validation, redaction helpers, and mocked workflows.

## How to Run the Tests

Run the full no-server suite from the repository root:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils tests.test_entity_extractor_normalization tests.test_leroy_overrides_writer_query_cases tests.test_leroy_overrides_writer_conflicts_with_fixture
```

Run the compile check:

```bash
python3 -m compileall .
```

Run one test file at a time:

```bash
python3 -m unittest tests.test_promote_security
```

The local environment uses `python3`; `python` may not be available on the PATH.

## Manual Interactive Override-Agent Check

The two most recent `/write_override` commits introduced an interactive LangGraph agent with thread checkpointing and interrupt/resume behavior. In addition to unit tests, run the local CLI harness for a quick manual sanity check:

```bash
python3 test_cli.py
```

What to verify manually:

- The CLI prints a unique session thread id.
- The assistant can ask a follow-up clarification when needed.
- A follow-up answer resumes the same graph session (instead of restarting).
- Interrupt/pause prompts are surfaced clearly and can be resumed with the next reply.
- Requests that span multiple geographical scopes (e.g., "remove mm2 from France and North America") produce two separate TOML stanzas without requiring user clarification.

Debug output from the run is written to `override_agent.log`. Third-party library loggers (`httpx`, `httpcore`, `openai`) are suppressed to `WARNING` level so only application-level messages appear in the log.

## Test Files at a Glance

| Test file | Main purpose |
| --- | --- |
| `tests/test_openai_agent_client.py` | Verifies Azure OpenAI request payload construction without making network calls. |
| `tests/test_query_response_parsing.py` | Verifies Query2 variance and quota response parsing, including malformed responses. |
| `tests/test_promote_security.py` | Verifies deterministic promotion parsing and signed approval-token behavior. |
| `tests/test_dp_ama_state.py` | Verifies DP workflows use request-scoped data instead of global mutable state. |
| `tests/test_config.py` | Verifies shared environment-variable parsing and validation helpers. |
| `tests/test_logging_utils.py` | Verifies logging redaction helpers and safe command-entry logging fields. |
| `tests/test_entity_extractor_normalization.py` | Verifies geographical scope normalization in the entity extractor. |
| `tests/test_leroy_overrides_writer_query_cases.py` | Verifies end-to-end TOML generation output matches fixture-driven query cases. |
| `tests/test_leroy_overrides_writer_conflicts_with_fixture.py` | Verifies conflict detection behavior against a fixture `override.toml` using JSON-defined conflict cases. |

## `tests/test_openai_agent_client.py`

This file tests `_build_payload()` in `openai_agent/openai_agent_client.py`.

These tests do not call Azure OpenAI. They only validate the JSON payload that would be sent to the Azure OpenAI HTTP endpoint.

### `test_build_payload_converts_functions_to_tools`

Checks that legacy OpenAI `functions` input is converted to modern `tools` format:

- `functions` is not included in the final payload.
- `function_call` is not included in the final payload.
- `tools` contains function definitions in modern tool-call shape.
- `tool_choice` defaults to the converted selection behavior.

Why it matters: the repo still has code that uses old function-calling conventions. This test protects the adapter logic that keeps those callers working with the newer tool-call API.

### `test_build_payload_honors_model_and_generation_controls`

Checks that `_build_payload()` preserves key model and generation settings:

- `model`
- `temperature`
- `top_p`
- `seed`
- `max_completion_tokens`

Why it matters: earlier client code ignored or hard-coded some request options. This test makes sure callers can control model behavior predictably.

### `test_build_payload_converts_named_function_choice`

Checks that a legacy named function choice like:

```python
{"name": "lookup"}
```

becomes the modern tool choice shape:

```python
{"type": "function", "function": {"name": "lookup"}}
```

Why it matters: workflows that force a specific function/tool need deterministic conversion instead of relying on the model to choose.

## `tests/test_query_response_parsing.py`

This file tests pure response parsing for Query2 workflows:

- `lerai/query2_variance_addition.py`
- `lerai/quota_exceed.py`

The tests do not call Query2. They pass synthetic JSON strings directly into `handle_response()`.

## Variance Response Tests

### `test_variance_empty_result_is_quiet_when_silent`

Checks that an empty variance result returns an empty string when `silent=True`.

Why it matters: scheduled jobs should stay quiet when there is nothing actionable.

### `test_variance_formats_regions_that_need_updates`

Checks that a valid variance row is included in the formatted result.

Why it matters: users need region identifiers and names in the bot response when Query2 finds large regions needing variance changes.

### `test_variance_handles_invalid_json`

Passes invalid JSON and checks that the parser returns a clear error string.

Why it matters: malformed upstream responses should not crash the command handler.

### `test_variance_handles_non_object_json`

Passes valid JSON with the wrong top-level shape, such as `[]`.

Why it matters: Query2 responses are expected to be JSON objects with fields such as `returncode`, `stdout`, and `stderr`.

### `test_variance_handles_short_data_row`

Passes a data row that does not contain enough columns.

Why it matters: the formatter indexes into row fields. This test protects against `IndexError` from malformed rows.

## Quota Response Tests

### `test_quota_empty_result_is_quiet_when_silent`

Checks that an empty quota result returns an empty string when `silent=True`.

Why it matters: the quota check should not create noise when no quota exceedance exists.

### `test_quota_formats_region_quota_exceedance`

Checks that a valid quota exceedance row includes the LR id, fp-config name, current count, and quota in the output.

Why it matters: this is the normal positive-result path users care about.

### `test_quota_handles_invalid_json`

Passes invalid JSON and checks for a clear parser error.

Why it matters: upstream failures should produce diagnostics instead of exceptions.

### `test_quota_handles_short_data_row`

Passes a quota row with missing numeric fields.

Why it matters: malformed rows should be rejected clearly before formatting.

### `test_quota_handles_non_numeric_values`

Passes a row where a numeric field contains text.

Why it matters: quota comparisons are numeric. This protects against crashes and string-comparison mistakes.

## `tests/test_promote_security.py`

This file tests promotion parsing and approval token security in `lerai/promote.py`.

The tests do not call Webex or LeROY. They use pure functions and patched environment variables/time.

## Promote Parser Tests

### `test_parse_approver_equals_token_equals`

Checks this format:

```text
/promote approver=Bruce token=abc123
```

Expected result:

- approver: `Bruce`
- token: `abc123`

### `test_parse_ask_name_token`

Checks this format:

```text
/promote ask Bruce token abc123
```

Expected result:

- approver: `Bruce`
- token: `abc123`

### `test_parse_name_token_colon`

Checks this format:

```text
/promote Bruce, token: abc123
```

Expected result:

- approver: `Bruce`
- token: `abc123`

### `test_parse_unknown_format`

Checks that unsupported free-form text returns `(None, None)`.

Why it matters: promotion is a production-action workflow. Parsing should be deterministic and reject ambiguous input instead of guessing.

## Promotion Token Tests

### `test_signed_token_round_trip`

Creates a signed approval token with a patched timestamp, then decodes it while it is still fresh.

Checks decoded fields:

- requester email
- approver email
- Webex space
- original LeROY token
- timestamp

Why it matters: this proves the normal signed-token path works without involving Webex or LeROY.

### `test_tampered_token_is_rejected`

Changes one character in a valid signed token and checks that decoding returns `None`.

Why it matters: approval tokens must have integrity protection. A modified token should not be accepted.

### `test_expired_token_is_rejected`

Creates a token, advances patched time beyond the configured TTL, and checks that decoding returns `None`.

Why it matters: old approval tokens should not remain valid indefinitely.

### `test_missing_secret_blocks_token_creation`

Clears environment variables and checks that token creation raises `ValueError` when `PROMOTION_TOKEN_SECRET` is missing.

Why it matters: unsigned or weakly configured promotion tokens should fail closed.

## `tests/test_dp_ama_state.py`

This file tests DP workflow state behavior in `lerai/DP_AMA.py`.

The tests do not call MySQL or Azure OpenAI. They patch fetch and LLM helper functions.

### `test_module_no_longer_exposes_dplist_global`

Checks that `DP_AMA.py` no longer exposes `dplist_save`.

Why it matters: the old global variable could leak data between concurrent user requests.

### `test_summarize_uses_passed_dpinfo_without_fetching`

Passes request-scoped DP data into `summarize_dps()` and verifies:

- `fetch_dp_info()` is not called,
- the LLM summarization helper receives the provided DP data and question.

Why it matters: when a workflow already has a DP snapshot, it should use that exact snapshot.

### `test_create_candidate_uses_passed_dpinfo_without_fetching`

Passes request-scoped DP data into `create_dp_candiate_answer()` and verifies no fetch occurs.

Why it matters: candidate generation should not silently use a different dataset than the caller supplied.

### `test_verify_uses_passed_dpinfo_without_fetching`

Passes request-scoped DP data into `verify_dp_candiate_answer()` and verifies no fetch occurs.

Why it matters: verification should check the answer against the same DP data used to create it.

### `test_verify_fetches_dpinfo_when_not_provided`

Calls `verify_dp_candiate_answer()` without `dpinfo` and verifies that `fetch_dp_info()` is called once.

Why it matters: callers that do not provide request-scoped data still get the default fetch behavior.

## `tests/test_config.py`

This file tests shared config helpers in `lerai/config.py`.

The tests patch `os.environ` and use temporary files. They do not depend on real deployment environment variables or certificate files.

### `test_required_env_returns_present_value`

Checks that `required_env()` returns a present environment value.

### `test_required_env_rejects_missing_value`

Checks that `required_env()` raises `ConfigError` when the variable is missing.

Why it matters: required config should fail clearly.

### `test_optional_env_returns_default`

Checks that `optional_env()` returns a fallback when the variable is missing.

### `test_int_env_uses_default_and_minimum`

Checks that `int_env()` can return its default and validate a minimum.

### `test_int_env_rejects_invalid_integer`

Checks that non-integer text raises `ConfigError`.

### `test_int_env_rejects_value_below_minimum`

Checks that values below the allowed minimum raise `ConfigError`.

Why it matters: settings such as timeouts and TTLs should not accept invalid values silently.

### `test_bool_env_parses_true_and_false`

Checks accepted true and false forms, such as `yes` and `off`.

### `test_bool_env_rejects_invalid_value`

Checks that ambiguous boolean text such as `maybe` raises `ConfigError`.

### `test_json_env_parses_json`

Checks that `json_env()` parses a JSON object from an environment variable.

### `test_json_env_rejects_invalid_json`

Checks that malformed JSON raises `ConfigError`.

### `test_require_existing_file_env`

Creates a temporary file and checks that `require_existing_file_env()` accepts that path.

### `test_require_existing_file_env_rejects_missing_file`

Checks that a path to a missing file raises `ConfigError`.

### `test_require_cert_pair`

Creates temporary cert and key files, sets `CERT_PATH` and `KEY_PATH`, and checks that `require_cert_pair()` returns both paths.

Why it matters: mTLS-backed internal HTTP modules need cert/key settings to fail clearly when missing or invalid.

## `tests/test_logging_utils.py`

This file tests shared logging and redaction helpers in `lerai/logging_utils.py`.

### `test_redacts_sensitive_mapping_keys`

Checks that dictionaries with sensitive keys are redacted recursively:

- `token`
- nested `api_key`

It also verifies that non-sensitive keys are preserved.

Why it matters: structured logs often attach dictionaries. Secret-bearing keys should be redacted before logging.

### `test_redacts_email_addresses`

Checks that email addresses are replaced with `[REDACTED_EMAIL]`.

Why it matters: command logs should avoid retaining raw PII unless explicitly required by the deployment policy.

### `test_redacts_inline_secret_assignments`

Checks that inline text like this is redacted:

```text
token=abc123 api_key:xyz
```

Expected result:

```text
token=[REDACTED] api_key:[REDACTED]
```

Why it matters: user messages and error strings may contain `key=value` secret patterns.

### `test_redacts_bearer_and_signed_tokens`

Checks that bearer tokens and signed approval-token-like strings are redacted.

Why it matters: Webex tokens, API bearer tokens, and promotion approval tokens should not appear in logs.

### `test_log_user_request_uses_safe_extra_fields`

Calls `log_user_request()` under `assertLogs()` and verifies it does not crash.

Why it matters: Python logging reserves field names such as `message`. This test protects against using reserved `LogRecord` field names in `extra` data.

## `tests/test_entity_extractor_normalization.py`

This file tests `_normalize_geographical_scope()` in `lerai/overrides_pipeline/entity_extractor.py`.

These tests do not call the LLM. They validate pure normalization logic applied after tool-call argument parsing.

### `test_region_geo_name_is_mapped_to_code`

Checks that a human-readable geo name such as `"North America"` is mapped to its canonical code `"NA"`.

Why it matters: the LLM may return long-form region names. The normalizer must collapse these to codes before conflict detection.

### `test_region_default_geo_code_is_coerced_to_region_geo`

Checks that a scope key of `Region-default` containing a known geo code (e.g., `"NA"`) is promoted to `Region-geo`.

Why it matters: the LLM may choose an imprecise scope key. This coercion ensures the downstream conflict check uses the correct key.

### `test_region_default_global_words_become_default`

Checks that words like `"global"` under `Region-default` are normalized to `"default"`.

Why it matters: `"default"` is the canonical representation of the global scope in the override schema.

### `test_region_metro_spaces_convert_to_underscores`

Checks that metro names with spaces such as `"New York"` are converted to underscore form `"New_York"`.

Why it matters: the TOML schema uses underscored metro identifiers. Mismatched spacing would fail schema validation.

## `tests/test_leroy_overrides_writer_query_cases.py`

This file tests end-to-end TOML generation in `lerai/leroy_overrides_writer.py` using fixture-driven cases from `tests/fixtures/leroy_overrides_writer_query_cases.json`.

The tests patch `extract_intent` and `load_current_toml` so no LLM call or file system read occurs.

### `test_query_cases_match_expected_toml`

For each fixture case, calls `write_toml()` and checks that:

- The response contains `"Override Stanza Generated Successfully"`.
- The generated TOML in the code fence, after round-trip parsing with `tomlkit`, matches the canonical form of the fixture's `expected_toml`.

Why it matters: TOML generation is deterministic after extraction. This test locks in the exact stanza shape for each known query pattern, preventing silent regressions.

## `tests/test_leroy_overrides_writer_conflicts_with_fixture.py`

This file tests conflict detection behavior in `lerai/leroy_overrides_writer.py` using a fixture `override.toml` from `tests/fixtures/override.toml` and conflict cases from `tests/fixtures/leroy_overrides_writer_conflict_cases.json`.

The tests patch `extract_intent` and `load_current_toml` to control inputs without touching the file system or LLM.

### `test_conflict_behavior_matches_fixture_expectations`

For each fixture case, calls `write_toml()` and verifies:

- All `contains` strings appear in the response.
- All `not_contains` strings do not appear in the response.
- `"Error generating override"` is present when `is_error` is true, absent otherwise.
- `"Conflict Detected"` is present when `is_conflict` is true, absent otherwise.

Why it matters: conflict detection is a safety gate on production override writes. This test systematically covers expected conflicts and expected clean paths from a shared fixture base.

## What These Tests Do Not Cover Yet

The suite is useful but intentionally narrow. It does not currently cover:

1. Live Webex bot command execution.
2. Real Azure OpenAI requests.
3. Real MySQL queries.
4. Real Query2, LeROY, Footprint, or internal HTTP endpoints.
5. End-to-end scheduled jobs.
6. Full promotion approval handler behavior with mocked Webex API and LeROY HTTP responses.
7. Request correlation id propagation.
8. Production logging handler configuration.

## Good Next Tests to Add

1. Handler-level tests for `/promote` and `/approve` with mocked Webex and LeROY clients.
2. Config adoption tests as each service module moves to `lerai/config.py` helpers.
3. Tests for user-facing error messages that should not expose raw exception detail.
4. Tests for retry behavior around idempotent read-only HTTP calls.
5. Tests for request correlation id creation and propagation once that feature is added.
