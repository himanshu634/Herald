"""Syncing a mailbox through its connector into the triage pipeline."""

from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

from herald_server.connectors.base import AuthRevoked, FetchResult, InboundMessage, RateLimited
from herald_server.crypto import SecretBox
from herald_server.events import MAILBOX_STATUS
from herald_server.mailboxes import active_mailbox_ids_for_address
from herald_server.models import Email, EmailStatus, Event, Mailbox, MailboxStatus
from herald_server.sync import sync_mailbox


async def demo_workspace(client) -> str:
    response = await client.post("/api/workspaces/demo")
    assert response.status_code == 201
    return response.json()["id"]


def add_mailbox(app, workspace_id: str, **fields) -> str:
    services = app.state.services
    fields.setdefault("credentials_enc", services.secrets.seal({"token": "t"}))
    mailbox = Mailbox(
        workspace_id=workspace_id, provider="fake", email_address="owner@shop.in", **fields
    )
    with Session(services.engine) as session:
        session.add(mailbox)
        session.commit()
        return mailbox.id


def message(provider_message_id: str, subject: str = "Product questions") -> InboundMessage:
    return InboundMessage(
        provider_message_id=provider_message_id,
        sender="riya@customer.in",
        subject=subject,
        body="Does the cabin bag fit Indigo?",
        received_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
    )


def load_mailbox(app, mailbox_id: str) -> Mailbox:
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        return mailbox


def emails_of(app, mailbox_id: str) -> list[Email]:
    with Session(app.state.services.engine) as session:
        return list(session.exec(select(Email).where(Email.mailbox_id == mailbox_id)).all())


async def sync(app, mailbox_id: str) -> None:
    await app.state.queue.enqueue_sync(mailbox_id)
    await app.state.queue.drain()


async def test_sync_stores_new_mail_and_runs_triage(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1"), message("m2", "Refund please")]

    await sync(app, mailbox_id)

    emails = emails_of(app, mailbox_id)
    assert sorted(e.provider_message_id for e in emails) == ["m1", "m2"]
    assert all(e.status != EmailStatus.NEW for e in emails)
    mailbox = load_mailbox(app, mailbox_id)
    assert mailbox.cursor == "1"
    assert mailbox.last_synced_at is not None


async def test_sync_twice_does_not_duplicate(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1")]
    await sync(app, mailbox_id)

    fake_connector.queue = [message("m1")]
    await sync(app, mailbox_id)

    assert len(emails_of(app, mailbox_id)) == 1
    assert load_mailbox(app, mailbox_id).cursor == "2"


async def test_auth_revoked_marks_needs_reauth(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    mailbox_id = add_mailbox(app, workspace_id)
    fake_connector.raise_on_fetch = AuthRevoked()

    await sync(app, mailbox_id)

    assert load_mailbox(app, mailbox_id).status == MailboxStatus.NEEDS_REAUTH
    with Session(app.state.services.engine) as session:
        events = session.exec(
            select(Event).where(Event.workspace_id == workspace_id, Event.type == MAILBOX_STATUS)
        ).all()
    assert [e.data for e in events] == [
        {"mailbox_id": mailbox_id, "email_address": "owner@shop.in", "status": "needs_reauth"}
    ]


def status_events(app, workspace_id: str) -> list[Event]:
    with Session(app.state.services.engine) as session:
        return list(
            session.exec(
                select(Event).where(
                    Event.workspace_id == workspace_id, Event.type == MAILBOX_STATUS
                )
            ).all()
        )


async def test_auth_revoked_does_not_override_a_disconnect(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    mailbox_id = add_mailbox(app, workspace_id)

    async def disconnect_then_revoke(credentials, cursor) -> FetchResult:
        # The owner disconnects while this fetch is in flight, then the provider says revoked.
        with Session(app.state.services.engine) as session:
            mailbox = session.get(Mailbox, mailbox_id)
            assert mailbox is not None
            mailbox.status = MailboxStatus.DISCONNECTED
            mailbox.credentials_enc = None
            session.add(mailbox)
            session.commit()
        raise AuthRevoked()

    fake_connector.fetch_changes = disconnect_then_revoke

    assert await sync_mailbox(app.state.services, mailbox_id) == []

    assert load_mailbox(app, mailbox_id).status == MailboxStatus.DISCONNECTED
    assert status_events(app, workspace_id) == []


async def test_undecryptable_credentials_mark_needs_reauth(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    other_key = SecretBox(Fernet.generate_key().decode())
    mailbox_id = add_mailbox(app, workspace_id, credentials_enc=other_key.seal({"token": "t"}))

    assert await sync_mailbox(app.state.services, mailbox_id) == []

    assert "fetch_changes" not in fake_connector.calls
    assert load_mailbox(app, mailbox_id).status == MailboxStatus.NEEDS_REAUTH
    assert [e.data["status"] for e in status_events(app, workspace_id)] == ["needs_reauth"]


async def test_rate_limited_keeps_cursor(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client), cursor="7")
    fake_connector.raise_on_fetch = RateLimited(30)

    with pytest.raises(RateLimited):
        await sync_mailbox(app.state.services, mailbox_id)

    assert load_mailbox(app, mailbox_id).cursor == "7"


async def test_inline_sync_failure_logs_only_the_type(app, client, fake_connector, caplog):
    mailbox_id = add_mailbox(app, await demo_workspace(client), cursor="7")
    fake_connector.raise_on_fetch = RuntimeError("leak-me-xyz")

    await sync(app, mailbox_id)

    assert "RuntimeError" in caplog.text
    assert "leak-me-xyz" not in caplog.text
    assert load_mailbox(app, mailbox_id).cursor == "7"


async def test_paused_mailbox_is_not_fetched(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client), status=MailboxStatus.PAUSED)
    fake_connector.queue = [message("m1")]

    await sync(app, mailbox_id)

    assert "fetch_changes" not in fake_connector.calls
    assert emails_of(app, mailbox_id) == []


async def test_same_address_in_two_workspaces_each_get_a_copy(app, client, fake_connector):
    ws_a, ws_b = await demo_workspace(client), await demo_workspace(client)
    mailbox_a, mailbox_b = add_mailbox(app, ws_a), add_mailbox(app, ws_b)
    assert sorted(
        active_mailbox_ids_for_address(app.state.services, "fake", "OWNER@Shop.in")
    ) == sorted([mailbox_a, mailbox_b])

    # The fake's queue empties on each fetch, so sync one mailbox at a time.
    fake_connector.queue = [message("m1")]
    await sync(app, mailbox_a)
    fake_connector.queue = [message("m1")]
    await sync(app, mailbox_b)

    for workspace_id, mailbox_id in ((ws_a, mailbox_a), (ws_b, mailbox_b)):
        listed = (await client.get(f"/api/workspaces/{workspace_id}/emails")).json()
        assert len(listed) == 1
        assert listed[0]["workspace_id"] == workspace_id
        assert [e.id for e in emails_of(app, mailbox_id)] == [listed[0]["id"]]


async def test_repeat_inside_one_batch_is_stored_once(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.queue = [message("m1"), message("m1")]

    await sync(app, mailbox_id)

    assert len(emails_of(app, mailbox_id)) == 1
    assert load_mailbox(app, mailbox_id).cursor == "1"
