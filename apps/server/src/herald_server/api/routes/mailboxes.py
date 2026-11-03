"""Mailboxes in one workspace: connect, list, sync now, pause, resume and disconnect."""

from typing import Annotated

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Path, status
from sqlmodel import Session, col, select

from herald_server.api.deps import (
    ConnectorDep,
    QueueDep,
    SecretsDep,
    ServicesDep,
    SessionDep,
    WorkspaceDep,
)
from herald_server.api.schemas import ConnectOut, MailboxOut
from herald_server.bus import BusEvent
from herald_server.events import to_bus
from herald_server.mailboxes import (
    StatusConflict,
    disconnect_mailbox,
    stage_status_event,
    subscribe_mailbox,
    unsubscribe_mailbox,
)
from herald_server.models import Mailbox, MailboxStatus
from herald_server.services import Services

router = APIRouter(prefix="/api/workspaces/{workspace_id}/mailboxes", tags=["mailboxes"])

MailboxId = Annotated[str, Path()]


def _out(mailbox: Mailbox) -> MailboxOut:
    return MailboxOut.model_validate(mailbox, from_attributes=True)


def _get_mailbox(session: Session, workspace_id: str, mailbox_id: str) -> Mailbox:
    # Another workspace's mailbox is a 404, the same as a missing one.
    mailbox = session.get(Mailbox, mailbox_id)
    if mailbox is None or mailbox.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return mailbox


def _load(services: Services, workspace_id: str, mailbox_id: str) -> Mailbox:
    with Session(services.engine) as session:
        return _get_mailbox(session, workspace_id, mailbox_id)


def _move(
    services: Services,
    workspace_id: str,
    mailbox_id: str,
    to: MailboxStatus,
    only_from: MailboxStatus,
) -> tuple[Mailbox, BusEvent]:
    """Owner action: change the status only from `only_from`, else 409."""
    with Session(services.engine) as session:
        # Load, check and change in one session, so a sync that marks the mailbox
        # needs_reauth in between cannot be overwritten.
        mailbox = _get_mailbox(session, workspace_id, mailbox_id)
        if mailbox.status != only_from:
            raise HTTPException(
                status_code=409, detail=f"Mailbox is {mailbox.status}, not {only_from}"
            )
        mailbox.status = to
        event = stage_status_event(session, mailbox)
        session.commit()
        session.refresh(mailbox)
        session.refresh(event)
        return mailbox, to_bus(event)


async def _act(
    services: Services,
    workspace_id: str,
    mailbox_id: str,
    to: MailboxStatus,
    only_from: MailboxStatus,
) -> Mailbox:
    mailbox, event = await asyncify(_move)(services, workspace_id, mailbox_id, to, only_from)
    await services.bus.publish(event)
    return mailbox


@router.get("")
def list_mailboxes(workspace: WorkspaceDep, session: SessionDep) -> list[MailboxOut]:
    rows = session.exec(
        select(Mailbox)
        .where(Mailbox.workspace_id == workspace.id)
        .order_by(col(Mailbox.created_at).desc())
    ).all()
    return [_out(row) for row in rows]


# provider is read by ConnectorDep.
@router.post("/{provider}/connect")  # noqa: FAST003
def start_connect(
    workspace: WorkspaceDep, secrets: SecretsDep, connector: ConnectorDep
) -> ConnectOut:
    # No auth yet, so the signed state is the only thing that ties the account the owner
    # approves to this workspace when the provider redirects back. The callback checks it.
    state = secrets.seal({"workspace_id": workspace.id, "provider": connector.provider})
    return ConnectOut(authorization_url=connector.authorization_url(state))


@router.post("/{mailbox_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_now(
    workspace: WorkspaceDep, services: ServicesDep, queue: QueueDep, mailbox_id: MailboxId
) -> MailboxOut:
    mailbox = await asyncify(_load)(services, workspace.id, mailbox_id)
    if mailbox.status != MailboxStatus.ACTIVE:
        raise HTTPException(status_code=409, detail=f"Mailbox is {mailbox.status}, not active")
    await queue.enqueue_sync(mailbox.id)
    return _out(mailbox)


@router.post("/{mailbox_id}/pause")
async def pause(
    workspace: WorkspaceDep, services: ServicesDep, mailbox_id: MailboxId
) -> MailboxOut:
    mailbox = await _act(
        services, workspace.id, mailbox_id, MailboxStatus.PAUSED, MailboxStatus.ACTIVE
    )
    await unsubscribe_mailbox(services, mailbox)
    return _out(mailbox)


@router.post("/{mailbox_id}/resume")
async def resume(
    workspace: WorkspaceDep, services: ServicesDep, queue: QueueDep, mailbox_id: MailboxId
) -> MailboxOut:
    mailbox = await _act(
        services, workspace.id, mailbox_id, MailboxStatus.ACTIVE, MailboxStatus.PAUSED
    )
    await subscribe_mailbox(services, mailbox)
    # Catch up on mail that arrived while paused; the cursor was kept.
    await queue.enqueue_sync(mailbox.id)
    return _out(await asyncify(_load)(services, workspace.id, mailbox.id))


@router.delete("/{mailbox_id}")
async def disconnect(
    workspace: WorkspaceDep, services: ServicesDep, mailbox_id: MailboxId
) -> MailboxOut:
    mailbox = await asyncify(_load)(services, workspace.id, mailbox_id)
    try:
        mailbox = await disconnect_mailbox(services, mailbox)
    except StatusConflict as exc:
        raise HTTPException(status_code=409, detail=f"Mailbox is {exc.status}") from exc
    return _out(mailbox)
