# Server Access Next Steps

This document explains the immediate next steps once we get access to the server that runs LeRAI. The goal is to verify the runtime environment safely before exercising workflows that can affect production systems.

The first server session should be treated as a discovery and validation pass, not a feature deployment. Avoid triggering `/promote`, `/approve`, or any workflow that changes external state until read-only checks, configuration, and logs look healthy.

## Goals for the First Server Session

1. Confirm which code revision is deployed.
2. Confirm Python version, dependencies, environment variables, certificate paths, and service reachability.
3. Run local no-server tests on the server.
4. Review startup behavior and logs without exposing secrets.
5. Smoke-test read-only bot workflows.
6. Only then test production-action paths in a controlled way.

## Step 1: Identify the Deployed Code

On the server, find the deployed checkout and record:

```bash
pwd
git --no-pager status --short
git --no-pager log -1 --oneline
git --no-pager branch --show-current
```

If the server does not use a Git checkout, record the deployment package version, file timestamps, or whatever release identifier exists.

### Why This Matters

We need to know whether the server is running the code we just hardened locally or an older copy. Debugging is misleading if local code and server code differ.

## Step 2: Confirm Runtime Basics

Run:

```bash
python3 --version
python3 -m pip --version
python3 -m pip list
```

If the server uses a virtual environment, activate it first and then run the same commands.

Also check the process manager:

```bash
ps aux | grep -i lerai
ps aux | grep -i webex
```

If LeRAI is managed by `systemd`, `supervisor`, `pm2`, cron, a container, or another deployment tool, record the service name and restart command, but do not restart yet.

### Why This Matters

The local tests currently run under `python3`. The server may have a different Python version or dependency set. We need that baseline before interpreting failures.

## Step 3: Verify Required Environment Variables Exist

Check that required environment variables are present without printing secret values.

Use a safe presence-only check such as:

```bash
python3 - <<'PY'
import os

names = [
    "WEBEX_ACCESS_TOKEN",
    "WEBEX_SPACE_ID",
    "LR_OFFLOAD_WEBEX_SPACE_ID",
    "AZURE_OPENAI_URL",
    "AZURE_API_KEY",
    "AZURE_USER_ID",
    "AZURE_APP_NAME",
    "AZURE_OPENAI_TIMEOUT",
    "AZURE_OPENAI_VERIFY_SSL",
    "PROMOTION_TOKEN_SECRET",
    "PROMOTION_TOKEN_TTL_SECONDS",
    "CERT_PATH",
    "KEY_PATH",
    "RUN_QUERY2_URL",
    "LOG_ERRORS_URL",
    "EXPECTED_OBSERVED_URL",
    "OFFLINE_PROD_DIFF_ERRORS_URL",
    "LEROY_AGENT_PROMOTE_URL",
    "APPROVED_USERS",
]

for name in names:
    value = os.environ.get(name)
    if value:
        print(f"{name}: set ({len(value)} chars)")
    else:
        print(f"{name}: MISSING")
PY
```

Do not run `env`, `printenv`, or shell history commands that dump secrets into logs.

### Why This Matters

A large fraction of this bot's runtime behavior depends on environment variables. Missing or malformed config should be found before starting or restarting the bot.

## Step 4: Verify Certificate Files Without Printing Contents

Check that the configured mTLS files exist and are readable:

```bash
python3 - <<'PY'
import os
from pathlib import Path

for name in ["CERT_PATH", "KEY_PATH"]:
    value = os.environ.get(name)
    if not value:
        print(f"{name}: MISSING")
        continue
    path = Path(value)
    print(f"{name}: exists={path.exists()} file={path.is_file()} readable={os.access(path, os.R_OK)}")
PY
```

Do not `cat` certificate or key files.

### Why This Matters

Several internal HTTP workflows use client certificate authentication. A missing or unreadable cert/key pair will make those workflows fail even if the code is correct.

## Step 5: Install or Confirm Dependencies

If dependencies are not already installed, use the repository's dependency file:

```bash
python3 -m pip install -r requirements.txt
```

If the server uses a locked deployment environment, do not install directly. Instead, record missing packages and update the deployment process.

### Why This Matters

Local no-server tests were made import-friendly, but the live bot still needs runtime packages such as Webex, scheduler, requests, and PyMySQL-related dependencies.

## Step 6: Run No-Server Validation on the Server

Before starting the bot, run the pure test suite:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils
python3 -m compileall .
```

Expected result:

```text
44 tests passing
compileall completes without syntax errors
```

If these tests fail on the server but pass locally, stop and investigate the server environment before testing Webex or internal endpoints.

### Why This Matters

These tests do not require external services. If they fail, the problem is likely Python version, dependency import behavior, path layout, or code drift.

## Step 7: Review Existing Logs Before Restarting

Find the current log location through the process manager or deployment configuration.

Useful checks:

```bash
# systemd example, only if systemd is used
journalctl -u <service-name> --since "24 hours ago" --no-pager

# file log example
ls -lah /path/to/logs
tail -n 200 /path/to/lerai.log
```

Look for:

- import failures,
- missing environment variables,
- certificate errors,
- Webex authentication errors,
- Azure OpenAI HTTP errors,
- Query2 or LeROY errors,
- accidental raw token or prompt logging from older deployed code.

### Why This Matters

Logs tell us whether the server has already been failing before any new change. They also help identify operational assumptions that are not visible in the repo.

## Step 8: Start or Restart the Bot Carefully

Only restart after code revision, environment, certs, dependencies, and no-server tests are understood.

Record the exact command used. Examples might be:

```bash
systemctl restart <service-name>
supervisorctl restart <program-name>
python3 lerai_main.py
```

After startup, immediately inspect logs for the first few minutes.

Expected healthy signals:

- bot process stays running,
- no import errors,
- no missing config exceptions,
- Webex connection establishes,
- scheduler registration behavior is understood,
- no raw secrets are logged.

### Why This Matters

Restarting can change user-facing bot availability. The first restart should be deliberate and reversible.

## Step 9: Smoke-Test Read-Only Workflows First

Start with commands that should not mutate production state.

Suggested order:

1. A simple command that only routes through Webex and returns a quick pre-execute message.
2. `/dp` or `/lrdp` only if MySQL access is expected and safe.
3. `query_variance` with awareness that it calls Query2 but should only read and format results.
4. `quota_exceed` with the same Query2 caveat.
5. `airflow_errors`, `expected_observed_diff`, and `diff_offline_prod` once internal HTTP endpoints and Azure OpenAI are confirmed.
6. `/fd` once Footprint API cert access and Azure OpenAI are confirmed.
7. `/write_override` only after deciding whether generated TOML output should be treated as advisory or operational.

For each command, record:

- command text,
- whether pre-execute response appears,
- final response,
- log lines generated,
- latency,
- whether any raw secret or prompt appeared in logs.

### Why This Matters

Read-only workflow smoke tests isolate connectivity and runtime issues without creating production changes.

## Step 10: Delay `/promote` and `/approve` Until Controls Are Confirmed

Do not run promotion commands until these are confirmed:

- `PROMOTION_TOKEN_SECRET` is set and stable across bot restarts.
- `PROMOTION_TOKEN_TTL_SECONDS` is sane.
- `APPROVED_USERS` parses correctly and owner confirms the approver list.
- `LEROY_AGENT_PROMOTE_URL` points to the intended environment.
- `CERT_PATH` and `KEY_PATH` are correct.
- LeROY endpoint behavior is understood.
- There is an agreed dry-run or non-production promotion token, if available.

When ready, test promotion in the safest available mode:

1. Use a non-production or dry-run LeROY token if the upstream service supports it.
2. Use two known approvers from `APPROVED_USERS`.
3. Confirm approval token creation and expiry behavior.
4. Confirm same-space, cross-space, and DM routing only if needed.
5. Confirm audit/log output does not expose the original promotion token or approval token.

### Why This Matters

Promotion is a production-action workflow. It must be tested after read-only workflows and configuration are known-good.

## Step 11: Capture Server-Specific Facts Back Into Docs

After the first server session, update documentation with owner-confirmed facts:

- process manager and restart command,
- Python version,
- dependency installation process,
- log location,
- config source and secret manager,
- which scheduled jobs are enabled,
- whether LeROY has dry-run/idempotency support,
- which Webex spaces are production versus test spaces,
- service owners for Query2, LeROY, Footprint, and internal HTTP endpoints.

Good target docs:

- `docs/PROJECT_FLOW.md`
- `docs/CODE_QUALITY_REVIEW.md`
- a new deployment/runbook document if needed

## Immediate Stop Conditions

Stop testing and do not proceed to production-action workflows if any of these occur:

1. The deployed code revision is unknown.
2. The bot logs raw Webex tokens, Azure API keys, promotion tokens, cert paths, or private key material.
3. No-server tests fail on the server.
4. Certificate files are missing or unreadable.
5. `PROMOTION_TOKEN_SECRET` is missing.
6. `APPROVED_USERS` is missing, malformed, or owner-unconfirmed.
7. `LEROY_AGENT_PROMOTE_URL` points to an unexpected environment.
8. Webex authentication fails.
9. Internal endpoints return unexpected non-read-only behavior.

## Recommended First Server Checklist

Use this as the short version during the first access window:

```text
[ ] Confirm deployed code revision.
[ ] Confirm Python and virtualenv.
[ ] Confirm dependency installation process.
[ ] Check required env vars by presence only.
[ ] Check cert/key files exist and are readable.
[ ] Run no-server unittest suite.
[ ] Run compileall.
[ ] Review existing logs before restart.
[ ] Start/restart bot only after checks pass.
[ ] Watch startup logs.
[ ] Smoke-test read-only commands.
[ ] Defer promotion until approvers, secret, endpoint, and dry-run plan are confirmed.
[ ] Record server-specific facts back into docs.
```

## Suggested First Command Sequence

After startup looks healthy, use this order:

```text
1. Webex bot mention/help or lowest-risk command available.
2. query_variance
3. quota_exceed
4. airflow_errors
5. expected_observed_diff
6. diff_offline_prod
7. /dp with a harmless read-only question
8. /fd with a narrow read-only question
9. /write_override with an obviously non-actionable test request
10. /promote only with owner-approved dry-run procedure
```

The exact command order should be adjusted if a service owner says a workflow is expensive, noisy, or not safe to exercise during the first session.
