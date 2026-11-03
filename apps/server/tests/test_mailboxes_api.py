"""Connecting, listing, pausing and disconnecting mailboxes, and the OAuth callback."""

import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from sqlmodel import Session, select

from herald_server.connectors.base import AuthRevoked, InboundMessage, MissingRefreshToken
from herald_server.models import Email, Mailbox, MailboxStatus

WEB_URL = "http://localhost:5173"


async def demo_workspace(client) -> str:
    response = await client.post("/api/workspaces/demo")
    assert response.status_code == 201
    return response.json()["id"]


def message(provider_message_id: str) -> InboundMessage:
    return InboundMessage(
        provider_message_id=provider_message_id,
        sender="riya@customer.in",
        subject="Product questions",
        body="Does the cabin bag fit Indigo?",
        received_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
    )


def mailboxes_of(app, workspace_id: str) -> list[Mailbox]:
    with Session(app.state.services.engine) as session:
        return list(session.exec(select(Mailbox).where(Mailbox.workspace_id == workspace_id)).all())


def emails_of(app, workspace_id: str) -> list[Email]:
    with Session(app.state.services.engine) as session:
        return list(session.exec(select(Email).where(Email.workspace_id == workspace_id)).all())


async def start_connect(client, workspace_id: str) -> str:
    """POST connect and return the signed state from the authorization URL."""
    response = await client.post(f"/api/workspaces/{workspace_id}/mailboxes/fake/connect")
    assert response.status_code == 200
    url = response.json()["authorization_url"]
    return parse_qs(urlsplit(url).query)["state"][0]


async def callback(client, **params):
    return await client.get("/api/oauth/fake/callback", params=params)


def redirect_query(response) -> dict[str, list[str]]:
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(WEB_URL)
    return parse_qs(urlsplit(location).query)


async def connect(app, client, workspace_id: str) -> str:
    """Run the whole connect flow and return the new mailbox id."""
    state = await start_connect(client, workspace_id)
    query = redirect_query(await callback(client, code="c", state=state))
    await app.state.queue.drain()
    return query["mailbox_connected"][0]


async def test_connect_returns_signed_state_for_workspace(app, client, fake_connector):
    ws = await demo_workspace(client)
    state = await start_connect(client, ws)

    assert app.state.services.secrets.open(state) == {"workspace_id": ws, "provider": "fake"}


async def test_connect_unknown_provider_is_404(client):
    ws = await demo_workspace(client)
    response = await client.post(f"/api/workspaces/{ws}/mailboxes/nope/connect")
    assert response.status_code == 404
    assert response.json()["detail"] == "Mail provider not available"


async def test_callback_creates_active_mailbox_and_backfills(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.queue = [message("m1")]
    state = await start_connect(client, ws)

    response = await callback(client, code="c", state=state)
    await app.state.queue.drain()

    query = redirect_query(response)
    [mailbox] = mailboxes_of(app, ws)
    assert query == {"mailbox_connected": [mailbox.id]}
    assert mailbox.status == MailboxStatus.ACTIVE
    assert mailbox.email_address == "owner@shop.in"
    assert len(emails_of(app, ws)) == 1
    assert "subscribe" in fake_connector.calls


async def test_callback_with_forged_state_is_rejected(app, client, fake_connector):
    ws = await demo_workspace(client)

    response = await callback(client, code="c", state="x")

    assert redirect_query(response) == {"mailbox_error": ["invalid_state"]}
    assert mailboxes_of(app, ws) == []
    assert "complete_authorization" not in fake_connector.calls


async def test_callback_with_expired_state_is_rejected(app, client, fake_connector, monkeypatch):
    ws = await demo_workspace(client)
    # Seal first, then read the clock: Fernet's encrypt reads it too, and a seal that crossed
    # a second boundary after `real_now` would still be inside max_age at real_now + 601.
    state = await start_connect(client, ws)
    real_now = time.time()
    monkeypatch.setattr("cryptography.fernet.time.time", lambda: real_now + 601)

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["invalid_state"]}
    assert mailboxes_of(app, ws) == []


async def test_callback_with_state_for_another_provider_is_rejected(app, client, fake_connector):
    ws = await demo_workspace(client)
    state = app.state.services.secrets.seal({"workspace_id": ws, "provider": "gmail"})

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["invalid_state"]}
    assert "complete_authorization" not in fake_connector.calls


async def test_callback_with_state_for_unknown_workspace_is_rejected(app, client, fake_connector):
    state = app.state.services.secrets.seal({"workspace_id": "gone", "provider": "fake"})

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["invalid_state"]}
    assert "complete_authorization" not in fake_connector.calls


async def test_callback_access_denied(app, client, fake_connector):
    ws = await demo_workspace(client)
    state = await start_connect(client, ws)

    response = await callback(client, error="access_denied", state=state)

    assert redirect_query(response) == {"mailbox_error": ["access_denied"]}
    assert mailboxes_of(app, ws) == []


async def test_callback_without_refresh_token(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.raise_on_authorize = MissingRefreshToken()
    state = await start_connect(client, ws)

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["no_refresh_token"]}
    assert mailboxes_of(app, ws) == []


async def test_callback_with_bad_code_is_rejected(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.raise_on_authorize = AuthRevoked("invalid_grant")
    state = await start_connect(client, ws)

    response = await callback(client, code="bad", state=state)

    assert redirect_query(response) == {"mailbox_error": ["authorization_failed"]}
    assert mailboxes_of(app, ws) == []


async def test_callback_for_unconfigured_provider_redirects(app, client):
    ws = await demo_workspace(client)
    state = app.state.services.secrets.seal({"workspace_id": ws, "provider": "fake"})

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["provider_unavailable"]}


async def test_subscribe_failure_leaves_mailbox_active(app, client, fake_connector, caplog):
    ws = await demo_workspace(client)
    fake_connector.raise_on_subscribe = RuntimeError("leak-me-xyz")

    mailbox_id = await connect(app, client, ws)

    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.id == mailbox_id
    assert mailbox.status == MailboxStatus.ACTIVE
    assert "RuntimeError" in caplog.text
    assert "leak-me-xyz" not in caplog.text


async def test_reconnect_reuses_row_and_keeps_cursor(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        mailbox.status = MailboxStatus.NEEDS_REAUTH
        mailbox.cursor = "7"
        session.add(mailbox)
        session.commit()

    assert await connect(app, client, ws) == mailbox_id

    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.status == MailboxStatus.ACTIVE
    # The callback queues a sync that continues from the kept cursor; a reset would give "1".
    assert mailbox.cursor == "8"


async def test_mailbox_out_has_no_credentials(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)

    [body] = (await client.get(f"/api/workspaces/{ws}/mailboxes")).json()

    assert body["id"] == mailbox_id
    assert body["provider"] == "fake"
    assert body["status"] == "active"
    assert "credentials_enc" not in body
    assert "cursor" not in body
    assert "provider_state" not in body


async def test_other_workspace_cannot_see_or_disconnect_mailbox(app, client, fake_connector):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    mailbox_id = await connect(app, client, ws_a)
    base = f"/api/workspaces/{ws_b}/mailboxes/{mailbox_id}"

    assert (await client.get(f"/api/workspaces/{ws_b}/mailboxes")).json() == []
    for action in ("sync", "pause", "resume"):
        assert (await client.post(f"{base}/{action}")).status_code == 404
    assert (await client.delete(base)).status_code == 404

    [mailbox] = mailboxes_of(app, ws_a)
    assert mailbox.status == MailboxStatus.ACTIVE
    assert mailbox.credentials_enc is not None


async def test_pause_resume_and_disconnect(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    base = f"/api/workspaces/{ws}/mailboxes/{mailbox_id}"

    paused = await client.post(f"{base}/pause")
    assert paused.json()["status"] == "paused"
    assert "unsubscribe" in fake_connector.calls
    assert (await client.post(f"{base}/pause")).status_code == 409
    assert (await client.post(f"{base}/sync")).status_code == 409

    fake_connector.calls.clear()
    resumed = await client.post(f"{base}/resume")
    assert resumed.json()["status"] == "active"
    assert "subscribe" in fake_connector.calls
    assert (await client.post(f"{base}/resume")).status_code == 409
    assert (await client.post(f"{base}/sync")).status_code == 202

    removed = await client.delete(base)
    assert removed.json()["status"] == "disconnected"
    assert "revoke" in fake_connector.calls
    assert (await client.delete(base)).status_code == 409
    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.credentials_enc is None
