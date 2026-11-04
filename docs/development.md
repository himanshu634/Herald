# Herald: Development

How to set up, run, test and debug Herald on your machine, and how to run it on a server. How to propose a change is in [CONTRIBUTING.md](../CONTRIBUTING.md). How the parts fit together is in [architecture.md](architecture.md).

## What you need

- [uv](https://docs.astral.sh/uv/). It installs Python 3.13 for you.
- [pnpm](https://pnpm.io) 11 and Node 22+
- Docker, for the full stack only. Lite mode needs none.
- An API key for the AI: `OPENROUTER_API_KEY` (the default provider) or `ANTHROPIC_API_KEY`. There is no offline model, so the app needs one to triage mail. The tests do not.

## Set up

```bash
make install
```

```bash
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env`. To use Claude directly, set `HERALD_MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. `HERALD_MODEL_NAME` picks another model; empty means the provider's default. Every setting is listed under "Configuration" in [architecture.md](architecture.md#configuration).

`make help` lists every task.

## Run it

Pick the mode that fits what you are changing.

| Mode | Command | What runs | Use it for |
| --- | --- | --- | --- |
| Lite | `make lite`, then `make web` | API on :8000 with SQLite, an in-memory event bus and the pipeline run inline. No Docker. | Most web and pipeline work |
| Full stack | `make dev` | Postgres and Redis in Docker, then the API, the arq worker and the web app in one terminal | Anything about the worker, the queue, retries, Redis, cron jobs or Postgres |
| Full stack, split | `make infra`, then `make api`, `make worker`, `make web`, each in its own terminal | The same, with one log per terminal | Reading the worker's log on its own |
| All in Docker | `make docker-dev` | Everything in containers, with hot reload (web :5173, API :8000) | Checking the container setup |

Open http://localhost:5173. The web app proxies `/api` to the API on :8000.

- Click **Open the Tripfold demo** for a business with its topics, facts and rules already set up. A business you set up yourself shows only the Connect Gmail screen until it has a mailbox. The demo is the one exception.
- To send the demo an email without Gmail, post it to the API: `POST /api/workspaces/{id}/emails`. The API docs are at http://localhost:8000/docs.
- `make api`, `make lite` and the Docker dev stack set `HERALD_DEBUG=1`, so a 500 shows its traceback in the browser.
- `make dev` leaves Postgres and Redis running when you press Ctrl-C. `make infra-down` stops them.
- The API reloads when you edit `apps/server` or `packages/core`. With `make dev` and `make worker` the worker does not: restart it after a change. `make docker-dev` reloads both.

### Start again with an empty database

- Lite mode: delete `apps/server/herald-dev.db`.
- Postgres: `docker compose -f infra/docker-compose.yml down -v`, then `make infra`.

## Tests

```bash
make test
```

This runs pytest over `packages/core`, `packages/evals` and `apps/server`, then Vitest in `apps/web`. The server tests use the in-memory bus, the inline queue, SQLite and `ScriptedModel` (`tests_support/scripted_model.py`), so they need no Docker and no API key. `ScriptedModel` returns exactly the notes and verdicts each test gives it.

Run one test or one slice from the repo root:

```bash
uv run pytest apps/server/tests/test_api.py::test_workspaces_are_isolated
```

```bash
uv run pytest packages/core/tests -k decide
```

```bash
pnpm -C apps/web exec vitest run src/lib/ui/tones.spec.ts
```

A few tests are marked `live`. They call OpenRouter and skip when `OPENROUTER_API_KEY` is not set. To run only them:

```bash
uv run pytest -m live
```

## Lint and format

```bash
make lint
```

```bash
make format
```

`make lint` runs `ruff check`, `ruff format --check`, ESLint with Prettier, and svelte-check. For the web app alone: `pnpm -C apps/web lint` and `pnpm -C apps/web check`.

## API types

The web app's API types are generated from FastAPI's OpenAPI schema. After you change `apps/server/src/herald_server/api/schemas.py` or a route's signature, run:

```bash
make gen-api
```

Commit the new `apps/web/src/lib/api/schema.d.ts` with the change. The internal routes are not in the schema, so changing them does not change this file.

## Database migrations

The schema is managed with Alembic. `make migrate` brings the database to the latest revision, and `make api`, `make lite` and `make dev` run it for you. The API and worker refuse to start on a database that is behind, so run `make migrate` after you pull.

After you change `apps/server/src/herald_server/models.py`:

1. Start Postgres and migrate it: `make infra`, then `make migrate`. Write migrations against Postgres, because enum changes show up only there.
2. Write the migration: `make migration m="what changed"`.
3. Read the file it writes and fix it. Autogenerate misses renames (it drops and adds, which loses data), data that must move, and changes to a partial index's `WHERE`.
4. `make migrate`, then `make migrate-check`.
5. `make test`. `test_migrations.py` fails when the migrations and the models differ.

If two branches each added a migration, run `uv run alembic merge heads -m "merge"` in `apps/server` and commit the file. More detail is under "Database migrations" in [architecture.md](architecture.md#database-migrations).

## Evals

The evals run labelled test emails through the real triage graph and write a score report. Run them after you change a prompt, the notes, the rules or `decide`:

```bash
make eval
```

```bash
make eval ARGS="--case sue-is-a-name"
```

They need `OPENROUTER_API_KEY` (or `ANTHROPIC_API_KEY` with `ARGS="--model anthropic"`) and cost real model calls. Reports go to `packages/evals/results/`, which git ignores. The datasets, the baseline and how to add a case are in [evals.md](evals.md).

## Tracing

To see what the model was asked and what it said:

```bash
make langfuse
```

This starts Langfuse on http://localhost:3000 (log in with `dev@herald.test`). `.env.example` already has its dev keys. Restart the API and worker, and each triage run shows up as a trace. `make langfuse-down` stops it and keeps its data. Tracing is for development only: traces hold customer emails, and the production image has no Langfuse package. See "Tracing (dev)" in [architecture.md](architecture.md#tracing-dev).

## Logs

The API and worker log one line per email arrival and per pipeline step. Set `HERALD_LOG_LEVEL=DEBUG` in `.env` for more.

## Gmail on your machine

Connecting Gmail needs a Google Cloud project. Do this once:

1. In a Google Cloud project, enable the **Gmail API** and the **Cloud Pub/Sub API**.
2. Set up the OAuth consent screen as External. Under Data access, add the scopes `gmail.readonly` and `gmail.send`, and add yourself as a test user. While the app is in Testing, a connection lasts 7 days.
3. Create a Web OAuth client with the redirect URI `http://localhost:8000/api/oauth/gmail/callback` (`{HERALD_PUBLIC_API_URL}/api/oauth/gmail/callback`). Put its id and secret in `HERALD_GOOGLE_CLIENT_ID` and `HERALD_GOOGLE_CLIENT_SECRET`.
4. Create a Pub/Sub topic, for example `herald-gmail`. Give `gmail-api-push@system.gserviceaccount.com` the **Pub/Sub Publisher** role on it. Set `HERALD_GMAIL_TOPIC=projects/<project>/topics/herald-gmail`.
5. Create a service account for push. Create a **push** subscription to `{HERALD_PUBLIC_API_URL}/api/webhooks/gmail` with authentication on, using that service account and an audience string. Set `HERALD_GMAIL_PUSH_SERVICE_ACCOUNT` and `HERALD_GMAIL_PUSH_AUDIENCE` to match.
6. Set `HERALD_TOKEN_KEY` to a new Fernet key:

   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   It encrypts the stored mailbox credentials. If you lose or change it, every mailbox must reconnect.

Restart the API and the worker. The connect screen now offers Gmail.

Google cannot push to `localhost`. Without a tunnel, new mail arrives on the 15-minute catch-up, or when you ask for a sync with `POST /api/workspaces/{id}/mailboxes/{mailbox_id}/sync`. The catch-up is an arq cron job, so it runs only with the worker (`make dev`), not in lite mode. For live push, expose the API with a tunnel, set `HERALD_PUBLIC_API_URL` to the tunnel URL, and point the OAuth redirect URI and the push subscription at it.

## Run it on your server

Production runs nginx (serving the web app and proxying `/api`), the API, the worker, Postgres and Redis, all in Docker. Copy `.env.example` to `.env` and set:

- `POSTGRES_PASSWORD`
- `ANTHROPIC_API_KEY`. Production uses Claude unless `HERALD_MODEL_PROVIDER` says otherwise.
- `HERALD_WEB_URL`, the public URL of the web app, and `HERALD_PUBLIC_API_URL`, the public URL of its API. Gmail sign-in and push are built from it.
- `HERALD_INTERNAL_TOKEN`, the secret the worker sends to the API. Make one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- The Gmail settings, if you connect Gmail (see [Gmail on your machine](#gmail-on-your-machine))

Then:

```bash
make docker-prod
```

It listens on `HERALD_PORT` (default 8080). Put TLS in front of it. Stop it with `make docker-prod-down`. There is no sign-in yet: anyone who can reach it can read your mail. Keep it behind a VPN or a sign-in proxy. Google's push must still reach `/api/webhooks/gmail`; without it, new mail arrives only on the 15-minute catch-up.

## Where things are

| You want to change | Look in |
| --- | --- |
| What the AI is told | `packages/core/src/herald_core/prompts/`, `prompt.py` |
| How an email is routed | `packages/core/src/herald_core/decide.py` |
| The safety floor's word check | `packages/core/src/herald_core/safety.py` |
| A pipeline step | `packages/core/src/herald_core/nodes/` (one file each); `graph.py` wires them |
| A model provider | `packages/core/src/herald_core/providers/` |
| An API route | `apps/server/src/herald_server/api/routes/` |
| Tables | `apps/server/src/herald_server/models.py`, then a migration |
| The demo business | `apps/server/src/herald_server/seed.py` |
| Gmail | `apps/server/src/herald_server/connectors/gmail/` |
| A page in the web app | `apps/web/src/routes/` |
| A UI component | `apps/web/src/lib/ui/`, shown at http://localhost:5173/design-system |
| Colours, type and spacing | `apps/web/src/lib/styles/tokens.css` |
