# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Herald is multi-tenant email triage for one-person businesses: a LangGraph pipeline writes notes on each customer email, the owner's plain-text rules and a fixed safety floor decide what alerts them. Read `docs/` before changing behaviour — `architecture.md` (flow, pipeline, status, SSE, plug-in points), `decisions.md` (wins over `product-scope.md` where they differ). The demo business, Tripfold, is seed data in `apps/server/src/herald_server/seed.py`.

## Commands

Needs uv, pnpm (11) and Node 22+. `make help` lists all tasks.

```bash
make install        # uv sync + pnpm install
make lite           # API on :8000 with no Docker: SQLite, in-memory bus, inline pipeline, fake model
make web            # SvelteKit on :5173, proxies /api to :8000
make dev            # full stack in one terminal: Postgres + Redis in Docker, then API, worker and web
make migrate        # bring the database to the latest schema (make api / lite / dev run it first)
make migration m="…"  # write a migration from model changes, then read it
make infra && make api && make worker   # full stack: Postgres + Redis, separate arq worker (each in its own terminal)
make test           # pytest (core + evals + server) and vitest
make eval           # triage evals on Claude -> score report in packages/evals/results (see docs/evals.md)
make lint           # ruff check, ruff format --check, prettier + eslint, svelte-check
make format
make gen-api        # regenerate apps/web/src/lib/api/schema.d.ts from FastAPI's OpenAPI
```

Single tests (run from the repo root; pytest config lives in the root `pyproject.toml`):

```bash
uv run pytest apps/server/tests/test_api.py::test_workspaces_are_isolated
uv run pytest packages/core/tests -k decide
pnpm -C apps/web exec vitest run src/lib/ui/tones.spec.ts
```

Web-only: `pnpm -C apps/web check` (svelte-check), `pnpm -C apps/web lint`.

## Architecture

Three packages plus the evals; Python is one uv workspace (root `pyproject.toml`), JS is a pnpm workspace containing only `apps/web`.

- **`packages/core` (`herald_core`)** — business-agnostic and I/O-free (no DB, no Redis). `schema.py` holds the shared Pydantic types (`WorkspaceConfig`, `Email`, `Notes`, `Decision`, `Route`). `graph.py` builds the LangGraph graph once and shares it across tenants; each run carries its workspace config in state (`state.py`). Each node is one file in `nodes/`, and `graph.py` only wires them. `word_check` (regex safety floor, `safety.py`), `write_notes` and `judge_rules` run in parallel, then `decide` (`decide.py`, plain Python). `model.py` has the `TriageModel` protocol with `AnthropicModel` and the offline `FakeModel`. `model_tools.py` has the tools the model may call (`sender_history`, served from the history `gather_context` fetched); thread and corrections are pre-fetched into the prompt.
- **`apps/server` (`herald_server`)** — FastAPI app (`api/main.py:create_app`) and arq worker (`worker/main.py`) share `Services` (`services.py`: engine, bus, compiled graph). `pipeline.process_email` never opens the database: it loads the email, runs `triage` and saves the result through `AgentApi` (`internal/client.py`), which calls the API's token-guarded internal routes (`api/routes/internal.py`, `/internal/v1`, not in OpenAPI). The save route sets status, commits, publishes `email.noted`, and records `alert.sent` when the route is `alert`. Inline mode calls the same routes in memory. Alerts stay in the app. The only mail that leaves it is a reply the owner writes and sends (`replies.py`). Settings are `HERALD_*` env vars or `.env` (`settings.py`). The history tools are one file each in `tools/` and call those routes; their queries live in `internal/history.py`, scoped by the email's own row. The thread query also returns the owner's sent replies (`from_owner`).
- **`packages/evals` (`herald_evals`)** — labelled test emails (TOML in `datasets/`) run through the real graph, scored into a Markdown report and a JSON run record. Labels say what Herald should do; cases start `reviewed = false` until a person agrees. See `docs/evals.md`.
- **`apps/web`** — SvelteKit (Svelte 5 runes forced on) built as a static SPA (`adapter-static`, `ssr = false`); FastAPI owns all server logic. `src/lib/api/client.ts` wraps routes with types from the generated `schema.d.ts`; `src/lib/events.svelte.ts` is the SSE client. Import `src/lib` via the `#lib/*` subpath alias.

Invariants that span files:

- **The AI never sets status.** `Notes` has no status field. Status changes only in `decide` (via `STATUS_FOR_ROUTE` in `models.py`) and in owner actions (on-it / not-urgent / done routes). If the AI fails, notes are empty and the email routes to "needs a look"; a safety-floor word match still alerts.
- **Tenancy:** every tenant-owned row has `workspace_id` and every query filters on it (`test_workspaces_are_isolated` guards this). Routes get the workspace via `WorkspaceDep` in `api/deps.py`.
- **Triage goes through the API:** nothing in `pipeline.py` or `tools/` may import `sqlmodel` or touch `services.engine`. The worker needs `HERALD_INTERNAL_TOKEN` (the Makefile and compose files set a dev one).
- **Events:** stage with `events.add_event` in the caller's transaction, commit, then publish with `to_bus` — never publish an uncommitted event. The `event` table is what SSE replays from on `Last-Event-ID`; Redis channel is `herald:ws:{id}`.
- **Sync DB in async code:** DB work lives in plain sync functions using `Session(services.engine)` and is called with `asyncify(...)` from async routes and the pipeline.
- **Swappable backends:** `EventBus` (`redis`/`memory`), `JobQueue` (`arq`/`inline`), `TriageModel` (`anthropic`/`fake`), `MailConnector` (`gmail`; `FakeConnector` in tests). Tests use the in-process set via `apps/server/tests/conftest.py`, so they need no Docker or API key.
- **Mail connectors are provider-neutral:** only code in `connectors/<provider>/` knows a provider. A mailbox's `cursor` and `provider_state` are opaque everywhere else.
- **Migrations:** Alembic, in `herald_server/migrations` (`migrate.py` runs them). `make migrate` brings the database to the latest revision; the API and worker only check it is there and refuse to start otherwise. After a model change, run `make migration m="…"` against a migrated Postgres, read the file (autogenerate misses partial index `WHERE` changes, renames and data moves), then `make migrate-check`. Never call `create_all` outside tests. Keep the naming convention in `models.py`: it matches the constraint names of databases made before migrations. See "Database migrations" in `docs/architecture.md`.
- **Dev errors:** `make api`, `make lite` and the Docker dev stack set `HERALD_DEBUG=1`, so a 500 carries its traceback to the browser. Leave it off in production.
- **Auth, when added, must be a cookie** — `EventSource` cannot send an `Authorization` header.
- After changing API schemas (`api/schemas.py`), run `make gen-api` and commit the regenerated `schema.d.ts`.

## Web design system

Tokens are in `src/lib/styles/tokens.css`, components in `src/lib/ui` (exported from `index.ts`), with a gallery at `/design-system`. Components use the semantic tokens (`--color-*`, `--tone-*`), never the primitives (`--concrete-*`, `--chartreuse-*`).

## Style

Ruff, line length 100, target Python 3.13, first-party imports `herald_core` / `herald_server`. Web uses tabs and Prettier. Docs and comments are written in short, plain sentences.

**Comment complex logic as you write it.** Where the code is not obvious from reading it (sync cursors and retries, locking or concurrency, auth and signature checks, ordering rules such as `decide`, parsing of outside data, anything that guards an invariant), add a short comment that says why it works this way and what would break if it changed. Do not comment code that says what it does on its own.
