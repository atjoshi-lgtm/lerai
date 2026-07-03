# LeRAI

LeRAI is a Webex-based operational assistant for Large Region workflows.

It provides command-driven workflows for:

- offline vs production diff summarization,
- Airflow error summarization,
- expected vs observed offload analysis,
- DP and FD question answering,
- Query2 variance and quota checks,
- promotion request/approval flow,
- LeROY override TOML generation.

## Documentation

- Project architecture and flow: `docs/PROJECT_FLOW.md`
- Code quality and reliability review: `docs/CODE_QUALITY_REVIEW.md`
- Test suite guide: `docs/TEST_GUIDE.md`
- Server access and validation steps: `docs/SERVER_ACCESS_NEXT_STEPS.md`
- Implementation change logs:
	- `docs/IMPLEMENTATION_CHANGES.md`
	- `docs/IMPLEMENTATION_CHANGES_CONFIG_QUERY2.md`
	- `docs/IMPLEMENTATION_CHANGES_LOGGING_REDACTION.md`

## Local Validation

Run the no-server unit tests:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils
```

Run syntax compile checks:

```bash
python3 -m compileall .
```