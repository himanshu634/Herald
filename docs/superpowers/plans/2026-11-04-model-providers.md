# Model Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the triage model a plug-in found through entry points, add an OpenRouter provider as the default, and remove `FakeModel`.

**Architecture:** `herald_core.providers` defines a `ModelProvider` protocol and loads providers from the `herald.model_providers` entry-point group. Core ships `anthropic` (the existing `AnthropicModel`, moved) and `openrouter` (new, `openai` SDK). The server, worker, tracing and evals pick a provider by name from settings. Tests use a scripted test double in test code; a few `live` tests call OpenRouter.

**Tech Stack:** Python 3.13, uv workspace, `openai` SDK 3.x, `anthropic` SDK, pydantic 2, pydantic-settings, pytest (asyncio auto mode), FastAPI.

**Spec:** `docs/superpowers/specs/2026-11-04-model-providers-design.md`

## Global Constraints

- Entry-point group: `herald.model_providers`. Built-in names: `anthropic`, `openrouter`. The entry point's name equals the provider's `name`.
- `openrouter` provider: `default_model = "openai/gpt-oss-20b"`, `api_key_env = "OPENROUTER_API_KEY"`, base URL `https://openrouter.ai/api/v1`, header `X-Title: Herald`, `extra_body` carries `{"provider": {"require_parameters": True}, "reasoning": {"effort": "low"}}`.
- `anthropic` provider: `default_model = "claude-haiku-5-5"`, `api_key_env = "ANTHROPIC_API_KEY"`.
- Settings: `model_provider: str = "openrouter"`, `model_name: str | None = None` (empty means the provider's default). `anthropic_api_key` is removed.
- A provider reads only its own key variable, from the process environment first, then the `.env` files. Startup fails when the provider is unknown (message lists installed names) or its key is missing (message names the variable).
- No keyword heuristics and no `fake` provider in shipped code (`src/`). Test doubles live in test code only.
- `MAX_TOOL_ROUNDS = 1`: one round with tools, then a request with `tool_choice="none"`. Every model failure raises `ModelError`.
- `infra/docker-compose.prod.yml` keeps `anthropic` as its explicit default.
- Existing invariants hold: nothing in `pipeline.py` or `tools/` imports `sqlmodel`; the AI never sets status.
- Style: ruff, line length 100, Python 3.13. Comments are short plain sentences and say why for non-obvious logic. Match the surrounding comment density.

## Review Focus

1. Key set only in `.env`, not in `os.environ` → the provider still gets it (pydantic-settings never exports `.env` to `os.environ`). Test in Task 4.
2. `HERALD_MODEL_PROVIDER` misspelled → startup fails naming the bad value and listing installed names. Test in Task 1.
3. OpenRouter returns a refusal, an empty parse, or still asks for a tool on the last round → `ModelError`, email lands in Needs a look. Tests in Task 2.
4. The model sends tool arguments that are not valid JSON → the tool gets an error result and the model still answers; nothing crashes. Test in Task 2.
5. Provider switched from `anthropic` to `openrouter` with only `ANTHROPIC_API_KEY` set → startup fails naming `OPENROUTER_API_KEY`; the Anthropic key is never sent. Test in Task 4.

---

### Task 1: Provider registry and the Anthropic provider

**Files:**
- Create: `packages/core/src/herald_core/providers/__init__.py`
- Create: `packages/core/src/herald_core/providers/anthropic.py`
- Modify: `packages/core/src/herald_core/model.py` (move `AnthropicModel`, `_run`, `_result` out; keep `TriageModel`, `ModelError`, `MAX_TOOL_ROUNDS`, `RULES_ASK`, `_Verdicts`, `_SETUP_INSTRUCTIONS`, `FakeModel` for now; drop `DEFAULT_MODEL`)
- Modify: `packages/core/pyproject.toml` (entry points)
- Modify: `apps/server/src/herald_server/settings.py`, `apps/server/src/herald_server/services.py`, `packages/evals/src/herald_evals/cli.py` — only their imports of `AnthropicModel` / `DEFAULT_MODEL`, pointed at the new module, so the suite stays green. Their real rewiring is Tasks 3 and 4.
- Test: `packages/core/tests/test_providers.py`; modify `packages/core/tests/test_model.py` imports

**Interfaces:**
- Produces:
  - `herald_core.providers.ModelProvider` (Protocol): `name: str`, `default_model: str`, `api_key_env: str`, `build(self, model: str, api_key: str, max_retries: int = 2) -> TriageModel` (`max_retries` goes to the SDK client; the evals pass 6)
  - `herald_core.providers.ENTRY_POINT_GROUP = "herald.model_providers"`
  - `herald_core.providers.load_provider(name: str) -> ModelProvider` — raises `UnknownProvider(ValueError)` whose message contains the bad name and every installed name
  - `herald_core.providers.provider_names() -> list[str]` (sorted)
  - `herald_core.providers.anthropic.AnthropicModel` (unchanged constructor: `client=None, model=..., api_key=None`) and `herald_core.providers.anthropic.provider`
  - `herald_core.providers.anthropic.DEFAULT_MODEL = "claude-haiku-5-5"`

- [ ] **Step 1: Write the failing tests** in `test_providers.py`:

```python
def test_built_in_providers_are_installed():
    assert "anthropic" in provider_names()  # Task 2 adds "openrouter" here

def test_anthropic_provider_builds_its_model():
    provider = load_provider("anthropic")
    assert provider.name == "anthropic"
    assert provider.default_model == "claude-haiku-5-5"
    assert provider.api_key_env == "ANTHROPIC_API_KEY"
    assert isinstance(provider.build("claude-haiku-5-5", "sk-test"), AnthropicModel)

def test_unknown_provider_lists_the_installed_ones():
    with pytest.raises(UnknownProvider) as info:
        load_provider("openrutor")
    assert "openrutor" in str(info.value)
    assert "anthropic" in str(info.value)
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest packages/core/tests/test_providers.py -v` → ImportError.

- [ ] **Step 3: Implement.** `load_provider` uses `importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)` and loads the matching entry point. Register `anthropic = "herald_core.providers.anthropic:provider"` under `[project.entry-points."herald.model_providers"]` in core's `pyproject.toml`, then run `uv sync` so the editable install publishes the entry point. `provider` is a small frozen dataclass instance (or class with class attributes) whose `build` returns `AnthropicModel(AsyncAnthropic(api_key=api_key, max_retries=max_retries), model=model)`. Move `AnthropicModel` without behaviour changes; update `test_model.py` to import it from the new module.

- [ ] **Step 4: Run** `uv run pytest packages/core apps/server packages/evals -q` → all pass.

- [ ] **Step 5: Commit** — `git commit -m "Load model providers from entry points; move AnthropicModel into one"`

### Task 2: OpenRouter provider

**Files:**
- Create: `packages/core/src/herald_core/providers/openrouter.py`
- Modify: `packages/core/pyproject.toml` (add `openai>=3.40` dependency; entry point `openrouter = "herald_core.providers.openrouter:provider"`), root `pyproject.toml` (register pytest marker `live: calls a real model provider; skipped without its API key`), `uv.lock` via `uv sync`
- Test: `packages/core/tests/test_openrouter.py`, `packages/core/tests/test_live.py`; widen `test_built_in_providers_are_installed`

**Interfaces:**
- Consumes: `ModelProvider`, `ModelError`, `MAX_TOOL_ROUNDS`, `RULES_ASK`, `_Verdicts`, `_SETUP_INSTRUCTIONS` from `herald_core.model`; `ModelTool` from `herald_core.model_tools`; `system_prompt`, `user_message` from `herald_core.prompt`
- Produces: `herald_core.providers.openrouter.OpenRouterModel(client: AsyncOpenAI | None = None, model: str = DEFAULT_MODEL)` implementing `TriageModel`; the provider's `build` makes `AsyncOpenAI(api_key=api_key, base_url=BASE_URL, max_retries=max_retries, default_headers={"X-Title": "Herald"})`; `DEFAULT_MODEL = "openai/gpt-oss-20b"`; `BASE_URL = "https://openrouter.ai/api/v1"`; `provider`

Behaviour (mirror `AnthropicModel` method by method; `write_notes`, `judge_rules` and `suggest_setup` build the same system and user content it builds, including `RULES_ASK` and the no-rules short cut):
- One private `_parse(system, content, output, tools=())` that calls `client.chat.completions.parse(model=..., messages=[{"role": "system", ...}, {"role": "user", ...}], response_format=output, extra_body=EXTRA_BODY, **tools_kwargs)`.
- Tools: convert each `tool.definition` (Anthropic shape) to `{"type": "function", "function": {"name", "description", "parameters": input_schema, "strict": True}}`. The SDK's `parse()` rejects function tools that are not strict.
- Loop like `AnthropicModel._parse`: on `finish_reason == "tool_calls"` append the assistant message (with its `tool_calls`) and one `{"role": "tool", "tool_call_id", "content"}` per call, then call again; the last round passes `tool_choice="none"`. Tool arguments are a JSON string: invalid JSON, an unknown tool name and a `ToolError` each become content starting `"Error: "`.
- `openai.APIError` and pydantic `ValidationError` → `ModelError`. After the loop, `message.refusal` set or `message.parsed is None` → `ModelError` naming the `finish_reason`.
- No `cache_control`, no temperature.

- [ ] **Step 1: Write the failing tests** in `test_openrouter.py`, with a stub client like `test_model.py`'s (an object whose `chat.completions.parse` records kwargs and returns queued responses built from `openai.types.chat.ParsedChatCompletion`, or simple namespaces with `choices[0].message` and `choices[0].finish_reason`):
  - `test_notes_call_sends_schema_and_routing` — kwargs have `response_format is Notes`, `model == "openai/gpt-oss-20b"`, `extra_body == {"provider": {"require_parameters": True}, "reasoning": {"effort": "low"}}`, first message role `system` with `system_prompt("Tripfold", CONFIG)`.
  - `test_rules_call_ends_with_rules_ask` — user content ends with `f"\n\n{RULES_ASK}"`; returns the parsed `_Verdicts.verdicts`.
  - `test_no_rules_means_no_call` — config without rules → `[]`, zero client calls.
  - `test_tool_round_then_answer` — first response `finish_reason="tool_calls"` with one `sender_history` call; second call's messages hold the assistant message and a `tool` message with `SenderLookup`'s text, and kwargs carry `tool_choice="none"`; tools kwarg has `strict: True`.
  - `test_bad_tool_arguments_go_back_as_an_error` — arguments `"{not json"` → tool message content starts with `"Error: "`, the call still returns notes.
  - `test_refusal_raises_model_error`, `test_empty_parse_raises_model_error`, `test_api_error_raises_model_error` (raise `openai.APIConnectionError(request=httpx.Request("POST", BASE_URL))`).
  - `test_openrouter_provider` — `load_provider("openrouter")` has the constraint values and `build(...)` returns an `OpenRouterModel`.
- In `test_live.py`, mark the module `pytest.mark.live` and skip unless `os.environ.get("OPENROUTER_API_KEY")`: `test_live_notes` (a Tripfold "Where is my order #123?" email → `Notes` with `topic` in the config's topic names), `test_live_rules` (an email that meets one rule → that `rule_id` in the verdicts), `test_live_setup_draft` (≥1 topic), `test_live_tool_round` (offered `SenderLookup`; returns notes, no exception).

- [ ] **Step 2: Run** `uv run pytest packages/core/tests/test_openrouter.py -v` → fails (module missing).
- [ ] **Step 3: Implement** `openrouter.py`, the dependency and the entry point; `uv sync`.
- [ ] **Step 4: Run** `uv run pytest packages/core -q` → pass, live tests skipped.
- [ ] **Step 5: Commit** — `git commit -m "Add the OpenRouter model provider"`

### Task 3: Scripted test double; core and evals off FakeModel; evals CLI by provider

**Files:**
- Create: `tests_support/scripted_model.py` (repo root); root `pyproject.toml` pytest `pythonpath = ["tests_support"]`
- Modify: `packages/core/tests/test_graph.py`, `packages/core/tests/test_config.py`, `packages/evals/tests/test_evals.py`
- Modify: `packages/evals/src/herald_evals/cli.py`, `docs/evals.md`

**Interfaces:**
- Consumes: `load_provider`, `provider_names` (Task 1); `Settings.secret` arrives in Task 4, so here the CLI reads the key with its existing `.env` reader, generalised to take the variable name (`_load_dotenv(name)`).
- Produces (`tests_support/scripted_model.py`):
  - `plain_notes(email: Email, config: WorkspaceConfig, **overrides) -> Notes` — `topic=config.topics[0].name`, `urgency=Urgency.NORMAL`, `anger=1`, `summary=email.subject[:120]`, `sure=True`, then `overrides`.
  - `class ScriptedModel` implementing `TriageModel`: `__init__(self, notes=None, verdicts=None, setup=None)`. Each argument may be a value, a callable `(email, config) -> value` (`setup`: `(name, description) -> SetupDraft`), or an `Exception` instance to raise. Defaults: `plain_notes`, `[]`, `DEFAULT_SETUP` (one topic `Questions` / `"Anything that fits no other topic"`, no facts, one guidance line, one alert rule). Attributes are public and may be reassigned by tests. `calls: list[tuple[str, dict]]` records `("write_notes" | "judge_rules" | "suggest_setup", kwargs)`.
  - No keyword logic of any kind.

Steps:
- [ ] **Step 1:** Write `tests_support/scripted_model.py` with a short test of its own in `packages/core/tests/test_scripted_model.py` (default notes use the first topic; an `Exception` argument is raised; a callable gets the email; `calls` records names in order).
- [ ] **Step 2:** Rewrite each `FakeModel` use in `test_graph.py`, `test_config.py` and `test_evals.py` on `ScriptedModel`. The subclass doubles (`CountingModel`, `BrokenModel`, `CrashingModel`, `RecordingModel`, `AskingModel`, `BothAskModel`, `GatedModel`, `FailingModel`, `Spy`) subclass `ScriptedModel` and keep calling `super()`. Where a test relied on the fake's guess (a newsletter closing, an "Unsubscribe" promotion, a floor word), script the notes it needs (`plain_notes(..., topic=SPAM_TOPIC)`, `RuleVerdict(rule_id="r-newsletter", matched=True, quote=...)`) and keep the assertion on the route. Delete `test_fake_suggest_setup_is_deterministic`; it tests only the fake.
- [ ] **Step 3: Evals CLI.** `--model` takes `choices=provider_names()`, default `"openrouter"`; `--model-name` defaults to `HERALD_MODEL_NAME` or empty, meaning the provider's `default_model`. `_model(provider_name, model_name)` loads the provider, reads `provider.api_key_env` (environment, then `.env`), exits with `"<VAR> is not set (in the environment or .env)."` when missing, and calls `provider.build(model_name, key, max_retries=6)`. Meta records `model` (provider), `model_name` (resolved), `temperature: "API default"`. CLI tests that ran `--model fake` monkeypatch `herald_evals.cli._model` to return a `ScriptedModel`. Update `docs/evals.md` commands (no `--model fake`; OpenRouter is the default; `--model anthropic` for Claude direct).
- [ ] **Step 4: Run** `uv run pytest packages/core packages/evals -q` → pass.
- [ ] **Step 5: Commit** — `git commit -m "Test with a scripted model; evals pick a provider by name"`

### Task 4: Server wiring, tracing, and server tests

**Files:**
- Modify: `apps/server/src/herald_server/settings.py`, `services.py`, `api/main.py`, `worker/main.py` (only if needed), `tracing.py`, root `pyproject.toml` dev group (add `openinference-instrumentation-openai` beside the anthropic one)
- Modify: `apps/server/tests/conftest.py`, every server test that breaks without the fake's guesses
- Modify: `packages/evals/src/herald_evals/cli.py` (use `Settings.secret` instead of its own `.env` reader)
- Test: `apps/server/tests/test_services.py` (new)

**Interfaces:**
- Consumes: `load_provider`, `UnknownProvider` (Task 1); `ScriptedModel`, `plain_notes` (Task 3)
- Produces:
  - `Settings.model_provider: str = "openrouter"`, `Settings.model_name: str | None = None`, `Settings.secret(name: str) -> str | None` — process environment first, then the `model_config` env files (later file wins, as pydantic-settings does), empty strings count as unset. Use `dotenv.dotenv_values`.
  - `build_services(settings: Settings, model: TriageModel | None = None) -> Services`; `create_app(settings: Settings | None = None, model: TriageModel | None = None) -> FastAPI`
  - `build_model(settings: Settings) -> TriageModel` in `services.py` — raises `RuntimeError` naming the variable when the key is missing; lets `UnknownProvider` propagate.
  - Server test fixture `scripted_model` returning the `ScriptedModel` the `app` fixture passes to `create_app`.

- [ ] **Step 1: Write the failing tests** in `test_services.py`:
  - `test_key_from_dotenv_reaches_the_provider(tmp_path, monkeypatch)` — `.env` in `tmp_path` with `OPENROUTER_API_KEY=sk-or-test`, `monkeypatch.chdir(tmp_path)`, `monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)` → `Settings().secret("OPENROUTER_API_KEY") == "sk-or-test"` and `build_model(Settings())` returns an `OpenRouterModel`.
  - `test_missing_key_names_the_variable` — only `ANTHROPIC_API_KEY` set, provider `openrouter` → `RuntimeError` whose message contains `OPENROUTER_API_KEY` and not the Anthropic key's value.
  - `test_unknown_provider_fails_at_startup` — `model_provider="nope"` → `UnknownProvider`.
  - `test_model_name_defaults_to_the_provider_default` — `model_name=None` → the built model uses `"openai/gpt-oss-20b"`.
- [ ] **Step 2: Run** them → fail.
- [ ] **Step 3: Implement** settings, `build_model`, the `model=` parameters, and tracing: the run tag becomes `f"{provider}/{model}"` from the resolved settings, with no provider names in the code; instrument the OpenAI SDK as well as Anthropic when the instrumentor is importable (same guard as the Anthropic one). Update `test_tracing.py`'s tag tests to the new format (`test_build_tracing_tags_fake_runs_as_fake` becomes a test that the tag carries provider and resolved model).
- [ ] **Step 4: Server tests.** `conftest.py`: drop `model_provider="fake"`; the `app` fixture builds `ScriptedModel()` and passes it to `create_app`; add the `scripted_model` fixture. Run `uv run pytest apps/server -q`, and for each failure that relied on the fake's guess, set `scripted_model.notes` / `.verdicts` / `.setup` in that test to what it needs. Keep each test's assertion about routing, status, events or API shape unchanged.
- [ ] **Step 5: Run** `uv run pytest -q` → all pass, live tests skipped.
- [ ] **Step 6: Commit** — `git commit -m "Pick the model provider from settings; server tests use the scripted model"`

### Task 5: Remove FakeModel and update the docs

**Files:**
- Modify: `packages/core/src/herald_core/model.py` (delete `FakeModel`, `_FAKE_BULK_MARKERS`, `_FAKE_TOPICS`, and the module docstring's fake sentence), `CLAUDE.md`, `README.md`, `.env.example`, `docs/architecture.md`, `docs/decisions.md`, `Makefile` (lite help text if it names the fake)

- [ ] **Step 1:** Delete the fake. `grep -rn "FakeModel\|_FAKE_\|model_provider=\"fake\"\|--model fake" --include=*.py .` (excluding `.venv`) → no hits.
- [ ] **Step 2: Docs.** `.env.example`: `HERALD_MODEL_PROVIDER` (default `openrouter`; `anthropic` for Claude direct), `OPENROUTER_API_KEY=`, `ANTHROPIC_API_KEY=` (needed only with `anthropic`), `HERALD_MODEL_NAME` (empty = provider default). `docs/architecture.md`: the plug-in table row for `TriageModel` lists the entry-point group and both providers; the settings table row `HERALD_MODEL_PROVIDER` shows default `openrouter`; a short "Model providers" paragraph on writing a plug-in (a `ModelProvider` object registered under `herald.model_providers` in the plug-in package's `pyproject.toml`); the tracing note says real generations show with either provider. `CLAUDE.md`: `make lite` line ("OpenRouter model, needs `OPENROUTER_API_KEY`"), the `model.py` sentence, and the swappable-backends bullet (`TriageModel` via provider plug-ins; tests use `ScriptedModel` from `tests_support/`). `README.md` line 70. `docs/decisions.md` open question line: build defaults to OpenRouter, Claude direct optional, no fake.
- [ ] **Step 3: Run** `make lint` and `uv run pytest -q` → pass.
- [ ] **Step 4: Commit** — `git commit -m "Remove FakeModel; document model providers"`
