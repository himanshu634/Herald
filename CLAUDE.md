# CLAUDE.md

Guidance for Claude Code in this repository.

Herald is multi-tenant email triage for one-person businesses. A LangGraph pipeline writes notes on each customer email. The owner's plain-text rules and a fixed safety floor decide what alerts them. The demo business, Tripfold, is seed data in `apps/server/src/herald_server/seed.py`.

Read `docs/` before you change behaviour:

- `architecture.md`: flow, pipeline, status, SSE, plug-in points, database migrations.
- `decisions.md`: wins over `product-scope.md` where they differ.
- `development.md`: setup, env vars, Gmail on your machine, tracing, deploys.
- `evals.md`, `design-system.md`.

## Commands

Needs uv, pnpm 11 and Node 22+. `make help` lists every task.

```bash
make install          # uv sync + pnpm install
make lite             # API on :8000, no Docker: SQLite, in-memory bus, inline pipeline (needs OPENROUTER_API_KEY)
make web              # SvelteKit on :5173, proxies /api to :8000
make dev              # Postgres + Redis in Docker, then API, worker and web in one terminal
make infra            # Postgres + Redis only; then make api and make worker, each in its own terminal
make migrate          # bring the database to the latest schema (api, lite and dev run it first)
make migration m="…"  # write a migration from model changes; read it before you commit
make migrate-check    # fail when a model change has no migration
make test             # pytest (core, evals, server) and vitest
make lint             # ruff check, ruff format --check, eslint + prettier, svelte-check
make format
make gen-api          # regenerate apps/web/src/lib/api/schema.d.ts from FastAPI's OpenAPI
make eval ARGS="…"    # triage evals; e.g. ARGS="--model anthropic", "--case <id>", "--repeats 3"
make langfuse         # local Langfuse on :3000 for dev tracing
```

Single tests, from the repo root (pytest config is in the root `pyproject.toml`):

```bash
uv run pytest apps/server/tests/test_api.py::test_workspaces_are_isolated
uv run pytest packages/core/tests -k decide
pnpm -C apps/web exec vitest run src/lib/ui/tones.spec.ts
```

Tests need no Docker or API key. The few `live` tests call OpenRouter and skip without `OPENROUTER_API_KEY`.

## Layout

One uv workspace for Python (root `pyproject.toml`). One pnpm workspace that holds only `apps/web`.

### `packages/core` (`herald_core`)

Business-agnostic and I/O-free: no database, no Redis.

- `schema.py`: shared Pydantic types (`WorkspaceConfig`, `Email`, `Notes`, `Decision`, `Route`).
- `graph.py`: builds the graph once and shares it across tenants. Each run carries its workspace config in state (`state.py`). Each node is one file in `nodes/`; `graph.py` only wires them:

  ```
  START -> word_check ───────────────────────────────┐
  START -> gather_context ┬-> write_notes ───────────┼-> decide -> END
                          └-> judge_rules ───────────┘
  ```

  `word_check` is the regex safety floor (`safety.py`). `decide` (`decide.py`) is plain Python.
- `model.py`: the `TriageModel` protocol. `providers/` holds the provider registry (entry-point group `herald.model_providers`): `openrouter` (default) and `anthropic`.
- `tools.py`: tools that run in code before the model reads the email (`Toolbox`). `model_tools.py`: tools the model may call itself (`sender_history`, served from the history `gather_context` fetched). Thread and corrections go into the prompt up front.

### `apps/server` (`herald_server`)

- FastAPI app (`api/main.py:create_app`) and arq worker (`worker/main.py`) share `Services` (`services.py`: engine, bus, compiled graph). Settings are `HERALD_*` env vars or `.env` (`settings.py`).
- `pipeline.process_email` loads the email, runs the graph and saves the result through `AgentApi` (`internal/client.py`). That client calls the token-guarded internal routes (`api/routes/internal.py`, `/internal/v1`, not in OpenAPI). The save route sets status, commits, publishes `email.noted`, and records `alert.sent` when the route is `alert`. Inline mode calls the same routes in memory.
- `tools/`: the history tools, one file each, bound to the email being judged (`bound.py`). Their queries live in `internal/history.py`. The thread query also returns the owner's sent replies (`from_owner`).
- `sync.py` pulls mail through a connector. `setup.py` drafts the first config at onboarding. `status.py` holds the owner actions. `replies.py` sends owner replies. `crypto.py` seals mailbox credentials and OAuth state (`HERALD_TOKEN_KEY`). `tracing.py` is dev-only Langfuse and the only file that knows it.
- Alerts stay in the app. The only mail that leaves it is a reply the owner writes and sends.

### `packages/evals` (`herald_evals`)

Labelled test emails (TOML in `src/herald_evals/datasets/`) run through the real graph, scored into a Markdown report and a JSON run record in `packages/evals/results/`. Labels say what Herald should do. Cases start `reviewed = false` until a person agrees.

### `apps/web`

SvelteKit with Svelte 5 runes forced on, built as a static SPA (`adapter-static`, `ssr = false`). FastAPI owns all server logic. `src/lib/api/client.ts` wraps the routes with types from the generated `schema.d.ts`. `src/lib/events.svelte.ts` is the SSE client. Import `src/lib` through the `#lib/*` alias.

## Invariants

- **The AI never sets status.** `Notes` has no status field. `decide` picks a route, and the internal save route maps it to a status with `STATUS_FOR_ROUTE` (`models.py`). Owner actions (on-it, not-urgent, done) are the only other way status changes.
- **AI failure never loses the safety floor.** Model nodes never raise; a raise in the parallel step would stop `word_check` and `decide` too. A failure goes into state. If the model is unavailable, the worker tries the email again later. On the last try, or for any other failure, notes stay empty and the email goes to "needs a look". A safety-floor word match still alerts.
- **Tenancy.** Every tenant-owned row has `workspace_id` and every query filters on it (`test_workspaces_are_isolated` guards this). Routes get the workspace through `WorkspaceDep` (`api/deps.py`). History-tool inputs carry no workspace or email id; the server binds both, so the model cannot reach another tenant.
- **Triage goes through the API.** Nothing in `pipeline.py` or `tools/` may import `sqlmodel` or touch `services.engine`. The API and worker share `HERALD_INTERNAL_TOKEN` (the Makefile and compose files set a dev one).
- **Events.** Stage with `events.add_event` in the caller's transaction, commit, then publish with `to_bus`. Never publish an uncommitted event. SSE replays from the `event` table on `Last-Event-ID`. The Redis channel is `herald:ws:{id}`.
- **Sync DB in async code.** DB work lives in plain sync functions using `Session(services.engine)`, called with `asyncify(...)` from async routes and the pipeline.
- **Swappable backends.** `EventBus` (`redis`, `memory`), `JobQueue` (`arq`, `inline`), `TriageModel` (provider plug-ins), `MailConnector` (`gmail`). Tests use the in-process set from `apps/server/tests/conftest.py`, with `FakeConnector` and `ScriptedModel` (`tests_support/`).
- **Mail connectors are provider-neutral.** Only code in `connectors/<provider>/` knows a provider. A mailbox's `cursor` and `provider_state` are opaque everywhere else.
- **Migrations.** Alembic, in `herald_server/migrations`; `migrate.py` runs them. The API and worker only check the schema is current and refuse to start otherwise. After a model change, run `make migration m="…"` against a migrated Postgres, read the file (autogenerate misses partial index `WHERE` changes, renames and data moves), then `make migrate-check`. Never call `create_all` outside tests. Keep the naming convention in `models.py`: it matches the constraint names of databases made before migrations.
- **API types.** After changing `api/schemas.py`, run `make gen-api` and commit the regenerated `schema.d.ts`.
- **Dev errors.** `make api`, `make lite` and the Docker dev stack set `HERALD_DEBUG=1`, so a 500 carries its traceback to the browser. Leave it off in production.
- **Auth, when added, must be a cookie.** `EventSource` cannot send an `Authorization` header.

## Web design system

Tokens are in `src/lib/styles/tokens.css`. Components are in `src/lib/ui`, exported from `index.ts`, with a gallery at `/design-system`. Components use the semantic tokens (`--color-*`, `--tone-*`), never the primitives (`--concrete-*`, `--chartreuse-*`).

## Style

- Python: Ruff, line length 100, target 3.13, first-party `herald_core` and `herald_server`.
- Web: tabs and Prettier.
- Docs and comments: short, plain sentences.

**Comment complex logic as you write it.** Where the code is not obvious from reading it (sync cursors and retries, locking or concurrency, auth and signature checks, ordering rules such as `decide`, parsing of outside data, anything that guards an invariant), add a short comment that says why it works this way and what would break if it changed. Do not comment code that says what it does on its own.
