# Mail Connectors (Gmail First) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a business connect a real mailbox to its workspace, with Gmail as the first connector, and feed new inbox mail into the existing triage pipeline.

**Architecture:** A provider-neutral `MailConnector` protocol in `herald_server.connectors`, with a registry keyed by provider name. Gmail is one entry. A provider-neutral `Mailbox` table holds encrypted credentials, an opaque sync cursor and subscription state. One `sync_mailbox` job asks the mailbox's connector for changes since its cursor, stores new `Email` rows and the new cursor in one transaction, then queues `process_email` for each. Gmail push arrives through Pub/Sub at `/api/webhooks/{provider}`. A daily cron renews subscriptions, and a 15-minute cron queues catch-up syncs.

**Tech Stack:** FastAPI, SQLModel, arq + Redis, httpx (Gmail REST, no Google client library), cryptography (Fernet), PyJWT (Pub/Sub OIDC check), pytest with `httpx.MockTransport`.

**Spec:** There is no separate spec document. This plan implements the design in the "Herald Mail Intake" artifact (https://claude.ai/artifact/DuJkWXxmMerNWHajkt7fi7), changed in one way: the user asked for Gmail to be **one connector among several**. So the table, routes and job are provider-neutral, and nothing outside `connectors/gmail/` names Gmail. Read `docs/architecture.md` and `CLAUDE.md` before starting.

**Scope:** Backend only: models, connector interface, Gmail connector, API routes, webhook, worker jobs and docs. There are no web UI tasks. The Google Cloud setup is a runbook at the end, not code.

## Global Constraints

- Python 3.13, Ruff line length 100. Follow the existing module style: a module docstring, plain sync DB functions called with `asyncify`, and `Session(services.engine)`.
- **Provider-neutral outside `connectors/gmail/`.** Models, routes, `sync.py`, `mailboxes.py` and the worker never import from `connectors.gmail` and never branch on `provider == "gmail"`. They use `services.connectors[mailbox.provider]`.
- **Tenancy:** every query filters on `workspace_id`. The only exceptions are the webhook lookup by address and the two cron jobs, which are cross-tenant by design. Each exception carries a comment saying so.
- **Events:** `add_event` in the same transaction, commit, then `to_bus` and publish. New event type: `mailbox.status`.
- **Credentials never leave the server.** `MailboxOut` has no credential fields. Logs never print tokens, codes or `credentials_enc`.
- Gmail scope is exactly `https://www.googleapis.com/auth/gmail.readonly`.
- **Comment complex logic** (rule in `CLAUDE.md`): cursor handling, locking, signature checks, MIME parsing and dedupe each get a short comment explaining why.
- **No migrations yet.** `create_all` does not add columns to an existing table. After Task 2, delete `apps/server/herald-dev.db` (lite mode) or run `docker compose down -v` (Postgres).
- **Tests need no network, Docker or Redis.** Mock HTTP with `httpx.MockTransport` and use the inline queue.
- After changing `api/schemas.py`, run `make gen-api` and commit `apps/web/src/lib/api/schema.d.ts`.

## Review Focus

- **A notification arrives while that mailbox is syncing.** It must not be lost. The arq job takes a Redis lock; if the lock is held, it re-queues itself with a 10 s delay. Task 11 checks this by hand against real Redis.
- **Gmail returns 429 during a large backfill.** The job is retried after `retry_after` instead of failing, and the cursor is not moved. The test goes in Task 8, and the arq `Retry` mapping in Task 11.
- **The owner reconnects a mailbox that was `needs_reauth` or `disconnected`.** The existing row is reused and becomes `active` with new credentials. Its cursor is kept, so no mail is skipped. Test in Task 9.
- **One address is connected in two workspaces.** One push queues one sync for each workspace, and each stores its own `Email` row. Tests in Task 8 and Task 10.
- **Subscription renewal fails for one mailbox.** The others are still renewed. A revoked token marks only that mailbox `needs_reauth`. Test in Task 11.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `apps/server/src/herald_server/crypto.py` (new) | `SecretBox`: Fernet seal/open for credentials and OAuth state |
| `apps/server/src/herald_server/settings.py` | New settings (token key, Google client, Pub/Sub) |
| `apps/server/src/herald_server/models.py` | `MailboxStatus`, `Mailbox`; `Email.mailbox_id`, `Email.provider_message_id` |
| `apps/server/src/herald_server/connectors/__init__.py` (new) | `build_connectors(settings, http) -> dict[str, MailConnector]` |
| `apps/server/src/herald_server/connectors/base.py` (new) | `MailConnector` protocol, shared types, errors |
| `apps/server/src/herald_server/connectors/gmail/mime.py` (new) | Raw RFC 822 → sender, subject, plain-text body |
| `apps/server/src/herald_server/connectors/gmail/client.py` (new) | Thin Gmail and OAuth REST client over httpx |
| `apps/server/src/herald_server/connectors/gmail/push.py` (new) | Pub/Sub OIDC check and envelope decode |
| `apps/server/src/herald_server/connectors/gmail/connector.py` (new) | `GmailConnector`: implements `MailConnector` with the client |
| `apps/server/src/herald_server/mailboxes.py` (new) | Mailbox DB functions, connect, disconnect, renew |
| `apps/server/src/herald_server/sync.py` (new) | `sync_mailbox`: fetch changes, store emails and cursor |
| `apps/server/src/herald_server/queue.py` | `enqueue_sync` on both queues |
| `apps/server/src/herald_server/services.py` | `connectors`, `secrets`, `http` on `Services` |
| `apps/server/src/herald_server/events.py` | `MAILBOX_STATUS` |
| `apps/server/src/herald_server/api/routes/mailboxes.py` (new) | List, connect, sync, pause, resume, disconnect |
| `apps/server/src/herald_server/api/routes/oauth.py` (new) | OAuth callback for any provider |
| `apps/server/src/herald_server/api/routes/webhooks.py` (new) | Push webhook for any provider |
| `apps/server/src/herald_server/api/schemas.py` | `MailboxOut`, `ConnectOut` |
| `apps/server/src/herald_server/worker/main.py` | Sync job with lock, two cron jobs |
| `packages/core/src/herald_core/adapters.py` | Remove the unused `EmailSource` |
| `apps/server/tests/fake_connector.py` (new) | `FakeConnector` for tests |
| `docs/architecture.md`, `docs/decisions.md`, `.env.example` | Docs |

---

### Task 1: Settings, dependencies and `SecretBox`

**Files:**
- Modify: `apps/server/pyproject.toml` (add `"cryptography>=44"`, `"pyjwt[crypto]>=2.10"`)
- Modify: `apps/server/src/herald_server/settings.py`
- Modify: `.env.example`
- Create: `apps/server/src/herald_server/crypto.py`
- Test: `apps/server/tests/test_crypto.py`

**Interfaces:**
- Produces:
  - `class BadSecret(Exception)`
  - `class SecretBox: __init__(self, key: str)`, `seal(self, data: dict[str, Any]) -> str`, `open(self, token: str, *, max_age: int | None = None, now: int | None = None) -> dict[str, Any]`
  - New `Settings` fields, all defaulting to `None` unless shown: `token_key`, `public_api_url: str = "http://localhost:8000"`, `google_client_id`, `google_client_secret`, `gmail_topic`, `gmail_push_audience`, `gmail_push_service_account`.

- [ ] **Step 1: Write the failing tests**

```python
import time

from cryptography.fernet import Fernet
import pytest
from herald_server.crypto import BadSecret, SecretBox

KEY = Fernet.generate_key().decode()

def test_seal_and_open_round_trip():
    box = SecretBox(KEY)
    assert box.open(box.seal({"refresh_token": "r1"})) == {"refresh_token": "r1"}

def test_tampered_token_is_rejected():
    box = SecretBox(KEY)
    token = box.seal({"a": 1})
    with pytest.raises(BadSecret):
        box.open(token[:-4] + "AAAA")

def test_other_key_is_rejected():
    with pytest.raises(BadSecret):
        SecretBox(Fernet.generate_key().decode()).open(SecretBox(KEY).seal({"a": 1}))

def test_expired_token_is_rejected():
    box = SecretBox(KEY)
    token = box.seal({"a": 1})
    with pytest.raises(BadSecret):
        box.open(token, max_age=600, now=int(time.time()) + 601)
```

- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_crypto.py -v`. Expected: FAIL, `ModuleNotFoundError: herald_server.crypto`.
- [ ] **Step 3: Implement `SecretBox`.** JSON-encode, then use `Fernet.encrypt`. `open` uses `decrypt_at_time(token, max_age, now)` when `now` is given, otherwise `decrypt(token, ttl=max_age)`. Map `InvalidToken` and JSON errors to `BadSecret`. Add the settings and their comments: `token_key` is a Fernet key from `Fernet.generate_key()`, and `gmail_topic` looks like `projects/<project>/topics/herald-gmail`. Add the same keys to `.env.example`, empty, with one comment line each.
- [ ] **Step 4: Run** `uv sync && uv run pytest apps/server/tests/test_crypto.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(server): add SecretBox and mail connector settings`.

---

### Task 2: `Mailbox` model and `Email` source columns

**Files:**
- Modify: `apps/server/src/herald_server/models.py`
- Test: `apps/server/tests/test_models.py`

**Interfaces:**
- Produces:

```python
class MailboxStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"

class Mailbox(SQLModel, table=True):
    # unique (workspace_id, provider, email_address): a reconnect updates the row.
    id: str                                   # _id()
    workspace_id: str                         # FK workspace.id, index
    provider: str                             # registry key, e.g. "gmail"
    email_address: str                        # stored lower-case, index
    status: MailboxStatus                     # index
    credentials_enc: str | None               # SecretBox token; None once disconnected
    cursor: str | None                        # opaque to everything but the connector
    provider_state: dict[str, Any]            # JSON, default {}; connector-owned
    subscription_expires_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime                      # _now()
```

  On `Email`, add `mailbox_id: str | None` (FK `mailbox.id`, index) and `provider_message_id: str | None`, with `__table_args__ = (UniqueConstraint("mailbox_id", "provider_message_id"),)`. Both stay `None` for test-box emails. NULLs never collide, in SQLite or Postgres.

- [ ] **Step 1: Write the failing tests** (an in-memory SQLite engine with `create_all`):
  - `test_same_message_twice_in_one_mailbox_is_rejected`: the second insert raises `IntegrityError`.
  - `test_same_message_id_in_two_mailboxes_is_allowed`
  - `test_test_box_emails_without_mailbox_do_not_collide`: two `Email` rows with both columns `None` commit.
  - `test_one_address_per_provider_per_workspace`: a duplicate `(workspace_id, "gmail", "a@x.com")` raises `IntegrityError`, while the same address in another workspace commits.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_models.py -v`. Expected: FAIL, `ImportError: Mailbox`.
- [ ] **Step 3: Implement** the model and columns above.
- [ ] **Step 4: Run** `uv run pytest apps/server -v`. Expected: all PASS, including the existing API tests.
- [ ] **Step 5: Commit** `feat(server): add Mailbox model and email source columns`.

---

### Task 3: Connector contract, registry and services wiring

**Files:**
- Create: `apps/server/src/herald_server/connectors/__init__.py`, `connectors/base.py`, `connectors/gmail/__init__.py`
- Create: `apps/server/tests/fake_connector.py`
- Modify: `services.py`, `api/main.py` (close `services.http`), `worker/main.py` (`shutdown` closes `services.http`), `events.py` (add `MAILBOX_STATUS = "mailbox.status"`)
- Modify: `packages/core/src/herald_core/adapters.py`: delete `EmailSource` and change the module docstring to "Plug-in points that each deployment implements: where alerts go." Nothing imports it; check with `grep -rn EmailSource packages apps`.
- Modify: `apps/server/tests/conftest.py`
- Test: `apps/server/tests/test_connectors.py`

**Interfaces:**
- Produces, in `connectors/base.py`, the contract every provider implements:

```python
class InboundMessage(BaseModel):
    provider_message_id: str
    sender: str            # bare address, lower-case
    subject: str
    body: str              # plain text, at most 50_000 chars
    received_at: datetime

class FetchResult(BaseModel):
    messages: list[InboundMessage]
    cursor: str            # where the next fetch starts

class ConnectedAccount(BaseModel):
    email_address: str     # lower-case
    credentials: dict[str, str]

class Subscription(BaseModel):
    expires_at: datetime | None
    provider_state: dict[str, Any]

class PushNotice(BaseModel):
    email_address: str     # lower-case

class AuthRevoked(Exception): ...          # owner revoked access / password changed
class MissingRefreshToken(Exception): ...  # OAuth returned no long-lived credential
class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None: ...
class PushRejected(Exception): ...         # bad or missing signature -> 401
class PushIgnored(Exception): ...          # well-signed but unusable body -> ack with 204

class MailConnector(Protocol):
    provider: str
    def authorization_url(self, state: str) -> str: ...
    async def complete_authorization(self, code: str) -> ConnectedAccount: ...
    async def subscribe(self, credentials: dict[str, str], provider_state: dict[str, Any]) -> Subscription: ...
    async def unsubscribe(self, credentials: dict[str, str], provider_state: dict[str, Any]) -> None: ...
    async def fetch_changes(self, credentials: dict[str, str], cursor: str | None) -> FetchResult: ...
    async def revoke(self, credentials: dict[str, str]) -> None: ...
    async def parse_push(self, headers: Mapping[str, str], body: bytes) -> PushNotice: ...
```

  Contract notes to copy into the protocol's docstring: `fetch_changes(cursor=None)` means "first sync: recent mail plus a fresh cursor". A connector that finds its cursor too old falls back to the same path itself, and never raises for an expired cursor. A provider without push raises `PushIgnored` from `parse_push`.

- Produces `Services` fields: `http: httpx.AsyncClient`, `secrets: SecretBox | None` (None when `token_key` is unset), and `connectors: dict[str, MailConnector]`.
- Produces `build_connectors(settings: Settings, http: httpx.AsyncClient) -> dict[str, MailConnector]`. It returns `{"gmail": GmailConnector(...)}` only when `token_key`, `google_client_id`, `google_client_secret` and `gmail_topic` are all set, and `{}` otherwise. Task 6 fills in `GmailConnector`; until then this task imports nothing from `connectors.gmail`, and the Gmail branch is added in Task 6.
- Produces `tests/fake_connector.py: class FakeConnector`, with `provider = "fake"`:
  - `queue: list[InboundMessage]` is what the next `fetch_changes` returns, after which the list is cleared.
  - `raise_on_fetch: Exception | None`.
  - `calls: list[str]` records the method names called.
  - `account = ConnectedAccount(email_address="owner@shop.in", credentials={"token": "t"})`.
  - The cursor is `str(int(cursor or 0) + 1)`.
  - `parse_push` reads JSON `{"email": ...}` and raises `PushRejected` unless the header `x-fake-auth: ok` is present.
- `conftest.py`: the `settings` fixture adds `token_key=Fernet.generate_key().decode()`. New fixture `fake_connector(app)` sets `app.state.services.connectors["fake"] = FakeConnector()` and returns it.

- [ ] **Step 1: Write the failing tests:** `test_no_connectors_without_google_settings` (`build_connectors(Settings(...defaults...), http) == {}`) and `test_services_have_secrets_when_key_set(app)` (`app.state.services.secrets is not None`).
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_connectors.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement** the types, protocol, registry, `Services` fields and fake. Build `httpx.AsyncClient(timeout=20)` in `build_services`.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(server): add provider-neutral MailConnector contract and registry`.

---

### Task 4: Gmail MIME parsing

**Files:**
- Create: `apps/server/src/herald_server/connectors/gmail/mime.py`
- Test: `apps/server/tests/connectors/test_gmail_mime.py` (build fixtures with `email.message.EmailMessage`, then base64url-encode)

**Interfaces:**
- Produces `BODY_LIMIT = 50_000`, `class ParsedMessage(NamedTuple): sender: str; subject: str; body: str`, and `parse_raw_message(raw: str) -> ParsedMessage`.
  - `raw` is Gmail's base64url `raw` field, which may lack padding.
  - Parse with `email.message_from_bytes(..., policy=email.policy.default)`.
  - Take the body from `get_body(preferencelist=("plain", "html"))`. HTML is reduced to text with `html.parser` (stdlib), dropping tags and `script` and `style` content.
  - The sender comes from `email.utils.parseaddr` and is lower-cased.
  - A missing subject becomes `""`. A missing body becomes `""`.
  - The body is cut to `BODY_LIMIT`.

- [ ] **Step 1: Write the failing tests:**
  - `test_plain_text_message`: sender `"Riya <Riya@Customer.in>"` gives `"riya@customer.in"`; subject and body come out unchanged.
  - `test_multipart_alternative_prefers_plain`
  - `test_html_only_message_becomes_text`: `<p>Where is <b>my order</b>?</p><style>p{}</style>` gives a body containing `"Where is my order?"` and no `<` or `p{`.
  - `test_nested_multipart_mixed_with_attachment`: the body is the text part, and the attachment bytes are not in it.
  - `test_non_utf8_charset`: an `iso-8859-1` body containing `"café"` decodes to `"café"`.
  - `test_unpadded_base64url_is_accepted`
  - `test_encoded_word_subject`: `=?UTF-8?B?...?=` decodes.
  - `test_long_body_is_cut_to_limit`: `len(body) == 50_000`.
  - `test_missing_subject_and_body`: gives `("x@y.com", "", "")`.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/connectors/test_gmail_mime.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement `parse_raw_message`.** Restore padding with `raw + "=" * (-len(raw) % 4)` before `base64.urlsafe_b64decode`, and comment why.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(gmail): parse raw messages into sender, subject and text body`.

---

### Task 5: Gmail REST client

**Files:**
- Create: `apps/server/src/herald_server/connectors/gmail/client.py`
- Test: `apps/server/tests/connectors/test_gmail_client.py`

**Interfaces:**
- Consumes: `AuthRevoked` and `RateLimited` from `connectors/base.py`.
- Produces these constants:

```python
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
```

- Produces these errors and result types: `class HistoryExpired(Exception)` and `class MessageGone(Exception)`, plus `TokenSet(access_token: str, refresh_token: str | None)`, `Profile(email_address: str, history_id: str)`, `WatchResult(history_id: str, expiration: datetime)`, `HistoryPage(message_ids: list[str], history_id: str, next_page_token: str | None)`, `MessagePage(message_ids: list[str], next_page_token: str | None)` and `RawMessage(id: str, raw: str, label_ids: list[str], internal_date: datetime)`, all as NamedTuples.
- Produces `class GmailClient`, built with `__init__(self, http: httpx.AsyncClient, client_id: str, client_secret: str, redirect_uri: str)`:
  - `exchange_code(code) -> TokenSet`
  - `refresh(refresh_token) -> str` (the access token)
  - `revoke(token) -> None`
  - `get_profile(access) -> Profile`
  - `watch(access, topic: str) -> WatchResult`: the body is `{"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "include"}`, and `expiration` is milliseconds since 1970 → UTC datetime.
  - `stop(access) -> None`
  - `list_history(access, start_history_id, page_token=None) -> HistoryPage`: params `historyTypes=messageAdded`, `labelId=INBOX`, `maxResults=500`. Message ids come from `history[].messagesAdded[].message.id`, keeping only messages whose `labelIds` include `"INBOX"` and exclude `"DRAFT"` and `"SENT"`.
  - `list_messages(access, q, max_results, page_token=None) -> MessagePage`
  - `get_raw_message(access, message_id) -> RawMessage`: `format=raw`.
- Error mapping, applied to every call:
  - `400` with `{"error": "invalid_grant"}` from `TOKEN_URL` → `AuthRevoked`.
  - `401` from `API` → `AuthRevoked`.
  - `429`, or `403` whose `error.errors[].reason` is `rateLimitExceeded` or `userRateLimitExceeded` → `RateLimited(retry_after)`. `retry_after` is the `Retry-After` header, or 30.
  - `404` from `list_history` → `HistoryExpired`.
  - `404` from `get_raw_message` → `MessageGone`.
  - Anything else → `response.raise_for_status()`.

- [ ] **Step 1: Write the failing tests.** Each builds `httpx.AsyncClient(transport=httpx.MockTransport(handler))` and checks the request in `handler`:
  - `test_refresh_invalid_grant_raises_auth_revoked`
  - `test_list_history_404_raises_history_expired`
  - `test_list_history_keeps_inbox_and_drops_sent_and_drafts`: three records labelled `["INBOX"]`, `["SENT"]` and `["DRAFT", "INBOX"]` give `["m1"]`.
  - `test_list_history_sends_cursor_and_filters`: the request query has `startHistoryId=100`, `historyTypes=messageAdded` and `labelId=INBOX`.
  - `test_watch_sends_topic_and_inbox_filter`: checks the JSON body equals the dict above, and that expiration `"1762790400000"` becomes `datetime(2025, 11, 10, 16, 0, tzinfo=UTC)`.
  - `test_429_raises_rate_limited_with_retry_after`: header `Retry-After: 12` gives `retry_after == 12`.
  - `test_403_user_rate_limit_raises_rate_limited`
  - `test_get_raw_message_404_raises_message_gone`
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/connectors/test_gmail_client.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement `GmailClient`.** Use one private `_request(method, url, *, access=None, **kw) -> dict` for the error mapping.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(gmail): add REST client for OAuth, watch, history and messages`.

---

### Task 6: `GmailConnector`

**Files:**
- Create: `apps/server/src/herald_server/connectors/gmail/connector.py`
- Modify: `apps/server/src/herald_server/connectors/__init__.py` (add the Gmail branch to `build_connectors`)
- Test: `apps/server/tests/connectors/test_gmail_connector.py`

**Interfaces:**
- Consumes: `GmailClient` and its errors (Task 5), `parse_raw_message` (Task 4), and the `connectors/base.py` types (Task 3).
- Produces `BACKFILL_QUERY = "in:inbox newer_than:2d"` and `BACKFILL_LIMIT = 50`.
- Produces `class GmailConnector(MailConnector)`, with `provider = "gmail"`, built as `__init__(self, client: GmailClient, *, client_id: str, topic: str, push_audience: str | None, push_service_account: str | None, signing_key_for: Callable[[str], Any] | None = None)`. Task 7 adds `parse_push` and uses `signing_key_for`.
  - `authorization_url(state)`: `AUTH_URL` with `client_id`, `redirect_uri`, `response_type=code`, `scope=SCOPE`, `access_type=offline`, `prompt=consent`, `include_granted_scopes=true` and `state`.
  - `complete_authorization(code)`: `exchange_code`, raising `MissingRefreshToken` if `refresh_token` is None. Then `get_profile` gives the address. Returns `ConnectedAccount(email_address=lower, credentials={"refresh_token": ...})`.
  - `subscribe`: refresh, `watch`, return `Subscription(expires_at=watch.expiration, provider_state={})`.
  - `unsubscribe`: refresh, `stop`.
  - `revoke`: `client.revoke(refresh_token)`.
  - `fetch_changes(credentials, cursor)`:
    - **cursor None, or `HistoryExpired`:**
      1. Call `get_profile` **first** and use its `history_id` as the new cursor. Mail that arrives during the backfill is then picked up by the next history sync, and dedupe removes overlaps. Comment this.
      2. `list_messages(BACKFILL_QUERY, BACKFILL_LIMIT)`, first page only.
    - **Otherwise:**
      1. Follow `list_history` `next_page_token` until it is None, collecting ids in order without duplicates.
      2. The new cursor is the **last page's** `history_id`.
    - **For each id:**
      - Call `get_raw_message`. Skip on `MessageGone`.
      - Skip unless `"INBOX"` is in its `label_ids`.
      - Run `parse_raw_message`, and use `internal_date` as `received_at`.
    - Refresh the access token once per call.

- [ ] **Step 1: Write the failing tests.** Use a `MockTransport` handler that routes on URL path and serves canned JSON, with raw messages built as in Task 4:
  - `test_authorization_url_requests_offline_readonly_access`: parse the query and assert `scope`, `access_type=offline`, `prompt=consent` and `state`.
  - `test_complete_authorization_without_refresh_token_raises`
  - `test_complete_authorization_returns_lowercase_address`
  - `test_first_fetch_backfills_and_takes_cursor_from_profile`: `cursor=None` with a profile `historyId` of `"500"` gives `result.cursor == "500"` and two messages, and the profile request comes before the list request (record the order in the handler).
  - `test_fetch_follows_every_history_page`: two pages (`nextPageToken` `"p2"`) return messages from both, and `cursor` equals page 2's `historyId`.
  - `test_expired_cursor_falls_back_to_backfill`: `history` returns 404, and the result is the backfill messages with the profile cursor. No exception.
  - `test_message_deleted_between_list_and_get_is_skipped`
  - `test_duplicate_ids_across_pages_fetched_once`
  - `test_build_connectors_includes_gmail_when_configured`: with all four settings set, `"gmail"` is in the registry.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/connectors/test_gmail_connector.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement `GmailConnector`** and the registry branch. The redirect URI is `f"{settings.public_api_url}/api/oauth/gmail/callback"`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(gmail): add GmailConnector with history sync and backfill`.

---

### Task 7: Pub/Sub push verification

**Files:**
- Create: `apps/server/src/herald_server/connectors/gmail/push.py`
- Modify: `connectors/gmail/connector.py` (`parse_push`)
- Test: `apps/server/tests/connectors/test_gmail_push.py`

**Interfaces:**
- Produces `GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}` and `GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"`.
- Produces `verify_push_token(token: str, *, audience: str, service_account: str, signing_key_for: Callable[[str], Any]) -> None`:
  - Decode with `jwt.decode(token, key, algorithms=["RS256"], audience=audience)`.
  - Then require `iss` to be in `GOOGLE_ISSUERS`, `email == service_account` and `email_verified is True`.
  - Any failure raises `PushRejected`.
- Produces `decode_envelope(body: bytes) -> PushNotice`:
  - Read JSON `message.data`, standard base64 as Pub/Sub sends it, which contains JSON `{"emailAddress", "historyId"}`.
  - Lower-case the address.
  - Any malformed part raises `PushIgnored`.
- `GmailConnector.parse_push(headers, body)`:
  - If `push_audience` or `push_service_account` is unset, raise `PushRejected`. Never accept unsigned pushes; comment this.
  - Take the bearer token from `authorization`. A missing header raises `PushRejected`.
  - Run `verify_push_token`. The default `signing_key_for` is a cached `jwt.PyJWKClient(GOOGLE_CERTS_URL).get_signing_key_from_jwt(token).key`, called through `asyncify` because it does blocking HTTP.
  - Then `decode_envelope`.

- [ ] **Step 1: Write the failing tests.** Generate an RSA key with `cryptography`, sign tokens with `jwt.encode(..., algorithm="RS256")`, and pass `signing_key_for=lambda _: public_key`:
  - `test_valid_push_returns_address`: `"Owner@Shop.in"` gives `"owner@shop.in"`.
  - `test_wrong_audience_is_rejected`
  - `test_wrong_service_account_is_rejected`
  - `test_unverified_email_is_rejected`
  - `test_token_signed_by_other_key_is_rejected`
  - `test_missing_authorization_header_is_rejected`
  - `test_push_rejected_when_audience_not_configured`
  - `test_malformed_data_is_ignored`: valid JWT, `data` not base64 → `PushIgnored`.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/connectors/test_gmail_push.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement** the functions and `parse_push` above.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(gmail): verify Pub/Sub push tokens and decode notifications`.

---

### Task 8: Mailbox service, `sync_mailbox` and `enqueue_sync`

**Files:**
- Create: `apps/server/src/herald_server/mailboxes.py`, `apps/server/src/herald_server/sync.py`
- Modify: `apps/server/src/herald_server/queue.py`
- Test: `apps/server/tests/test_sync.py`

**Interfaces:**
- Consumes: `Mailbox`, `MailboxStatus` (Task 2), `MailConnector` and its errors, `services.connectors`, `services.secrets` (Task 3), and `MAILBOX_STATUS`.
- Produces in `mailboxes.py` (plain sync functions unless marked async):
  - `get_mailbox(services, mailbox_id) -> Mailbox | None`
  - `set_status(services, mailbox_id, status: MailboxStatus) -> BusEvent`: saves, stages `mailbox.status` with `{"mailbox_id", "email_address", "status"}`, commits and returns the event to publish.
  - `active_mailbox_ids_for_address(services, provider: str, email_address: str) -> list[str]`: cross-tenant, for the webhook.
  - `active_mailbox_ids(services) -> list[str]`: cross-tenant, for cron.
- Produces in `sync.py`: `async def sync_mailbox(services: Services, mailbox_id: str) -> list[str]`, which returns the new email ids.
  1. Load the mailbox. Return `[]` unless it is `ACTIVE`, has `credentials_enc`, and its provider is in `services.connectors`. Log the reason.
  2. `credentials = services.secrets.open(mailbox.credentials_enc)`.
  3. `result = await connector.fetch_changes(credentials, mailbox.cursor)`. `AuthRevoked` → `set_status(NEEDS_REAUTH)`, publish, return `[]`. `RateLimited` propagates and the cursor does not move.
  4. `_store(services, mailbox_id, result) -> tuple[list[str], list[BusEvent]]` runs in one transaction:
     - Skip messages whose `(mailbox_id, provider_message_id)` already exists.
     - Insert each `Email(workspace_id=mailbox.workspace_id, mailbox_id, provider_message_id, sender, subject, body, received_at)` and stage an `email.received` event with the same data as `api/routes/emails.py:_store_received`.
     - Set `mailbox.cursor = result.cursor` and `last_synced_at = now`.
     - Commit.
     - On `IntegrityError`, roll back and return `([], [])`. A concurrent sync stored them, and the comment must say this.
  5. Publish the events and return the ids.
- Produces on `JobQueue`: `async def enqueue_sync(self, mailbox_id: str) -> None`.
  - `ArqQueue` enqueues `SYNC_MAILBOX_JOB = "sync_mailbox"`.
  - `InlineQueue` runs `sync_mailbox` under a per-mailbox `asyncio.Lock`, then calls `enqueue_email` for each returned id, tracked in `_tasks` so `drain()` waits for it.
  - `drain()` must loop until both syncs and the triage tasks they spawn are finished; the existing `while self._tasks` loop already does this.

- [ ] **Step 1: Write the failing tests.** Use the `app` and `fake_connector` fixtures and insert `Mailbox` rows directly, with `credentials_enc=services.secrets.seal({"token": "t"})`:
  - `test_sync_stores_new_mail_and_runs_triage`: queue two messages, `enqueue_sync`, `drain`. Both emails exist with `mailbox_id` set and a status other than `new`, and the mailbox `cursor == "1"`.
  - `test_sync_twice_does_not_duplicate`: queue the same message again, sync. There is still one email, and `cursor == "2"`.
  - `test_auth_revoked_marks_needs_reauth`: `raise_on_fetch = AuthRevoked()` → status `needs_reauth`, and a `mailbox.status` event is in the `event` table.
  - `test_rate_limited_keeps_cursor`: calling `sync_mailbox` directly raises `RateLimited`, and the cursor is unchanged.
  - `test_paused_mailbox_is_not_fetched`: `"fetch_changes" not in fake.calls`.
  - `test_same_address_in_two_workspaces_each_get_a_copy`: two mailboxes with the same address in two workspaces, one message each. Each workspace lists one email, and `test_workspaces_are_isolated` still passes.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_sync.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement** `mailboxes.py`, `sync.py` and `enqueue_sync` on both queues.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(server): sync mailboxes through any connector into the pipeline`.

---

### Task 9: Mailbox routes and the OAuth callback

**Files:**
- Create: `apps/server/src/herald_server/api/routes/mailboxes.py`, `api/routes/oauth.py`
- Modify: `api/schemas.py`, `api/main.py` (include the routers), `api/deps.py` (`SecretsDep`, `ConnectorDep`), `mailboxes.py` (add the connect functions)
- Test: `apps/server/tests/test_mailboxes_api.py`

**Interfaces:**
- Consumes everything from Tasks 2–8.
- Produces schemas:
  - `MailboxOut` with `id`, `workspace_id`, `provider`, `email_address`, `status`, `subscription_expires_at`, `last_synced_at` and `created_at`. It has no credentials, cursor or `provider_state`.
  - `ConnectOut(authorization_url: str)`.
- Produces deps:
  - `SecretsDep` returns 503 `"Mail connectors need HERALD_TOKEN_KEY"` when `services.secrets` is None.
  - `ConnectorDep` reads the `provider` path param and returns 404 `"Mail provider not available"` when it is not in the registry.
- Produces in `mailboxes.py`:
  - `upsert_connected(services, workspace_id, provider, account: ConnectedAccount) -> Mailbox` reuses the `(workspace_id, provider, email_address)` row. It sets new `credentials_enc` and `status=ACTIVE` and **keeps `cursor`**.
  - `async def connect_mailbox(services, workspace_id, connector, code) -> Mailbox`:
    1. Call `complete_authorization`, then `upsert_connected`.
    2. Call `subscribe` and save `subscription_expires_at` and `provider_state`. A subscribe failure is logged and the mailbox stays `ACTIVE`; the cron retries it, and catch-up syncs cover the gap until then.
    3. Stage and publish `mailbox.status`.
  - `async def disconnect_mailbox(services, mailbox) -> Mailbox`: best-effort `unsubscribe` and `revoke` (errors are logged and ignored), set `credentials_enc=None` and `status=DISCONNECTED`, then publish. Emails are kept.
- Routes on `/api/workspaces/{workspace_id}/mailboxes`. Each one loads the mailbox filtered by `workspace_id` and returns 404 for another workspace's mailbox.

| Method and path | Result |
| --- | --- |
| `GET ""` | `list[MailboxOut]`, newest first |
| `POST "/{provider}/connect"` | `ConnectOut`. `state = secrets.seal({"workspace_id", "provider"})` |
| `POST "/{mailbox_id}/sync"` | 202 and `enqueue_sync`. 409 unless `ACTIVE` |
| `POST "/{mailbox_id}/pause"` | `ACTIVE` → `PAUSED`, best-effort `unsubscribe`. 409 otherwise |
| `POST "/{mailbox_id}/resume"` | `PAUSED` → `ACTIVE`, `subscribe`, `enqueue_sync`. 409 otherwise |
| `DELETE "/{mailbox_id}"` | `disconnect_mailbox`, returns `MailboxOut` |

- Route `GET /api/oauth/{provider}/callback?code=&state=&error=` always answers `303` to `settings.web_url`:
  - `error` param → `?mailbox_error=access_denied`.
  - `state` that fails `secrets.open(state, max_age=600)` → `?mailbox_error=invalid_state`.
  - A state provider that differs from the path provider, or an unknown workspace → `?mailbox_error=invalid_state`.
  - `MissingRefreshToken` → `?mailbox_error=no_refresh_token`.
  - Success → `connect_mailbox`, `enqueue_sync`, then `?mailbox_connected=<mailbox_id>`.

- [ ] **Step 1: Write the failing tests** (`fake_connector` fixture, provider `"fake"`):
  - `test_connect_returns_signed_state_for_workspace`: the `state` query param opens to `{"workspace_id": ws, "provider": "fake"}`.
  - `test_connect_unknown_provider_is_404`
  - `test_callback_creates_active_mailbox_and_backfills`: queue one message, call the callback with a valid state, `drain`. Response 303 with `mailbox_connected=`; one `active` mailbox; one email; `fake.calls` contains `"subscribe"`.
  - `test_callback_with_forged_state_is_rejected`: `state="x"` → 303 with `mailbox_error=invalid_state`, and no mailbox.
  - `test_callback_with_expired_state_is_rejected`: get a state from `connect`, then `monkeypatch.setattr("cryptography.fernet.time.time", lambda: real_now + 601)` before calling the callback. The callback calls `open(state, max_age=600)` without `now`, so Fernet reads the patched clock.
  - `test_callback_access_denied`
  - `test_callback_without_refresh_token`: the fake raises `MissingRefreshToken` → `mailbox_error=no_refresh_token`.
  - `test_reconnect_reuses_row_and_keeps_cursor`: set the mailbox to `needs_reauth` with `cursor="7"`, run the callback again. There is one row, `active`, `cursor == "7"`.
  - `test_mailbox_out_has_no_credentials`: `"credentials_enc" not in body` and `"cursor" not in body`.
  - `test_other_workspace_cannot_see_or_disconnect_mailbox`: 404s.
  - `test_pause_resume_and_disconnect`: the status walk, 409 on `pause` twice, and after `DELETE` the status is `disconnected` and `"revoke" in fake.calls`.
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_mailboxes_api.py -v`. Expected: FAIL (404s, routes missing).
- [ ] **Step 3: Implement** the deps, service functions, routes and callback.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5: Run** `make gen-api`. Expected: `schema.d.ts` gains `MailboxOut` and `ConnectOut`.
- [ ] **Step 6: Commit** `feat(api): connect, list, pause and disconnect mailboxes`.

---

### Task 10: Push webhook

**Files:**
- Create: `apps/server/src/herald_server/api/routes/webhooks.py`
- Modify: `api/main.py`
- Test: `apps/server/tests/test_webhooks.py`

**Interfaces:**
- Consumes: `connector.parse_push`, `PushRejected`, `PushIgnored` and `active_mailbox_ids_for_address`.
- Produces route `POST /api/webhooks/{provider}`:
  - Unknown provider → 404.
  - `PushRejected` → 401.
  - `PushIgnored` → 204.
  - Otherwise, `enqueue_sync` for every active mailbox with that provider and address, then 204. Unknown or inactive addresses also get 204, so Pub/Sub stops retrying; comment this.
  - The route never calls the mail provider directly.

- [ ] **Step 1: Write the failing tests:**
  - `test_push_queues_sync_for_matching_mailbox`: a queued message is stored after `drain`.
  - `test_push_without_auth_is_401`
  - `test_push_for_unknown_address_is_acked`: 204, no emails.
  - `test_push_for_paused_mailbox_is_acked_without_sync`
  - `test_push_syncs_every_workspace_with_that_address`: two workspaces, one email each.
  - `test_push_to_unknown_provider_is_404`
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_webhooks.py -v`. Expected: FAIL (404).
- [ ] **Step 3: Implement** the route.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(api): accept mail push notifications per provider`.

---

### Task 11: Worker sync job, lock and cron jobs

**Files:**
- Modify: `apps/server/src/herald_server/worker/main.py`, `mailboxes.py`
- Modify: `apps/server/tests/fake_connector.py` (add `raise_on_subscribe: Exception | None`)
- Test: `apps/server/tests/test_renewals.py`

**Interfaces:**
- Produces `async def renew_subscriptions(services) -> int` in `mailboxes.py`, cross-tenant. For every `ACTIVE` mailbox whose provider is registered, it calls `subscribe` and saves `subscription_expires_at` and `provider_state`. `AuthRevoked` → `set_status(NEEDS_REAUTH)` and publish. Any other exception is logged, and the loop goes on to the next mailbox. Returns the number renewed.
- In `worker/main.py`:
  - `sync_mailbox_job(ctx, mailbox_id)`:
    1. Take `lock = ctx["redis"].lock(f"herald:sync:{mailbox_id}", timeout=300)`.
    2. If `not await lock.acquire(blocking=False)`, enqueue `SYNC_MAILBOX_JOB` again with `_job_id=f"sync-again:{mailbox_id}"` and `_defer_by=10`, then return. The comment must explain that a sync already running may have read history before this change arrived, so a rerun is needed, and that the fixed job id collapses a burst into one rerun.
    3. Otherwise run `sync_mailbox`. Map `RateLimited` to `raise Retry(defer=e.retry_after)`. Release the lock in `finally`.
    4. Call `ctx["redis"].enqueue_job(PROCESS_EMAIL_JOB, id)` for each new id.
    5. Register it as `func(sync_mailbox_job, name=SYNC_MAILBOX_JOB, keep_result=0, max_tries=5)`. `keep_result=0` matters: with a stored result, arq refuses to enqueue the same `_job_id` again for an hour. Comment this.
  - `cron_jobs`:
    - `cron(renew_subscriptions_job, hour={3}, minute={0})`.
    - `cron(catch_up_syncs_job, minute={0, 15, 30, 45})`, which enqueues `SYNC_MAILBOX_JOB` for each `active_mailbox_ids(services)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_renew_updates_expiry`
  - `test_renew_marks_revoked_mailbox_and_continues`: one fake raises `AuthRevoked` on `subscribe` (add `raise_on_subscribe` to `FakeConnector`). That mailbox becomes `needs_reauth`, the other's expiry is updated, and the return value is 1.
  - `test_renew_skips_paused_and_disconnected`
- [ ] **Step 2: Run** `uv run pytest apps/server/tests/test_renewals.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement** `renew_subscriptions` and the worker changes.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5: Check the lock by hand.**
  1. Run `make infra`, then `make worker`.
  2. In a Python shell, add a sleep to `FakeConnector.fetch_changes` and register it on a scratch worker.
  3. Enqueue `sync_mailbox` twice for one mailbox, 1 s apart.

  Expected: the worker log shows one sync, one `sync-again` rerun about 10 s later, and no `IntegrityError`. Record the result in the PR description.
- [ ] **Step 6: Commit** `feat(worker): lock per-mailbox syncs, renew subscriptions, catch-up syncs`.

---

### Task 12: Docs and final check

**Files:**
- Modify: `docs/architecture.md`
  - Plug-in table: replace the `EmailSource` row with `MailConnector | herald_server.connectors | GmailConnector; FakeConnector in tests`.
  - Add a "Mail connectors" section: the mailbox flow in a mermaid `sequenceDiagram` (push → webhook → `sync_mailbox` → `process_email`), the `MailboxStatus` table, and the cron jobs.
  - Configuration table: the new settings.
  - "Not built yet": remove the real-inbox item. Add an Outlook connector and filter-based watch labels.
- Modify: `docs/decisions.md`: add a 2026-11-03 row: "**Mail connectors are provider-neutral; Gmail is the first.** One `Mailbox` table and one sync job serve every provider; provider details live in the connector and its opaque cursor." Why: Outlook and IMAP can be added later without changing tables or routes.
- Modify: `CLAUDE.md`: under the "Swappable backends" invariant, add `MailConnector` (`gmail`, `FakeConnector` in tests). Add one invariant: "Only code in `connectors/<provider>/` knows a provider; the cursor and `provider_state` are opaque elsewhere."

- [ ] **Step 1: Make the doc edits** above.
- [ ] **Step 2: Run** `make lint && make test`. Expected: no Ruff errors, and all pytest and vitest tests pass.
- [ ] **Step 3: Run** `uv run pytest -q 2>&1 | tail -1`. Expected: `N passed`, with no warnings about unclosed `httpx.AsyncClient`.
- [ ] **Step 4: Commit** `docs: describe mail connectors and the Gmail connector`.

---

## Runbook: Google Cloud setup (manual, once)

1. In a Google Cloud project, enable the **Gmail API** and **Cloud Pub/Sub API**.
2. Configure the OAuth consent screen as External, add the scope `gmail.readonly`, and add test users. While it is in Testing, refresh tokens expire after 7 days and only 100 test users can connect.
3. Create a Web OAuth client. Its redirect URI is `{HERALD_PUBLIC_API_URL}/api/oauth/gmail/callback`. Put the client id and secret in `.env`.
4. Create the topic `herald-gmail`. Grant `gmail-api-push@system.gserviceaccount.com` the **Pub/Sub Publisher** role on it. Set `HERALD_GMAIL_TOPIC=projects/<project>/topics/herald-gmail`.
5. Create a service account for push auth. Create a **push** subscription to `{HERALD_PUBLIC_API_URL}/api/webhooks/gmail` with authentication on, using that service account and an audience string. Set `HERALD_GMAIL_PUSH_SERVICE_ACCOUNT` and `HERALD_GMAIL_PUSH_AUDIENCE` to match.
6. Set `HERALD_TOKEN_KEY` to the output of `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Losing this key means every mailbox has to reconnect.
7. For local push testing, expose the API with a tunnel and use the tunnel URL as `HERALD_PUBLIC_API_URL`. Without a tunnel, use `POST /mailboxes/{id}/sync` or wait for the 15-minute catch-up.
8. Before a public launch, apply for restricted-scope verification and the CASA security assessment.
