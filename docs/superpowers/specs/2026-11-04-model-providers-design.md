# Model Providers: Design

Date: 2026-11-04 · Branch: `feat/model-providers` · Status: draft for review

## Goal

Try small, fast open-weight models for triage, through OpenRouter. Today the model is chosen by an if/else in `services.py` between `AnthropicModel` and the offline `FakeModel`. This change makes the model a plug-in, adds OpenRouter as a provider, and removes `FakeModel`.

## Decisions taken in brainstorming

- **Providers are plug-ins found through Python entry points.** Core ships two, `anthropic` and `openrouter`. Any installed package can add one without a change to Herald.
- **OpenRouter is the default provider.** The direct Anthropic provider stays, for prompt caching and the eval baselines.
- **`FakeModel` is removed completely.** No `fake` provider, no keyword heuristics in shipped code. `make lite` needs an OpenRouter key.
- **Tests make real calls only where they check the AI's judgement.** Plumbing tests use a scripted test double that returns exactly what the test hands it. It has no keyword logic and lives in test code only.
- **The default model is picked by an eval bake-off**, not from public benchmarks. OpenRouter publishes no latency figures, and generic scores do not say how a model handles Herald's rules and safety floor. `openai/gpt-oss-20b` is the default until the bake-off runs.

## Plugin contract

`herald_core/providers/__init__.py`:

```python
class ModelProvider(Protocol):
    name: str            # what HERALD_MODEL_PROVIDER says, e.g. "openrouter"
    default_model: str   # used when HERALD_MODEL_NAME is empty
    api_key_env: str     # e.g. "OPENROUTER_API_KEY"

    def build(self, model: str, api_key: str) -> TriageModel: ...


ENTRY_POINT_GROUP = "herald.model_providers"

def load_provider(name: str) -> ModelProvider: ...
def provider_names() -> list[str]: ...
```

Core registers its two in `packages/core/pyproject.toml`:

```toml
[project.entry-points."herald.model_providers"]
anthropic = "herald_core.providers.anthropic:provider"
openrouter = "herald_core.providers.openrouter:provider"
```

`load_provider` reads the group with `importlib.metadata.entry_points`. An unknown name raises an error that lists the installed names. The entry point's name must equal the provider's `name`.

### Files

| File | Holds |
| --- | --- |
| `herald_core/model.py` | `TriageModel`, `ModelError`, `MAX_TOOL_ROUNDS`, `RULES_ASK`, `_Verdicts`, the setup instructions. Nothing provider-specific. |
| `herald_core/providers/__init__.py` | `ModelProvider`, `load_provider`, `provider_names` |
| `herald_core/providers/anthropic.py` | `AnthropicModel` (moved unchanged), `provider` |
| `herald_core/providers/openrouter.py` | `OpenRouterModel`, `provider` |

`model_tools.py` keeps the tool definition in Anthropic's shape (`name`, `description`, `input_schema`). The OpenRouter provider converts it.

## Settings and wiring

- `model_provider: str = "openrouter"`. No fixed list: a plug-in adds names.
- `model_name: str | None = None`. Empty means the provider's `default_model`.
- `anthropic_api_key` goes. The key is read from the env var the provider names (`api_key_env`), from the process environment first and then the `.env` files. Values in `.env` never reach `os.environ`, so Herald reads them itself (`dotenv_values`, already a dependency through pydantic-settings). Each provider reads only its own variable, so an Anthropic key is never sent to OpenRouter by mistake, and production's `ANTHROPIC_API_KEY` keeps working.
- Startup fails when the provider is unknown or its key is missing, with a message that names the variable.
- `services.build_services(settings, model=None)`: a passed `model` is used as is (tests). Otherwise it calls `load_provider(settings.model_provider).build(...)`. `tracing.py` and the evals CLI use the same lookup and tag runs with `provider/model`, with no provider names in their code.

## OpenRouter provider

- `openai` SDK (`AsyncOpenAI`) at `https://openrouter.ai/api/v1`, with `max_retries=6` in the evals as now. Headers `X-Title: Herald`.
- Structured output with `chat.completions.parse(response_format=<pydantic model>)`.
- `extra_body={"provider": {"require_parameters": True}}`, so OpenRouter routes only to endpoints that support structured outputs and tool calls. Without it, a request can land on an endpoint that ignores the schema.
- `reasoning: {"effort": "low"}` in `extra_body`. Models that do not reason ignore it. The bake-off can change it.
- The tool loop matches `AnthropicModel`: one round with the tools, then the same request with `tool_choice="none"` so the model has to answer with the schema. Every tool call gets a `tool` message with its result. A tool failure goes back as error text.
- No `cache_control`: OpenRouter's providers cache repeated prefixes on their own.
- `openai.APIError`, a pydantic `ValidationError`, a refusal and an empty parse all raise `ModelError`. The email then goes to "Needs a look" as today, and a safety-floor word match still alerts.
- If the SDK's strict schema rejects a construct in `Notes`, `SetupDraft` or `_Verdicts`, the fix goes in the schema the model sees, not in `schema.py`'s meaning.

## Removing FakeModel

- Delete `FakeModel`, `_FAKE_BULK_MARKERS`, `_FAKE_TOPICS`.
- Evals CLI: `--model` choices come from `provider_names()`, default `openrouter`. `--model fake` goes. Run metadata records provider, model and temperature ("API default").
- Docs: `CLAUDE.md`, `README.md`, `.env.example`, `docs/architecture.md` (plug-in table, settings table, tracing note), `docs/evals.md`, `docs/decisions.md`.
- `infra/docker-compose.prod.yml` keeps `anthropic` as its explicit default until the bake-off picks an OpenRouter model.

## Tests

- **`ScriptedModel`** (test code only, shared by the core, server and evals tests). It returns the `Notes`, verdicts or `SetupDraft` the test gives it, either fixed or from a function of the email, or raises the exception it is given. It records each call's arguments. It can hold a call on an event, for the parallel-run test. It replaces `CountingModel`, `BrokenModel`, `CrashingModel`, `RecordingModel`, `AskingModel`, `GatedModel` and the evals' `FailingModel` and `Spy`.
- **Server tests** pass a `ScriptedModel` through the `app` fixture (`create_app(settings, model=...)`). `model_provider="fake"` goes from `conftest.py`.
- **Tests that leaned on the fake's guesses** (capitals meaning anger, "unsubscribe" meaning spam, a question with no topic word meaning unsure) now script those notes. They test `decide`, routing and the API, not judgement. Judgement is what the evals measure.
- **Provider unit tests** use a stub client that records request kwargs, as `test_model.py` does for Anthropic now: schema passed, tool round then `tool_choice="none"`, tool results sent back, errors mapped to `ModelError`.
- **Registry tests:** both built-in names load, `provider_names()` lists them, an unknown name fails with the list, a missing key fails at startup.
- **Live smoke tests**, marked `live` and skipped without `OPENROUTER_API_KEY`: notes for one email, rule verdicts, a setup draft, and a run where the model is offered the tool.

## Bake-off

After the provider lands, with `OPENROUTER_API_KEY` in `.env`, run the evals (3 runs per case) for:

| Model | Size (active) | $/M in / out |
| --- | --- | --- |
| `openai/gpt-oss-20b` | 21B (3.6B) | 0.03 / 0.13 |
| `qwen/qwen3-30b-a3b-instruct-2507` | 30B (3B) | 0.10 / 0.30 |
| `google/gemma-4-26b-a4b-it` | 26B (4B) | 0.10 / 0.30 |
| `mistralai/mistral-small-3.2-24b-instruct` | 24B dense | 0.075 / 0.20 |

Prices are OpenRouter's list on 2026-11-04. The pick: missed alerts at or under 5% first, then the lowest median time per email. The baseline is Claude Haiku's last run: 3% missed alerts, 98% topic accuracy, 3.2 s median. The table goes in the PR and the winner becomes `default_model`.

## Out of scope

- Self-hosted endpoints (Ollama, vLLM). The OpenRouter provider could take a base URL later, or a plug-in could add one.
- Per-workspace model choice.
- Fallback from one provider to another when a call fails.
