"""Connected mailboxes: connect, disconnect, lookups and status changes, for every provider."""

import logging

from asyncer import asyncify
from sqlmodel import Session, select

from herald_server.bus import BusEvent
from herald_server.connectors.base import (
    AuthRevoked,
    ConnectedAccount,
    MailConnector,
    Subscription,
)
from herald_server.crypto import BadSecret
from herald_server.events import MAILBOX_STATUS, add_event, to_bus
from herald_server.models import Event, Mailbox, MailboxStatus
from herald_server.services import Services

log = logging.getLogger(__name__)


class StatusConflict(Exception):
    """The mailbox is not in a status that allows this change (the API answers 409)."""

    def __init__(self, status: MailboxStatus) -> None:
        super().__init__(f"Mailbox is {status}")
        self.status = status


def stage_status_event(session: Session, mailbox: Mailbox) -> Event:
    """Stage `mailbox.status` with the mailbox's current status. Publish it after commit."""
    return add_event(
        session,
        mailbox.workspace_id,
        MAILBOX_STATUS,
        {
            "mailbox_id": mailbox.id,
            "email_address": mailbox.email_address,
            "status": mailbox.status,
        },
    )


def get_mailbox(services: Services, mailbox_id: str) -> Mailbox | None:
    """By id alone, for jobs. A route must also check the mailbox's `workspace_id`."""
    with Session(services.engine) as session:
        return session.get(Mailbox, mailbox_id)


def set_status(
    services: Services,
    mailbox_id: str,
    status: MailboxStatus,
    *,
    only_from: MailboxStatus | None = None,
) -> BusEvent | None:
    """Save the new status and its `mailbox.status` event. Publish the returned event.

    With `only_from`, change nothing and return None unless the mailbox is in that status.
    By id alone, for jobs that hold a trusted mailbox id. A route must first load the
    mailbox filtered by `workspace_id`.
    """
    with Session(services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        if mailbox is None:
            raise LookupError(f"mailbox {mailbox_id} not found")
        # Checked in this session, against the committed row: the caller's copy may be stale.
        if only_from is not None and mailbox.status != only_from:
            return None
        mailbox.status = status
        event = stage_status_event(session, mailbox)
        session.commit()
        session.refresh(event)
        return to_bus(event)


async def mark_needs_reauth(services: Services, mailbox_id: str) -> None:
    """Mark the mailbox needs_reauth and publish the status, if it is still ACTIVE."""
    # Only from ACTIVE: the owner may have paused or disconnected the mailbox while the
    # provider call was in flight. Overwriting that with NEEDS_REAUTH would undo their choice
    # and publish a false status event.
    event = await asyncify(set_status)(
        services, mailbox_id, MailboxStatus.NEEDS_REAUTH, only_from=MailboxStatus.ACTIVE
    )
    if event is not None:
        await services.bus.publish(event)


def active_mailbox_ids_for_address(
    services: Services, provider: str, email_address: str
) -> list[str]:
    # Cross-tenant by design: a push names only the address, not the workspace. At most one
    # mailbox per address is live (one business per mailbox), so this is at most one id; a
    # list keeps the caller simple.
    with Session(services.engine) as session:
        return list(
            session.exec(
                select(Mailbox.id).where(
                    Mailbox.provider == provider,
                    Mailbox.email_address == email_address.lower(),
                    Mailbox.status == MailboxStatus.ACTIVE,
                )
            ).all()
        )


def active_mailbox_ids(services: Services) -> list[str]:
    # Cross-tenant by design: the catch-up cron syncs every active mailbox in every workspace.
    with Session(services.engine) as session:
        return list(
            session.exec(select(Mailbox.id).where(Mailbox.status == MailboxStatus.ACTIVE)).all()
        )


def open_credentials(services: Services, mailbox: Mailbox) -> dict[str, str] | None:
    """Decrypt the mailbox's credentials, or None when that is not possible."""
    if mailbox.credentials_enc is None or services.secrets is None:
        return None
    try:
        return services.secrets.open(mailbox.credentials_enc)
    except BadSecret:
        # Only a reconnect fixes this; the next sync marks the mailbox needs_reauth.
        log.warning("BadSecret on credentials of mailbox %s", mailbox.id)
        return None


def upsert_connected(
    services: Services, workspace_id: str, provider: str, account: ConnectedAccount
) -> tuple[Mailbox, BusEvent]:
    """Save a freshly authorized account as an ACTIVE mailbox, reusing its row on reconnect.

    Stages `mailbox.status` in the same transaction; publish the returned event.
    The cursor is kept, so a mailbox that was needs_reauth or disconnected resumes where its
    last sync stopped and no mail in the gap is skipped.
    """
    if services.secrets is None:
        raise RuntimeError("token_key is not set")
    email_address = account.email_address.lower()
    # expire_on_commit=False: every field is set in Python or by the flush (the event id), so
    # the objects are complete at commit and nothing after it touches the database. A refresh
    # after the commit could fail with the mailbox already saved, and connect_mailbox promises
    # its caller that an exception means nothing was saved.
    with Session(services.engine, expire_on_commit=False) as session:
        mailbox = session.exec(
            select(Mailbox).where(
                Mailbox.workspace_id == workspace_id,
                Mailbox.provider == provider,
                Mailbox.email_address == email_address,
            )
        ).first()
        if mailbox is None:
            mailbox = Mailbox(
                workspace_id=workspace_id, provider=provider, email_address=email_address
            )
        mailbox.credentials_enc = services.secrets.seal(account.credentials)
        mailbox.status = MailboxStatus.ACTIVE
        session.add(mailbox)
        event = stage_status_event(session, mailbox)
        session.commit()
        return mailbox, to_bus(event)


def _save_subscription(services: Services, mailbox_id: str, subscription: Subscription) -> None:
    with Session(services.engine) as session:
        # By id alone: the caller already loaded this mailbox filtered by workspace_id.
        mailbox = session.get(Mailbox, mailbox_id)
        if mailbox is None:
            return
        mailbox.subscription_expires_at = subscription.expires_at
        # provider_state is a JSON column without mutation tracking: assign a new dict.
        mailbox.provider_state = dict(subscription.provider_state)
        session.add(mailbox)
        session.commit()


async def subscribe_mailbox(services: Services, mailbox: Mailbox) -> None:
    """Start push for the mailbox and save the subscription. Best effort.

    A failure is logged and the mailbox stays ACTIVE: the renewal cron retries the subscribe,
    and the catch-up sync fetches the mail that push would have announced until then.
    """
    connector = services.connectors.get(mailbox.provider)
    credentials = open_credentials(services, mailbox)
    if connector is None or credentials is None:
        return
    try:
        subscription = await connector.subscribe(credentials, mailbox.provider_state)
    except Exception as exc:
        # Only the type and id: provider errors can carry request headers with tokens.
        log.warning("%s on subscribe of mailbox %s", type(exc).__name__, mailbox.id)
        return
    await asyncify(_save_subscription)(services, mailbox.id, subscription)


async def renew_subscriptions(services: Services) -> int:
    """Renew push for every ACTIVE mailbox. Returns how many were renewed.

    A push subscription expires (Gmail's watch after 7 days). Without renewal, new mail
    would arrive only through the 15-minute catch-up sync.
    """
    # Cross-tenant by design (cron): the daily renewal covers every workspace.
    renewed = 0
    for mailbox_id in await asyncify(active_mailbox_ids)(services):
        # Load each row just before its call: an earlier provider call may have been slow, and
        # the owner may have paused or disconnected this mailbox in the meantime.
        mailbox = await asyncify(get_mailbox)(services, mailbox_id)
        if mailbox is None or mailbox.status != MailboxStatus.ACTIVE:
            continue
        connector = services.connectors.get(mailbox.provider)
        if connector is None or mailbox.credentials_enc is None or services.secrets is None:
            continue
        try:
            # BadSecret: the credentials no longer decrypt (e.g. token_key changed), so only
            # a reconnect can fix this mailbox, the same as a revoke.
            credentials = services.secrets.open(mailbox.credentials_enc)
            subscription = await connector.subscribe(credentials, mailbox.provider_state)
            await asyncify(_save_subscription)(services, mailbox_id, subscription)
        except (AuthRevoked, BadSecret) as exc:
            # Only the type and id: provider errors can carry request headers with tokens.
            log.warning("%s on renewal of mailbox %s", type(exc).__name__, mailbox_id)
            await mark_needs_reauth(services, mailbox_id)
            continue
        except Exception as exc:
            # One failing mailbox must not stop the renewal of the others. It stays ACTIVE:
            # tomorrow's run tries again, and the catch-up sync fetches its mail until then.
            log.warning("%s on renewal of mailbox %s", type(exc).__name__, mailbox_id)
            continue
        renewed += 1
    return renewed


async def _unsubscribe(
    connector: MailConnector, mailbox: Mailbox, credentials: dict[str, str]
) -> None:
    # Best effort: the mailbox is already paused or disconnected here. A watch left running
    # expires by itself, and its pushes start no sync because the mailbox is not ACTIVE.
    try:
        await connector.unsubscribe(credentials, mailbox.provider_state)
    except Exception as exc:
        log.warning("%s on unsubscribe of mailbox %s", type(exc).__name__, mailbox.id)


async def unsubscribe_mailbox(services: Services, mailbox: Mailbox) -> None:
    """Stop push for the mailbox. Best effort; errors are logged and ignored."""
    connector = services.connectors.get(mailbox.provider)
    credentials = open_credentials(services, mailbox)
    if connector is not None and credentials is not None:
        await _unsubscribe(connector, mailbox, credentials)


async def connect_mailbox(
    services: Services, workspace_id: str, connector: MailConnector, code: str
) -> Mailbox:
    """Finish OAuth: save the account as an ACTIVE mailbox, publish the status, subscribe.

    The caller has checked that `workspace_id` exists and queues the first sync.
    Raises the connector's `MissingRefreshToken` or `AuthRevoked` for a code that cannot be used.
    Raises only before the mailbox is saved: the steps after the commit are best effort, so
    an exception always means the connect did not happen.
    """
    account = await connector.complete_authorization(code)
    mailbox, event = await asyncify(upsert_connected)(
        services, workspace_id, connector.provider, account
    )
    # Publish before subscribing: the change is committed, and a slow provider should not
    # hold back the status the owner's open tabs are waiting for.
    try:
        await services.bus.publish(event)
    except Exception as exc:
        # The status and its event are committed; only the live update to open tabs is lost,
        # and they read the stored events on reload. Failing here would tell the owner the
        # connect failed although the mailbox exists, and would skip the subscribe below.
        log.warning("%s publishing status of mailbox %s", type(exc).__name__, mailbox.id)
    try:
        await subscribe_mailbox(services, mailbox)
    except Exception as exc:
        # subscribe_mailbox absorbs provider errors but not a failed save of the subscription.
        # Push is best effort here too: the renewal cron subscribes again, and the catch-up
        # sync reads the mail until then.
        log.warning("%s subscribing mailbox %s", type(exc).__name__, mailbox.id)
    return mailbox


def _mark_disconnected(
    services: Services, mailbox_id: str
) -> tuple[Mailbox, dict[str, str] | None, BusEvent]:
    with Session(services.engine) as session:
        # By id alone: the caller loaded this mailbox filtered by workspace_id.
        mailbox = session.get(Mailbox, mailbox_id)
        if mailbox is None:
            raise LookupError(f"mailbox {mailbox_id} not found")
        # Checked in this session, against the committed row: the caller's copy may be stale.
        if mailbox.status == MailboxStatus.DISCONNECTED:
            raise StatusConflict(mailbox.status)
        # Decrypt before clearing: unsubscribe and revoke need the credentials afterwards.
        credentials = open_credentials(services, mailbox)
        mailbox.credentials_enc = None
        mailbox.status = MailboxStatus.DISCONNECTED
        event = stage_status_event(session, mailbox)
        session.commit()
        session.refresh(mailbox)
        session.refresh(event)
        return mailbox, credentials, to_bus(event)


async def disconnect_mailbox(services: Services, mailbox: Mailbox) -> Mailbox:
    """Forget the credentials and stop push. Emails already stored are kept.

    `mailbox` must have been loaded filtered by `workspace_id`.
    Raises `StatusConflict` when the mailbox is already disconnected.
    """
    # Commit first, then call the provider: the mailbox is disconnected here even when the
    # provider is slow or down, and no sync can start from it in the meantime.
    mailbox, credentials, event = await asyncify(_mark_disconnected)(services, mailbox.id)
    await services.bus.publish(event)
    connector = services.connectors.get(mailbox.provider)
    if connector is not None and credentials is not None:
        await _unsubscribe(connector, mailbox, credentials)
        try:
            await connector.revoke(credentials)
        except Exception as exc:
            # Best effort: the credentials are gone from our side already.
            log.warning("%s on revoke of mailbox %s", type(exc).__name__, mailbox.id)
    return mailbox
