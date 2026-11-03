"""Emails in one workspace: the test-email box, the inbox list and the owner's actions."""

import logging
from typing import Annotated

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlmodel import Session, col, select

from herald_server.api.deps import QueueDep, ServicesDep, SessionDep, WorkspaceDep
from herald_server.api.schemas import EmailIn, EmailOut, TryIn, TryOut
from herald_server.bus import BusEvent
from herald_server.events import EMAIL_RECEIVED, EMAIL_STATUS, add_event, to_bus
from herald_server.models import STATUS_FOR_ROUTE, Correction, Email, EmailStatus
from herald_server.pipeline import trial_read
from herald_server.services import Services

router = APIRouter(prefix="/api/workspaces/{workspace_id}/emails", tags=["emails"])

EmailId = Annotated[str, Path()]

log = logging.getLogger(__name__)


def _out(email: Email) -> EmailOut:
    return EmailOut.model_validate(email, from_attributes=True)


def _get_email(session: Session, workspace_id: str, email_id: str) -> Email:
    email = session.get(Email, email_id)
    if email is None or email.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


def _check_email(services: Services, workspace_id: str, email_id: str) -> None:
    with Session(services.engine) as session:
        _get_email(session, workspace_id, email_id)


def _store_received(
    services: Services, workspace_id: str, data: EmailIn
) -> tuple[EmailOut, BusEvent]:
    with Session(services.engine) as session:
        # History matches senders by exact string, so store them in one canonical form.
        email = Email(
            workspace_id=workspace_id,
            **{**data.model_dump(), "sender": data.sender.strip().lower()},
        )
        session.add(email)
        event = add_event(
            session,
            workspace_id,
            EMAIL_RECEIVED,
            {"email_id": email.id, "sender": email.sender, "subject": email.subject},
        )
        session.commit()
        session.refresh(email)
        session.refresh(event)
        return _out(email), to_bus(event)


# The route decide chose, for each status the owner can send back to the inbox.
_OVERRIDDEN_ROUTE = {EmailStatus.ALERTED: "alert", EmailStatus.CLOSED: "closed"}


def _move(
    services: Services,
    workspace_id: str,
    email_id: str,
    to: EmailStatus,
    only_from: EmailStatus | None,
) -> tuple[EmailOut, BusEvent]:
    """Owner action: the only way, besides the decide step, that an email's status changes."""
    with Session(services.engine) as session:
        email = _get_email(session, workspace_id, email_id)
        previous = email.status
        if only_from is not None and previous is not only_from:
            raise HTTPException(status_code=409, detail=f"Email is {previous}, not {only_from}")
        email.status = to
        event = add_event(
            session, workspace_id, EMAIL_STATUS, {"email_id": email.id, "from": previous, "to": to}
        )
        # The owner overrode the decide step. Saved so the model sees it on later emails.
        overridden = _OVERRIDDEN_ROUTE.get(previous) if to is EmailStatus.INBOX else None
        if overridden is not None:
            session.add(
                Correction(
                    workspace_id=workspace_id,
                    email_id=email.id,
                    field="route",
                    from_value=overridden,
                    to_value="inbox",
                )
            )
        session.commit()
        session.refresh(email)
        session.refresh(event)
        return _out(email), to_bus(event)


async def _act(
    services: Services,
    workspace_id: str,
    email_id: str,
    to: EmailStatus,
    only_from: EmailStatus | None = None,
) -> EmailOut:
    email, event = await asyncify(_move)(services, workspace_id, email_id, to, only_from)
    await services.bus.publish(event)
    return email


@router.get("")
def list_emails(
    workspace: WorkspaceDep,
    session: SessionDep,
    status_: Annotated[EmailStatus | None, Query(alias="status")] = None,
) -> list[EmailOut]:
    query = select(Email).where(Email.workspace_id == workspace.id)
    if status_ is not None:
        query = query.where(Email.status == status_)
    rows = session.exec(query.order_by(col(Email.received_at).desc())).all()
    return [_out(row) for row in rows]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_test_email(
    data: EmailIn, workspace: WorkspaceDep, services: ServicesDep, queue: QueueDep
) -> EmailOut:
    # A draft workspace's config is the AI's unchecked guess; triage nothing against it.
    if not workspace.setup_done:
        raise HTTPException(status_code=409, detail="Finish setup before sending email")
    email, event = await asyncify(_store_received)(services, workspace.id, data)
    log.info("email %s arrived as a test email in workspace %s", email.id, workspace.id)
    await services.bus.publish(event)
    await queue.enqueue_email(email.id)
    return email


@router.get("/{email_id}")
def get_email(workspace: WorkspaceDep, session: SessionDep, email_id: EmailId) -> EmailOut:
    return _out(_get_email(session, workspace.id, email_id))


# Statuses the decide step set and the owner has not taken over. Re-reading runs decide again,
# so an email the owner is working on (in progress) or finished (done) must not be moved by it.
_REREADABLE = {
    EmailStatus.ALERTED,
    EmailStatus.NEEDS_A_LOOK,
    EmailStatus.INBOX,
    EmailStatus.CLOSED,
}


@router.post("/{email_id}/reread", status_code=status.HTTP_202_ACCEPTED)
async def reread(
    workspace: WorkspaceDep,
    session: SessionDep,
    queue: QueueDep,
    email_id: EmailId,
) -> EmailOut:
    """Run the email through triage again, with the business's current facts and rules."""
    email = _get_email(session, workspace.id, email_id)
    if email.status not in _REREADABLE:
        raise HTTPException(
            status_code=409, detail=f"Email is {email.status}; Herald re-reads only new mail"
        )
    # The owner already moved this email by hand (Not urgent, Move to Inbox). Decide would
    # run again and could put it straight back where they moved it from.
    corrected = session.exec(
        select(Correction.id).where(
            Correction.workspace_id == workspace.id,
            Correction.email_id == email.id,
            Correction.field == "route",
        )
    ).first()
    if corrected is not None:
        raise HTTPException(status_code=409, detail="You moved this email yourself")
    log.info("email %s queued for a re-read", email.id)
    await queue.enqueue_email(email.id)
    return _out(email)


@router.post("/{email_id}/try")
async def try_config(
    data: TryIn,
    workspace: WorkspaceDep,
    services: ServicesDep,
    email_id: EmailId,
) -> TryOut:
    """Read the email with a draft config and say what Herald would do. Saves nothing.

    Runs in the request, not the queue: the owner is waiting on the answer in the dialog.
    The tenant check uses its own short session, so no connection stays open while the
    model thinks.
    """
    await asyncify(_check_email)(services, workspace.id, email_id)
    notes, decision = await trial_read(services, email_id, data.config)
    return TryOut(status=STATUS_FOR_ROUTE[decision.route], notes=notes, decision=decision)


@router.post("/{email_id}/on-it")
async def mark_on_it(workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId) -> EmailOut:
    return await _act(services, workspace.id, email_id, EmailStatus.IN_PROGRESS)


@router.post("/{email_id}/not-urgent")
async def mark_not_urgent(
    workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId
) -> EmailOut:
    return await _act(
        services, workspace.id, email_id, EmailStatus.INBOX, only_from=EmailStatus.ALERTED
    )


@router.post("/{email_id}/done")
async def mark_done(workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId) -> EmailOut:
    return await _act(services, workspace.id, email_id, EmailStatus.DONE)


@router.post("/{email_id}/to-inbox")
async def move_to_inbox(
    workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId
) -> EmailOut:
    return await _act(
        services, workspace.id, email_id, EmailStatus.INBOX, only_from=EmailStatus.CLOSED
    )
