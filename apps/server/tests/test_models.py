"""Tests for the mailbox table and the unique rules on email source columns."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from herald_server.models import Email, Mailbox, MailboxStatus, Workspace


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _workspace(session: Session) -> Workspace:
    ws = Workspace(name="Acme", config={})
    session.add(ws)
    session.commit()
    return ws


def _mailbox(ws: Workspace, address: str = "a@x.com") -> Mailbox:
    return Mailbox(
        workspace_id=ws.id,
        provider="gmail",
        email_address=address,
        status=MailboxStatus.ACTIVE,
    )


def _email(ws: Workspace, mailbox_id: str | None = None, message_id: str | None = None) -> Email:
    return Email(
        workspace_id=ws.id,
        sender="s@x.com",
        subject="Hi",
        body="Body",
        mailbox_id=mailbox_id,
        provider_message_id=message_id,
    )


def test_same_message_twice_in_one_mailbox_is_rejected(session):
    ws = _workspace(session)
    box = _mailbox(ws)
    session.add(box)
    session.commit()
    session.add(_email(ws, box.id, "m1"))
    session.commit()
    session.add(_email(ws, box.id, "m1"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_message_id_in_two_mailboxes_is_allowed(session):
    ws = _workspace(session)
    box_a, box_b = _mailbox(ws, "a@x.com"), _mailbox(ws, "b@x.com")
    session.add_all([box_a, box_b])
    session.commit()
    session.add_all([_email(ws, box_a.id, "m1"), _email(ws, box_b.id, "m1")])
    session.commit()


def test_test_box_emails_without_mailbox_do_not_collide(session):
    ws = _workspace(session)
    session.add_all([_email(ws), _email(ws)])
    session.commit()


def test_one_address_per_provider_per_workspace(session):
    ws = _workspace(session)
    session.add(_mailbox(ws))
    session.commit()
    session.add(_mailbox(ws))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("status", [MailboxStatus.PAUSED, MailboxStatus.NEEDS_REAUTH])
def test_address_live_in_two_workspaces_is_rejected(session, status):
    ws, other = _workspace(session), _workspace(session)
    session.add(_mailbox(ws))
    session.commit()
    second = _mailbox(other)
    second.status = status
    session.add(second)
    with pytest.raises(IntegrityError):
        session.commit()


def test_disconnected_address_does_not_block_another_workspace(session):
    ws, other = _workspace(session), _workspace(session)
    gone = _mailbox(ws)
    gone.status = MailboxStatus.DISCONNECTED
    session.add(gone)
    session.commit()
    session.add(_mailbox(other))
    session.commit()

    # The same address under another provider is another mailbox.
    elsewhere = _mailbox(ws)
    elsewhere.provider = "outlook"
    session.add(elsewhere)
    session.commit()
