# Herald

**An open-source mailbox manager for a business run by one person.**

You answer every customer email yourself. Most can wait for tomorrow. A few can't: the customer at the airport with a broken bag, the order that must arrive before a trip, the email that mentions a lawyer. Herald reads every email as it arrives, tells you which few matter, and leaves the rest sorted for when you sit down to work.

It is free, MIT-licensed and runs on your own machine or server.

## What it does for you

- **Reads every email and writes notes on it.** Topic, urgency, how angry the customer is, risk flags and a one-line summary. Each note quotes the lines from the email that back it up, so you can check the AI's reasoning at a glance.
- **Alerts you only when it should.** An email is alerted when it is urgent, the customer is furious, or one of your own rules says so. It goes to the top of your inbox with the summary, the quote and the rule that fired, so you can decide at a glance.
- **Sorts the rest.** Your inbox opens with the most urgent emails first, then by anger, then newest first. One click marks an email "On it", "Not urgent" or "Done".
- **Says when it isn't sure.** An email the AI can't read, or isn't confident about, goes to "Needs a look". Nothing slips quietly into the normal pile.
- **Updates live.** New emails and their notes appear in the open inbox without a refresh.

## Your business, in your words

Herald knows nothing about your business until you tell it. You give it four things, all in plain words:

| You give it | Example: Tripfold, an online luggage brand |
| --- | --- |
| A few lines about the business | "We sell luggage, backpacks and travel accessories online across India. A bad day is a customer at the airport with a broken bag." |
| The topics customers write about | Orders and delivery, Returns and exchanges, Damaged or defective, Corporate gifting, and a few more |
| Contacts who always matter | `corporate-gifts@bigcorp.example` |
| Rules: "when …, then …" | When the customer is travelling in the next 48 hours and the order has not arrived, **alert me** |

A rule can alert you, raise or lower an email's urgency, or close it quietly (courier newsletters, for example). The AI answers each rule's "when" with yes or no and quotes the line that decided it. A bakery, a freelance developer and a small software company each write their own rules. Herald's code stays the same.

## What it will never do

- **It never replies to your customers.** You send every reply.
- **It never makes money decisions.** Refunds, credits and cancellations stay with you.
- **The AI never decides what happens to an email.** It writes notes. Your rules and your clicks move an email between "needs you now", "in progress" and "done", and you can always see which rule fired.
- **No rule can silence a real threat.** A safety floor sits under every rule and can't be switched off. It catches threats of violence or self-harm, a hacked account or data leak, and legal threats. A simple word check runs beside the AI, so an email written to trick the AI still alerts you.

## Where it is today

Herald is early. Today it has the inbox, AI notes, rules, the safety floor, in-app alerts and a demo business you can open in one click. Emails come in through the API or the "Send test email" box.

Coming next:

- Connect a real Gmail or Outlook inbox
- Write and edit rules in the app, and test a rule on past emails before it goes live
- Quiet hours, one reminder for an unopened alert, and a morning summary
- Corrections that teach the AI your business

**About your data:** Herald stores your email on your own server. With Claude turned on, the text of each email is sent to Anthropic to write its notes. The built-in offline model sends nothing anywhere, which is handy for trying Herald out.

## Try it

Needs [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io) and Node 22+.

```bash
make install
```

```bash
make lite
```

In a second terminal:

```bash
make web
```

Open http://localhost:5173 and click **New demo workspace**. This runs with no Docker and an offline model, so it needs no API key.

To use Claude, copy `.env.example` to `.env` and set `HERALD_MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

## For developers

Herald is multi-tenant: each business is a workspace, and its profile, topics, contacts and rules are data. A LangGraph pipeline writes the notes; a plain Python step applies the safety floor and the rules.

**Stack:** SvelteKit (Svelte 5) · FastAPI with SSE · LangGraph · Postgres · Redis (arq + pub/sub). See [docs/](docs/README.md) for the scope, decisions and architecture.

```
apps/web        SvelteKit single-page app
apps/server     FastAPI API + arq pipeline worker (herald_server)
packages/core   LangGraph pipeline, decide step, safety floor (herald_core)
docs            scope, decisions, architecture
```

Full stack, with Postgres and Redis in Docker and the API, worker and web app on your machine, in one terminal (Ctrl-C stops them; `make infra-down` stops the containers):

```bash
make dev
```

Or run each piece in its own terminal:

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

Or run the whole stack in Docker, with hot reload for the API, worker and web app (web on :5173, API on :8000):

```bash
make docker-dev
```

Production runs nginx (serving the web app and proxying `/api`), the API, the worker, Postgres and Redis. Copy `.env.example` to `.env`, set `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY`, `HERALD_WEB_URL` and `HERALD_INTERNAL_TOKEN` (the secret the worker sends to the API; `python -c "import secrets; print(secrets.token_urlsafe(32))"`), then:

```bash
make docker-prod
```

It listens on `HERALD_PORT` (default 8080); put TLS in front of it. Stop it with `make docker-prod-down`.

Checks:

```bash
make test
```

```bash
make lint
```

Run `make gen-api` after changing API schemas to regenerate the web app's types.

## License

[MIT](LICENSE)
