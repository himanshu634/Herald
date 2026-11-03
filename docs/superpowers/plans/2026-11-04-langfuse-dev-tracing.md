# Langfuse Dev Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In dev, every triage run (live, the owner's Try, and each eval case) shows up in a local Langfuse as one trace, with its node spans, its Claude calls (prompt, structured output, tokens, latency) and its outcome. Production does not change.

**Architecture:** Langfuse runs as its own opt-in compose project. `herald_server/tracing.py` is the only file that knows Langfuse. It returns a do-nothing `NoTracing` unless keys are set, the package is installed and Langfuse answers. When tracing is on:
- `TracedModel` puts a named span around each model call.
- OpenInference instruments the Anthropic SDK, so each call becomes a generation inside that span.
- A per-run LangGraph `CallbackHandler` adds the node spans.
- Outcomes (route, floor, unsure, AI failed, eval passed) are posted as Langfuse scores after the run.

`herald_core` only gains a `callbacks` passthrough on `triage()`. It never imports Langfuse.

**Tech Stack:** Langfuse server v4 (self-hosted, Docker), `langfuse` Python SDK 5.x (built on OpenTelemetry), `openinference-instrumentation-anthropic`, LangGraph callbacks.

**Spec:** none. The design was approved in chat on 2026-11-04 and its decisions are copied into Global Constraints below.

**Branch:** `feat/langfuse-dev-tracing` from `origin/main`. It must include PR #47, where the pipeline goes through `AgentApi`.

## Global Constraints

- Dev only. `langfuse` and `openinference-instrumentation-anthropic` go in the root `[dependency-groups] dev`, never in a package's `dependencies`. The prod image (`uv sync --no-dev --package herald-server`) must not contain them.
- Tracing is on only when `HERALD_LANGFUSE_PUBLIC_KEY` and `HERALD_LANGFUSE_SECRET_KEY` are both set. `HERALD_LANGFUSE_BASE_URL` defaults to `http://localhost:3000`.
- Herald passes the keys to `Langfuse(...)` itself. Values in `.env` never reach `os.environ` (see the comment on `anthropic_api_key` in `settings.py`).
- Pair Langfuse server v4 with Python SDK `langfuse>=5.1,<6`. Never mix server v3 with SDK 5.
- Use `openinference-instrumentation-anthropic`, not OpenLLMetry's `opentelemetry-instrumentation-anthropic`. OpenLLMetry does not wrap `AsyncMessages.parse`, which is the only method Herald calls.
- Compose project name: `herald-langfuse`, in `infra/docker-compose.langfuse.yml`. Only two ports are published on the host: web on `127.0.0.1:3000` and MinIO on `127.0.0.1:9090`. Postgres, Redis, ClickHouse and the worker publish nothing, because Herald already binds 5432 and 6379.
- Dev headless-init values (not secret, dev only):
  - org: `LANGFUSE_INIT_ORG_ID=herald-dev`, `LANGFUSE_INIT_ORG_NAME=Herald`
  - project: `LANGFUSE_INIT_PROJECT_ID=herald-dev`, `LANGFUSE_INIT_PROJECT_NAME=Herald (dev)`
  - keys: `LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-herald-dev`, `LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-herald-dev`
  - login: `LANGFUSE_INIT_USER_EMAIL=dev@herald.test`, `LANGFUSE_INIT_USER_PASSWORD=herald-dev-password`
- Trace names: `triage` (process_email), `trial-read` (the owner's Try), `eval` (each eval case run).
- Trace user and session:
  - Live runs and Try: user = workspace id, session = email id. Re-reads of one email group together.
  - Evals: user = `eval-<dataset>`, session = `eval-<run stamp>`. One `make eval` groups together.
- Trace tags, set at start: the run kind (`live`, `try` or `eval`), plus the model name.
- Scores, posted after the run:
  - `route`: categorical, the route value.
  - `floor`: boolean, any floor flag.
  - `unsure`: boolean, `notes is not None and not notes.sure`.
  - `ai_failed`: boolean, `notes is None`.
  - Eval traces get these four too, plus `passed`: boolean, `Scored.passed`.
- `TracedModel` span names are `model.write_notes` and `model.judge_rules`, not the node names, so they never read as duplicate nodes.
- Tests never trace. A repo-root `conftest.py` sets both `HERALD_LANGFUSE_*` keys to empty for every test, and `build_tracing` treats an empty key as unset. This matters because `cli.main` (called by the eval tests) and the worker read `get_settings()`, which reads `.env`.
- Trace checks query Langfuse's public API with basic auth `pk-lf-herald-dev:sk-lf-herald-dev`, polling up to 10 s because ingestion is async. Take the endpoint names from the installed SDK's API client (`client.api...`), since v4 may have moved them.
- The graph is compiled once and shared by every tenant. Never attach a callback at compile time. A `CallbackHandler` is made for each run.
- Tracing must never fail or block triage. Every call into Langfuse made in `tracing.py` while a run is going is wrapped: an error is logged once at WARNING and swallowed.
- docker-dev containers reach Langfuse at `http://host.docker.internal:3000`, with `extra_hosts: ["host.docker.internal:host-gateway"]`. This works on Docker Desktop (macOS). On Linux the web port, published on `127.0.0.1` only, can't be reached from the Docker bridge. Linux is out of scope.
- Out of scope:
  - owner corrections as scores;
  - tracing the setup draft (OpenInference still records those Claude calls as stray traces; leave them);
  - tracing in production;
  - Langfuse datasets and experiments.
- Style: comment the why of anything non-obvious (lazy imports, the once-per-process instrumentation, swallowing errors). Short plain sentences.

## Review Focus

1. **Keys in `.env` but Langfuse not running:** expect one WARNING at startup, tracing off, and no per-email export noise. Triage is unchanged. Covered by `test_tracing_is_off_when_langfuse_is_down` (Task 2).
2. **Langfuse fails mid-run** (score post or span raises): the email is still saved with its decision. Covered by `test_tracing_errors_never_reach_triage` (Task 3).
3. **A model error inside a traced run:** the `ModelError` reaches the graph unchanged, so the email goes to Needs a look, and `ai_failed` is scored true. Covered by `test_traced_model_passes_errors_through` (Task 2) and `test_outcome_scores` (Task 2).
4. **Two tenants triaged at once on the shared graph:** each run's callbacks see only their own email. Covered by `test_callbacks_stay_with_their_run` (Task 1).
5. **Keys set where the package is missing** (the prod image): expect a WARNING "langfuse is not installed", tracing off, no crash. Covered by `test_tracing_is_off_when_langfuse_is_missing` (Task 2), plus the `uv tree` check in Task 4.

---

### Task 0: Local Langfuse stack and API smoke check

This task has no TDD: it is infra plus a throwaway check that pins the SDK names Tasks 2–4 use.

**Files:**
- Create: `infra/docker-compose.langfuse.yml`
- Modify: `Makefile` (new `langfuse` and `langfuse-down` targets, plus `.PHONY`)
- Modify: `pyproject.toml` (root dev group)
- Modify: `uv.lock`

- [ ] **Step 1: Write `infra/docker-compose.langfuse.yml`**
  - Start from the official file at the release tag `v4.74.0` (`https://raw.githubusercontent.com/langfuse/langfuse/v4.74.0/docker-compose.yml`), with `name: herald-langfuse`.
  - Pin `langfuse/langfuse` and `langfuse/langfuse-worker` to `4.74.0`, or to the newest `4.x` tag that exists.
  - Ports: web becomes `127.0.0.1:3000:3000`, MinIO becomes `127.0.0.1:9090:9000`, and every other `ports:` entry is removed. If the official `LANGFUSE_S3_*` endpoints point at `localhost:9090`, keep them.
  - Fill the `LANGFUSE_INIT_*` values from Global Constraints.
  - Leave the `# CHANGEME` secrets at their dev placeholders, under a header comment: "Dev only. Never deploy this file."

- [ ] **Step 2: Add Makefile targets**
  - `langfuse:` runs `docker compose -f infra/docker-compose.langfuse.yml up -d --wait`, with help text "Start local Langfuse on :3000 (dev tracing, Docker)".
  - `langfuse-down:` runs the same file's `down`.
  - Add both to `.PHONY`.

- [ ] **Step 3: Add the dev dependencies**

Run: `uv add --dev "langfuse>=5.1,<6" openinference-instrumentation-anthropic`
Expected: both appear under `[dependency-groups] dev` in the root `pyproject.toml`, and `uv.lock` is updated.

- [ ] **Step 4: Start Langfuse and log in**

Run: `make langfuse`, then open http://localhost:3000 and log in as `dev@herald.test`.
Expected: the project "Herald (dev)" exists.

- [ ] **Step 5: Smoke-check the SDK names (throwaway, not committed)**

Write `$SCRATCH/langfuse_smoke.py`, where `$SCRATCH` is a temp folder outside the repo, and run it with `uv run python $SCRATCH/langfuse_smoke.py` from the repo root, with `ANTHROPIC_API_KEY` set. The script must, in this order:
1. Make `Langfuse(public_key="pk-lf-herald-dev", secret_key="sk-lf-herald-dev", base_url="http://localhost:3000")` and assert `auth_check()`.
2. Call `AnthropicInstrumentor().instrument()`.
3. Inside `propagate_attributes(trace_name="smoke", user_id="w1", session_id="e1", tags=["live"])` and `start_as_current_observation(as_type="span", name="root")`:
   - run a two-node LangGraph with `config={"callbacks": [CallbackHandler(public_key="pk-lf-herald-dev")]}`. The second node makes one `AsyncAnthropic().messages.parse(...)` call, with a tiny `output_format` model, inside `start_as_current_observation(as_type="span", name="model.write_notes")`. This is the shape Herald's traces will have;
   - read `get_current_trace_id()`.
4. Call `create_score(trace_id=..., name="route", value="alert", data_type="CATEGORICAL")` and `create_score(..., name="floor", value=1, data_type="BOOLEAN")`.
5. Call `shutdown()`.

The script then polls the public API for the trace named `smoke`. Expected, asserted by the script:
- user `w1`, session `e1` and tag `live`;
- the two node spans;
- a `messages.parse` generation with model and token usage, whose parent is the `model.write_notes` span;
- the two scores.

Also print where `model.write_notes` landed: under the node span or under `root`. Either is fine, but write the answer down.

If a name differs in the installed SDK (for example `base_url` versus `host`, or `get_current_trace_id`), or the generation does not nest (for example the instrumentor needs `tracer_provider=`), write the working names into the Interfaces block of Task 2 before you start it. Keep the polling helper's API calls: Tasks 3 and 4 reuse them for their checks.

- [ ] **Step 6: Commit**

```bash
git add infra/docker-compose.langfuse.yml Makefile pyproject.toml uv.lock
git commit -m "Add a local Langfuse stack for dev tracing"
```

---

### Task 1: `triage()` takes per-run callbacks

**Files:**
- Modify: `packages/core/src/herald_core/graph.py` (`triage`)
- Test: `packages/core/tests/test_graph.py`

**Interfaces:**
- Produces: `async def triage(graph, email, config, *, business_name: str, tools: Toolbox | None = None, callbacks: list[Any] | None = None) -> TriageState`. When `callbacks` is set, it is passed as `config={"callbacks": callbacks}` to `graph.ainvoke`. When it is `None` or empty, no `config` is passed and the behaviour is the same as today.

- [ ] **Step 1: Write the failing tests**

```python
from langchain_core.callbacks import AsyncCallbackHandler

class NodeNames(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.names: list[str] = []
        self.subjects: set[str] = set()

    async def on_chain_start(self, serialized, inputs, *, name=None, **kwargs):
        self.names.append(name or "")
        if isinstance(inputs, dict) and "email" in inputs:
            self.subjects.add(inputs["email"].subject)


async def test_triage_passes_callbacks_to_the_graph():
    seen = NodeNames()
    graph = build_graph(FakeModel())
    await triage(graph, email("Hi", "Where is my bag?"), CONFIG, business_name="Tripfold",
                 callbacks=[seen])
    assert {"word_check", "write_notes", "judge_rules", "decide"} <= set(seen.names)


async def test_callbacks_stay_with_their_run():
    # One compiled graph serves every tenant: a run's callbacks must not see another run.
    graph = build_graph(FakeModel())
    a, b = NodeNames(), NodeNames()
    await asyncio.gather(
        triage(graph, email("Tenant A", "Bag late"), CONFIG, business_name="A", callbacks=[a]),
        triage(graph, email("Tenant B", "Bag lost"), CONFIG, business_name="B", callbacks=[b]),
    )
    assert a.subjects == {"Tenant A"} and b.subjects == {"Tenant B"}
```

- [ ] **Step 2: Run the tests to make sure they fail**

Run: `uv run pytest packages/core/tests/test_graph.py -k callbacks -v`
Expected: FAIL with `TypeError: triage() got an unexpected keyword argument 'callbacks'`.

- [ ] **Step 3: Add the `callbacks` parameter to `triage()`** in `graph.py`. Type it as `list[Any]`, so core does not import langchain types.

- [ ] **Step 4: Run the core tests**

Run: `uv run pytest packages/core/tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/core
git commit -m "Let triage() take per-run callbacks"
```

---

### Task 2: `tracing.py`: settings, on/off, `TracedModel`, outcome scores

**Files:**
- Create: `apps/server/src/herald_server/tracing.py`
- Modify: `apps/server/src/herald_server/settings.py`
- Create: `conftest.py` (repo root: an autouse fixture that empties the Langfuse keys for every test)
- Test: `apps/server/tests/test_tracing.py`

**Interfaces:**
- Consumes: `triage(..., callbacks=...)` from Task 1. Also the SDK names confirmed in Task 0 Step 5:
  - `Langfuse(public_key=, secret_key=, base_url=)`
  - `.auth_check()`
  - `propagate_attributes(trace_name=, user_id=, session_id=, tags=, metadata=)`
  - `.start_as_current_observation(as_type="span", name=)`
  - `.get_current_trace_id()`
  - `.create_score(trace_id=, name=, value=, data_type=)`
  - `.shutdown()`
  - `langfuse.langchain.CallbackHandler`
  - `openinference.instrumentation.anthropic.AnthropicInstrumentor`
- Produces, in `herald_server.tracing`:
  - `@dataclass class Run: trace_id: str | None; callbacks: list[Any]`
  - `class Tracing(Protocol)`, with:
    - `enabled: bool`
    - `def wrap_model(self, model: TriageModel) -> TriageModel`
    - `def run(self, name: str, *, user_id: str, session_id: str, tags: list[str], metadata: dict[str, str]) -> AbstractContextManager[Run]`
    - `def score(self, trace_id: str | None, name: str, value: str | bool) -> None`
    - `def shutdown(self) -> None`
  - `NO_TRACING: Tracing`: the do-nothing implementation. `wrap_model` returns its argument, `run` yields `Run(None, [])`, and `score` and `shutdown` do nothing.
  - `class LangfuseTracing` implements `Tracing`. Its constructor takes `(client, model_name: str, propagate, handler)`. `propagate` is `propagate_attributes` and `handler` is `CallbackHandler`. They are passed in so the stub tests never touch the SDK, and `build_tracing` passes the real ones, imported lazily.
  - `class TracedModel` implements `TriageModel`. Its constructor takes `(inner: TriageModel, client)`. `write_notes` and `judge_rules` each run inside a span named `model.write_notes` or `model.judge_rules`. `suggest_setup` passes through with no span.
  - `def build_tracing(settings: Settings) -> Tracing`
  - `def record_outcome(tracing: Tracing, run: Run, decision: Decision, notes: Notes | None) -> None` posts the scores `route`, `floor`, `unsure` and `ai_failed`.
- Settings fields:
  - `langfuse_public_key: str | None = None`
  - `langfuse_secret_key: SecretStr | None = None`
  - `langfuse_base_url: str = "http://localhost:3000"`
  - With the `HERALD_` prefix, the env names are `HERALD_LANGFUSE_PUBLIC_KEY`, `HERALD_LANGFUSE_SECRET_KEY` and `HERALD_LANGFUSE_BASE_URL`.

- [ ] **Step 1: Write the failing tests** in `apps/server/tests/test_tracing.py`.

The model-level tests use `StubClient`, a fake that records span names and scores and can be told to raise. It implements only the client methods `TracedModel`, `LangfuseTracing.score` and `run` use. There are seven tests:
  - `test_tracing_is_off_without_keys`
  - `test_tracing_is_off_with_empty_keys`
  - `test_tracing_is_off_when_langfuse_is_missing`
  - `test_tracing_is_off_when_langfuse_is_down`
  - `test_traced_model_passes_calls_through`
  - `test_traced_model_passes_errors_through`
  - `test_outcome_scores`

```python
def test_tracing_is_off_without_keys(settings):
    assert build_tracing(settings) is NO_TRACING


def test_tracing_is_off_with_empty_keys(settings):
    keyed = settings.model_copy(update={"langfuse_public_key": "", "langfuse_secret_key": SecretStr("")})
    assert build_tracing(keyed) is NO_TRACING


def test_tracing_is_off_when_langfuse_is_missing(settings, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "langfuse", None)  # import raises ImportError
    keyed = settings.model_copy(update={"langfuse_public_key": "pk", "langfuse_secret_key": SecretStr("sk")})
    assert build_tracing(keyed) is NO_TRACING
    assert "langfuse is not installed" in caplog.text


def test_tracing_is_off_when_langfuse_is_down(settings, caplog):
    keyed = settings.model_copy(update={
        "langfuse_public_key": "pk", "langfuse_secret_key": SecretStr("sk"),
        "langfuse_base_url": "http://127.0.0.1:9",  # nothing listens here
    })
    assert build_tracing(keyed) is NO_TRACING
    # One warning, not one per email. Count only Herald's records: the SDK logs on its own.
    assert len([r for r in caplog.records if r.name == "herald_server.tracing"]) == 1
    assert not tracing._instrumented  # anthropic stays unpatched for the rest of the session


async def test_traced_model_passes_calls_through():
    client = StubClient()
    traced = TracedModel(FakeModel(), client)
    notes = await traced.write_notes(EMAIL, "Tripfold", CONFIG)
    assert notes == await FakeModel().write_notes(EMAIL, "Tripfold", CONFIG)
    await traced.judge_rules(EMAIL, "Tripfold", CONFIG)
    assert client.spans == ["model.write_notes", "model.judge_rules"]


async def test_traced_model_passes_errors_through():
    traced = TracedModel(FailingModel(), StubClient())  # FailingModel raises ModelError
    with pytest.raises(ModelError):
        await traced.write_notes(EMAIL, "Tripfold", CONFIG)


def test_outcome_scores():
    client = StubClient()
    tracing = LangfuseTracing(client, model_name="claude-haiku-5-5",
                              propagate=stub_propagate, handler=object)
    decision = Decision(route=Route.ALERT, urgency=None, reason="floor",
                        floor_flags=[RiskFlag.LEGAL_THREAT])
    record_outcome(tracing, Run("t1", []), decision, notes=None)
    assert client.scores == [("t1", "route", "alert"), ("t1", "floor", True),
                             ("t1", "unsure", False), ("t1", "ai_failed", True)]
```

Use the `RiskFlag` member that exists in `schema.py`. The test's point is that any floor flag counts.

- [ ] **Step 2: Run the tests to make sure they fail**

Run: `uv run pytest apps/server/tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: herald_server.tracing`.

- [ ] **Step 3: Add the settings fields**, with a comment that says they are dev only and that tracing is on only when both keys are set and not empty.

Create a repo-root `conftest.py` with one autouse fixture. It uses `monkeypatch.setenv` to set `HERALD_LANGFUSE_PUBLIC_KEY` and `HERALD_LANGFUSE_SECRET_KEY` to `""`, and calls `get_settings.cache_clear()` before and after the test. Its comment says why: a developer's `.env` keys must never send test runs to Langfuse, and `cli.main` in the eval tests reads `get_settings()`.

- [ ] **Step 4: Implement `tracing.py`**
  - `build_tracing` returns `NO_TRACING` unless both keys are set.
  - It imports `langfuse` lazily. On `ImportError` it logs a WARNING "langfuse is not installed; tracing is off" and returns `NO_TRACING`. The comment says why the import is lazy: the prod image has no dev group.
  - It makes the client and calls `auth_check()`. On `False` or any exception it calls `client.shutdown()`, so no exporter thread is left running, logs one WARNING naming the base URL, and returns `NO_TRACING`.
  - Only after auth succeeds, it instruments Anthropic once per process, through a module-level `_instrumented` flag. The comment says why: `create_app` runs once per test and on every reload, and double instrumenting wraps `parse` twice.
  - `LangfuseTracing.run` combines `propagate(...)` with a root `start_as_current_observation(as_type="span", name=name)`. It yields `Run(trace_id=client.get_current_trace_id(), callbacks=[handler(public_key=...)])`. The handler gets the public key because Herald never sets the `LANGFUSE_*` env vars. The tags are the given tags plus `model_name`.
  - `score` and the trace-opening calls in `run` catch `Exception`, log a WARNING and carry on. Never let one reach triage.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest apps/server/tests/test_tracing.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add conftest.py apps/server/src/herald_server/tracing.py apps/server/src/herald_server/settings.py apps/server/tests
git commit -m "Add dev-only Langfuse tracing: settings, traced model, outcome scores"
```

---

### Task 3: Trace live triage and Try in the API and worker

**Files:**
- Modify: `apps/server/src/herald_server/services.py` (`Services.tracing`; `build_services` wraps the model)
- Modify: `apps/server/src/herald_server/pipeline.py` (`_run`, `process_email`, `trial_read`)
- Modify: `apps/server/src/herald_server/api/main.py` (lifespan shutdown)
- Modify: `apps/server/src/herald_server/worker/main.py` (`shutdown`)
- Modify: call sites of `process_email` and `trial_read`: `queue.py`, `worker/main.py`, `api/routes/emails.py`
- Test: `apps/server/tests/test_tracing.py`

**Interfaces:**
- Consumes: `build_tracing`, `Tracing`, `Run`, `record_outcome` and `NO_TRACING` from Task 2.
- Produces:
  - `Services.tracing: Tracing`.
  - `build_services` calls `tracing = build_tracing(settings)` and `model = tracing.wrap_model(model)` before `build_graph(model)`.
  - New signatures:
    - `process_email(api, graph, email_id, tracing: Tracing = NO_TRACING) -> Decision`
    - `trial_read(api, graph, email_id, config, tracing: Tracing = NO_TRACING)`
  - Inside, `_run` opens `tracing.run(...)`, passes `run.callbacks` to `triage()`, then calls `record_outcome(...)`. It uses name `triage` with tag `live` for `process_email`, and name `trial-read` with tag `try` for `trial_read`. User = `email.workspace_id`, session = `email.id`, metadata = `{"email_id": email.id}`.

- [ ] **Step 1: Write the failing tests**

`RecordingTracing` is a stub `Tracing` that records `run(...)` calls and scores. The error test uses the real `LangfuseTracing` over Task 2's `StubClient(raise_all=True)`, so it tests the real error handling, not a stub's.

```python
async def test_process_email_traces_one_run(app, client, agent_api):
    # helper: POST a test email the way existing tests do. The inline queue triages it
    # once already, and running process_email again on it is fine (a re-read does the same).
    email_id = await make_test_email(client)
    tracing = RecordingTracing()
    await process_email(agent_api, app.state.services.graph, email_id, tracing)
    (name, kw), = tracing.runs
    assert name == "triage" and kw["session_id"] == email_id and "live" in kw["tags"]
    assert {s[1] for s in tracing.scores} == {"route", "floor", "unsure", "ai_failed"}


async def test_trial_read_is_traced_as_try(...):
    # same shape: name == "trial-read", "try" in tags


async def test_tracing_errors_never_reach_triage(app, client, agent_api):
    email_id = await make_test_email(client)
    tracing = LangfuseTracing(StubClient(raise_all=True), model_name="fake")
    decision = await process_email(agent_api, app.state.services.graph, email_id, tracing)
    detail = (await client.get(f"/api/workspaces/{WS}/emails/{email_id}")).json()
    assert detail["decision"]["route"] == decision.route  # saved as usual
```

Use the email detail route and workspace id the existing tests use. Don't add a new route.

- [ ] **Step 2: Run the tests to make sure they fail**

Run: `uv run pytest apps/server/tests/test_tracing.py -v`
Expected: the new tests FAIL with `TypeError` on the extra `tracing` argument.

- [ ] **Step 3: Wire it in**
  - Add the `tracing` parameter to `process_email`, `trial_read` and `_run`. The call sites pass `services.tracing`, or `ctx["services"].tracing` in the worker.
  - The pipeline has no try/except of its own around tracing. `LangfuseTracing.run` catches its own errors: if opening the trace fails, it yields `Run(None, [])`, so triage runs untraced.
  - Call `services.tracing.shutdown()` last in the FastAPI lifespan and in the worker's `shutdown`, with a comment: the SDK batches spans in a background thread, and a process that exits without this loses the last ones.

- [ ] **Step 4: Run all server tests**

Run: `uv run pytest apps/server/tests -v`
Expected: all PASS.

- [ ] **Step 5: Check by hand**
  1. Put the dev keys in `.env` with `HERALD_MODEL_PROVIDER=anthropic`, then run `make langfuse` and `make dev`.
  2. Send a test email from the inbox and use Try once.

  Expected, checked with Task 0's polling helper: a `triage` trace and a `trial-read` trace. Each has node spans, `model.write_notes` and `model.judge_rules` spans that hold `messages.parse` generations, and the four scores.

- [ ] **Step 6: Commit**

```bash
git add apps/server
git commit -m "Trace live triage and Try runs in Langfuse when dev tracing is on"
```

---

### Task 4: Trace eval runs, wire docker-dev, write the docs

**Files:**
- Modify: `packages/evals/src/herald_evals/runner.py` (`Trial.trace_id`, `run_case`, `run_all`)
- Modify: `packages/evals/src/herald_evals/cli.py` (`main`, `_report`)
- Modify: `infra/docker-compose.dev.yml` (the `x-server` anchor)
- Modify: `.env.example`, `docs/architecture.md`, `docs/decisions.md`, `README.md`
- Test: `packages/evals/tests/test_evals.py`

**Interfaces:**
- Consumes: `Tracing`, `NO_TRACING`, `build_tracing` and `Run` from Task 2. `Scored.passed` from `score.py`.
- Produces:
  - `Trial.trace_id: str | None = None`.
  - `run_case(model, dataset, case, run, now, tracing: Tracing = NO_TRACING, session: str = "")`
  - `run_all(model, work, *, repeats=1, concurrency=4, progress=None, tracing: Tracing = NO_TRACING, session: str = "")`
  - Each trial runs under `tracing.run("eval", user_id=f"eval-{dataset.name}", session_id=session, tags=["eval", dataset.name], metadata={"case": case.id, "run": str(run)})`, on a graph built from `tracing.wrap_model(recorder)`. After the run, `record_outcome(...)` posts the four outcome scores, the same as for live runs.
  - `_report` returns `list[Scored]`.

- [ ] **Step 1: Write the failing test**

```python
async def test_run_all_traces_each_trial():
    tracing = RecordingTracing()  # same stub as in the server tests; copy, don't import tests
    data = ds.load_named("tripfold")
    trials = await run_all(FakeModel(), [(data, data.cases[0])], repeats=2,
                           tracing=tracing, session="eval-test")
    assert [r[0] for r in tracing.runs] == ["eval", "eval"]
    assert all(t.trace_id == "trace-1" for t in trials)  # the stub's fixed id
    assert {s[1] for s in tracing.scores} == {"route", "floor", "unsure", "ai_failed"}
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest packages/evals/tests/test_evals.py -k traces -v`
Expected: FAIL with `TypeError` on `tracing`.

- [ ] **Step 3: Implement the eval changes**
  - Add the new parameters to `runner.py`.
  - In `cli.main`, skip tracing on `--rescore`, which makes no model calls. Otherwise:
    - make `tracing = build_tracing(get_settings())` and `session = f"eval-{stamp}"`;
    - pass both to `run_all`;
    - after `_report`, post `tracing.score(s.trial.trace_id, "passed", s.passed)` for each `Scored`;
    - call `tracing.shutdown()` in a `finally`.
  - Record the session in `meta["langfuse_session"]` only when `tracing.enabled`.

- [ ] **Step 4: Wire docker-dev**
  - In `x-server` in `docker-compose.dev.yml`, add `HERALD_LANGFUSE_BASE_URL: http://host.docker.internal:3000` to `environment`, and `extra_hosts: ["host.docker.internal:host-gateway"]`.
  - Comment: Langfuse is its own compose project, and the containers reach it through the host's published port (Docker Desktop). The keys still come from `.env`.

- [ ] **Step 5: Write the docs**
  - `.env.example`: a commented "Dev tracing (Langfuse)" block with the three variables and the dev keys.
  - `docs/architecture.md`:
    - three rows in the Configuration table: default unset, off in lite mode unless set;
    - a short "Tracing (dev)" section covering `make langfuse`, what a trace holds, the scores, and that real generations need `HERALD_MODEL_PROVIDER=anthropic`;
    - nothing in "Not built yet" changes.
  - `docs/decisions.md`: one row dated 2026-11-04. It says Langfuse, self-hosted and dev only, through the dev dependency group. Why: traces hold customer emails, so they stay on our machine, and the prod image cannot trace.
  - `README.md`: add `make langfuse` beside the other dev commands.

- [ ] **Step 6: Check that the prod image can't trace**

Run: `uv tree --package herald-server --no-dev | grep -ci langfuse`
Expected: `0`.

- [ ] **Step 7: Run everything**

Run: `make test && make lint`
Expected: all PASS.

Then run `make eval ARGS="--case sue-is-a-name --repeats 2"` with Langfuse up and the keys set.
Expected, checked with Task 0's polling helper: two `eval` traces in one session, each with the four outcome scores and a `passed` score.

- [ ] **Step 8: Commit**

```bash
git add packages/evals infra/docker-compose.dev.yml .env.example docs README.md
git commit -m "Trace eval runs in Langfuse and document dev tracing"
```
