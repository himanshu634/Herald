"""The owner's reply to a customer: one send per draft, outcomes, status, tenancy."""

from datetime import UTC, datetime, timedelta

import httpx
from sqlmodel import Session, select
from test_sync import add_mailbox, demo_workspace, emails_of, message, sync

from herald_server import replies
from herald_server.connectors.base import (
    AuthRevoked,
    RateLimited,
    SendNotAllowed,
    SendRejected,
)
from herald_server.events import EMAIL_STATUS, REPLY_STATUS
from herald_server.models import (
    Email,
    EmailStatus,
    Event,
    Mailbox,
    MailboxStatus,
    Reply,
    ReplyStatus,
)
from herald_server.replies import reply_subject

MESSAGE_ID = "<a1@mail.customer.in>"


async def setup(app, client, *, mailbox_fields=None, **message_fields) -> tuple[str, str, str]:
    """A demo workspace, a mailbox that can send, and one synced customer email."""
    workspace_id = await demo_workspace(client)
    mailbox_id = add_mailbox(app, workspace_id, **{"can_send": True, **(mailbox_fields or {})})
    app.state.services.connectors["fake"].queue = [
        message(
            "m1",
            **{
                "thread_id": "th1",
                "internet_message_id": MESSAGE_ID,
                "references": "<r0@x>",
                **message_fields,
            },
        )
    ]
    await sync(app, mailbox_id)
    (email,) = emails_of(app, mailbox_id)
    return workspace_id, mailbox_id, email.id


async def post_reply(
    client, workspace_id: str, email_id: str, key: str = "draft-0001", mark_done: bool = False
) -> httpx.Response:
    return await client.post(
        f"/api/workspaces/{workspace_id}/emails/{email_id}/replies",
        json={"body": "Yes, it fits the cabin limit.", "client_key": key, "mark_done": mark_done},
    )


def events_of(app, workspace_id: str, type_: str) -> list[Event]:
    with Session(app.state.services.engine) as session:
        return list(
            session.exec(
                select(Event).where(Event.workspace_id == workspace_id, Event.type == type_)
            ).all()
        )


def load_email(app, email_id: str) -> Email:
    with Session(app.state.services.engine) as session:
        email = session.get(Email, email_id)
        assert email is not None
        return email


def load_mailbox(app, mailbox_id: str) -> Mailbox:
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        return mailbox


def insert_reply(app, workspace_id: str, mailbox_id: str, email_id: str, **fields) -> str:
    reply = Reply(
        workspace_id=workspace_id,
        email_id=email_id,
        mailbox_id=mailbox_id,
        client_key=fields.pop("client_key", "other-draft"),
        from_address="owner@shop.in",
        to_address="riya@customer.in",
        subject="Re: Product questions",
        body="Earlier reply",
        **fields,
    )
    with Session(app.state.services.engine) as session:
        session.add(reply)
        session.commit()
        return reply.id


def load_reply(app, reply_id: str) -> Reply:
    with Session(app.state.services.engine) as session:
        reply = session.get(Reply, reply_id)
        assert reply is not None
        return reply


def test_reply_subject():
    assert reply_subject("Product questions") == "Re: Product questions"
    assert reply_subject("Re: Product questions") == "Re: Product questions"
    assert reply_subject("RE: Product questions") == "RE: Product questions"
    assert reply_subject("re:x") == "re:x"
    assert reply_subject("") == "Re: "


async def test_reply_sends_in_the_thread(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["error"] is None
    assert body["sent_at"] is not None
    (sent,) = fake_connector.sent
    assert sent.to_address == "riya@customer.in"
    assert sent.from_address == "owner@shop.in"
    assert sent.subject == "Re: Product questions"
    assert sent.in_reply_to == MESSAGE_ID
    assert sent.references == f"<r0@x> {MESSAGE_ID}"
    assert sent.provider_thread_id == "th1"
    assert sent.body == "Yes, it fits the cabin limit."
    (event,) = events_of(app, ws, REPLY_STATUS)
    assert event.data == {"email_id": email_id, "reply_id": body["id"], "status": "sent"}
    reply = load_reply(app, body["id"])
    assert reply.provider_message_id == "sent-1"
    assert reply.mailbox_id == mailbox_id


async def test_reply_without_thread_headers(app, client, fake_connector):
    ws, _, email_id = await setup(
        app, client, thread_id=None, internet_message_id=None, references=None
    )

    assert (await post_reply(client, ws, email_id)).json()["status"] == "sent"

    (sent,) = fake_connector.sent
    assert sent.in_reply_to is None
    assert sent.references is None
    assert sent.provider_thread_id is None


async def test_reply_goes_to_reply_to(app, client, fake_connector):
    ws, _, email_id = await setup(app, client, reply_to="riya.home@customer.in")

    await post_reply(client, ws, email_id)

    assert fake_connector.sent[0].to_address == "riya.home@customer.in"
    assert (await post_reply(client, ws, email_id)).json()["to_address"] == (
        "riya.home@customer.in"
    )


async def test_bad_reply_to_falls_back_to_sender(app, client, fake_connector):
    bad = ["a", "a@x.in, b@x.in", "a@b@x.in", "a@x.in\r\nBcc: z@x.in", "a @x.in", "<a@x.in>"]
    # One workspace: an address can be live in only one, so every case shares the mailbox.
    ws, mailbox_id, _ = await setup(app, client, reply_to="unused@customer.in")
    fake_connector.queue = [message(f"bad-{i}", reply_to=value) for i, value in enumerate(bad)]
    await sync(app, mailbox_id)
    emails = {e.reply_to: e.id for e in emails_of(app, mailbox_id)}

    for i, value in enumerate(bad):
        fake_connector.sent.clear()
        response = await post_reply(client, ws, emails[value], key=f"draft-bad-{i}")

        assert response.json()["status"] == "sent", value
        assert fake_connector.sent[0].to_address == "riya@customer.in", value


async def test_reply_leaves_status_alone(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    before = load_email(app, email_id).status
    status_events = len(events_of(app, ws, EMAIL_STATUS))

    await post_reply(client, ws, email_id)

    assert load_email(app, email_id).status == before
    assert len(events_of(app, ws, EMAIL_STATUS)) == status_events


async def test_send_and_mark_done(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    before = load_email(app, email_id).status

    response = await post_reply(client, ws, email_id, mark_done=True)

    assert response.json()["status"] == "sent"
    assert load_email(app, email_id).status == EmailStatus.DONE
    (event,) = events_of(app, ws, EMAIL_STATUS)
    assert event.data == {"email_id": email_id, "from": before, "to": "done"}


async def test_mark_done_on_a_done_email_adds_no_event(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    await client.post(f"/api/workspaces/{ws}/emails/{email_id}/done")

    await post_reply(client, ws, email_id, mark_done=True)

    assert load_email(app, email_id).status == EmailStatus.DONE
    assert len(events_of(app, ws, EMAIL_STATUS)) == 1


async def test_not_sent_does_not_mark_done(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    before = load_email(app, email_id).status
    fake_connector.raise_on_send = SendRejected()

    response = await post_reply(client, ws, email_id, mark_done=True)

    assert response.status_code == 200
    assert response.json()["status"] == "not_sent"
    assert response.json()["error"] == "rejected"
    assert load_email(app, email_id).status == before
    assert events_of(app, ws, EMAIL_STATUS) == []


async def test_same_client_key_sends_once(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)

    first = await post_reply(client, ws, email_id, key="draft-0001")
    second = await post_reply(client, ws, email_id, key="draft-0001")

    assert len(fake_connector.sent) == 1
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "sent"


async def test_same_key_after_send_not_allowed_returns_the_row(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    fake_connector.raise_on_send = SendNotAllowed()
    first = await post_reply(client, ws, email_id)
    assert load_mailbox(app, mailbox_id).can_send is False

    second = await post_reply(client, ws, email_id)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "not_sent"
    assert fake_connector.calls.count("send_reply") == 1


async def test_key_from_another_email_is_409(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    fake_connector.queue = [message("m2", subject="Another question")]
    await sync(app, mailbox_id)
    other_id = next(e.id for e in emails_of(app, mailbox_id) if e.id != email_id)
    await post_reply(client, ws, email_id, key="draft-0001")

    response = await post_reply(client, ws, other_id, key="draft-0001")

    assert response.status_code == 409
    assert response.json()["detail"] == "already_sending"
    assert len(fake_connector.sent) == 1


async def test_second_reply_while_sending_is_409(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    insert_reply(app, ws, mailbox_id, email_id, status=ReplyStatus.SENDING)

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "already_sending"
    assert fake_connector.sent == []


async def test_stale_sending_row_does_not_block(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    stale_id = insert_reply(
        app,
        ws,
        mailbox_id,
        email_id,
        status=ReplyStatus.SENDING,
        created_at=datetime.now(UTC) - timedelta(minutes=3),
    )

    response = await post_reply(client, ws, email_id)

    assert response.json()["status"] == "sent"
    assert load_reply(app, stale_id).status == ReplyStatus.UNKNOWN
    assert load_reply(app, stale_id).error == "unknown"
    assert {"reply_id": stale_id, "email_id": email_id, "status": "unknown"} in [
        e.data for e in events_of(app, ws, REPLY_STATUS)
    ]


async def test_timeout_is_unknown_and_not_retried(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    fake_connector.raise_on_send = httpx.ReadTimeout("t")

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["error"] == "unknown"
    assert fake_connector.calls.count("send_reply") == 1


async def test_unknown_reply_does_not_block_the_next(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    fake_connector.raise_on_send = httpx.ReadTimeout("t")
    await post_reply(client, ws, email_id, key="draft-0001")
    fake_connector.raise_on_send = None

    response = await post_reply(client, ws, email_id, key="draft-0002")

    assert response.json()["status"] == "sent"


async def test_rate_limit_is_not_sent(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    fake_connector.raise_on_send = RateLimited(5.0)

    response = await post_reply(client, ws, email_id)

    assert response.json()["status"] == "not_sent"
    assert response.json()["error"] == "rate_limited"
    mailbox = load_mailbox(app, mailbox_id)
    assert mailbox.status == MailboxStatus.ACTIVE
    assert mailbox.can_send is True


async def test_send_not_allowed_turns_off_can_send(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    fake_connector.raise_on_send = SendNotAllowed()

    response = await post_reply(client, ws, email_id)

    assert response.json()["status"] == "not_sent"
    assert response.json()["error"] == "send_not_allowed"
    assert load_mailbox(app, mailbox_id).can_send is False
    fake_connector.raise_on_send = None
    blocked = await post_reply(client, ws, email_id, key="draft-0002")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "send_not_allowed"


async def test_auth_revoked_marks_needs_reauth(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    fake_connector.raise_on_send = AuthRevoked()

    response = await post_reply(client, ws, email_id)

    assert response.json()["status"] == "not_sent"
    assert response.json()["error"] == "auth"
    assert load_mailbox(app, mailbox_id).status == MailboxStatus.NEEDS_REAUTH


async def test_unreadable_credentials_are_not_sent(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        mailbox.credentials_enc = "not a sealed token"
        session.add(mailbox)
        session.commit()

    response = await post_reply(client, ws, email_id)

    assert response.json()["status"] == "not_sent"
    assert response.json()["error"] == "auth"
    assert "send_reply" not in fake_connector.calls


async def test_email_without_mailbox_is_409(app, client, fake_connector):
    ws = await demo_workspace(client)
    email = Email(workspace_id=ws, sender="riya@customer.in", subject="Hi", body="Question")
    with Session(app.state.services.engine) as session:
        session.add(email)
        session.commit()
        email_id = email.id

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "no_mailbox"


async def test_paused_mailbox_is_409(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client)
    with Session(app.state.services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        assert mailbox is not None
        mailbox.status = MailboxStatus.PAUSED
        session.add(mailbox)
        session.commit()

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "mailbox_inactive"
    assert fake_connector.sent == []


async def test_mailbox_without_send_is_409(app, client, fake_connector):
    ws, _, email_id = await setup(app, client, mailbox_fields={"can_send": False})

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "send_not_allowed"


async def test_mailbox_without_connector_is_409(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    del app.state.services.connectors["fake"]

    response = await post_reply(client, ws, email_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "mailbox_inactive"
    with Session(app.state.services.engine) as session:
        assert session.exec(select(Reply)).all() == []


async def test_replies_are_isolated(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    other = await demo_workspace(client)
    await post_reply(client, ws, email_id)

    assert (await post_reply(client, other, email_id, key="draft-0002")).status_code == 404
    url = f"/api/workspaces/{other}/emails/{email_id}/replies"
    assert (await client.get(url)).status_code == 404
    assert len(fake_connector.sent) == 1


async def test_unknown_email_is_404(app, client, fake_connector):
    ws = await demo_workspace(client)

    assert (await post_reply(client, ws, "nope")).status_code == 404
    assert (await client.get(f"/api/workspaces/{ws}/emails/nope/replies")).status_code == 404


async def test_list_replies_oldest_first(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    first = (await post_reply(client, ws, email_id, key="draft-0001")).json()
    second = (await post_reply(client, ws, email_id, key="draft-0002")).json()

    response = await client.get(f"/api/workspaces/{ws}/emails/{email_id}/replies")

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [first["id"], second["id"]]
    assert response.json()[0]["body"] == "Yes, it fits the cabin limit."


async def test_reply_input_is_checked(app, client, fake_connector):
    ws, _, email_id = await setup(app, client)
    url = f"/api/workspaces/{ws}/emails/{email_id}/replies"

    assert (await client.post(url, json={"body": "", "client_key": "draft-0001"})).status_code == (
        422
    )
    assert (await client.post(url, json={"body": "Hi", "client_key": "short"})).status_code == 422
    assert fake_connector.sent == []


async def test_email_out_carries_mailbox_and_reply_to(app, client, fake_connector):
    ws, mailbox_id, email_id = await setup(app, client, reply_to="riya.home@customer.in")

    email = (await client.get(f"/api/workspaces/{ws}/emails/{email_id}")).json()

    assert email["mailbox_id"] == mailbox_id
    assert email["reply_to"] == "riya.home@customer.in"


def race(monkeypatch, app, ws: str, mailbox_id: str, email_id: str, client_key: str) -> None:
    """Commit another request's SENDING row just after this request's key lookup."""
    real = replies._by_key
    raced = False

    def by_key(session, workspace_id, email_id_, key):
        nonlocal raced
        found = real(session, workspace_id, email_id_, key)
        if not raced:
            raced = True
            insert_reply(
                app, ws, mailbox_id, email_id, client_key=client_key, status=ReplyStatus.SENDING
            )
        return found

    monkeypatch.setattr(replies, "_by_key", by_key)


async def test_same_key_race_returns_the_other_row(app, client, fake_connector, monkeypatch):
    ws, mailbox_id, email_id = await setup(app, client)
    race(monkeypatch, app, ws, mailbox_id, email_id, client_key="draft-0001")

    response = await post_reply(client, ws, email_id, key="draft-0001")

    assert response.status_code == 200
    assert response.json()["status"] == "sending"
    assert fake_connector.calls.count("send_reply") == 0


async def test_other_draft_race_is_409(app, client, fake_connector, monkeypatch):
    ws, mailbox_id, email_id = await setup(app, client)
    race(monkeypatch, app, ws, mailbox_id, email_id, client_key="draft-other")

    response = await post_reply(client, ws, email_id, key="draft-0001")

    assert response.status_code == 409
    assert response.json()["detail"] == "already_sending"
    assert fake_connector.calls.count("send_reply") == 0
