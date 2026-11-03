"""The owner's reply to a customer email: the checks, one send through the mailbox, the outcome.

Only the reply route calls `send_reply`, after the owner presses Send. The AI never sends.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from typing import Literal

from asyncer import asyncify
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from herald_server.api.schemas import ReplyIn
from herald_server.bus import BusEvent
from herald_server.connectors.base import (
    AuthRevoked,
    MailConnector,
    OutboundReply,
    RateLimited,
    SendNotAllowed,
    SendRejected,
)
from herald_server.events import REPLY_STATUS, add_event, to_bus
from herald_server.mailboxes import clear_can_send, mark_needs_reauth, open_credentials
from herald_server.models import (
    Email,
    EmailStatus,
    Event,
    Mailbox,
    MailboxStatus,
    Reply,
    ReplyError,
    ReplyStatus,
)
from herald_server.services import Services
from herald_server.status import stage_move

log = logging.getLogger(__name__)

# The connector call is two requests (a token refresh, then the send itself), and both run
# under SEND_TIMEOUT. A SENDING row older than STALE_SENDING therefore cannot belong to a live
# send: its process died mid-send. If STALE_SENDING were shorter than the slowest send, a live
# send would be marked unknown and a second reply could start beside it.
SEND_TIMEOUT = 60  # seconds
STALE_SENDING = timedelta(minutes=2)

BlockReason = Literal[
    "no_mailbox", "mailbox_inactive", "send_not_allowed", "already_sending", "no_recipient"
]


class ReplyBlocked(Exception):
    """The reply cannot be sent now; nothing was saved or sent (the API answers 409)."""

    def __init__(self, reason: BlockReason) -> None:
        super().__init__(reason)
        self.reason: BlockReason = reason


class EmailNotFound(Exception):
    """No such email in this workspace (the API answers 404)."""


def reply_subject(subject: str) -> str:
    """The subject of a reply: "Re: " once, never "Re: Re: "."""
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}"


def is_stale(reply: Reply) -> bool:
    """A SENDING row older than STALE_SENDING: its process died mid-send (see above)."""
    # SQLite returns naive datetimes (all written in UTC) and Postgres aware ones. Comparing a
    # naive one with an aware now() raises TypeError, so a naive value is read as UTC.
    created = reply.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return reply.status == ReplyStatus.SENDING and created < datetime.now(UTC) - STALE_SENDING


def recipient(email: Email) -> str:
    """Where a reply to this email goes. Empty when the sender could not be parsed.

    The web app's To line shows this value (`EmailOut.reply_address`), so it is the one rule.
    """
    # Reply-To is written by whoever sent the mail, so it is used only when it is one plain
    # address. A list would copy strangers in, and a CR or LF could add headers to the reply.
    # Anything else falls back to From, which the provider has already parsed.
    reply_to = email.reply_to
    if reply_to and not any(c.isspace() or not c.isprintable() for c in reply_to):
        parsed = getaddresses([reply_to])
        if len(parsed) == 1 and parsed[0][1] == reply_to:
            local, _, domain = reply_to.partition("@")
            if local and domain and "@" not in domain:
                return reply_to
    return email.sender


def _provider_thread_id(email: Email) -> str | None:
    # sync._store writes f"{mailbox_id}:{provider thread id}". Mailbox ids are hex with no
    # colon, so the provider's id is everything after the first one, colons included.
    if email.thread_id is None:
        return None
    prefix, sep, thread = email.thread_id.partition(":")
    return thread if sep and thread and prefix == email.mailbox_id else None


def _outbound(email: Email, mailbox: Mailbox, reply: Reply) -> OutboundReply:
    # In-Reply-To names the customer's mail and References the whole chain, newest last. Mail
    # clients thread the reply under the customer's email with them; without them it arrives
    # as a new conversation.
    references = " ".join(r for r in (email.references, email.internet_message_id) if r)
    return OutboundReply(
        from_address=mailbox.email_address,
        to_address=reply.to_address,
        subject=reply.subject,
        body=reply.body,
        in_reply_to=email.internet_message_id,
        references=references or None,
        provider_thread_id=_provider_thread_id(email),
    )


def _stage_status(session: Session, reply: Reply) -> Event:
    return add_event(
        session,
        reply.workspace_id,
        REPLY_STATUS,
        {"email_id": reply.email_id, "reply_id": reply.id, "status": reply.status},
    )


@dataclass
class _Begun:
    reply: Reply
    events: list[BusEvent]
    # Set only when this call must send. None means the draft's key already had a row.
    send: tuple[MailConnector, Mailbox, OutboundReply] | None = None


def _by_key(session: Session, workspace_id: str, email_id: str, client_key: str) -> Reply | None:
    reply = session.exec(
        select(Reply).where(Reply.workspace_id == workspace_id, Reply.client_key == client_key)
    ).first()
    # The key is the browser's draft id. Another email's reply must never come back for it.
    if reply is not None and reply.email_id != email_id:
        raise ReplyBlocked("already_sending")
    return reply


def _expire_stale(session: Session, workspace_id: str, email_id: str) -> list[Event]:
    # A SENDING row older than STALE_SENDING belongs to a process that died mid-send. Left
    # alone it would block this email's replies forever. It turns UNKNOWN, not NOT_SENT: the
    # customer may have the email. Compared in SQL, because SQLite returns naive datetimes.
    stale = session.exec(
        select(Reply).where(
            Reply.workspace_id == workspace_id,
            Reply.email_id == email_id,
            Reply.status == ReplyStatus.SENDING,
            col(Reply.created_at) < datetime.now(UTC) - STALE_SENDING,
        )
    ).all()
    events = []
    for reply in stale:
        log.warning("reply %s was left sending; marked unknown", reply.id)
        reply.status = ReplyStatus.UNKNOWN
        reply.error = "unknown"
        session.add(reply)
        events.append(_stage_status(session, reply))
    # Flushed before the new SENDING row is added, so uq_reply_one_sending never sees both.
    session.flush()
    return events


def _begin(services: Services, workspace_id: str, email_id: str, data: ReplyIn) -> _Begun:
    """Check, then save a SENDING row. The row is committed before the send starts."""
    # expire_on_commit=False: every field is set in Python or by the flush, and the caller
    # reads the mailbox and the reply after this session has closed.
    with Session(services.engine, expire_on_commit=False) as session:
        email = session.get(Email, email_id)
        if email is None or email.workspace_id != workspace_id:
            raise EmailNotFound
        # The key comes before the mailbox checks. A resend of a draft whose send failed and
        # cleared can_send must get its own not_sent row back, not a 409.
        existing = _by_key(session, workspace_id, email.id, data.client_key)
        if existing is not None:
            # A resend of a draft whose process died mid-send must not show "sending" forever.
            stale_events = []
            if existing.status == ReplyStatus.SENDING:
                stale_events = _expire_stale(session, workspace_id, email.id)
                session.commit()
            return _Begun(reply=existing, events=[to_bus(e) for e in stale_events])
        mailbox = session.get(Mailbox, email.mailbox_id) if email.mailbox_id else None
        if mailbox is None or mailbox.workspace_id != workspace_id:
            raise ReplyBlocked("no_mailbox")
        connector = services.connectors.get(mailbox.provider)
        # No connector means the provider is switched off in this process (its settings are
        # unset). Checked here, before the row exists, so it cannot end as "unknown".
        if mailbox.status != MailboxStatus.ACTIVE or connector is None:
            raise ReplyBlocked("mailbox_inactive")
        if not mailbox.can_send:
            raise ReplyBlocked("send_not_allowed")
        # An empty To is a From the provider could not parse, and the provider would refuse
        # it. The shop's own address is a form sent from the shop with no usable Reply-To:
        # sending would mail the owner, not the customer. Checked before _expire_stale, which
        # writes, so a refusal saves nothing.
        to_address = recipient(email)
        if not to_address or to_address.lower() == mailbox.email_address.lower():
            raise ReplyBlocked("no_recipient")
        stale_events = _expire_stale(session, workspace_id, email.id)
        reply = Reply(
            workspace_id=workspace_id,
            email_id=email.id,
            mailbox_id=mailbox.id,
            client_key=data.client_key,
            from_address=mailbox.email_address,
            to_address=to_address,
            subject=reply_subject(email.subject),
            body=data.body,
        )
        session.add(reply)
        outbound = _outbound(email, mailbox, reply)
        try:
            session.commit()
        except IntegrityError:
            # Two requests passed the checks above at once. Either a double click with the
            # same key (the (workspace_id, client_key) constraint) or a second draft while one
            # is in flight (uq_reply_one_sending). The other request sends; this one does not.
            session.rollback()
            existing = _by_key(session, workspace_id, email.id, data.client_key)
            if existing is not None:
                return _Begun(reply=existing, events=[])
            raise ReplyBlocked("already_sending") from None
        return _Begun(
            reply=reply,
            events=[to_bus(e) for e in stale_events],
            send=(connector, mailbox, outbound),
        )


@dataclass
class _Outcome:
    status: ReplyStatus
    error: ReplyError | None = None
    provider_message_id: str | None = None
    # The grant is gone, or its stored credentials no longer open: the mailbox needs a reconnect.
    revoked: bool = False


async def _deliver(
    services: Services,
    reply_id: str,
    connector: MailConnector,
    mailbox: Mailbox,
    outbound: OutboundReply,
) -> _Outcome:
    """Call the connector once. Never retried: an unknown outcome may have reached the customer."""
    credentials = open_credentials(services, mailbox)
    if credentials is None:
        # Only a reconnect fixes credentials that no longer open, so the mailbox moves to
        # needs_reauth like a revoked grant. Without it the panel offers no Reconnect.
        return _Outcome(ReplyStatus.NOT_SENT, "auth", revoked=True)
    # The connector contract: these four mean the provider did not send. Anything else, a
    # timeout or a 5xx included, may have sent the mail, so the owner is told to check.
    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            sent = await connector.send_reply(credentials, outbound)
    except RateLimited:
        return _Outcome(ReplyStatus.NOT_SENT, "rate_limited")
    except AuthRevoked:
        return _Outcome(ReplyStatus.NOT_SENT, "auth", revoked=True)
    except SendNotAllowed:
        return _Outcome(ReplyStatus.NOT_SENT, "send_not_allowed")
    except SendRejected:
        return _Outcome(ReplyStatus.NOT_SENT, "rejected")
    except Exception as exc:
        # Only the type and id: provider errors can carry addresses, bodies or tokens.
        log.warning("%s sending reply %s", type(exc).__name__, reply_id)
        return _Outcome(ReplyStatus.UNKNOWN, "unknown")
    return _Outcome(ReplyStatus.SENT, provider_message_id=sent.provider_message_id)


def _finish(
    services: Services, workspace_id: str, reply_id: str, outcome: _Outcome, mark_done: bool
) -> tuple[Reply, list[BusEvent]]:
    """Save the outcome and, for "Send and mark done", the email's new status, in one commit."""
    with Session(services.engine) as session:
        reply = session.get(Reply, reply_id)
        assert reply is not None and reply.workspace_id == workspace_id
        reply.status = outcome.status
        reply.error = outcome.error
        reply.provider_message_id = outcome.provider_message_id
        if outcome.status == ReplyStatus.SENT:
            reply.sent_at = datetime.now(UTC)
        session.add(reply)
        events = [_stage_status(session, reply)]
        # Only a sent reply marks the email done: the customer has not heard back otherwise.
        if outcome.status == ReplyStatus.SENT and mark_done:
            email = session.get(Email, reply.email_id)
            assert email is not None
            if email.status != EmailStatus.DONE:
                events.append(stage_move(session, workspace_id, email, EmailStatus.DONE))
        session.commit()
        session.refresh(reply)
        for event in events:
            session.refresh(event)
        return reply, [to_bus(e) for e in events]


async def _publish(services: Services, events: list[BusEvent]) -> None:
    for event in events:
        try:
            await services.bus.publish(event)
        except Exception as exc:
            # The outcome is committed; only the live update is lost, and tabs replay the
            # stored event. Failing here would tell the owner a sent reply failed.
            log.warning("%s publishing event %s", type(exc).__name__, event.id)


async def send_reply(services: Services, workspace_id: str, email_id: str, data: ReplyIn) -> Reply:
    """Send the owner's reply once and return its row, whatever the outcome.

    Raises `EmailNotFound` and `ReplyBlocked`; in both cases nothing was sent.
    """
    # Three steps, so no database session is open while the provider is called: commit a
    # SENDING row (it stops a second send of this draft or this email), send, save the outcome.
    begun = await asyncify(_begin)(services, workspace_id, email_id, data)
    await _publish(services, begun.events)
    if begun.send is None:
        return begun.reply
    connector, mailbox, outbound = begun.send
    outcome = await _deliver(services, begun.reply.id, connector, mailbox, outbound)
    reply, events = await asyncify(_finish)(
        services, workspace_id, begun.reply.id, outcome, data.mark_done
    )
    await _publish(services, events)
    # After the outcome is saved, so a failure here cannot leave the reply SENDING.
    if outcome.error == "send_not_allowed":
        await asyncify(clear_can_send)(services, mailbox.id)
    elif outcome.revoked:
        await mark_needs_reauth(services, mailbox.id)
    return reply


def list_replies(services: Services, workspace_id: str, email_id: str) -> list[Reply]:
    """The email's replies, oldest first. Raises `EmailNotFound`."""
    with Session(services.engine) as session:
        email = session.get(Email, email_id)
        if email is None or email.workspace_id != workspace_id:
            raise EmailNotFound
        return list(
            session.exec(
                select(Reply)
                .where(Reply.workspace_id == workspace_id, Reply.email_id == email_id)
                .order_by(col(Reply.created_at), col(Reply.id))
            ).all()
        )
