# AGENT.md

## Purpose
This agent is responsible for implementing and maintaining LeRAI command workflows and supporting modules with safe, minimal, test-validated changes.

Current delivery focus:
- Build and harden the overrides pipeline end-to-end (intent extraction, conflict detection, TOML generation, schema validation, and response formatting).
- Maintain and extend the CPLEX offline quota agent.

Primary responsibilities:
- Deliver code changes requested by users across command handlers, workflow modules, override pipeline, and supporting utilities.
- Keep tests and documentation aligned with behavior changes.
- Preserve operational safety for promotion and override-generation paths.

Non-goals:
- Making infrastructure or production runtime changes outside the repository.
- Running destructive git operations unless explicitly requested.
- Introducing broad refactors that are not required for the user request.

## Repository Context
Project summary:
- LeRAI is a Webex-based operational assistant for Large Region workflows, including data summaries, Query2 checks, promotion approvals, and LeROY override TOML generation.

Key areas and ownership boundaries:
- lerai/lerai_main.py: Webex bot startup and command registration.
- lerai/lerai_commands.py: Command classes and dispatch behavior.
- lerai/leroy_overrides_writer.py: Override orchestration entry point. It still provisions a transient Git workspace per request, but the current supervisor no longer uses that workspace as the source of truth for live override state. The override agent now fetches live state directly from the LeROY override API.
- lerai/api_clients/override_api.py: mTLS-backed LeROY override API client. `fetch_override_and_token()` fetches the current override body plus optimistic-concurrency token. `submit_offline_override()` submits the final TOML for deployment/offline execution with enhanced error handling to detect upstream failures from multiple response formats, coerce success flags, and raise descriptive exceptions.
- lerai/override_agent/tools.py: LangGraph supervisor tools. `refresh_live_override_snapshot` (STEP 3) fetches live override state upfront and caches it in graph state. `detect_override_conflicts` now uses injected state instead of fetching inline, and returns plain JSON strings instead of Command objects. Other tools include `extract_override_intent`, `generate_and_validate_toml`, `search_leroy_documentation`, `lookup_infrastructure_data`, `get_unique_infrastructure_values`, `lookup_directive_schema`, `request_deployment_approval`, `apply_override_to_workspace`, and `deploy_and_trigger_offline_computation`. Unified error format: `{"ok": False, "error_type": "...", "details": "..."}`.
- lerai/override_agent/state.py: `OverrideAgentState` with custom reducers (`_last_nonempty`) for handling parallel writes to `base_override_token`, `live_override_toml`, and `draft_toml`.
- lerai/override_agent/nodes.py: Supervisor node that routes requests to tools. State updates for `base_override_token` and `live_override_toml` now come directly from tool Command objects rather than being extracted from tool message content.
- lerai/override_agent/graph.py: Singleton LangGraph app sharing `lerai_checkpoints.db` checkpointer.
- lerai/cplex_agent/: Standalone LangGraph agent for CPLEX offline quota computation. Contains `state.py` (`CplexAgentState`), `tools.py` (`trigger_offline_quota_computation`, `CPLEX_TOOLS`), `nodes.py` (`supervisor_node`), and `graph.py` (singleton `get_compiled_graph()` sharing `lerai_checkpoints.db` with the override agent).
- lerai/cplex_runner.py: Bridges Webex bot traffic to the CPLEX agent (thread-id resolution, graph invoke, threaded reply).
- lerai/overrides_pipeline/entity_extractor.py: Structured intent extraction and normalization.
- lerai/overrides_pipeline/conflict_detector.py: Conflict checks against existing override records.
- lerai/overrides_pipeline/toml_generator.py: TOML stanza creation, schema validation, and the deterministic `execute_ast_update` nuke-and-append AST engine that mutates a parsed `override.toml` document.
- lerai/git_workspace.py: Transient Git workspace wrapper (`TransientGitWorkspace`) still used by Diff Analyst and by transitional override-entry scaffolding.
- lerai/config.py: Shared environment parsing/validation helpers.
- lerai/logging_utils.py: Logging redaction helpers now disabled (no-op) to facilitate debugging.
- openai_agent/openai_agent_client.py: Azure OpenAI request construction and HTTP calls.
- tests/: Regression tests and fixture-driven behavior checks, with priority on overrides pipeline coverage.
- docs/: Architecture, implementation notes, and test guide.

Domain terms to preserve:
- LR: Large Region scope used by commands and queries.
- LeROY overrides: TOML override-record stanzas with schema and conflict rules.
- Query2 checks: variance-addition and quota-exceed reporting paths.
- Promotion flow: requester/approver flow with signed approval tokens.

## Architectural Patterns and Recent Changes

### State Management with Custom Reducers
The `OverrideAgentState` now uses custom reducer functions for `base_override_token`, `live_override_toml`, and `draft_toml` to handle parallel tool writes safely. The `_last_nonempty` reducer ensures that when multiple tools update the same state key in parallel, the latest non-empty value is retained. This allows tools to update state independently without merge conflicts.

### Decoupled Snapshot Fetching
The `refresh_live_override_snapshot` tool (STEP 3 in the workflow) explicitly fetches the live override TOML and concurrency token upfront and caches them in graph state. Downstream tools like `detect_override_conflicts` then use `InjectedState("live_override_toml")` to consume this cached value instead of fetching independently. This reduces duplicate API calls and ensures all operations in an editing session use the same base token for optimistic concurrency control.

### Tool Return Format Standardization
Tools now use consistent structured return formats:
- Success: Return plain JSON strings with relevant fields (e.g., `{"ok": True, "has_conflict": False, ...}`) or Command objects that update state.
- Failure: Return structured error format `{"ok": False, "error_type": "ErrorType", "details": "error message"}` for consistent error handling.

### Enhanced API Error Handling
The `submit_offline_override` function in `override_api.py` now handles multiple response formats from upstream endpoints:
- Stdout-wrapped responses: Parses Python dict strings from the `stdout` field.
- Direct structured responses: Accepts JSON payloads that directly contain offline override results.
- Upstream failures: Detects failure indicators (`success: False`, non-zero returncode) and constructs detailed error messages from `offline_run_errors` and `stderr`.
Helper functions `_coerce_success_flag`, `_looks_like_offline_result`, and `_build_upstream_failure_message` make the logic testable and maintainable.

Domain terms to preserve:
- LR: Large Region scope used by commands and queries.
- LeROY overrides: TOML override-record stanzas with schema and conflict rules.
- Query2 checks: variance-addition and quota-exceed reporting paths.
- Promotion flow: requester/approver flow with signed approval tokens.

## Inputs and Outputs
Typical request types:
- Bug fixes in workflow modules.
- Feature changes in commands and override pipeline.
- Test additions/updates.
- Documentation alignment with recent commits.

Done criteria:
- Requested behavior is implemented end-to-end.
- Relevant tests pass, or inability to run tests is clearly stated.
- Documentation is updated when externally visible behavior changes.
- Final response includes changed files, validation steps, and residual risks.

Output format expectations:
- For implementation tasks: summary of changes, validation results, and follow-ups.
- For review tasks: findings first (highest severity first), then assumptions/questions, then brief summary.

## Operating Rules
Safety:
- Never run destructive commands such as git reset --hard or force checkout without explicit user request.
- Never revert unrelated local changes.
- Never expose secrets, tokens, keys, or sensitive user data in logs or responses.

Editing:
- Prefer minimal, targeted edits that preserve existing style and APIs.
- Use ASCII by default unless the file already relies on non-ASCII content.
- Add comments only when logic is not self-evident.

Tooling and search:
- Prefer rg/rg --files for fast code and file discovery.
- Parallelize read-only context gathering where possible.
- Validate edited files with tests or static checks relevant to the change.

## Standard Workflow
1. Discover
- Identify impacted modules, tests, and docs.
- Read enough surrounding code to avoid behavioral regressions.

2. Implement
- Apply focused file edits.
- Avoid unrelated cleanup or formatting churn.

3. Validate
- Run targeted tests first, then broader suite if needed.
- Run compile checks when touching multiple Python modules.

4. Report
- Provide concise summary of what changed and why.
- Include test commands run and outcomes.
- Call out residual risks and follow-up options.

## Testing and Validation
Environment:
- Activate venv: source /home/atjoshi/lerai/.venv/bin/activate
- Use python3 for local commands.
- Export all environment variables using `source exports.sh`

Baseline validation commands:
- Full regression suite:
  python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils tests.test_entity_extractor_normalization tests.test_leroy_overrides_writer_query_cases tests.test_leroy_overrides_writer_conflicts_with_fixture
- Compile check:
  python3 -m compileall .

Targeted validation by area:
- Override pipeline normalization:
  python3 -m unittest tests.test_entity_extractor_normalization
- Override API client behavior:
  python3 -m unittest tests.test_override_api
- Override deploy result compaction:
  python3 -m unittest tests.test_override_agent_tools
- Override generation query cases:
  python3 -m unittest tests.test_leroy_overrides_writer_query_cases
- Override conflict behavior:
  python3 -m unittest tests.test_leroy_overrides_writer_conflicts_with_fixture
- Promotion token and parser behavior:
  python3 -m unittest tests.test_promote_security

## Quality Bar
- Preserve backward-compatible behavior unless the request explicitly changes behavior.
- Add or update tests for logic changes in core workflows.
- Keep docs in docs/ aligned with user-visible behavior and command surface.
- Favor deterministic parsing/validation for safety-critical flows (promotion and overrides).
- Do not write prompts as string literals in code; all the prompt text should be in `lerai/prompts/`.

## Communication Style
- Provide short progress updates during multi-step tasks.
- Be explicit about assumptions when requirements are ambiguous.
- Ask clarifying questions only when ambiguity changes implementation outcome.
- Final responses should include:
  - What changed
  - Why it changed
  - How it was validated
  - Any remaining risks or follow-up options

## Repo-Specific Notes
- Scheduler jobs exist but may be disabled in startup wiring; avoid claiming scheduled behavior without checking current registration.
- Override conflict behavior is rule-driven via lerai/prompts/leroy_override_conflict_rules.json.
- Response formatting for override writer is template-driven via lerai/prompts/leroy_override_writer_response_templates.json.
- Keep fixture-driven tests synchronized with behavior changes in override extraction/conflict/generation paths.

## Handoff Rules
When work is complete, provide:
1. Files changed.
2. Behavioral impact.
3. Validation performed (or why not run).
4. Suggested next steps when meaningful.

## Running code in shell (e.g., while running the interactive `test_override_cli.py` for debugging):
- Activate venv using `source /home/atjoshi/lerai/.venv/bin/activate`
- Export all environment variables using `source exports.sh`
- Run the script with python3, e.g., `python3 test_override_cli.py`
- If running any internal (to debug using `__main__`), make sure that all the appropriate custom modules are in the PYTHONPATH, e.g., `PYTHONPATH=lerai python3 lerai/leroy_overrides_writer.py`.