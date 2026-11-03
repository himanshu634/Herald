# Herald

Herald is email triage for a business run by one person. An AI pipeline built on LangGraph reads every customer email. The owner's own rules decide what alerts them, and a safety floor nobody can switch off catches threats. It is multi-tenant: each business is a workspace set up with plain words, not code.

**Stack:** SvelteKit (Svelte 5) · FastAPI with SSE · LangGraph · Postgres · Redis (arq + pub/sub). See [docs/](docs/README.md).

## Layout

```
apps/web        SvelteKit single-page app
apps/server     FastAPI API + arq pipeline worker (herald_server)
packages/core   LangGraph pipeline, decide step, safety floor (herald_core)
docs            scope, decisions, architecture
```

## Run it

Needs uv, pnpm and Node 22+. Docker is only needed for the full stack.

```bash
make install
```

Quickest run, with no Docker (SQLite, in-memory events, pipeline in the API process, offline fake model):

```bash
make lite
```

```bash
make web
```

Open http://localhost:5173 and click **New demo workspace**.

Full stack, with Postgres, Redis and a separate worker, each in its own terminal:

```bash
make infra
```

```bash
make api
```

```bash
make worker
```

```bash
make web
```

Upgrading from an older checkout: there are no migrations yet, so startup does not add new columns to existing tables. Delete `apps/server/herald-dev.db` (lite mode) or run `docker compose down -v` (Postgres) and start again. See "Upgrading an existing dev database" in `docs/architecture.md`.

To use Claude instead of the fake model, copy `.env.example` to `.env` and set `HERALD_MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. To get phone alerts, set `HERALD_NTFY_TOPIC`.

## Checks

```bash
make test
```

```bash
make lint
```

Run `make gen-api` after changing API schemas to regenerate the web app's types.
