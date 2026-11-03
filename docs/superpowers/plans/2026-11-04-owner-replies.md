# Owner Replies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner write a reply to a customer email in Herald and send it from the connected Gmail, in the customer's thread, for example to say "your issue is fixed".

**Architecture:** The `MailConnector` contract gets one method, `send_reply`, and Gmail implements it with the `gmail.send` scope and `users.messages.send`. At intake, Herald saves the headers a reply needs (`Message-ID`, `References`, `Reply-To`). A new `Reply` row records each send. The reply route does its work in three steps: a sync transaction inserts the row as `sending`, the send runs with no session open, and a second sync transaction saves the outcome, stages events and can mark the email done. Sent replies join the thread context, so the model sees what the owner already told the customer.

**Tech Stack:** FastAPI, SQLModel, httpx (Gmail REST), Python `email` package (MIME build), SvelteKit with Svelte 5 runes, pytest, vitest.

**Spec:** None. The user asked for a plan without a spec, so this plan is the design. Task 4 records the decision in `docs/decisions.md`. Read `CLAUDE.md`, `docs/architecture.md` (Mail intake, Sync job) and `docs/decisions.md` before starting.

**Out of scope:** AI-drafted replies, attachments, HTML bodies, quoting the original email, Outlook and IMAP, and sending to anyone other than the customer who wrote.

## Global Constraints

- **The AI never sends.** Only the reply route sends, and only after the owner presses Send. No job, pipeline step or model output calls `send_reply`.
- **Status:** a reply never changes an email's status unless the owner asks for "Send and mark done". Even then, only the shared owner-action helper moves the status (Task 4).
- **Provider-neutral outside `connectors/gmail/`.** `replies.py`, routes and models use `services.connectors[mailbox.provider]` and never name Gmail.
- **Tenancy:** every query filters on `workspace_id`. `test_workspaces_are_isolated`-style coverage for replies is in Task 4.
- **Events:** stage with `add_event`, commit, then publish with `to_bus`. New event type: `reply.status`.
- **No session across an `await`.** DB work is sync functions called with `asyncify`, as everywhere else.
- **Never retry a send automatically.** An unknown outcome may mean the customer got the email.
- **Logs** name ids and error types only, never bodies, addresses or tokens.
- Gmail scopes are exactly `https://www.googleapis.com/auth/gmail.readonly` and `https://www.googleapis.com/auth/gmail.send`.
- **No migrations.** After Task 1 and Task 4, delete `apps/server/herald-dev.db` or run `docker compose -f infra/docker-compose.yml down -v`.
- After changing `api/schemas.py`, run `make gen-api` and commit `apps/web/src/lib/api/schema.d.ts`.
- **Comment complex logic** (rule in `CLAUDE.md`): the three-step send, the stale `sending` rule, the error-to-outcome mapping and header handling each get a short comment saying why.
- Ruff, line length 100. Web uses tabs and Prettier. Use the `svelte-code-writer` skill for `.svelte` files.

## Review Focus

- **Two tabs, or a double click, send the same reply.** One row with the same `client_key` sends once. A second key while one reply is `sending` gets 409. Tests in Task 4.
- **The process dies mid-send.** The `sending` row must not block the email forever. A `sending` row older than 2 minutes turns `unknown` on the next attempt. Test in Task 4.
- **Gmail times out or answers 5xx.** The reply is `unknown`, not retried, and the UI tells the owner to check Gmail's Sent folder. Tests in Task 3 and Task 4.
- **A contact-form email: `From` is a no-reply address and `Reply-To` is the customer.** The reply goes to `Reply-To`. Tests in Task 1 and Task 4.
- **The mailbox was connected before this change, or the owner unticked "send" on Google's consent screen.** `can_send` is false, the API answers 409 and the UI offers a reconnect. Reconnecting an active mailbox turns sending on. Tests in Task 2 and Task 6.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `apps/server/src/herald_server/connectors/gmail/mime.py` | Also read `Message-ID`, `References`, `Reply-To` |
| `apps/server/src/herald_server/connectors/gmail/compose.py` (new) | Build the raw MIME reply |
| `apps/server/src/herald_server/connectors/gmail/client.py` | Two scopes, granted scope on `TokenSet`, `send_message` |
| `apps/server/src/herald_server/connectors/gmail/connector.py` | Pass reply headers on intake, `can_send`, `send_reply` |
| `apps/server/src/herald_server/connectors/base.py` | Reply headers on `InboundMessage`, `can_send`, `OutboundReply`, `SentReply`, send errors, protocol method |
| `apps/server/src/herald_server/models.py` | `Email` reply-header columns, `Mailbox.can_send`, `ReplyStatus`, `Reply` |
| `apps/server/src/herald_server/sync.py` | Store the reply headers |
| `apps/server/src/herald_server/mailboxes.py` | Save `can_send` on connect; `clear_can_send` |
| `apps/server/src/herald_server/status.py` (new) | `stage_move`: the owner-action status change, shared by actions and replies |
| `apps/server/src/herald_server/replies.py` (new) | Start, send and finish a reply |
| `apps/server/src/herald_server/api/routes/replies.py` (new) | `POST` and `GET` replies |
| `apps/server/src/herald_server/api/routes/emails.py` | `_move` uses `stage_move` |
| `apps/server/src/herald_server/api/schemas.py` | `ReplyIn`, `ReplyOut`; `EmailOut.mailbox_id`, `EmailOut.reply_to`; `MailboxOut.can_send` |
| `apps/server/src/herald_server/events.py` | `REPLY_STATUS` |
| `apps/server/src/herald_server/tools/history.py`, `packages/core/src/herald_core/history.py`, `prompt.py` | Owner replies in the thread |
| `apps/server/tests/fake_connector.py` | `send_reply`, `sent`, `raise_on_send`, `can_send=True` |
| `apps/web/src/lib/inbox/reply.ts` (new), `ReplyBox.svelte` (new), `EmailPanel.svelte`, `routes/+page.svelte` | Compose, send and show replies |
| `apps/web/src/lib/mailbox/MailboxMenu.svelte`, `lib/api/client.ts`, `lib/events.svelte.ts` | Allow-replies reconnect, API calls, new event |

---

### Task 1: Save reply headers at intake

**Files:**
- Modify: `connectors/gmail/mime.py`, `connectors/base.py`, `connectors/gmail/connector.py` (the `InboundMessage(...)` in `fetch_changes`), `models.py` (`Email`), `sync.py` (`_store`)
- Test: `apps/server/tests/connectors/test_gmail_mime.py`, `apps/server/tests/test_sync.py`

**Interfaces:**
- Produces: `ParsedMessage` gains `message_id: str | None`, `references: str | None`, `reply_to: str | None`.
- Produces: `InboundMessage` and `Email` gain `internet_message_id: str | None = None`, `references: str | None = None`, `reply_to: str | None = None`. These are RFC 5322 headers, so the names are provider-neutral (`internet_message_id` is Outlook's term too).

- [ ] **Step 1: Write the failing MIME tests** in `test_gmail_mime.py`:
  - `test_parse_keeps_reply_headers`: `Message-ID: <a1@mail.customer.in>`, `References: <r0@x> <r1@x>`, `Reply-To: "Riya" <Riya@Customer.in>` parse to `message_id == "<a1@mail.customer.in>"`, `references == "<r0@x> <r1@x>"`, `reply_to == "riya@customer.in"`.
  - `test_parse_without_reply_headers`: all three are `None`.
  - `test_reply_to_takes_the_first_address`: `Reply-To: a@x.in, b@x.in` gives `"a@x.in"`.
  - `test_long_references_keep_the_newest_twenty`: 30 ids in, the last 20 out, space-joined.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/connectors/test_gmail_mime.py -v`. Expected: the four new tests FAIL.
- [ ] **Step 3: Implement in `parse_raw_message`.** Strip the values and fold whitespace to single spaces, so a CR/LF in a header can never reach an outgoing header. Take `Reply-To` with `getaddresses` and keep the first address, lower-cased, or `None`. Cap `References` to the last 20 ids (RFC 5322 §3.6.4 allows trimming, and Gmail threads on the newest ones). Cap `message_id` at 998 chars.
- [ ] **Step 4: Thread the fields through.** Add them to `InboundMessage`, set them in `GmailConnector.fetch_changes`, add the three columns to `Email` (no index), and copy them in `sync._store`.
- [ ] **Step 5: Write the failing sync test** `test_sync_stores_reply_headers` in `test_sync.py`: a `message(...)` with the three fields set is stored with the same values on its `Email` row.
- [ ] **Step 6: Run** `uv run pytest apps/server/tests/connectors/test_gmail_mime.py apps/server/tests/test_sync.py -v`. Expected: PASS.
- [ ] **Step 7: Commit** `Save the headers a reply needs at intake`.

### Task 2: Ask Gmail for send permission and record it

**Files:**
- Modify: `connectors/gmail/client.py` (`SCOPE`, `TokenSet`, `exchange_code`), `connectors/gmail/connector.py` (`authorization_url`, `complete_authorization`), `connectors/base.py` (`ConnectedAccount`), `models.py` (`Mailbox`), `mailboxes.py` (`upsert_connected`), `api/schemas.py` (`MailboxOut`), `tests/fake_connector.py`, `docs/architecture.md` (Mail intake bullet "The scope is `gmail.readonly`")
- Test: `tests/connectors/test_gmail_connector.py`, `tests/test_mailboxes_api.py`

**Interfaces:**
- Produces: `client.READ_SCOPE`, `client.SEND_SCOPE`, `client.SCOPES = (READ_SCOPE, SEND_SCOPE)`. `SCOPE` goes away.
- Produces: `TokenSet(access_token, refresh_token, scope: str)`, where `scope` is Google's space-separated granted list (`""` when missing).
- Produces: `ConnectedAccount.can_send: bool = False`, `Mailbox.can_send: bool = False`, `MailboxOut.can_send: bool`.

- [ ] **Step 1: Write the failing tests:**
  - `test_authorization_url_asks_to_read_and_send`: the URL's `scope` param is `"<read> <send>"`.
  - `test_complete_authorization_reports_send_permission`, parametrized on the token response `scope`: read and send gives `can_send is True`. Read only gives `False`, because Google's granular consent lets the owner untick a scope. A missing `scope` field gives `False`.
  - `test_reconnecting_an_active_mailbox_turns_on_sending` in `test_mailboxes_api.py`: connect with `fake_connector.account.can_send = False`, then connect again with `True`. One mailbox row, still `active`, and `GET /mailboxes` shows `can_send: true`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** `upsert_connected` sets `mailbox.can_send = account.can_send` on every connect. Then a reconnect that grants send turns it on, and one that drops send turns it off. `FakeConnector.account` gets `can_send=True`. Update the architecture bullet: Herald reads inbox mail and sends only replies the owner writes. The scopes are `gmail.readonly` and `gmail.send`.
- [ ] **Step 4: Run** `uv run pytest apps/server/tests -k "authorization or reconnect or mailbox" -v`, then `make gen-api`. Expected: PASS.
- [ ] **Step 5: Commit** `Ask Gmail for send permission and record it per mailbox`.

**Manual, once, before Task 7:** in Google Cloud console, under OAuth consent screen → Data access, add `https://www.googleapis.com/auth/gmail.send`. Without this, Google never grants it. Add this line to the Google Cloud runbook in `docs/architecture.md` (or wherever the runbook from the mail-connectors plan now lives).

### Task 3: Send contract and the Gmail send

**Files:**
- Modify: `connectors/base.py`, `connectors/gmail/client.py`, `connectors/gmail/connector.py`, `tests/fake_connector.py`
- Create: `connectors/gmail/compose.py`
- Test: `tests/connectors/test_gmail_compose.py` (new), `tests/connectors/test_gmail_client.py`, `tests/connectors/test_gmail_connector.py`

**Interfaces:**
- Produces in `base.py`:
  ```python
  class OutboundReply(BaseModel):
      from_address: str
      to_address: str
      subject: str            # final subject, "Re: ..." already applied by the caller
      body: str               # plain text
      in_reply_to: str | None  # the customer email's Message-ID
      references: str | None   # its References plus its Message-ID
      provider_thread_id: str | None

  class SentReply(BaseModel):
      provider_message_id: str

  class SendNotAllowed(Exception): """The account did not grant permission to send."""
  class SendRejected(Exception): """The provider refused this message. It was not sent."""
  ```
  `MailConnector.send_reply(self, credentials: dict[str, str], reply: OutboundReply) -> SentReply`. The docstring says that `AuthRevoked`, `RateLimited`, `SendNotAllowed` and `SendRejected` all mean the message was not sent, and that any other exception means the outcome is unknown.
- Produces: `compose.build_reply(reply: OutboundReply) -> str` (base64url raw, no padding). Also `GmailClient.send_message(access: str, raw: str, thread_id: str | None) -> str` (the new message id).
- Produces: `FakeConnector.sent: list[OutboundReply]` and `FakeConnector.raise_on_send: Exception | None`. Its `send_reply` appends to `calls` and returns `SentReply(provider_message_id=f"sent-{len(sent)}")`.

- [ ] **Step 1: Write the failing compose tests.** Decode the result with `email.message_from_bytes(..., policy=email.policy.default)`:
  - `test_reply_carries_thread_headers`: `From`, `To`, `Subject`, `In-Reply-To`, `References` match the input. `Message-ID` exists and ends with `@shop.in>` (the from domain).
  - `test_header_values_cannot_add_headers`: a subject `"Hi\r\nBcc: evil@x.in"` gives a message with no `Bcc` header and a subject on one line. Assert on the parsed message, not on what `email.policy` is expected to do.
  - `test_body_keeps_unicode`: `"धन्यवाद, fixed ✓"` round-trips as the text/plain content.
  - `test_no_thread_headers_when_missing`: `in_reply_to=None` gives no `In-Reply-To` or `References` header.
- [ ] **Step 2: Write the failing client tests** with `httpx.MockTransport`:
  - `test_send_posts_raw_and_thread`: POST to `.../messages/send` with JSON `{"raw": raw, "threadId": "t1"}` returns `"m9"`. No `threadId` key when it is `None`.
  - `test_send_403_insufficient_scope_is_send_not_allowed`: a 403 with reason `insufficientPermissions`, or with message `Request had insufficient authentication scopes.`, raises `SendNotAllowed`.
  - `test_send_4xx_is_rejected`: 400 and 404 raise `SendRejected`. The exception message names the status only, never the response body.
  - `test_send_5xx_is_unknown`: a 500 raises `httpx.HTTPStatusError`, not a connector error.
  - `test_send_429_is_rate_limited`: raises `RateLimited` (already mapped by `_request`).
- [ ] **Step 3: Run them.** Expected: FAIL.
- [ ] **Step 4: Implement `build_reply`.** Use `EmailMessage` with `policy.SMTP`. Before setting each header value, replace every run of CR/LF and other whitespace with one space. Set `Message-ID` with `make_msgid(domain=<from domain>)` and set `Date`. `References` is passed as given (the caller builds it).
- [ ] **Step 5: Implement `send_message`.** Use `_request` directly, not `_api`, because the 403 and 4xx mapping is specific to sending. Check rate limits first (`_request` already does), then the scope 403, then other 4xx. Let 5xx and transport errors propagate. Add a comment saying the split decides whether the owner is told "not sent" or "check Sent".
- [ ] **Step 6: Implement `GmailConnector.send_reply`.** Refresh the token, `build_reply`, `send_message(access, raw, reply.provider_thread_id)`, then return `SentReply`. Gmail needs `threadId`, the matching `References`/`In-Reply-To` and a matching subject to keep the reply in the thread. Say so in a comment.
- [ ] **Step 7: Write and pass** `test_send_reply_refreshes_and_sends_in_thread` in `test_gmail_connector.py`.
- [ ] **Step 8: Run** `uv run pytest apps/server/tests/connectors -v`. Expected: PASS.
- [ ] **Step 9: Commit** `Add send_reply to the connector contract and Gmail`.

### Task 4: The reply route

**Files:**
- Create: `status.py`, `replies.py`, `api/routes/replies.py`
- Modify: `models.py`, `events.py`, `api/routes/emails.py` (`_move`), `api/schemas.py`, `api/main.py` (router tuple), `mailboxes.py`, `docs/decisions.md`, `docs/architecture.md`, `docs/product-scope.md`
- Test: `apps/server/tests/test_replies.py` (new). Reuse `add_mailbox`, `message`, `sync` and `demo_workspace` from `test_sync.py` (`from test_sync import ...`, the same way `fake_connector` is imported).

**Interfaces:**
- Consumes: `OutboundReply`, `SentReply` and the send errors (Task 3), `Mailbox.can_send` (Task 2), and the `Email` reply headers (Task 1).
- Produces in `models.py`:
  ```python
  class ReplyStatus(StrEnum):
      SENDING = "sending"; SENT = "sent"; NOT_SENT = "not_sent"; UNKNOWN = "unknown"

  class Reply(SQLModel, table=True):
      # UniqueConstraint("workspace_id", "client_key")
      id, workspace_id (fk, index), email_id (fk, index), mailbox_id (fk)
      client_key: str
      from_address: str; to_address: str; subject: str; body: str
      status: ReplyStatus = SENDING (index)
      error: str | None     # one of the error kinds below, never provider text
      provider_message_id: str | None
      created_at: datetime; sent_at: datetime | None
  ```
  Add a partial unique index `uq_reply_one_sending` on `email_id` where `status == SENDING`. Build it from the column, exactly like `uq_mailbox_live_address`, because the enum is stored by name.
- Produces: `status.stage_move(session, workspace_id: str, email: Email, to: EmailStatus, only_from: EmailStatus | None = None) -> Event`. It raises `WrongStatus(previous)` and holds today's `_move` body (correction rows included) except the session and commit. `_move` calls it and maps `WrongStatus` to 409.
- Produces: `events.REPLY_STATUS = "reply.status"`, with data `{"email_id", "reply_id", "status"}`.
- Produces in `replies.py`:
  - `STALE_SENDING = timedelta(minutes=2)`
  - `reply_subject(subject: str) -> str`: adds `"Re: "` unless the subject already starts with `re:` in any case. An empty subject gives `"Re: "`.
  - `class ReplyBlocked(Exception)` with `reason: Literal["no_mailbox", "mailbox_inactive", "send_not_allowed", "already_sending"]`
  - `async def send_reply(services, workspace_id: str, email_id: str, data: ReplyIn) -> Reply`
  - `def list_replies(services, workspace_id: str, email_id: str) -> list[Reply]`, oldest first
  - Error kinds saved in `Reply.error`: `"rate_limited"`, `"auth"`, `"send_not_allowed"`, `"rejected"`, `"unknown"`.
- Produces in `mailboxes.py`: `clear_can_send(services, mailbox_id: str) -> None`.
- Produces in `schemas.py`: `ReplyIn(body: str 1..20_000, client_key: str 8..64, mark_done: bool = False)`, plus `ReplyOut(id, email_id, to_address, subject, body, status, error, created_at, sent_at)`. `EmailOut` gains `mailbox_id: str | None` and `reply_to: str | None`.
- Produces in routes: `POST /api/workspaces/{workspace_id}/emails/{email_id}/replies` returns 200 `ReplyOut`. The outcome is in `status`, because the reply row is the resource. `ReplyBlocked` gives 409 with `detail` set to the reason. An unknown email or one in another workspace gives 404. `GET` on the same path returns `list[ReplyOut]`.

**How `send_reply` runs** (the comment in the code says why each step is separate):
1. `_begin`, sync, one transaction. Load the email filtered by workspace (404). Load its mailbox and decide:
   - `email.mailbox_id is None` → `no_mailbox`
   - mailbox not `ACTIVE` → `mailbox_inactive`
   - `not can_send` → `send_not_allowed`
   
   A row with this `client_key` already exists → return it, and the caller returns without sending. Otherwise turn any `SENDING` row for this email older than `STALE_SENDING` into `UNKNOWN`: its process died mid-send, and the customer may have it. Then insert a `SENDING` row and commit. `IntegrityError` on `uq_reply_one_sending` → `already_sending`. The row's fields:
   - `to_address`: `email.reply_to or email.sender`
   - `from_address`: the mailbox address
   - `subject`: `reply_subject(email.subject)`
   - `in_reply_to`: `email.internet_message_id`
   - `references`: `email.references` plus `internet_message_id`
   - `provider_thread_id`: the part after the first `:` of `email.thread_id` (`sync._store` writes `f"{mailbox_id}:{thread}"`, and mailbox ids are hex with no colon)
2. Open the credentials. If that fails, the outcome is `NOT_SENT`, `"auth"`. Otherwise call `connector.send_reply` once, with no session open:
   - `SentReply` → `SENT`
   - `RateLimited` → `NOT_SENT`, `"rate_limited"`
   - `AuthRevoked` → `NOT_SENT`, `"auth"`, then `mark_needs_reauth`
   - `SendNotAllowed` → `NOT_SENT`, `"send_not_allowed"`, then `clear_can_send`
   - `SendRejected` → `NOT_SENT`, `"rejected"`
   - any other `Exception` → `UNKNOWN`, `"unknown"`, logging the reply id and exception type only
3. `_finish`, sync, one transaction. Save the status, `sent_at` and `provider_message_id`, and stage `reply.status`. If `SENT` and `mark_done` and the email is not already `DONE`, also call `stage_move(..., EmailStatus.DONE)`. Commit, refresh and return the events. The caller publishes each one.

- [ ] **Step 1: Refactor `_move` onto `status.stage_move`** with no behaviour change. Run `uv run pytest apps/server/tests/test_api.py -v`. Expected: PASS.
- [ ] **Step 2: Write the failing tests** in `test_replies.py`. Setup: a demo workspace, `add_mailbox(..., can_send=True)`, sync one `message(...)` with thread and reply headers, and POST a reply.
  - `test_reply_sends_in_the_thread`: `fake.sent[0]` has `to_address == "riya@customer.in"`, `from_address == "owner@shop.in"`, subject `"Re: Product questions"`, `in_reply_to` the stored Message-ID and `provider_thread_id` the raw thread id. Response `status == "sent"`. A `reply.status` event is stored.
  - `test_reply_goes_to_reply_to`
  - `test_reply_leaves_status_alone`: the email's status is unchanged and no `email.status` event is stored.
  - `test_send_and_mark_done`: the status is `done` and an `email.status` event is stored.
  - `test_not_sent_does_not_mark_done`: with `raise_on_send = SendRejected()` and `mark_done`, the status is unchanged and the response is `not_sent` with `error == "rejected"`.
  - `test_same_client_key_sends_once`: two POSTs with one key give one `fake.sent` entry and the same reply id.
  - `test_second_reply_while_sending_is_409`: insert a fresh `SENDING` row directly → 409 `already_sending`.
  - `test_stale_sending_row_does_not_block`: a `SENDING` row with `created_at` 3 minutes ago becomes `unknown`, and the new reply sends.
  - `test_timeout_is_unknown_and_not_retried`: with `raise_on_send = httpx.ReadTimeout("t")`, the response is `unknown` and `fake.calls.count("send_reply") == 1`.
  - `test_rate_limit_is_not_sent`
  - `test_send_not_allowed_turns_off_can_send`
  - `test_auth_revoked_marks_needs_reauth`
  - `test_email_without_mailbox_is_409`: a test-box email (`POST /emails`) → `no_mailbox`
  - `test_paused_mailbox_is_409` and `test_mailbox_without_send_is_409`
  - `test_replies_are_isolated`: POST and GET through another workspace's id → 404.
  - `test_list_replies_oldest_first`
- [ ] **Step 3: Run** `uv run pytest apps/server/tests/test_replies.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the models, `replies.py`, the routes and the schemas, then register `replies` in `create_app`. Run `make gen-api`.
- [ ] **Step 5: Run** `uv run pytest apps/server/tests -v`. Expected: PASS.
- [ ] **Step 6: Write the docs.**
  - `decisions.md` row dated 2026-11-04: **"Owner-written replies are sent from Herald."** It must say this is the one thing that leaves the app, that the owner writes and sends every reply, that the AI never sends, and that it does not change "Alerts stay in the app".
  - `architecture.md`: a short Replies section covering the three steps, the outcomes, the stale rule and the event. Also add the `Reply` table and the new `Email` and `Mailbox` columns to the DB-reset paragraph.
  - `product-scope.md`: in the Replies row and the "No replying on the owner's behalf" line, say the owner can now write and send replies, and AI drafts are still roadmap.
- [ ] **Step 7: Commit** `Let the owner reply to a customer from Herald`.

### Task 5: Owner replies in the thread context

Last backend task, so it can be cut on its own.

**Files:**
- Modify: `packages/core/src/herald_core/history.py` (`ThreadMessage`), `packages/core/src/herald_core/prompt.py` (thread block), `apps/server/src/herald_server/tools/history.py` (`ThreadTool._query`)
- Test: `packages/core/tests/test_prompt.py`, `apps/server/tests/test_history_tools.py`

**Interfaces:**
- Produces: `ThreadMessage.from_owner: bool = False`. `EmailContext.thread_ids` then holds reply ids as well as email ids. It is only stored for the record (`grep` shows no reader beyond `test_history.py`).

- [ ] **Step 1: Write the failing tests:**
  - `test_thread_includes_sent_owner_replies`: two emails and one `SENT` reply in a thread, in time order. The result shows the reply between them with `from_owner=True`.
  - `test_thread_skips_unsent_replies`: `SENDING`, `NOT_SENT` and `UNKNOWN` replies are left out, because the customer may never have seen them.
  - `test_thread_skips_replies_after_this_email`: the `before` cutoff applies to `sent_at`.
  - Extend `test_tools_are_isolated`: another workspace's reply in a thread with the same id never shows.
  - `test_owner_reply_is_labelled` in `test_prompt.py`: a `from_owner` message renders `from="the owner"`, not the mailbox address. A bare address means nothing to the model.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Query `Reply` joined to `Email` on `email_id`, with `Reply.workspace_id == self.workspace_id`, `Email.thread_id == args.thread_id`, `status == SENT` and `sent_at < before`. Merge with the email rows by time and keep the newest `limit`, oldest first.
- [ ] **Step 4: Run** `uv run pytest packages/core/tests apps/server/tests/test_history_tools.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `Show the owner's sent replies in the thread context`.

### Task 6: Web: compose, send and show replies

**The layout is open.** Herald's earlier screens each went through a `design-directions` round. If the owner wants options, run that first. The states, the copy and the contract below are fixed.

**Files:**
- Create: `apps/web/src/lib/inbox/reply.ts`, `reply.spec.ts`, `ReplyBox.svelte`
- Modify: `lib/api/client.ts`, `lib/events.svelte.ts` (`EVENT_TYPES`), `lib/inbox/EmailPanel.svelte`, `routes/+page.svelte`, `lib/mailbox/MailboxMenu.svelte`

**Interfaces:**
- Consumes: `ReplyIn`, `ReplyOut`, `EmailOut.mailbox_id`, `EmailOut.reply_to`, `MailboxOut.can_send` (generated types), and the `reply.status` event.
- Produces in `client.ts`: `type Reply = components['schemas']['ReplyOut']`, `api.reply(workspaceId, emailId, { body, client_key, mark_done }): Promise<Reply>` and `api.replies(workspaceId, emailId): Promise<Reply[]>`.
- Produces in `reply.ts`:
  - `replyState(email: Email, mailboxes: Mailbox[]): 'ok' | 'no_mailbox' | 'inactive' | 'reconnect'`
  - `replyNotice(reply: Reply): string`
  - `REPLY_COPY`, the exact strings below

**Copy (exact):**
- `no_mailbox`: "Replies need a connected Gmail. This email came in without one."
- `inactive`: "This mailbox is paused or disconnected. Resume it to reply."
- `reconnect`: "Herald can read this mailbox but can't send from it yet. Reconnect Gmail and allow sending." The panel offers a Reconnect button that starts the same connect flow as `MailboxMenu`.
- `sent`: "Sent to {to_address}, {formatTime(sent_at)}."
- `not_sent`: "Not sent. Nothing reached the customer." followed by one line per error:
  - `rate_limited`: "Gmail asked Herald to slow down. Try again in a minute."
  - `auth`: "Gmail access has ended. Reconnect Gmail."
  - `send_not_allowed`: "Gmail didn't allow sending. Reconnect Gmail and allow sending."
  - `rejected`: "Gmail refused this message."
- `unknown`: "Herald couldn't confirm this was sent. Check Gmail's Sent folder before you send it again."

**Behaviour:**
- `ReplyBox` shows a text area, a primary **Send** and a secondary **Send and mark done**. Both are disabled while the body is blank or a send is in flight. `r` focuses the text area when no field has focus.
- `client_key` is `crypto.randomUUID()`, made once per draft and kept until the server answers. A POST that fails at the network layer resends with the same key, so it cannot send twice. A new key is made after any answer.
- After `not_sent`, the draft stays in the box. After `unknown`, the draft stays and the button reads **Send again anyway**.
- Under the actions, the panel lists the email's replies (`api.replies` when the panel opens). On a `reply.status` event for the open email, it fetches them again, so other tabs stay current.
- `MailboxMenu` shows **Allow replies** for an `active` mailbox with `can_send === false`. It calls `onreconnect`.

- [ ] **Step 1: Write the failing tests** in `reply.spec.ts`:
  - `replyState`: no `mailbox_id` gives `no_mailbox`. A paused mailbox gives `inactive`. An active mailbox without send gives `reconnect`. An active mailbox with send gives `ok`.
  - `replyNotice`: one case per status and error, equal to `REPLY_COPY`.
- [ ] **Step 2: Run** `pnpm -C apps/web exec vitest run src/lib/inbox/reply.spec.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** `reply.ts`, the client calls and the event type, then `ReplyBox.svelte` and the panel and menu wiring with the `svelte-code-writer` skill. Use `Button` and the design tokens. The text area follows `SetupEditor.svelte`'s field style.
- [ ] **Step 4: Run** `pnpm -C apps/web exec vitest run` and `pnpm -C apps/web check`. Expected: PASS.
- [ ] **Step 5: Check in the browser** (`make lite` and `make web`) on the demo workspace. Tripfold has no mailbox, so the panel shows the `no_mailbox` line and no box. A real send is checked in Task 7.
- [ ] **Step 6: Commit** `Compose and send replies from the email panel`.

### Task 7: Final check

- [ ] **Step 1: Run** `make test` and `make lint`. Expected: all pass.
- [ ] **Step 2: Real Gmail, by hand** (needs the consent-screen scope from Task 2):
  - Connect a test Gmail and send it a mail from a second account.
  - Reply from Herald. In the second account, the reply sits in the same conversation, from the owner's address.
  - Answer it from the second account. Herald's notes for that new email show the owner's earlier reply in the thread.
  - Reconnect a mailbox with "send" unticked: the panel shows the reconnect line, and the API answers 409.
- [ ] **Step 3: Push the branch and open the PR** (`gh-help` first; base `main`).
