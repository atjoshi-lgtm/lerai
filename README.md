# LeRAI

LeRAI is a Webex-based operational assistant for Large Region workflows.

It provides command-driven workflows for:

- offline vs production diff summarization,
- Airflow error summarization,
- expected vs observed offload analysis,
- DP and FD question answering,
- Query2 variance and quota checks,
- promotion request/approval flow,
- interactive LeROY override TOML generation through a thread-aware agent.

## Documentation

- Project architecture and flow: `docs/PROJECT_FLOW.md`
- Test suite guide: `docs/TEST_GUIDE.md`
- Agent operating guide: `AGENT.md`
- Historical implementation and quality notes: `archive/`

## Local Validation

Run the no-server unit tests:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils
```

Run syntax compile checks:

```bash
python3 -m compileall .
```