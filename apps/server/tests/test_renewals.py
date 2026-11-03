"""The daily cron that renews push subscriptions for every active mailbox."""

from datetime import UTC, datetime

from cryptography.fernet import Fernet
from fake_connector import FakeConnector
from sqlmodel import Session, select

from herald_server.connectors.base import AuthRevoked, Subscription
from herald_server.crypto import SecretBox
from herald_server.events import MAILBOX_STATUS
from herald_server.mailboxes import renew_subscriptions
from herald_server.models import Event, Mailbox, MailboxStatus

OLD_EXPIRY = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
NEW_EXPIRY = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


async def demo_workspace(client) -> str:
    response = await client.post("/api/workspaces/demo")
    assert response.status_code == 201
    return response.json()["id"]


def add_mailbox(app, workspace_id: str, provider: str = "fake", **fields) -> str:
    services = app.state.services
    fields.setdefault("credentials_enc", services.secrets.seal({"token": "t"}))
    mailbox = Mailbox(
        workspace_id=workspace_id,
        provider=provider,
        email_address=f"owner@{provider}.in",
        subscription_expires_at=OLD_EXPIRY,
        provider_state={"history_id": "1"},
        **fields,
    )
    with Session(services.engine) as session:
        session.add(mailbox)
        session.commit()
        return mailbox.id


def load_mailbox(app, mailbox_id: str) -> Mailbox:
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        return mailbox


def expiry_of(app, mailbox_id: str) -> datetime | None:
    expires_at = load_mailbox(app, mailbox_id).subscription_expires_at
    # SQLite drops the time zone; the stored value is UTC.
    return expires_at.replace(tzinfo=UTC) if expires_at else None


def status_events(app, workspace_id: str) -> list[dict]:
    with Session(app.state.services.engine) as session:
        events = session.exec(
            select(Event).where(Event.workspace_id == workspace_id, Event.type == MAILBOX_STATUS)
        ).all()
        return [e.data for e in events]


def renewed_subscription() -> Subscription:
    return Subscription(expires_at=NEW_EXPIRY, provider_state={"history_id": "2"})


async def test_renew_updates_expiry(app, client, fake_connector):
    mailbox_id = add_mailbox(app, await demo_workspace(client))
    fake_connector.subscription = renewed_subscription()

    assert await renew_subscriptions(app.state.services) == 1

    assert expiry_of(app, mailbox_id) == NEW_EXPIRY
    assert load_mailbox(app, mailbox_id).provider_state == {"history_id": "2"}


async def test_renew_marks_revoked_mailbox_and_continues(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    revoked = FakeConnector()
    revoked.provider = "fake-revoked"
    revoked.raise_on_subscribe = AuthRevoked()
    app.state.services.connectors["fake-revoked"] = revoked
    revoked_id = add_mailbox(app, workspace_id, provider="fake-revoked")
    healthy_id = add_mailbox(app, workspace_id)
    fake_connector.subscription = renewed_subscription()

    assert await renew_subscriptions(app.state.services) == 1

    assert load_mailbox(app, revoked_id).status == MailboxStatus.NEEDS_REAUTH
    assert expiry_of(app, revoked_id) == OLD_EXPIRY
    assert expiry_of(app, healthy_id) == NEW_EXPIRY
    assert status_events(app, workspace_id) == [
        {
            "mailbox_id": revoked_id,
            "email_address": "owner@fake-revoked.in",
            "status": "needs_reauth",
        }
    ]


async def test_renew_marks_undecryptable_credentials(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    other_key = SecretBox(Fernet.generate_key().decode())
    mailbox_id = add_mailbox(app, workspace_id, credentials_enc=other_key.seal({"token": "t"}))

    assert await renew_subscriptions(app.state.services) == 0

    assert "subscribe" not in fake_connector.calls
    assert load_mailbox(app, mailbox_id).status == MailboxStatus.NEEDS_REAUTH
    assert [e["status"] for e in status_events(app, workspace_id)] == ["needs_reauth"]


async def test_renew_logs_other_errors_and_continues(app, client, fake_connector, caplog):
    workspace_id = await demo_workspace(client)
    failing = FakeConnector()
    failing.provider = "fake-failing"
    failing.raise_on_subscribe = RuntimeError("leak-me-xyz")
    app.state.services.connectors["fake-failing"] = failing
    failing_id = add_mailbox(app, workspace_id, provider="fake-failing")
    healthy_id = add_mailbox(app, workspace_id)
    fake_connector.subscription = renewed_subscription()

    assert await renew_subscriptions(app.state.services) == 1

    assert load_mailbox(app, failing_id).status == MailboxStatus.ACTIVE
    assert expiry_of(app, healthy_id) == NEW_EXPIRY
    assert "RuntimeError" in caplog.text
    assert "leak-me-xyz" not in caplog.text
    assert status_events(app, workspace_id) == []


async def test_renew_skips_paused_and_disconnected(app, client, fake_connector):
    workspace_id = await demo_workspace(client)
    paused_id = add_mailbox(app, workspace_id, status=MailboxStatus.PAUSED)
    disconnected = FakeConnector()
    disconnected.provider = "fake-gone"
    app.state.services.connectors["fake-gone"] = disconnected
    disconnected_id = add_mailbox(
        app,
        workspace_id,
        provider="fake-gone",
        status=MailboxStatus.DISCONNECTED,
        credentials_enc=None,
    )
    fake_connector.subscription = renewed_subscription()

    assert await renew_subscriptions(app.state.services) == 0

    assert "subscribe" not in fake_connector.calls
    assert "subscribe" not in disconnected.calls
    assert expiry_of(app, paused_id) == OLD_EXPIRY
    assert expiry_of(app, disconnected_id) == OLD_EXPIRY
