# LeRAI

LeRAI is a Webex-based operational assistant for Large Region workflows.

It provides command-driven workflows for:

- offline vs production diff summarization,
- Airflow error summarization,
- expected vs observed offload analysis,
- DP and FD question answering,
- Query2 variance and quota checks,
- promotion request/approval flow,
- interactive LeROY override TOML generation through a thread-aware agent,
- semantic override conflict classification with scope-aware warnings,
- LeROY documentation search and infrastructure lookup for override-related questions.

The override conflict pipeline now uses hierarchical geography mappings from `lerai/data/` (including metro, country, and geo relationships) to detect direct collisions, carve-outs, ineffective broad rules, dead-code overlap, and partial map overlap.

The override agent also includes a hybrid LeROY knowledge-base search over `docs/leroy_manual/`, backed by a persisted local index in `lerai/data/chroma_index/`. That index is generated locally on demand and is intentionally gitignored.

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

Run the local override-agent CLI harness:

```bash
python3 test_cli.py
```

The CLI now writes timestamped logs under `logs/test_cli/` and includes pretty-printed LLM request/response payloads for override-agent debugging.