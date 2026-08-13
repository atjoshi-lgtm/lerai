Here is a comprehensive and structured API specification designed specifically to be fed into your other AI instance. It details the exact endpoint flow, payloads, and necessary parsing logic to ensure the LangGraph agents can communicate with the backend flawlessly.

---

# LeRAI Agent API Implementation Guide

This document outlines the strict technical requirements, workflows, and parsing instructions for interacting with the LeRAI backend API. The backend orchestrates network configuration overrides via Git branches and a CPLEX quota computation engine.

The override workflow is state-locked. The base token identifies the production `override.toml` commit read at the start. After a successful offline run, the returned composite token records the complete state represented by the offline results: the production and `offline_test_branch` `override.toml` commits, plus the `blc.csv`, `fcs.csv`, and `expected_offload.csv` commits in both the offline_manual and production repositories. The same composite token is passed through diff verification and promotion so promotion can verify that this state has not changed.

## 1. Core Workflow & Endpoint Specifications

The override process strictly follows a sequential, state-locked four-step flow. Concurrency is prevented by passing state tokens between endpoints. The token flow is:

`base_token` (production `override.toml` commit) -> `composite_token` (returned after the offline run) -> same `composite_token` for diff verification -> same token for promotion.

### Step 1: Fetch Base State

Retrieve the current `override.toml` file from production and its associated state lock token.

* **Endpoint:** `GET /v1/override_token`
* **Query Parameters:** None.
* **Response Schema:**
```json
{
  "returncode": 0,
  "stdout": "{'token': '...', 'override': '...'}", 
  "stderr": ""
}

```


* ⚠️ **Critical Parsing Instruction for AI:** The backend does not serialize the underlying script's output as JSON; it returns a stringified Python dictionary in the `stdout` field. You **must** parse the `stdout` string (e.g., using `ast.literal_eval`) to extract the `token` (the `base_token`, representing the last production `override.toml` commit) and the `override` text.

### Step 2: Submit Overrides & Run Computation

Submit the modified TOML file to trigger the CPLEX computation.

* **Endpoint:** `POST /v1/run_offline_override`
* **Request Body (JSON):** ```json
{
"updated_toml": "",
"base_token": "<token extracted from Step 1>"
}
```
*(Note: `updated_toml` and `base_token` map exactly to the `OfflineOverrideRequest` Pydantic model.)*

```


* **Response Schema (on success — stdout-wrapped format):**
```json
{
  "returncode": 0,
  "stdout": "{'success': True, 'returncode': 0, 'token': '...', 'offline_diff': {...}, 'offline_run_errors': [], 'offline_run_log': '...'}",
  "stderr": ""
}

```


* **Response Schema (on success — direct structured format):**
```json
{
  "success": true,
  "returncode": 0,
  "token": "<composite_token>",
  "offline_diff": "...",
  "offline_run_errors": [],
  "offline_run_log": "..."
}

```


* **Response Schema (on upstream failure):**
```json
{
  "success": false,
  "returncode": 1,
  "offline_run_errors": ["Error message from upstream"],
  "offline_run_log": "...",
  "stderr": ""
}

```


* ⚠️ **Critical Parsing Instructions for AI:** 
1. **Multiple Response Formats:** The endpoint may return either a `stdout`-wrapped response (where the actual result is stringified in the `stdout` field) or a direct structured response. Your parsing logic must handle both:
   - If `stdout` is a non-empty string, parse it with `ast.literal_eval()` to extract the structured result.
   - If `stdout` is missing/empty but the response JSON itself contains offline override fields (`success`, `returncode`, `offline_run_errors`, etc.), treat the JSON payload as the result directly.
2. **Success Detection:** Check the `success` field (or coerce it if it's a string "true"/"false"). If `success` is `False` or missing with a non-zero `returncode`, treat it as a failure.
3. **Upstream Errors:** When `success` is `False`, preserve and surface all available diagnostics (`message`, `offline_run_errors`, `stderr`, `offline_run_log`, and `returncode`) in the failure payload returned to the agent.
4. **Token Extraction:** When successful, capture the returned `token` field as the `composite_token` for use in Step 3. This token ties together the production `override.toml` commit, the `offline_test_branch` `override.toml` commit, and the three offline and three production output-file commits (`blc.csv`, `fcs.csv`, and `expected_offload.csv`).

### Error Payload Truncation Standard

To avoid losing critical context while keeping payload size bounded, LeRAI uses one global truncation setting and explicit truncation markers.

- Environment variable: `LERAI_ERROR_TEXT_MAX_CHARS`
- Default: `4000`
- Hard cap: `50000`
- Applied in API adapters/tool wrappers that forward raw upstream details.

When clipping is applied, returned text includes this marker suffix:

```text
[TRUNCATED field=<name> original_chars=<N> shown_chars=<M> omitted_chars=<K>]
```

This ensures truncation is never silent.

### Step 3: Diff Verification

Generate a structured difference between the newly generated offline CSVs and the production CSVs.

* **Endpoint:** `GET /v1/offline_manual_prod_csv_diff`
* **Query Parameters:**
* `token`: `<composite_token extracted from Step 2>`


* **Response Schema:**
```json
{
  "returncode": 0,
  "token": "<composite_token>",
  "diff": {
    "blc.csv": {"filename": "blc.csv", "diff": "...", "offline_last_modified": "..."},
    "fcs.csv": {"filename": "fcs.csv", "diff": "...", "offline_last_modified": "..."},
    "expected_offload.csv": {"filename": "expected_offload.csv", "diff": "...", "offline_last_modified": "..."}
  },
  "override_diff": "<unified diff string>",
  "stderr": ""
}

```


* ⚠️ **Critical Parsing Instructions for AI:** 1. **Token Preservation:** This endpoint validates the state represented by the `composite_token` and returns that same token. Capture the returned `token` as the `promotion_token` for Step 4; do not create or expect a new token at this stage. Promotion uses it to verify that the production and offline commits examined during diff verification are still the current state.
2.  **Graceful Degradation:** The backend attempts to safely evaluate the CSV diff output. If the underlying Python script prints unexpected tracebacks, `diff` will degrade from a nested JSON Object into a raw String. Always check the data type of the `diff` key before iterating over it.
3.  **Per-File Errors:** If a specific CSV fails to diff, its object inside the `diff` dictionary will contain an `"error"` key instead of a `"diff"` key (e.g., `"error": "Error processing file:..."`).

### Step 4: Promotion

Promote the offline changes to production.

* **Endpoint:** `GET /v1/promote`
* **Query Parameters:**
* `token`: `<promotion_token returned from Step 3; the same composite token from Step 2>`


* **Response Schema:**
```json
{
  "stdout": "...",
  "stderr": "..."
}

```



---

## 2. LangGraph Agent Tool Specifications

### Tool Return Patterns

All tools in the override agent follow consistent return patterns for reliability and debuggability:

#### State-Updating Tools
Some tools use LangGraph `Command` objects to update graph state directly:
- `refresh_live_override_snapshot`: Returns `Command(update={...})` with `base_override_token` and `live_override_toml` keys to cache the live snapshot.

#### Result-Returning Tools
Most tools return plain JSON strings:
- Success format: `{"ok": True, ...result_fields...}` or structured result JSON.
- Failure format: `{"ok": False, "error_type": "ErrorTypeName", "details": "error message"}`.

Example structured success response from `detect_override_conflicts`:
```json
{
  "ok": true,
  "has_conflict": true,
  "conflicts": [
    {"type": "DIRECT_COLLISION", "severity": "high", "description": "..."}
  ],
  "message": "Detected 2 potential conflict(s).",
  "warnings": [],
  "invalid_mapnames": []
}
```

Example error response:
```json
{
  "ok": false,
  "error_type": "ConflictDetectionError",
  "details": "Failed to parse live override TOML: invalid syntax at line 42"
}
```

Example deployment error response with rich upstream context:
```json
{
  "ok": false,
  "error_type": "DeploymentError",
  "details": "Offline override failed upstream (returncode=1). Error: Cmd('git') failed ...\nmessage=Error: Cmd('git') failed ...\nstderr=fatal: remote error: Insufficient permissions"
}
```

If any field exceeds configured limits, the field text will include `[TRUNCATED ...]` marker metadata.

### Stateful Tool Execution (Injected State)

Tools can receive cached state from the graph using LangGraph's `InjectedState` pattern:
```python
def detect_override_conflicts(
    intent_json: str,
    live_override_toml: Annotated[str, InjectedState("live_override_toml")],
) -> str:
    # live_override_toml is injected from graph state, eliminating duplicate fetches
```

This pattern requires that an earlier tool (like `refresh_live_override_snapshot`) has populated the state key.

### Tool Execution Sequence (Override Workflow)

The supervisor prompt enforces this sequence for transactional override requests:

1. **DRAFT:** `extract_override_intent(synthesized_request: str) -> str`
   - Returns: `{"ok": true, "intent": {...}}` or `{"ok": false, "error_type": "ExtractionError", "details": "..."}`

2. **GENERATE:** `generate_and_validate_toml(intent_json: str) -> dict`
   - Input: JSON string from step 1
   - Returns: `{"ok": true, "toml": "...", "stanza": {...}}` or error dict

3. **FETCH SNAPSHOT:** `refresh_live_override_snapshot(runtime: ToolRuntime) -> Command`
   - Side effect: Updates graph state with `base_override_token` and `live_override_toml`
   - Returns: Command object updating graph state

4. **CHECK CONFLICTS:** `detect_override_conflicts(intent_json: str, live_override_toml: Annotated[str, InjectedState(...)]) -> str`
   - Input: JSON string from step 1, live TOML from graph state (injected)
   - Returns: `{"ok": true, "has_conflict": ..., "conflicts": [...], ...}` or error JSON

5. **REQUEST APPROVAL:** `request_deployment_approval(...) -> str`
   - Pauses graph execution and returns approval prompt to user

6. **APPLY IN-MEMORY:** `apply_override_to_workspace(new_intents_json: str, target_intents_json: str) -> str`
   - Inputs: New intents to add, old intents to delete (both JSON lists)
   - Returns: `{"ok": true, "draft_toml": "..."}` or error JSON
   - Side effect: Stores result in graph state `draft_toml`

7. **DEPLOY & TRIGGER:** `deploy_and_trigger_offline_computation(draft_toml: str) -> str`
   - Input: The draft TOML from state
  - Returns: `{"ok": true, "success": true, "returncode": 0, "offline_token": "..."}` or error JSON
  - On failure, compact payload preserves `message`, `offline_run_errors`, `stderr`, and `offline_run_log` (subject to the shared truncation policy above).
   - Calls `/v1/run_offline_override` endpoint with cached `base_override_token` and submits the draft TOML

### State Reducer Pattern

Graph state uses custom reducer functions to handle parallel tool writes:

```python
def _last_nonempty(old: str, new: str) -> str:
    """When parallel tools update the same key, the latest non-empty value wins."""
    return new if new else old
```

This is applied to:
- `base_override_token`: Optimistic concurrency token from the server
- `live_override_toml`: Current override TOML state from the server
- `draft_toml`: Working copy of the TOML being edited

---

## 2. General Error Handling Guidelines for the AI

* **Timeout Handling:** Most endpoints enforce strict subprocess timeouts (e.g., 120s or 1800s for CPLEX runs). If a process times out, the API returns an HTTP 504 status code. Your LangGraph agent should catch HTTP 504s gracefully.
* **Script Missing Errors:** If a backend auxiliary script is missing from the host environment, the API returns an HTTP 500 status code with a detail string like `Promotion script not found: ...`.