# AGENT.md

## Purpose
This agent is responsible for implementing and maintaining LeRAI command workflows and supporting modules with safe, minimal, test-validated changes.

Current delivery focus:
- Build and harden the overrides pipeline end-to-end (intent extraction, conflict detection, TOML generation, schema validation, and response formatting).

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
- lerai/leroy_overrides_writer.py: Override orchestration entry point.
- lerai/overrides_pipeline/entity_extractor.py: Structured intent extraction and normalization.
- lerai/overrides_pipeline/conflict_detector.py: Conflict checks against existing override records.
- lerai/overrides_pipeline/toml_generator.py: TOML stanza creation and schema validation.
- lerai/config.py: Shared environment parsing/validation helpers.
- lerai/logging_utils.py: Logging redaction and safe logging helpers.
- openai_agent/openai_agent_client.py: Azure OpenAI request construction and HTTP calls.
- tests/: Regression tests and fixture-driven behavior checks, with priority on overrides pipeline coverage.
- docs/: Architecture, implementation notes, and test guide.

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

Baseline validation commands:
- Full regression suite:
  python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils tests.test_entity_extractor_normalization tests.test_leroy_overrides_writer_query_cases tests.test_leroy_overrides_writer_conflicts_with_fixture
- Compile check:
  python3 -m compileall .

Targeted validation by area:
- Override pipeline normalization:
  python3 -m unittest tests.test_entity_extractor_normalization
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
