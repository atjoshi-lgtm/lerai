# LeRAI

LeRAI is a Webex-based operational assistant for Large Region workflows.

It provides command-driven workflows for:

- offline vs production diff summarization,
- offline vs production promotion-gate analysis through the Diff Analyst LangGraph agent,
- Airflow error summarization,
- expected vs observed offload analysis,
- DP and FD question answering,
- Query2 variance and quota checks,
- promotion request/approval flow,
- interactive LeROY override TOML generation through a thread-aware agent that writes flat TOML records,
- approval-gated override deployment previews with explicit add/delete stanza review and split-and-replace guidance for partial overlaps,
- approval-gated override deployment through an mTLS-authenticated LeROY API with optimistic-concurrency tokens,
- standalone post-deployment offline quota computation through the CPLEX LangGraph agent,
- semantic override conflict classification with scope-aware warnings and explicit replace/add guidance,
- LeROY documentation search and infrastructure lookup for override-related questions,
- standardized error propagation with explicit truncation markers for oversized upstream failures.

## Override Architecture Status

The override path is currently in a hybrid migration state.

- The override supervisor now fetches live override state from `OVERRIDE_TOKEN_URL` and captures a `base_override_token` for optimistic concurrency.
- Conflict detection runs against the TOML returned by that API, not against a repo-local `override.toml` file.
- After approval, the supervisor applies the add/delete plan in memory and submits the final TOML to `RUN_OFFLINE_OVERRIDE_URL` over mTLS using `CERT_PATH` and `KEY_PATH`.
- The deployment response is compacted for the LLM context, but still preserves success status, return code, and the offline token when one is returned.
- Deployment and API-adapter error paths now preserve upstream diagnostics (`message`, `offline_run_errors`, `stderr`, and `offline_run_log`) and apply explicit clipping markers when payloads exceed configured limits.

### Error Truncation Policy

- A shared truncation helper (`lerai/error_truncation.py`) is used by override/API/diff/OpenAI wrappers.
- Global control variable: `LERAI_ERROR_TEXT_MAX_CHARS` (default `4000`, hard cap `50000`).
- When truncation occurs, the emitted text includes a marker of the form:

```text
[TRUNCATED field=<name> original_chars=<N> shown_chars=<M> omitted_chars=<K>]
```

- This avoids silent clipping and makes partial payloads explicit in user-facing errors.

Some orchestration still reflects the older Git-backed model:

- `lerai/leroy_overrides_writer.py` and `test_override_cli.py` still create a transient Git workspace per request/session.
- That workspace is currently migration scaffolding and is no longer the source of truth for override conflict detection or deployment submission.
- Diff Analyst and other Git-oriented workflows still use `TransientGitWorkspace` directly.

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
python3 -m unittest tests.test_openai_agent_client tests.test_query_response_parsing tests.test_promote_security tests.test_dp_ama_state tests.test_config tests.test_logging_utils tests.test_git_workspace tests.test_entity_extractor_normalization tests.test_leroy_overrides_writer_query_cases tests.test_leroy_overrides_writer_conflicts_with_fixture tests.test_mapname_validation tests.test_conflict_detector_object_count tests.test_toml_generator_comment_preservation tests.test_toml_generator tests.test_override_api tests.test_override_agent_tools tests.test_error_truncation
```

Run syntax compile checks:

```bash
python3 -m compileall .
```

Run the local override-agent CLI harness:

```bash
python3 test_override_cli.py
```

The override CLI writes timestamped logs under `logs/test_cli/` and includes pretty-printed LLM request/response payloads for override-agent debugging. It also renders approval interrupts as human-readable markdown, shows multiple interrupts in order when present, and avoids raw interrupt object wrappers so deployment decisions can be tested locally. The CLI automatically creates a per-session ephemeral Git workspace (just like production) and cleans it up on exit.
The current supervisor logic no longer reads live override state from that workspace; it fetches live TOML and deploy tokens from the override API.

## Recent diff_agent_v2 and last-five-commit summary

The most recent repository changes focus on the v2 Diff Analyst workflow while keeping the original `diff_agent` flow intact for historical context.

- `lerai/diff_agent_v2/` was added as a fresh LangGraph implementation for transient repo comparison and LLM correlation.
- `state.py`, `utils.py`, `nodes.py`, and `graph.py` were created to hold typed state, enrichment logic, and the v2 execution path.
- `test_diffv2_cli.py` was added to validate the v2 pipeline locally without the Webex bot.
- Map translation logic was corrected to normalize numeric and `mr-<id>` keys before name lookup.
- Geography enrichment was added with reverse lookups across the metro/country/geo reference tables.
- The v2 request payload is now logged in a human-readable, indented format before the LLM call.
- The Webex command registration path was fixed so `/analyze_diff_v2` does not collide with `/analyze_diff`.

Important changes in the last five commits:

- `54ce78c` / `7c65fa5`: added the new v2 Diff Analyst scaffolding and files, while preserving the older `diff_agent` implementation alongside them.
- `4a08838`: captured the current state of the older diff_agent and then built `diff_agent_v2` from scratch as a new branch of work.
- `589ebf5`: removed unused files and cleaned workspace handling around the diff and override agent code.
- `15d91af`: removed unused imports and cleaned additional workspace handling in override generation.

These updates are intentionally documented alongside the older `diff_agent` notes rather than replacing them, so both workflows remain visible and traceable.

Run the local Diff Analyst CLI harness:

```bash
python3 test_diff_cli.py
```

The Diff Analyst CLI runs a one-shot LangGraph DAG that:

- compares local `override.toml` changes against production branch state,
- extracts TOML and CSV timestamps,
- captures source repository and branch provenance for offline and production inputs,
- filters CSV unified diffs to focus on structural and significant changes,
- generates a promotion recommendation report and deterministic `/promote` command footer.

Run the local Diff Analyst v2 CLI harness:

```bash
python3 test_diffv2_cli.py
```

The v2 CLI is the newer transient-repo graph for diff analysis. It:

- clones the config, offline CSV, and prod CSV repos into a temp directory,
- computes BLC and FCS structural diffs and quota deltas,
- normalizes maprule identifiers to match `mapruleid_mapname.csv`,
- adds geographic metadata (`metro`, `country`, and `geo`) for each changed row,
- sends the final JSON payload to the model as a pretty-formatted request with indented content,
- returns a final recommendation report in Slack/Webex markdown.

The Webex command for the v2 workflow is `/analyze_diff_v2`; the older `/analyze_diff` command remains documented separately and is intentionally left untouched here.

Run the local CPLEX CLI harness:

```bash
python3 test_cplex_cli.py
```

Note: Running these CLIs requires environment variables to be set. The canonical source is `exports.sh`:

```bash
source exports.sh
```

If you need to set them manually, provide all required Git workspace values:

```bash
export CERT_PATH=<path-to-client-cert>
export KEY_PATH=<path-to-client-key>
export OVERRIDE_TOKEN_URL=<override-token-endpoint>
export RUN_OFFLINE_OVERRIDE_URL=<offline-override-endpoint>
export RUN_OFFLINE_OVERRIDE_TIMEOUT_SEC=<optional-timeout-seconds>
export LERAI_ERROR_TEXT_MAX_CHARS=<optional-max-error-text-chars>

# Transitional Git workspace settings still used by the Webex/CLI bridge
export LEROY_GIT_REPO_URL=<your-repo-url>
export LEROY_GIT_BRANCH=<your-branch>
export LEROY_GIT_SSH_KEY_PATH=<path-to-ssh-key>
export LEROY_OVERRIDE_TOML_RELATIVE_PATH=<path-inside-cloned-repo>

# Required when testing the standalone CPLEX/offline trigger path
export LEROY_OFFLINE_REMOTE_HOST=<user@cplex-host>
export LEROY_OFFLINE_SSH_KEY_PATH=<path-to-ssh-key>
export LEROY_OFFLINE_REPO_DIR=<remote-leroy-config-repo-dir>
export LEROY_OFFLINE_DOCKER_CONTAINER=<airflow-worker-container>
export LEROY_OFFLINE_DAGS_DIR=<airflow-dags-dir>
export LEROY_OFFLINE_SCRIPT_PATH=<compute_quota_offline.py-path>
export LEROY_OFFLINE_OVERRIDE_PATH=<override-toml-path-on-remote>
export LEROY_OFFLINE_DYNAMIC_PATH=<dynamic-config-path-on-remote>
export LEROY_OFFLINE_TRIGGER_TIMEOUT_SEC=<timeout-seconds>
```