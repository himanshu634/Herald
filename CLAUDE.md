# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Herald is multi-tenant email triage for one-person businesses: a LangGraph pipeline writes notes on each customer email, the owner's plain-text rules and a fixed safety floor decide what alerts them. Read `docs/` before changing behaviour — `architecture.md` (flow, pipeline, status, SSE, plug-in points), `decisions.md` (wins over `product-scope.md` where they differ). The demo business, Tripfold, is seed data in `apps/server/src/herald_server/seed.py`.

## Commands

Needs uv, pnpm (11) and Node 22+. `make help` lists all tasks.

```bash
make install        # uv sync + pnpm install
make lite           # API on :8000 with no Docker: SQLite, in-memory bus, inline pipeline, fake model
make web            # SvelteKit on :5173, proxies /api to :8000
make infra && make api && make worker   # full stack: Postgres + Redis, separate arq worker (each in its own terminal)
make test           # pytest (core + server) and vitest
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

Three packages; Python is one uv workspace (root `pyproject.toml`), JS is a pnpm workspace containing only `apps/web`.

- **`packages/core` (`herald_core`)** — business-agnostic and I/O-free (no DB, no Redis). `schema.py` holds the shared Pydantic types (`WorkspaceConfig`, `Email`, `Notes`, `Decision`, `Route`). `graph.py` builds the LangGraph graph once and shares it across tenants; each run carries its workspace config in state. `word_check` (regex safety floor, `safety.py`) and `write_notes` run in parallel, then `judge_rules`, then `decide` (`decide.py`, plain Python). `model.py` has the `TriageModel` protocol with `AnthropicModel` and the offline `FakeModel`.
- **`apps/server` (`herald_server`)** — FastAPI app (`api/main.py:create_app`) and arq worker (`worker/main.py`) share `Services` (`services.py`: engine, bus, compiled graph). `pipeline.process_email` loads an email, runs `triage`, saves notes/decision/status, publishes events, and records an `alert.sent` event when the route is `alert`. Alerts stay in the app: nothing is sent outside it. Settings are `HERALD_*` env vars or `.env` (`settings.py`).
- **`apps/web`** — SvelteKit (Svelte 5 runes forced on) built as a static SPA (`adapter-static`, `ssr = false`); FastAPI owns all server logic. `src/lib/api/client.ts` wraps routes with types from the generated `schema.d.ts`; `src/lib/events.svelte.ts` is the SSE client. Import `src/lib` via the `#lib/*` subpath alias.

Invariants that span files:

- **The AI never sets status.** `Notes` has no status field. Status changes only in `decide` (via `STATUS_FOR_ROUTE` in `models.py`) and in owner actions (on-it / not-urgent / done routes). If the AI fails, notes are empty and the email routes to "needs a look"; a safety-floor word match still alerts.
- **Tenancy:** every tenant-owned row has `workspace_id` and every query filters on it (`test_workspaces_are_isolated` guards this). Routes get the workspace via `WorkspaceDep` in `api/deps.py`.
- **Events:** stage with `events.add_event` in the caller's transaction, commit, then publish with `to_bus` — never publish an uncommitted event. The `event` table is what SSE replays from on `Last-Event-ID`; Redis channel is `herald:ws:{id}`.
- **Sync DB in async code:** DB work lives in plain sync functions using `Session(services.engine)` and is called with `asyncify(...)` from async routes and the pipeline.
- **Swappable backends:** `EventBus` (`redis`/`memory`), `JobQueue` (`arq`/`inline`), `TriageModel` (`anthropic`/`fake`), `MailConnector` (`gmail`; `FakeConnector` in tests). Tests use the in-process set via `apps/server/tests/conftest.py`, so they need no Docker or API key.
- **Mail connectors are provider-neutral:** only code in `connectors/<provider>/` knows a provider. A mailbox's `cursor` and `provider_state` are opaque everywhere else.
- **No migrations yet:** tables are created with `SQLModel.metadata.create_all` on startup. Delete `apps/server/herald-dev.db` after a model change in lite mode.
- **Auth, when added, must be a cookie** — `EventSource` cannot send an `Authorization` header.
- After changing API schemas (`api/schemas.py`), run `make gen-api` and commit the regenerated `schema.d.ts`.

## Web design system

Tokens are in `src/lib/styles/tokens.css`, components in `src/lib/ui` (exported from `index.ts`), with a gallery at `/design-system`. Components use the semantic tokens (`--color-*`, `--tone-*`), never the primitives (`--concrete-*`, `--chartreuse-*`).

## Style

Ruff, line length 100, target Python 3.13, first-party imports `herald_core` / `herald_server`. Web uses tabs and Prettier. Docs and comments are written in short, plain sentences.

**Comment complex logic as you write it.** Where the code is not obvious from reading it (sync cursors and retries, locking or concurrency, auth and signature checks, ordering rules such as `decide`, parsing of outside data, anything that guards an invariant), add a short comment that says why it works this way and what would break if it changed. Do not comment code that says what it does on its own.
