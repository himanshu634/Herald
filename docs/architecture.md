# Herald: Architecture

Herald is one monorepo with a SvelteKit front end, a FastAPI back end with a separate pipeline worker, and a core package that holds the LangGraph pipeline. No code in it knows about any one business.

## Repo layout

| Path | What it is | Tooling |
| --- | --- | --- |
| `packages/core` | `herald_core`: shared types, safety-floor word check, decide step, LangGraph graph, AI model adapters, plug-in interfaces. No database and no Redis. | uv, pytest |
| `apps/server` | `herald_server`: the FastAPI API (`herald_server.api.main:app`) and the arq worker (`herald_server.worker.main.WorkerSettings`). They share the tables, event bus and pipeline code. For triage the worker reaches the database only through the API's internal routes. | uv, FastAPI CLI, arq |
| `packages/evals` | `herald_evals`: test emails with known answers, run through the real graph, and the score report. See [evals.md](evals.md). | uv, pytest |
| `apps/web` | SvelteKit (Svelte 5, runes) built as a static single-page app. API types are generated from FastAPI's OpenAPI schema. | pnpm, Vite, svelte-check, Vitest |
| `docs` | Scope, decisions and this file | — |

The Python packages form one uv workspace (root `pyproject.toml`). The JS app is in a pnpm workspace (root `pnpm-workspace.yaml`). The `Makefile` runs both.

## How an email flows

```mermaid
sequenceDiagram
    participant Web as Web app
    participant API as FastAPI
    participant Q as Redis (arq queue)
    participant W as Worker
    participant DB as Postgres
    participant Bus as Redis pub/sub

    Web->>API: POST /api/workspaces/{id}/emails
    API->>DB: save email + event email.received
    API->>Bus: publish email.received
    API->>Q: enqueue process_email
    Q->>W: process_email(email_id)
    W->>API: GET /internal/v1/emails/{id}/triage-input
    W->>W: LangGraph: word check ∥ (history → notes) → rules → decide
    W->>API: GET .../history/* (the agent's tools)
    W->>API: POST .../triage-result
    API->>DB: save notes, decision, status, context + email.noted (+ alert.sent) in one commit
    API->>Bus: publish email.noted, then alert.sent
    Bus-->>API: events for workspace {id}
    API-->>Web: SSE /api/workspaces/{id}/events
```

## Internal routes

The worker's pipeline never opens the database. It loads the email, runs the agent's tools and saves the result through `AgentApi` (`herald_server/internal/client.py`), which calls the API's internal routes (`api/routes/internal.py`). The API is the one place that queries, commits and publishes.

| Route | Used by | Does |
| --- | --- | --- |
| `GET /internal/v1/emails/{id}/triage-input` | The pipeline | The email, the business name and the workspace config |
| `GET .../history/sender` | `sender_history` tool | Sender counts for 7 and 30 days, first seen, top topics, latest few |
| `GET .../history/thread` | `thread` tool | Earlier messages in the thread with the owner's sent replies, oldest first |
| `GET .../history/corrections` | `recent_corrections` tool | The owner's recent overrides in this business |
| `POST .../triage-result` | The pipeline | Saves notes, decision and context, sets status with `STATUS_FOR_ROUTE`, records `email.noted` and, for an alert, `alert.sent`. One commit, then publish. |

- Every route is keyed by the email being judged. The API takes the workspace and the "received before" cut-off from that row, so no caller can name another tenant. Tool inputs forbid extra fields, so a `workspace_id` query param is a 422.
- Every call needs the header `X-Herald-Internal-Token` with `HERALD_INTERNAL_TOKEN`, compared in constant time. With the arq queue the API and the worker refuse to start without it. The inline queue makes a random token per process, because its only caller is its own in-memory client.
- The routes sit outside `/api`, so nginx and the Vite proxy never forward them, and they are left out of the OpenAPI schema (`schema.d.ts` does not change).
- In lite mode and in tests the same routes are called in memory (`httpx.ASGITransport`), so every path runs the same code as the worker. The owner's trial read (`POST /api/workspaces/{id}/emails/{email_id}/try`) runs in the API process and uses that in-memory client too. It loads and runs the tools but never calls the save route.
- Failures: a read that fails on the network or gets a 5xx raises `ApiUnavailable`. So does a save whose request never reached the API (connect error or connect timeout). The worker retries those (`Retry`, 5 s more each try, sharing the job's 6 tries with AI retries), so an API that is still starting does not leave mail `new`. A save that may have reached the API is not retried, because a retry could publish its events twice. A tool's failure still only costs that tool's context (see History).
- The model's tools are read-only. Saving the result is the pipeline's call, not a tool, so the AI still never sets status.

## The pipeline

```mermaid
flowchart LR
    S((start)) --> WC[word_check<br/>regex safety terms]
    S --> G[gather_context<br/>history tools, no AI]
    G --> N[write_notes<br/>AI: topic, urgency, anger, flags, quotes]
    G --> R[judge_rules<br/>AI: the owner rules the email meets]
    WC --> D[decide<br/>plain Python]
    N --> D
    R --> D
    D --> E((end))
```

- Each node is one file in `herald_core/nodes/`. `graph.py` only wires them, and `state.py` holds the state they share.
- The graph is compiled once and shared by all tenants. Each run carries its workspace's config in the state.
- `word_check`, `write_notes` and `judge_rules` run in parallel. They write different state keys, except `asked` and `ai_failures`, which both model nodes write and a reducer joins.
- `write_notes` and `judge_rules` wait on `gather_context`. `word_check` does not.
- The two model calls run side by side because the rules prompt never reads the notes. Run one after the other, they took about 9 s; side by side, the slower one sets the time. `judge_rules` lists only the rules the email meets, with the line that decided each. A missing rule is a "no". Writing a "no" for every rule was most of that call's output, and so most of its time.
- If the AI fails (outage, refusal, bad output), the notes are empty and the email goes to "Needs a look". A safety-floor match from the word check still alerts. Rule verdicts that arrive without notes are not used, so a matched close rule cannot hide an email the AI could not read.
- If the rules call fails, `verdicts` is `None`, not `[]`, so a failure never reads as "no rule matched". The alerts still apply; anything that would go to the inbox or close goes to "Needs a look" ("Your rules could not be checked").

### When the AI fails

A model node never raises: a raise inside the parallel step would also stop `word_check` and `decide`, and the safety floor with them. It records an `AiFailure` in state (`ai_failures`, joined by a reducer) and `decide` runs as usual. The failure is saved in the email's context, and decide's reason says "The AI was unavailable" apart from "The AI could not read this email".

| Kind | Errors | What happens |
| --- | --- | --- |
| `unavailable` | 429, 529, other 5xx, 409, network, request timeout, the node deadline | The worker tries the email again later |
| `setup` | 401, 403, 404 (model name), 402 (billing) | No retry. "Needs a look", logged at ERROR: every email fails this way until fixed |
| `unreadable` | 400, 413, 422, refusal, invalid output, anything unknown | No retry. "Needs a look" |

- In the call: the client times out a request after 30 s and retries it once (`REQUEST_TIMEOUT`, `REQUEST_RETRIES` in `model.py`). Each model node has a 90 s deadline (`MODEL_DEADLINE`) that covers its tool round and that retry, and cuts short a long `retry-after` the SDK would sleep through. The SDK's defaults (600 s, 2 retries) could run past arq's 300 s job timeout, and arq never retries a job it timed out, so the email stayed `new` for good.
- Across jobs: when a call was `unavailable` and the job has tries left, `process_email` raises `ModelUnavailable` before it saves. The worker maps it to `Retry`, waiting 30 s and doubling to 8 min with ±20% jitter, and at least the API's `retry-after` (also capped at 8 min). With 6 tries an email waits at most about 15 minutes before it is saved.
- Never deferred: an alert, including a safety-floor match, is saved on the try that found it. The last try (`job_try >= PROCESS_EMAIL_TRIES`) always saves, so the email lands in "Needs a look" with its reason. The inline queue has no retries, so its one try is final.
- The owner's trial read returns 503 `ai_unavailable` instead of a result, and the dialog asks them to try again. The setup draft keeps its fixed fallback, and gets 120 s per request (`SETUP_TIMEOUT`): it runs in the owner's request, not a job, and writes a whole setup.
- `decide` order, first match wins: safety floor (one exception, below) → not for the business → owner rules (alert beats close; a set-urgency rule never lowers an urgent email) → urgent or anger 5 → anger 4 from an important contact, or about to cancel → rules not checked → unsure → spam → inbox.
- "Not for the business" means the AI filed the email under "Spam or not for me", is sure, and the sender is not an important contact. That mail closes before the rules and defaults, so a promotion that reads as urgent or names a rule's words stays quiet. `judge_rules` still runs on it, because it cannot see the notes; `decide` closes the email before it reads the verdicts. Unsure spam and spam from an important contact take the normal path. The safety floor still comes first.
- The one exception to the floor: mail read from the provider's Spam folder (`in_spam`) that the AI also files as not for the business goes to "Needs a look" with its floor flags, instead of alerting. Phishing is full of floor words. A Spam email the AI reads as real mail, or is unsure about, still alerts.

## History

Before the model reads an email, `gather_context` runs three tools in code: `sender_history` (recent emails from the same sender), `thread` (earlier messages in the thread) and `recent_corrections` (emails the owner moved to the inbox from an alert or from closed). This is a pre-fetch, not a model loop. The tools read Herald's own data through the API's internal routes (see Internal routes), never the mail provider.

The thread and the corrections go into the prompt. The sender history does not: the model gets a `sender_history` tool and calls it only when it needs the sender's earlier emails (see Model tools).

- Each tool is one file in `herald_server/tools/` and calls one internal route. They share the email they are bound to in `tools/bound.py`. The queries behind them are in `herald_server/internal/history.py`.
- The email is bound when the toolbox is built, and the API derives the workspace from it. No tool input has a workspace or email id.
- A tool sees only emails received before the current one.
- A tool that fails or takes over 2 s gives nothing, and its name goes into `email.context.failed`. Triage goes on.
- `word_check` never waits on the tools. A slow tool can delay the alert by at most the tool timeout (2 s).
- History goes into the user message inside a fenced `<history>` block. Its text is untrusted, so Herald strips `<history>`, `<message>`, `<email>` and `<business>` tags from it.
- `email.context` saves what triage looked up: repeat counts, the ids it fetched, the model tools the AI called (`asked`, as `node:tool`), failed tools and timings. The sender's ids reached the model only when `asked` has a `sender_history` call.
- `decide` also reads the sender history: the third email about the same thing this week alerts, after "about to cancel" and before "unsure". It counts this email plus earlier ones from the sender on the same topic in the 7 days before it (`SenderHistory.as_of` places the window) that are not done or closed.

## Model tools

The model may call a tool while it writes notes or judges rules. `herald_core/model_tools.py` holds them; `AnthropicModel` runs the loop. There is one so far, `sender_history`.

- It answers from the sender history `gather_context` already fetched (`SenderLookup`). `decide` needs that history for the repeat count whatever the model does, so the fetch stays in code. The model's lookup costs no second request, and the model and `decide` see the same data.
- It takes no input. The sender is always this email's own, so text in the email cannot steer the model into another customer's mail. It is `strict`, with a fixed description.
- Its answer is the sender section, cleaned and fenced in `<history>` like the history block. A new sender gets "No earlier emails from this sender." A failed fetch goes back as an error result, so the model answers without it.
- `write_notes` and `judge_rules` both offer it, with the same tool list, so the tools never change a workspace's prompt prefix.
- The model gets one round of tool calls (`MAX_TOOL_ROUNDS`). The next request sends `tool_choice: none`, so the structured answer comes back. Every call in a round gets its result, in one user message, and the assistant turn goes back unchanged, thinking blocks included.
- A tool round is one more model call before `decide`, so it delays every route, the safety floor's alerts included. `FakeModel` never calls a tool.

## The prompt

Claude gets one system prompt for each business and one user message for each email. `herald_core/prompt.py` builds both. `write_notes` and `judge_rules` send the same system prompt. Each call's output schema decides what Claude answers. The schema is part of the cached prefix, so each call keeps its own cache entry for the workspace.

| Layer | Changes when | Where it goes |
| --- | --- | --- |
| Herald: role, scales, flag definitions, fences | A Herald release | System prompt, first, from `triage.md` |
| Brand: name, profile, topics, facts, guidance, rules | The owner edits setup | System prompt, in `<business>` |
| History: thread, past corrections | Every email | User message, in `<history>`, before `<email>` |
| Sender history | When the model calls `sender_history` | A tool result, in `<history>` |
| Email: sender, important marker, subject, body | Every email | User message, in `<email>` |

Building rules:

- The order is fixed: Name, Profile, Topics, Facts, Guidance, Rules. The order is part of the cache key, so it must not depend on the data.
- An empty section is left out, heading and all. Claude never sees an empty list.
- A topic is `- Name: meaning`. A topic without a meaning is a bare label.
- List items stay on one line. Inner whitespace collapses, so an owner's line cannot start a fake section such as `Rules:`.
- Rules are written as `- id=<id>: <when>`. The rule's name and action are not shown. Claude judges the condition only and does not know which rules alert.
- The "(important contact)" marker on the email comes from code, with `WorkspaceConfig.is_important`. The contact list never goes into the prompt.
- The brand name comes from `Workspace.name`. The pipeline passes it with the config.
- Facts say what is true. Guidance says how to judge. Setup drafts facts only from the owner's description.
- The setup does not cover every case. For an email nothing covers, Claude judges it as the owner would from the facts, guidance and rules, and that goes into the notes (topic, urgency, summary). A rule verdict stays on what the rule's condition means: an email that is only like a rule's case is a no. When Claude cannot tell how the owner would want it, it sets `sure` to false and the email goes to "needs a look". It also writes `question` (the one thing the owner could answer to settle it) and, when one plain fact would settle it, `fact_draft`. A sure note never carries either. The owner answers in the inbox by saving a fact, which re-reads the email (see Status).

To change the general instructions, edit `packages/core/src/herald_core/prompts/triage.md`. It has no placeholders. It is read once at import, so a missing file stops the API and worker from starting. Tests check that it names every urgency, every risk flag and the spam topic.

## Status

The AI writes notes and never sets status. Status changes in two places only: the decide step (`new` → `alerted`, `needs_a_look`, `inbox` or `closed`) and the owner's actions:

| Action | From | To | Side effect |
| --- | --- | --- | --- |
| On it | any | `in_progress` | — |
| Not urgent | `alerted` only | `inbox` | A correction is saved |
| Move to Inbox | `closed` only | `inbox` | A correction is saved |
| Done | any | `done` | — |
| Send and mark done | any but `done` | `done` | Only when the reply is `sent` |
| Re-read | `alerted`, `needs_a_look`, `inbox` or `closed` | whatever decide says | The email goes through triage again with the current setup |

Both the action routes and "Send and mark done" change status through `status.stage_move`.

Re-read (`POST .../emails/{id}/reread`, 202) is how an answered question settles: the owner saves a fact or rule change, then asks Herald to read the email again. Before saving, the question dialog can try the change: `POST .../emails/{id}/try` (200) runs triage in the request with the unsaved config the owner sends and returns the status, notes and decision Herald would give. It writes nothing and publishes no event, so the email, its status and the saved config stay as they were. Each try is one more AI call. It is refused (409) once the owner has taken the email (in progress or done) or moved it by hand (a route correction exists), so decide never moves an email the owner has already placed.

## Live events (SSE)

- `GET /api/workspaces/{id}/events` streams `email.received`, `email.noted`, `email.status`, `mailbox.status`, `reply.status` and `alert.sent`.
- Each event is stored in the `event` table first, then published to Redis channel `herald:ws:{id}`. A tab only hears its own workspace.
- The browser's `EventSource` reconnects on its own and sends `Last-Event-ID`. The server replays missed events from the database.
- FastAPI sends a keep-alive comment every 15 s.
- SSE runs one way only. Owner actions are plain POSTs.
- Auth is not built yet. When it lands it must be a cookie, because `EventSource` cannot send an `Authorization` header.

## Multi-tenancy

- Every tenant-owned row has `workspace_id`, and every query filters on it. A test checks that one workspace cannot read another's emails.
- Each business is a `WorkspaceConfig`: profile, topics (each with a short meaning), facts, important contacts, owner guidance and rules. Tripfold is seed data in `herald_server/seed.py`.
- A business is added in one of two ways. One is the setup flow: `POST /api/workspaces/setup` takes a name and description, and the AI drafts topics with meanings, facts, guidance and rules (`herald_server/setup.py`). The owner edits the draft and saves it with `PUT /api/workspaces/{id}/config`. The other is a full config posted to `POST /api/workspaces`.
- A workspace stays a draft (`setup_done = false`) until its setup is saved. A draft workspace refuses email with `409`, because its config is the AI's unchecked guess.
- Owner guidance goes into the `<business>` block of the system prompt, after the facts (see "The prompt"). It shapes topic, urgency and anger only. The prompt says it cannot silence the safety floor, and the word check runs regardless. Routing stays with rules.
- Planned: per-workspace caps on AI calls and emails per day.

## Replies

The owner writes a reply in the email's panel and sends it through the email's mailbox (`herald_server/replies.py`). Only `POST /api/workspaces/{id}/emails/{email_id}/replies` sends, after the owner presses Send; the AI never sends. `GET` on the same path lists the email's replies, oldest first.

A send has three steps, so no database session is open while the provider is called:

1. **Begin.** In one transaction: look up the draft's `client_key`, check the mailbox, then commit a `sending` row. A key already used for this email returns its row and sends nothing, so a double click or a second tab sends once. A key used for another email, or a second draft while one is `sending`, answers 409 `already_sending` (the partial unique index `uq_reply_one_sending` allows one `sending` row per email). An email with no mailbox, a mailbox that is not `active`, or one without send permission answers 409 `no_mailbox`, `mailbox_inactive` or `send_not_allowed`. An email with no usable recipient (a `From` the provider could not parse), or one whose reply would go to the mailbox's own address (a form sent from the shop with no usable `Reply-To`), answers 409 `no_recipient`. Every 409 saves nothing.
2. **Send.** One call to `connector.send_reply`, under a 60 s timeout, and never retried.
3. **Finish.** In one transaction: save the outcome, stage `reply.status` (`email_id`, `reply_id`, `status`), and for "Send and mark done" move the email to `done` if the reply was sent. Commit, then publish.

The answer is 200 whatever the outcome; the reply's `status` says it:

| Status | Meaning | `error` |
| --- | --- | --- |
| `sent` | The provider took it | — |
| `not_sent` | The provider refused; nothing went out | `rate_limited`, `auth` (the grant was revoked or the stored credentials no longer open; the mailbox moves to `needs_reauth`), `send_not_allowed` (`can_send` turns off until a reconnect), `rejected` |
| `unknown` | A timeout, a 5xx or any other error. The customer may have it, so the owner checks the mailbox's Sent folder | `unknown` |

A `sending` row older than 2 minutes belongs to a process that died mid-send. The next reply to that email, or a resend of the same draft, turns it `unknown` (and stages `reply.status`), so it never blocks the email. Until then the API reports it as `unknown` (error `unknown`) wherever it returns the reply, without writing, so the panel never says "Sending…" forever. Two minutes is longer than the slowest send: two requests (a token refresh and the send) under the 60 s timeout.

The reply goes to the email's `Reply-To` when that is one plain address (a contact form sends from a no-reply address), and to `From` otherwise. `EmailOut.reply_address` carries that address (empty when there is none), so the web app's To line uses the server's rule instead of a copy of it. It carries `In-Reply-To` and `References`, and the provider's thread id, so it lands in the customer's thread.

## Mail connectors

A connector reads one kind of mailbox (Gmail first; Outlook and IMAP later). One `Mailbox` table, one sync job and one set of routes serve every provider. Only code in `herald_server/connectors/<provider>/` knows a provider. Everywhere else the cursor and `provider_state` are opaque, and code finds the connector with `services.connectors[mailbox.provider]`.

### How synced mail flows

```mermaid
sequenceDiagram
    participant Owner as Owner's browser
    participant API as FastAPI
    participant G as Gmail + Pub/Sub
    participant Q as Redis (arq queue)
    participant W as Worker
    participant DB as Postgres

    Owner->>API: POST /api/workspaces/{id}/mailboxes/gmail/connect
    API-->>Owner: authorization_url (carries signed state)
    Owner->>G: consent
    G-->>Owner: redirect to /api/oauth/gmail/callback
    Owner->>API: code + state
    API->>DB: save mailbox (credentials encrypted) + event mailbox.status
    API->>G: watch the inbox (push)
    API->>Q: enqueue sync_mailbox
    API-->>Owner: 303 to web app (mailbox_connected=id)

    G->>API: POST /api/webhooks/gmail (signed push)
    API->>Q: enqueue sync_mailbox for the active mailbox at that address
    Q->>W: sync_mailbox(mailbox_id)
    W->>G: fetch changes since the cursor
    W->>DB: save new emails + new cursor in one transaction, events email.received
    W->>Q: enqueue process_email for each new email
    Note over W: process_email runs the pipeline shown above
```

- The first sync (no cursor) reads the last 2 days of inbox mail (and Spam, when the mailbox reads it), at most 50 messages. The cursor is the profile `historyId`, read before the list, so mail that lands during the sync is read by the next one. The same path runs when Gmail no longer has the cursor's history (about a week).
- Later syncs read the history since the cursor. The new cursor is the `historyId` of the first page, so a re-read is possible but a loss is not. Stored mail is deduped on `(mailbox_id, provider_message_id)`.
- One fetch downloads at most 100 messages. A long gap (a reconnect or a resume keeps the cursor) is read in batches: the fetch stops before the history record that would pass the cap, its cursor is the last record it took, and it reports `has_more`. Each batch is stored with its cursor, and the caller fetches again (see Sync job). A single record with more than 100 messages is taken whole. Records at or before the start cursor are skipped, so the cursor always moves (Gmail documents only records after it, but a fetch that returned its own start cursor would loop on the mailbox forever).
- A mail that cannot be parsed is skipped, so one bad email cannot block the mailbox. A message that Gmail refuses with 400 or 410 is skipped and logged the same way. Any other refusal of a message (another 403, a 408 or a 5xx) fails the fetch, so the cursor does not move and the next sync (a push or the 15-minute catch-up) reads it again. A 403 for a daily or project quota is a rate limit.
- Only inbox mail is read, plus the Spam folder when the owner chose it (`read_spam`). Sent mail and drafts are skipped. The history query has no label filter (Gmail takes one, Herald may read two) and asks for `labelAdded` as well as `messageAdded`, so mail marked "Not spam" or moved back to the inbox is read too. The watch covers the same labels. Mail read from Spam is stored with `in_spam` and stays in Spam in Gmail.
- The Spam choice is a checkbox on the connect screen, sent in the sealed OAuth `state`. A reconnect sends none and keeps the mailbox's choice. The mailbox menu switches it later (`PATCH`): the watch is renewed for the new labels, and turning it on reads the last 2 days of Spam without moving the cursor.
- Herald sends only replies the owner writes. The scopes are `gmail.readonly` and `gmail.send`. Google lets the owner untick a scope, so each mailbox records whether send was granted (`can_send`).
- Credentials are encrypted with `HERALD_TOKEN_KEY` and never leave the server. The OAuth `state` is signed with the same key and expires after 10 minutes.
- Push is verified: the Pub/Sub JWT must match the audience and service account in the settings. A bad signature gets 401. A good push for an unknown or inactive address gets 204, so Pub/Sub does not retry it.

### Sync job

`sync_mailbox_job` uses a pending flag and a lock, not fixed job ids.

- Every job first sets the flag `herald:sync-pending:{mailbox_id}`.
- One job at a time per mailbox holds the Redis lock `herald:sync:{mailbox_id}`. Any other job sees the lock busy and returns, because the flag is already set.
- The lock holder loops while the flag is set: clear the flag, sync, enqueue `process_email` for each new email. A push that arrives during a sync sets the flag again.
- When a fetch reports `has_more`, the job sets the flag again, so the loop reads the next batch. The inline queue (lite mode) loops on `has_more` the same way.
- The loop stops after 120 s. After the lock is released, a leftover flag starts a fresh job.
- A rate limit from the provider retries the job (at least 5 s later, up to 5 tries). The cursor does not move, so the retry reads the same changes.
- A pause or disconnect that races a sync stops later syncs: a mailbox that is not `active` is not synced, and the sync never overwrites that status. A fetch already in flight can still store its mail and move the cursor.

### Mailbox status

| Status | Meaning | Moves out by |
| --- | --- | --- |
| `active` | Syncing and receiving push | Owner pauses, access is revoked, or owner disconnects |
| `paused` | Owner stopped it. Push is off, the cursor is kept. | Owner resumes (a catch-up sync runs) |
| `needs_reauth` | The owner revoked access, or the stored credentials no longer decrypt. Only an `active` mailbox moves here. | Owner connects again; the same row is reused. Another workspace cannot connect the address meanwhile. |
| `disconnected` | Credentials are deleted. Push is stopped and the grant is revoked, both best effort. Stored emails are kept. | Owner connects again; the same row and cursor are reused, unless another workspace has connected the address since |

The owner can disconnect from `active`, `paused` and `needs_reauth`. Every change saves a `mailbox.status` event in the same transaction, then publishes it to the live events stream.

One business per mailbox: an address is connected in at most one workspace at a time. Every status but `disconnected` holds the address. The connect checks this before it saves and answers `mailbox_in_use`. The partial unique index `uq_mailbox_live_address` on `(provider, email_address)`, over rows that are not `disconnected`, refuses a second connect that races past the check. A `disconnected` row does not hold the address, so another workspace can connect it; the old row and its emails stay with their workspace. A refused connect does not revoke the grant it just got: that grant is the same account's as the other workspace's, and a revoke would end both.

The API and the worker refuse to start when `HERALD_TOKEN_KEY` cannot decrypt the stored mailbox credentials (they open one to check, an `active` mailbox's when there is one). This catches a worker whose key differs from the API's, which would otherwise move every mailbox to `needs_reauth`. To change the key, disconnect every mailbox first, then reconnect them after the change.

### Routes

| Route | What it does |
| --- | --- |
| `GET /api/providers` | Providers this server can connect, like `["gmail"]`. Empty without `HERALD_TOKEN_KEY`. |
| `GET /api/workspaces/{id}/mailboxes` | List mailboxes. No credential fields. |
| `POST /api/workspaces/{id}/mailboxes/{provider}/connect` | Returns the provider's `authorization_url`. Optional body `{read_spam}`; leave it out on a reconnect. |
| `PATCH /api/workspaces/{id}/mailboxes/{mailbox_id}` | `{read_spam}`: read the Spam folder too, or stop. 409 when disconnected. |
| `GET /api/oauth/{provider}/callback` | Finishes the connect, then redirects to the web app |
| `POST /api/workspaces/{id}/mailboxes/{mailbox_id}/sync` | Queue a sync now (202). 409 unless `active`. |
| `POST .../pause`, `POST .../resume`, `DELETE .../{mailbox_id}` | Owner actions. 409 when the status does not allow it. |
| `POST /api/webhooks/{provider}` | Provider push. Verified by the connector. |

The OAuth callback always redirects to `HERALD_WEB_URL` with one outcome below. Once the state is checked, it also adds `workspace=<id>`, so the web opens the business the connect started from. The inbox keeps the same `workspace` param, with `view`, `q`, `urgent` and `email`, on its URL (`apps/web/src/lib/inbox/url.ts`); it drops `mailbox_connected` or `mailbox_error` once it has shown the notice. `provider_unavailable` and `invalid_state` come before that check and name no workspace. A refusal at the provider (`access_denied`) is reported only with a valid state; with a bad one it is `invalid_state`.

| Query | Meaning |
| --- | --- |
| `mailbox_connected=<id>` | The mailbox is saved and `active`. Its first sync is queued (if queueing fails, the catch-up sync runs it). A failure after the save is logged and does not change this answer. |
| `mailbox_error=access_denied` | The owner refused at the provider (and the state is valid) |
| `mailbox_error=provider_unavailable` | The provider is not set up, or `HERALD_TOKEN_KEY` is not set |
| `mailbox_error=invalid_state` | The state is bad, expired, for another provider, or names a missing workspace |
| `mailbox_error=authorization_failed` | No code came back, or the provider refused the code |
| `mailbox_error=no_refresh_token` | The provider gave no long-lived credential |
| `mailbox_error=mailbox_in_use` | Another workspace has this address connected (in any status but `disconnected`). Nothing is saved. |
| `mailbox_error=provider_error` | Any other failure before the mailbox is saved: for example the account has no Gmail, the owner deselected the scope, a rate limit, or a network error |

### Cron jobs

| Job | When | What it does |
| --- | --- | --- |
| `renew_subscriptions_job` | Daily at 03:00 | Renews push for every active mailbox. A Gmail watch lasts 7 days. A revoked grant moves the mailbox to `needs_reauth`. |
| `catch_up_syncs_job` | Every 15 minutes | Queues a sync for every active mailbox, to pick up mail whose push was lost |

Both jobs run across all workspaces on purpose. The times are the worker's local time (arq cron).

Google Cloud setup (consent screen, OAuth client, Pub/Sub topic and push subscription) is a manual step. It is described in the mail connectors plan. In the OAuth consent screen, under Data access, add the scope `https://www.googleapis.com/auth/gmail.send` too. Without it Google never grants send.

## Plug-in points

| Interface | Where | Built-in implementations |
| --- | --- | --- |
| `TriageModel` | `herald_core.model` | `AnthropicModel` (Claude, structured outputs), `FakeModel` (offline keyword heuristics) |
| `MailConnector` | `herald_server.connectors` | `GmailConnector`; `FakeConnector` in tests. The test-email box still posts to the API. |
| `EventBus` | `herald_server.bus` | `RedisEventBus`, `InMemoryEventBus` |
| `JobQueue` | `herald_server.queue` | `ArqQueue`, `InlineQueue` |
| `Tool` / `Toolbox` | `herald_core.tools` (types), `herald_server.tools` (tools that call the internal routes) | `SenderHistoryTool`, `ThreadTool`, `CorrectionsTool` |
| `ModelTool` | `herald_core.model_tools` | `SenderLookup` (the model's `sender_history`) |

## Configuration

Settings are read from `HERALD_*` environment variables or `.env` (see `.env.example`).

| Variable | Default | Lite mode (`make lite`) |
| --- | --- | --- |
| `HERALD_DATABASE_URL` | Postgres on localhost | SQLite file |
| `HERALD_BUS` | `redis` | `memory` |
| `HERALD_QUEUE` | `arq` | `inline` |
| `HERALD_MODEL_PROVIDER` | `fake` | `fake` |
| `HERALD_LOG_LEVEL` | `INFO` (one line per email arrival and pipeline step, in the API or worker terminal) | same |
| `HERALD_TOKEN_KEY` | unset (Gmail off: it needs this, the Google client id and secret, and the topic) | unset |
| `HERALD_PUBLIC_API_URL` | `http://localhost:8000` | same |
| `HERALD_WEB_URL` | `http://localhost:5173` | same |
| `HERALD_INTERNAL_TOKEN` | unset: the API and worker refuse to start with the arq queue. `make api`, `make worker` and `make docker-dev` set a dev value. At least 24 chars. | unset (a random one per process) |
| `HERALD_INTERNAL_API_URL` | `http://localhost:8000` (the compose files set `http://api:8000`) | not used |
| `HERALD_GOOGLE_CLIENT_ID`, `HERALD_GOOGLE_CLIENT_SECRET` | unset (Gmail off, as above) | unset |
| `HERALD_GMAIL_TOPIC` | unset (Gmail off: no mailbox can be connected) | unset |
| `HERALD_GMAIL_PUSH_AUDIENCE`, `HERALD_GMAIL_PUSH_SERVICE_ACCOUNT` | unset (every push is rejected) | unset |
| `HERALD_LANGFUSE_PUBLIC_KEY`, `HERALD_LANGFUSE_SECRET_KEY` | unset (tracing off; it needs both) | unset (off unless you set them) |
| `HERALD_LANGFUSE_BASE_URL` | `http://localhost:3000` (`make docker-dev` sets `http://host.docker.internal:3000`) | same |

## Tracing (dev)

Tracing is for development only. It sends each triage run to a Langfuse that runs on your machine, so you can see what the model was asked and what it said. The Langfuse packages are in the dev dependency group, so the production image cannot trace. Traces hold customer emails, so they never leave your machine.

- `make langfuse` starts Langfuse on `http://localhost:3000` (Docker). Log in with `dev@herald.test`. The dev keys are in `.env.example`. `make langfuse-down` stops it and keeps its data.
- `.env.example` sets both keys, so a `.env` copied from it traces. Restart the API and worker after you change them: settings are read at startup. Tracing turns on only when both keys are set and Langfuse accepts them. At startup Herald logs whether tracing is on. If Langfuse is down, it logs a warning and runs without tracing. Blank both keys to turn it off. Tracing never changes a triage result.
- `docker-compose.prod.yml` blanks the keys, and the production image has no Langfuse package.
- A live email is one trace named `triage`, with the email id as the session. A Try run (`trial-read`) is a trace of its own. An eval trial is a trace named `eval`, and all trials of one `herald-evals` run share a session, which the run record keeps as `langfuse_session`.
- Under the trace root, the model-call spans (`model.write_notes`, `model.judge_rules`) sit beside the LangGraph node spans.
- Each trace gets four outcome scores: `route`, `floor` (a safety-floor word matched), `unsure` and `ai_failed`. An eval trace also gets `passed`, set after the labels are checked. Use them to filter runs.
- Real generations (prompts and replies, tokens, cost) show up only with `HERALD_MODEL_PROVIDER=anthropic`. The fake model makes no API call, so you see the spans and scores only.
- Setup drafts are not traced as runs. Their Claude calls may show up as stray traces.

## Database migrations

The schema is managed with Alembic. The migrations live in `apps/server/src/herald_server/migrations/versions`, so they ship in the server package.

- `make migrate` (`python -m herald_server.migrate`) brings the database to the latest revision. `make api`, `make lite` and `make dev` run it first. In Docker, a one-shot `migrate` service runs it, and the API waits for it to finish.
- The API and the worker never change the schema. At startup they check that the database is at the latest revision, and refuse to start when it is not.
- A database made by `create_all` before migrations has no revision. `make migrate` compares it with the models. When they match exactly, it marks the database as migrated and keeps its data. When anything differs (a missing column, index or enum value), it refuses and names the differences. Start from an empty database then:
  - Lite mode: delete `apps/server/herald-dev.db`.
  - Postgres: run `docker compose -f infra/docker-compose.yml down -v`, then `make infra`.

### Changing the schema

1. Change the models in `models.py`.
2. With Postgres running and migrated (`make infra`, `make migrate`), run `make migration m="what changed"`. Alembic compares the models with the database and writes a new file in `versions/`. Write it against Postgres: enum changes show up only there.
3. Read the file and fix it. Autogenerate does not see:
   - a change to the `WHERE` of a partial index (`uq_mailbox_live_address`, `uq_reply_one_sending`): drop and recreate the index by hand;
   - a renamed column or table: it writes a drop and an add, which loses the data;
   - data that must move: write it in the migration with `op.execute`.
4. Run `make migrate`, then `make migrate-check`. The check fails when the models have a change no migration covers.
5. Run the tests. `test_migrations.py` builds a SQLite database from the migrations and fails if it differs from the models.

Enum columns are native Postgres enums that store the member *name* (`DISCONNECTED`, not `disconnected`). `alembic-postgresql-enum` writes the `ALTER TYPE` for added or removed values. Its operations do nothing on SQLite, where an enum is a plain string.

Constraint names come from the naming convention in `models.py`. It reproduces the names Postgres gave databases made before migrations, so those databases can be adopted. Do not change it: every existing constraint would need a rename.

Two branches that each add a migration leave two heads after both merge. Startup and `test_there_is_one_head` then fail. Run `uv run alembic merge heads -m "merge"` in `apps/server` and commit the file it writes.

Production rolls forward only. Write `downgrade()` where it is cheap; it is for development.

## Not built yet

- Business-system tools, and model tools other than `sender_history`
- Auth and per-workspace limits
- A settings page for editing a workspace after setup (`PUT /config` is ready for it)
- The rule test (the score report and the test-email set are in `packages/evals`)
- An Outlook connector, and IMAP
- Filter-based watch labels (Gmail watches the whole inbox)
- Binding the OAuth `state` to the browser that started the connect. It needs auth or a state cookie.
- A sweeper for emails left `new` when a sync fails after its commit
- Refusal fallbacks for the Claude model (a refusal currently routes the email to "Needs a look")
- A re-read sweep for emails saved with an `unavailable` or `setup` AI failure, a shared cooldown when the API is overloaded, and a fallback model on overload
