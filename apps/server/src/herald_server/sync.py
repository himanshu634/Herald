"""Pull new mail for one mailbox through its connector and store it for triage."""

import logging
from datetime import UTC, datetime

from asyncer import asyncify
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from herald_server.bus import BusEvent
from herald_server.connectors.base import AuthRevoked, FetchResult
from herald_server.crypto import BadSecret
from herald_server.events import EMAIL_RECEIVED, add_event, to_bus
from herald_server.mailboxes import get_mailbox, mark_needs_reauth
from herald_server.models import Email, Mailbox, MailboxStatus
from herald_server.services import Services

log = logging.getLogger(__name__)


def _store(
    services: Services, mailbox_id: str, result: FetchResult
) -> tuple[list[str], list[BusEvent]]:
    """Save the new emails and the new cursor in one transaction.

    They commit together so that a crash cannot move the cursor past mail that was never
    stored (lost mail), or store mail without moving the cursor (refetched, then deduped).
    """
    with Session(services.engine) as session:
        # By id alone: the job holds a trusted mailbox id. Routes filter on workspace_id first.
        mailbox = session.get(Mailbox, mailbox_id)
        if mailbox is None:
            return [], []
        incoming = [m.provider_message_id for m in result.messages]
        # Dedupe: a cursor can overlap the last sync, so some messages may be stored already.
        seen = set(
            session.exec(
                select(Email.provider_message_id).where(
                    Email.workspace_id == mailbox.workspace_id,
                    Email.mailbox_id == mailbox_id,
                    col(Email.provider_message_id).in_(incoming),
                )
            ).all()
        )
        ids: list[str] = []
        events = []
        for message in result.messages:
            # `seen` also drops a repeat inside this batch. Inserting both copies would hit
            # the unique constraint, roll back the batch and block the cursor on every sync.
            if message.provider_message_id in seen:
                continue
            seen.add(message.provider_message_id)
            email = Email(
                workspace_id=mailbox.workspace_id,
                mailbox_id=mailbox_id,
                provider_message_id=message.provider_message_id,
                sender=message.sender,
                subject=message.subject,
                body=message.body,
                received_at=message.received_at,
            )
            session.add(email)
            ids.append(email.id)
            events.append(
                add_event(
                    session,
                    mailbox.workspace_id,
                    EMAIL_RECEIVED,
                    {"email_id": email.id, "sender": email.sender, "subject": email.subject},
                )
            )
        mailbox.cursor = result.cursor
        mailbox.last_synced_at = datetime.now(UTC)
        try:
            session.commit()
        except IntegrityError:
            # Another sync of this mailbox fetched the same changes and committed first: it
            # stored these emails and moved the cursor. Keep its result, and add nothing.
            session.rollback()
            return [], []
        for event in events:
            session.refresh(event)
        return ids, [to_bus(event) for event in events]


async def sync_mailbox(services: Services, mailbox_id: str) -> list[str]:
    """Fetch and store new mail. Returns the new email ids, for the caller to triage.

    Raises `RateLimited` without moving the cursor, so the retry reads the same changes again.
    """
    mailbox = await asyncify(get_mailbox)(services, mailbox_id)
    if mailbox is None:
        log.info("sync skipped for mailbox %s: not found", mailbox_id)
        return []
    if mailbox.status != MailboxStatus.ACTIVE:
        log.info("sync skipped for mailbox %s: status is %s", mailbox_id, mailbox.status)
        return []
    if not mailbox.credentials_enc:
        log.info("sync skipped for mailbox %s: no credentials", mailbox_id)
        return []
    connector = services.connectors.get(mailbox.provider)
    if connector is None:
        log.info("sync skipped for mailbox %s: provider not configured", mailbox_id)
        return []
    if services.secrets is None:
        log.info("sync skipped for mailbox %s: token_key is not set", mailbox_id)
        return []

    # RateLimited is not caught: the cursor must stay where it is, or the changes the
    # provider refused to send now would be skipped for good. The caller retries later.
    try:
        # BadSecret: the credentials no longer decrypt (e.g. token_key changed), so only a
        # reconnect can fix this mailbox, the same as a revoke.
        credentials = services.secrets.open(mailbox.credentials_enc)
        result = await connector.fetch_changes(credentials, mailbox.cursor)
    except (AuthRevoked, BadSecret) as exc:
        # Log only the type and id: the exception may carry provider responses or tokens.
        log.warning("%s on mailbox %s", type(exc).__name__, mailbox_id)
        await mark_needs_reauth(services, mailbox_id)
        return []

    ids, events = await asyncify(_store)(services, mailbox_id, result)
    for event in events:
        await services.bus.publish(event)
    return ids
