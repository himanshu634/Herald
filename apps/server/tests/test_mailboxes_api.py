"""Connecting, listing, pausing and disconnecting mailboxes, and the OAuth callback."""

import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlmodel import Session, col, select

from herald_server import mailboxes
from herald_server.connectors.base import (
    AuthRevoked,
    InboundMessage,
    MissingRefreshToken,
    Subscription,
)
from herald_server.events import MAILBOX_STATUS
from herald_server.models import Email, Event, Mailbox, MailboxStatus

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


def status_events(app, workspace_id: str) -> list[str]:
    """The `status` of each `mailbox.status` event in the workspace, oldest first."""
    with Session(app.state.services.engine) as session:
        events = session.exec(
            select(Event)
            .where(Event.workspace_id == workspace_id, Event.type == MAILBOX_STATUS)
            .order_by(col(Event.id))
        ).all()
        return [e.data["status"] for e in events]


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
    assert query == {"mailbox_connected": [mailbox.id], "workspace": [ws]}
    assert mailbox.status == MailboxStatus.ACTIVE
    assert mailbox.email_address == "owner@shop.in"
    assert len(emails_of(app, ws)) == 1
    assert "subscribe" in fake_connector.calls
    assert status_events(app, ws) == ["active"]


async def test_connect_commits_status_event_with_the_status_change(app, client, fake_connector):
    ws = await demo_workspace(client)
    seen_at_subscribe: list[list[str]] = []

    async def subscribe(credentials, provider_state, *, include_spam=False) -> Subscription:
        # The provider call comes after the commit: the event is stored with the change.
        seen_at_subscribe.append(status_events(app, ws))
        return Subscription(expires_at=None, provider_state={})

    fake_connector.subscribe = subscribe

    await connect(app, client, ws)

    assert seen_at_subscribe == [["active"]]
    assert status_events(app, ws) == ["active"]


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

    assert redirect_query(response) == {"mailbox_error": ["access_denied"], "workspace": [ws]}
    assert mailboxes_of(app, ws) == []


async def test_callback_without_refresh_token(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.raise_on_authorize = MissingRefreshToken()
    state = await start_connect(client, ws)

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["no_refresh_token"], "workspace": [ws]}
    assert mailboxes_of(app, ws) == []


async def test_callback_with_bad_code_is_rejected(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.raise_on_authorize = AuthRevoked("invalid_grant")
    state = await start_connect(client, ws)

    response = await callback(client, code="bad", state=state)

    assert redirect_query(response) == {
        "mailbox_error": ["authorization_failed"],
        "workspace": [ws],
    }
    assert mailboxes_of(app, ws) == []


@pytest.mark.parametrize(
    "error",
    [
        httpx.HTTPStatusError(
            "leak-me-xyz",
            request=httpx.Request("GET", "https://provider.example/profile"),
            response=httpx.Response(403),
        ),
        httpx.ConnectError("leak-me-xyz"),
        RuntimeError("leak-me-xyz"),
    ],
)
async def test_callback_provider_error_redirects(app, client, fake_connector, caplog, error):
    ws = await demo_workspace(client)
    fake_connector.raise_on_authorize = error
    state = await start_connect(client, ws)

    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["provider_error"], "workspace": [ws]}
    assert mailboxes_of(app, ws) == []
    assert type(error).__name__ in caplog.text
    assert "leak-me-xyz" not in caplog.text


async def test_callback_reports_connected_when_failure_happens_after_save(
    app, client, fake_connector, monkeypatch, caplog
):
    ws = await demo_workspace(client)
    fake_connector.queue = [message("m1")]
    state = await start_connect(client, ws)
    bus = app.state.services.bus
    real_publish = bus.publish
    failures = [RuntimeError("leak-me-xyz")]

    async def publish_failing_once(event):
        # Only the first publish (the connect's status event) fails: the sync publishes too.
        if failures:
            raise failures.pop()
        await real_publish(event)

    monkeypatch.setattr(bus, "publish", publish_failing_once)

    response = await callback(client, code="c", state=state)
    await app.state.queue.drain()

    # The mailbox is saved: telling the owner the connect failed would be wrong.
    [mailbox] = mailboxes_of(app, ws)
    assert redirect_query(response) == {"mailbox_connected": [mailbox.id], "workspace": [ws]}
    assert mailbox.status == MailboxStatus.ACTIVE
    assert "subscribe" in fake_connector.calls
    # The first sync still ran.
    assert [e.provider_message_id for e in emails_of(app, ws)] == ["m1"]
    assert "RuntimeError" in caplog.text and mailbox.id in caplog.text
    assert "leak-me-xyz" not in caplog.text


async def test_callback_reports_connected_when_refresh_fails_after_commit(
    app, client, fake_connector, monkeypatch
):
    ws = await demo_workspace(client)
    state = await start_connect(client, ws)
    real_refresh = Session.refresh
    failures = [RuntimeError("leak-me-xyz")]

    def refresh_failing_once(self, instance, *args, **kwargs):
        # The first refresh in the flow would be the one right after the connect's commit.
        if failures:
            raise failures.pop()
        return real_refresh(self, instance, *args, **kwargs)

    monkeypatch.setattr(Session, "refresh", refresh_failing_once)

    response = await callback(client, code="c", state=state)
    monkeypatch.undo()
    await app.state.queue.drain()

    [mailbox] = mailboxes_of(app, ws)
    assert redirect_query(response) == {"mailbox_connected": [mailbox.id], "workspace": [ws]}
    assert mailbox.status == MailboxStatus.ACTIVE
    assert status_events(app, ws) == ["active"]


async def test_callback_reports_connected_when_saving_subscription_fails(
    app, client, fake_connector, monkeypatch, caplog
):
    ws = await demo_workspace(client)
    fake_connector.queue = [message("m1")]
    state = await start_connect(client, ws)

    def save_subscription(services, mailbox_id, subscription):
        raise RuntimeError("leak-me-xyz")

    monkeypatch.setattr("herald_server.mailboxes._save_subscription", save_subscription)

    response = await callback(client, code="c", state=state)
    await app.state.queue.drain()

    [mailbox] = mailboxes_of(app, ws)
    assert redirect_query(response) == {"mailbox_connected": [mailbox.id], "workspace": [ws]}
    assert [e.provider_message_id for e in emails_of(app, ws)] == ["m1"]
    assert "RuntimeError" in caplog.text and mailbox.id in caplog.text
    assert "leak-me-xyz" not in caplog.text


async def test_callback_reports_connected_when_first_sync_cannot_be_queued(
    app, client, fake_connector, monkeypatch, caplog
):
    ws = await demo_workspace(client)
    state = await start_connect(client, ws)

    async def enqueue_sync(mailbox_id):
        raise ConnectionError("leak-me-xyz")

    monkeypatch.setattr(app.state.queue, "enqueue_sync", enqueue_sync)

    response = await callback(client, code="c", state=state)

    # The catch-up sync runs the first sync later; the connect itself worked.
    [mailbox] = mailboxes_of(app, ws)
    assert redirect_query(response) == {"mailbox_connected": [mailbox.id], "workspace": [ws]}
    assert mailbox.status == MailboxStatus.ACTIVE
    assert "ConnectionError" in caplog.text and mailbox.id in caplog.text
    assert "leak-me-xyz" not in caplog.text


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


async def test_reconnecting_an_active_mailbox_turns_on_sending(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.account.can_send = False
    mailbox_id = await connect(app, client, ws)
    [before] = (await client.get(f"/api/workspaces/{ws}/mailboxes")).json()
    assert before["can_send"] is False

    fake_connector.account.can_send = True
    assert await connect(app, client, ws) == mailbox_id

    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.status == MailboxStatus.ACTIVE
    [after] = (await client.get(f"/api/workspaces/{ws}/mailboxes")).json()
    assert after["can_send"] is True


async def test_reconnect_after_disconnect_reuses_row_and_keeps_cursor(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        mailbox.cursor = "7"
        session.add(mailbox)
        session.commit()
    removed = await client.delete(f"/api/workspaces/{ws}/mailboxes/{mailbox_id}")
    assert removed.json()["status"] == "disconnected"
    assert mailboxes_of(app, ws)[0].credentials_enc is None

    assert await connect(app, client, ws) == mailbox_id

    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.status == MailboxStatus.ACTIVE
    assert mailbox.credentials_enc is not None
    # The callback queues a sync that continues from the kept cursor; a reset would give "1".
    assert mailbox.cursor == "8"
    assert status_events(app, ws) == ["active", "disconnected", "active"]


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
    # One event per change; the 409s add none.
    assert status_events(app, ws) == ["active", "paused", "active", "disconnected"]


async def test_connect_refuses_address_live_in_another_workspace(app, client, fake_connector):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    await connect(app, client, ws_a)
    [before] = mailboxes_of(app, ws_a)
    fake_connector.calls.clear()

    state = await start_connect(client, ws_b)
    response = await callback(client, code="c", state=state)
    await app.state.queue.drain()

    assert redirect_query(response) == {"mailbox_error": ["mailbox_in_use"], "workspace": [ws_b]}
    assert mailboxes_of(app, ws_b) == []
    assert status_events(app, ws_b) == []
    assert "complete_authorization" in fake_connector.calls
    # The new grant belongs to the same account as ws_a's live grant: revoking it would
    # break ws_a. Nothing is subscribed or synced either.
    assert "revoke" not in fake_connector.calls
    assert "subscribe" not in fake_connector.calls
    assert "fetch_changes" not in fake_connector.calls
    [after] = mailboxes_of(app, ws_a)
    assert after.status == MailboxStatus.ACTIVE
    assert after.credentials_enc == before.credentials_enc
    assert status_events(app, ws_a) == ["active"]


async def test_connect_allowed_when_other_workspace_disconnected(app, client, fake_connector):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    mailbox_a = await connect(app, client, ws_a)
    await client.delete(f"/api/workspaces/{ws_a}/mailboxes/{mailbox_a}")

    mailbox_b = await connect(app, client, ws_b)

    [new] = mailboxes_of(app, ws_b)
    assert new.id == mailbox_b != mailbox_a
    assert new.status == MailboxStatus.ACTIVE
    [old] = mailboxes_of(app, ws_a)
    assert old.id == mailbox_a
    assert old.status == MailboxStatus.DISCONNECTED
    assert old.credentials_enc is None
    assert status_events(app, ws_a) == ["active", "disconnected"]


async def test_reconnect_own_disconnected_row_refused_when_address_live_elsewhere(
    app, client, fake_connector
):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    mailbox_a = await connect(app, client, ws_a)
    await client.delete(f"/api/workspaces/{ws_a}/mailboxes/{mailbox_a}")
    await connect(app, client, ws_b)
    fake_connector.calls.clear()

    state = await start_connect(client, ws_a)
    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["mailbox_in_use"], "workspace": [ws_a]}
    assert "revoke" not in fake_connector.calls
    [old] = mailboxes_of(app, ws_a)
    assert old.status == MailboxStatus.DISCONNECTED
    assert old.credentials_enc is None
    assert status_events(app, ws_a) == ["active", "disconnected"]
    [live] = mailboxes_of(app, ws_b)
    assert live.status == MailboxStatus.ACTIVE


async def test_concurrent_connect_integrity_error_maps_to_in_use(
    app, client, fake_connector, monkeypatch
):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    await connect(app, client, ws_a)
    fake_connector.calls.clear()
    # Two callbacks race: ws_b's check ran before ws_a's commit, so only the partial unique
    # index catches the second live row, at commit.
    monkeypatch.setattr(mailboxes, "address_live_in_other_workspace", lambda *args: False)

    state = await start_connect(client, ws_b)
    response = await callback(client, code="c", state=state)

    assert redirect_query(response) == {"mailbox_error": ["mailbox_in_use"], "workspace": [ws_b]}
    assert mailboxes_of(app, ws_b) == []
    assert status_events(app, ws_b) == []
    assert "revoke" not in fake_connector.calls
    [live] = mailboxes_of(app, ws_a)
    assert live.status == MailboxStatus.ACTIVE


async def test_access_denied_with_bad_state_names_no_workspace(app, client, fake_connector):
    # The state is checked before the redirect names a business, so a forged one cannot send
    # the owner to another workspace.
    response = await callback(client, error="access_denied", state="forged")

    assert redirect_query(response) == {"mailbox_error": ["invalid_state"]}


async def test_providers_lists_configured_connectors(client, fake_connector):
    response = await client.get("/api/providers")

    assert response.status_code == 200
    assert "fake" in response.json()


async def test_providers_empty_without_token_key(app, client, fake_connector):
    app.state.services.secrets = None

    assert (await client.get("/api/providers")).json() == []


def spam_message(provider_message_id: str) -> InboundMessage:
    return message(provider_message_id).model_copy(update={"in_spam": True})


async def connect_with(app, client, workspace_id: str, read_spam: bool | None) -> str:
    response = await client.post(
        f"/api/workspaces/{workspace_id}/mailboxes/fake/connect",
        json=None if read_spam is None else {"read_spam": read_spam},
    )
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    query = redirect_query(await callback(client, code="c", state=state))
    await app.state.queue.drain()
    return query["mailbox_connected"][0]


async def test_connect_with_spam_saves_the_choice_and_reads_spam(app, client, fake_connector):
    ws = await demo_workspace(client)
    fake_connector.queue = [message("m1"), spam_message("s1")]

    await connect_with(app, client, ws, read_spam=True)

    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.read_spam is True
    assert "subscribe+spam" in fake_connector.calls
    assert "fetch_changes+spam" in fake_connector.calls
    stored = {e.provider_message_id: e.in_spam for e in emails_of(app, ws)}
    assert stored == {"m1": False, "s1": True}
    listed = (await client.get(f"/api/workspaces/{ws}/emails")).json()
    assert sorted(e["in_spam"] for e in listed) == [False, True]


async def test_reconnect_from_the_web_sends_no_spam_choice(app, client, fake_connector):
    # The web's request() always sets the JSON content type, even with no body.
    ws = await demo_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws}/mailboxes/fake/connect",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    assert "read_spam" not in app.state.services.secrets.open(state)


async def test_connect_without_a_choice_leaves_spam_off(app, client, fake_connector):
    ws = await demo_workspace(client)
    await connect_with(app, client, ws, read_spam=None)
    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.read_spam is False
    assert "fetch_changes" in fake_connector.calls


async def test_reconnect_without_a_choice_keeps_spam_on(app, client, fake_connector):
    ws = await demo_workspace(client)
    await connect_with(app, client, ws, read_spam=True)
    # The composer's and the menu's Reconnect send no choice.
    await connect_with(app, client, ws, read_spam=None)
    [mailbox] = mailboxes_of(app, ws)
    assert mailbox.read_spam is True


async def test_turning_spam_on_watches_spam_and_reads_recent_spam(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    [before] = mailboxes_of(app, ws)
    fake_connector.spam = [spam_message("s1")]
    fake_connector.calls.clear()

    response = await client.patch(
        f"/api/workspaces/{ws}/mailboxes/{mailbox_id}", json={"read_spam": True}
    )
    await app.state.queue.drain()

    assert response.status_code == 200
    assert response.json()["read_spam"] is True
    assert fake_connector.calls[:2] == ["subscribe+spam", "fetch_recent_spam"]
    [email] = emails_of(app, ws)
    assert (email.provider_message_id, email.in_spam) == ("s1", True)
    # Triage ran on it, and the cursor the sync owns did not move.
    assert email.status != "new"
    [after] = mailboxes_of(app, ws)
    assert after.cursor == before.cursor
    assert status_events(app, ws) == ["active", "active"]


async def test_turning_spam_off_watches_the_inbox_only(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect_with(app, client, ws, read_spam=True)
    fake_connector.calls.clear()

    response = await client.patch(
        f"/api/workspaces/{ws}/mailboxes/{mailbox_id}", json={"read_spam": False}
    )

    assert response.json()["read_spam"] is False
    assert fake_connector.calls == ["subscribe"]


async def test_setting_spam_to_the_same_value_calls_no_provider(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    fake_connector.calls.clear()

    response = await client.patch(
        f"/api/workspaces/{ws}/mailboxes/{mailbox_id}", json={"read_spam": False}
    )

    assert response.status_code == 200
    assert fake_connector.calls == []
    assert status_events(app, ws) == ["active"]


async def test_spam_backfill_failure_still_saves_the_choice(app, client, fake_connector, caplog):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    fake_connector.raise_on_fetch = RuntimeError("provider down")

    response = await client.patch(
        f"/api/workspaces/{ws}/mailboxes/{mailbox_id}", json={"read_spam": True}
    )

    assert response.status_code == 200
    assert response.json()["read_spam"] is True
    assert "RuntimeError on Spam backfill" in caplog.text


async def test_turning_spam_on_while_paused_reads_nothing_yet(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    base = f"/api/workspaces/{ws}/mailboxes/{mailbox_id}"
    await client.post(f"{base}/pause")
    fake_connector.calls.clear()

    response = await client.patch(base, json={"read_spam": True})

    assert response.json()["read_spam"] is True
    assert fake_connector.calls == []


async def test_spam_setting_refused_for_a_disconnected_mailbox(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    base = f"/api/workspaces/{ws}/mailboxes/{mailbox_id}"
    await client.delete(base)

    assert (await client.patch(base, json={"read_spam": True})).status_code == 409


async def test_other_workspace_cannot_change_spam_setting(app, client, fake_connector):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    mailbox_id = await connect(app, client, ws_a)

    response = await client.patch(
        f"/api/workspaces/{ws_b}/mailboxes/{mailbox_id}", json={"read_spam": True}
    )

    assert response.status_code == 404
    [mailbox] = mailboxes_of(app, ws_a)
    assert mailbox.read_spam is False
