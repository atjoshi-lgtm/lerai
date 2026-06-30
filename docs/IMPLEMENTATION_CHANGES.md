# Implementation Changes

This file records implementation work done after the handoff documentation and quality review were created. It explains what changed, why it changed, how the change reduces risk, and how it was validated without access to a running Webex bot or web server.

## 2026-06-30: No-Server Safety Pass

### Scope

This pass focused on two immediate high-impact changes that can be implemented and tested locally:

1. Harden the promotion approval flow so approval tokens are signed and expire.
2. Remove mutable global DP data state so concurrent DP workflows do not share hidden state.

No Webex bot server, MySQL database, Azure OpenAI endpoint, LeROY endpoint, or internal HTTP service was used for validation. Tests use pure functions and mocks.

## Promotion Approval Hardening

### Files Changed

- `lerai/promote.py`
- `tests/test_promote_security.py`
- `docs/IMPLEMENTATION_CHANGES.md`

### What Changed

#### 1. Approval tokens are now signed

Before this change, `create_approval_token()` produced a base64-url encoded string containing:

```text
sender_email|approver_email|webex_space|original_token|timestamp
```

That encoding was reversible and had no signature. Anyone who knew the format could inspect token contents, and there was no cryptographic integrity check.

Now `create_approval_token()` creates a versioned token:

```text
v2.<base64url-json-payload>.<base64url-hmac-signature>
```

The payload includes:

```json
{
  "version": "v2",
  "sender": "requester email",
  "approver": "approver email",
  "webex_space": "source space id or empty string",
  "original_token": "LeROY promotion token",
  "timestamp": 1234567890
}
```

The signature is HMAC-SHA256 over the encoded payload.

### Why This Changed

The approval flow can trigger a production action through `LEROY_AGENT_PROMOTE_URL`. Base64 encoding was not enough protection because it only obscured fields; it did not prove that the token was created by the bot.

HMAC signing means the bot can reject tokens that were modified or fabricated without the server-held secret.

### New Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `PROMOTION_TOKEN_SECRET` | Yes for `/promote` and `/approve` | Secret used to sign and verify approval tokens. |
| `PROMOTION_TOKEN_TTL_SECONDS` | No | Token lifetime in seconds. Defaults to `3600`. |

`PROMOTION_TOKEN_SECRET` must not be committed to source control. Generate it through the deployment secret system. A local development value can be generated with a command such as `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

#### 2. Approval tokens now expire

`decode_approval_token()` checks the timestamp embedded in the signed payload. Tokens are accepted only if:

- the signature is valid,
- required fields are present,
- the token version is supported,
- the timestamp is not in the future,
- the token age is within `PROMOTION_TOKEN_TTL_SECONDS`.

### Why This Changed

The old token included a timestamp but did not enforce it. That meant an old leaked approval token could remain useful indefinitely. Expiry reduces the blast radius of leaked or forgotten approval messages.

#### 3. `/promote` parsing is deterministic

Before this change, `handle_promotion_request()` sent the user's free-form message to Azure OpenAI and asked the model to extract `approver` and `token` JSON fields.

Now it uses `parse_promote_message()` with deterministic patterns. Supported forms include:

```text
/promote approver=Bruce token=abc123
/promote approver:Bruce token:abc123
/promote ask Bruce token abc123
/promote Bruce, token: abc123
```

If parsing fails, the bot returns a clear usage message:

```text
Please use: `/promote approver=<name> token=<token>`
```

### Why This Changed

Promotion is a production-action workflow. Extracting the approver and token through an LLM made the workflow slower, harder to test, and vulnerable to prompt formatting changes or prompt injection. Deterministic parsing removes that source of randomness.

#### 4. Approver lookup is case-insensitive

`_resolve_approver()` first checks for an exact key in `APPROVED_USERS`, then falls back to case-insensitive matching.

### Why This Changed

This keeps deterministic parsing user-friendly without involving the LLM. For example, `bruce`, `Bruce`, and `BRUCE` can resolve to the same configured approver name if the map has one matching key.

#### 5. External dependencies are deferred

`promote.py` no longer imports `requests` or `WebexTeamsAPI` at module import time. Instead, `_load_requests()` and `_load_webex_api()` import them when a workflow actually needs them.

### Why This Changed

No-server unit tests need to import pure functions such as `parse_promote_message()` and `decode_approval_token()` even when runtime dependencies are not installed in the local environment. Deferring these imports keeps tests lightweight and focused.

### Compatibility Notes

This change intentionally rejects old unsigned approval tokens. Because the bot is not currently running on a server in this environment, there should be no active pending approvals created by the old code. If an environment might have pending old tokens, coordinate rollout and ask users to re-request promotion after deployment.

## DP Global State Removal

### Files Changed

- `lerai/DP_AMA.py`
- `lerai/lerai_commands.py`
- `tests/test_dp_ama_state.py`
- `docs/IMPLEMENTATION_CHANGES.md`

### What Changed

#### 1. Removed `dplist_save`

Before this change, `DP_AMA.py` used a module-level global named `dplist_save`.

- `summarize_dps()` wrote to it.
- `create_dp_candiate_answer()` wrote to it.
- `verify_dp_candiate_answer()` read from it.

Now DP data is request-scoped:

- `fetch_dp_info()` fetches DP data from MySQL.
- `summarize_dps(userquestion, dpinfo="")` uses provided `dpinfo` or fetches it.
- `create_dp_candiate_answer(userquestion, dpinfo="")` uses provided `dpinfo` or fetches it.
- `verify_dp_candiate_answer(userquestion, candidate_answer, dpinfo="")` uses provided `dpinfo` or fetches it.

### Why This Changed

Module-level mutable state can be overwritten by concurrent Webex requests. The verification path had a hidden dependency on whichever request last populated `dplist_save`. Passing DP data explicitly makes the data flow visible and avoids cross-request contamination.

#### 2. `LRDPDevCommand` now uses one local DP snapshot

The development DP command now fetches DP data once:

```python
dpinfo = fetch_dp_info()
candidate_answer = create_dp_candiate_answer(full_text, dpinfo=dpinfo)
verification = verify_dp_candiate_answer(full_text, candidate_answer, dpinfo=dpinfo)
```

### Why This Changed

Candidate generation and verification should use the same input dataset. Fetching once also avoids redundant database calls in that workflow.

#### 3. MySQL dependency is deferred for DP tests

`DP_AMA.py` no longer imports `run_mysql_query` at module import time. `fetch_dp_info()` imports it only when DP data is actually fetched.

### Why This Changed

The local no-server environment does not have `pymysql` installed. Deferring the import lets tests validate request-scoped DP behavior without a database client.

## Tests Added

### `tests/test_promote_security.py`

Covers:

- deterministic parser with `approver=... token=...`, `ask ... token ...`, and `name, token: ...` formats,
- unknown promote message format,
- signed token round trip,
- tampered token rejection,
- expired token rejection,
- missing `PROMOTION_TOKEN_SECRET` failure.

### `tests/test_dp_ama_state.py`

Covers:

- `DP_AMA.py` no longer exposes `dplist_save`,
- DP functions use passed `dpinfo` without fetching,
- verification fetches data only when `dpinfo` is not provided.

## Validation Performed

The following validations were run after implementation:

```bash
python3 -m py_compile lerai/promote.py
python3 -m unittest tests.test_promote_security
python3 -m py_compile lerai/DP_AMA.py lerai/lerai_commands.py
python3 -m unittest tests.test_dp_ama_state
```

A broader validation pass should also be run before committing:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state
python3 -m compileall .
```

## Remaining Follow-Up Work

These are still open after this pass:

1. Add centralized config validation for all environment variables and cert paths.
2. Replace high-risk `print()` calls with structured logging and redaction.
3. Add TOML parsing and schema validation for LeROY override generation.
4. Add request correlation ids at command entry.
5. Add retry wrappers for idempotent external service reads.
6. Normalize package imports and remove the root `sys.path.insert` workaround when safe.
