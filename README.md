# LeRAI

LeRAI is a Webex-based operational assistant for Large Region workflows.

It provides command-driven workflows for:

- offline vs production diff summarization,
- Airflow error summarization,
- expected vs observed offload analysis,
- DP and FD question answering,
- Query2 variance and quota checks,
- promotion request/approval flow,
- interactive LeROY override TOML generation through a thread-aware agent that writes flat TOML records,
- approval-gated override deployment previews with explicit add/delete stanza review and split-and-replace guidance for partial overlaps,
- semantic override conflict classification with scope-aware warnings and explicit replace/add guidance,
- LeROY documentation search and infrastructure lookup for override-related questions.

The override conflict pipeline always evaluates against the absolute latest production state by using an ephemeral Git workspace cloned per request. Each request generates a unique temporary directory, clones the Git repository there, and evaluates conflict detection against the cloned `override.toml`. The workspace is deleted after the request completes, ensuring fresh production state is never stale.

The override conflict pipeline also uses hierarchical geography mappings from `lerai/data/` (including metro, country, and geo relationships) to detect direct collisions, carve-outs, ineffective broad rules, dead-code overlap, partial map overlap, and partial geographic overlap. The writer now normalizes nested intent payloads before TOML generation so override records stay flat in the generated file.

The override agent also includes a hybrid LeROY knowledge-base search over `docs/leroy_manual/`, backed by a persisted local index in `lerai/data/chroma_index/`. That index is generated locally on demand and is intentionally gitignored.

## Documentation

- Project architecture and flow: `docs/PROJECT_FLOW.md`
- Test suite guide: `docs/TEST_GUIDE.md`
- Agent operating guide: `AGENT.md`
- Historical implementation and quality notes: `archive/`

## Local Validation

Run the no-server unit tests:

```bash
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils tests.test_git_workspace tests.test_entity_extractor_normalization tests.test_leroy_overrides_writer_query_cases tests.test_leroy_overrides_writer_conflicts_with_fixture tests.test_mapname_validation tests.test_conflict_detector_object_count tests.test_toml_generator_comment_preservation tests.test_toml_generator
```

Run syntax compile checks:

```bash
python3 -m compileall .
```

Run the local override-agent CLI harness:

```bash
python3 test_cli.py
```

The CLI now writes timestamped logs under `logs/test_cli/` and includes pretty-printed LLM request/response payloads for override-agent debugging. It also renders approval interrupts as human-readable markdown, shows multiple interrupts in order when present, and avoids raw interrupt object wrappers so deployment decisions can be tested locally. The CLI automatically creates a per-session ephemeral Git workspace (just like production) and cleans it up on exit.

Note: Running `test_cli.py` requires the Git environment variables to be set:

```bash
export LEROY_GIT_REPO_URL=<your-repo-url>
export LEROY_GIT_SSH_KEY_PATH=<path-to-ssh-key>
```