"""Internal routes for the triage pipeline: load an email, run history lookups, save the result.

Only the worker calls these (or the inline queue, in memory). They sit outside /api, so nginx
and the Vite proxy never forward them, they are left out of the OpenAPI schema, and every call
needs the internal token. Each route is keyed by the email being judged: the workspace and the
"received before" cut-off come from that row, so no caller can pick another tenant.
"""

import hmac
import logging
from collections.abc import Callable
from typing import Annotated

from asyncer import asyncify
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from herald_core.history import (
    Corrections,
    CorrectionsIn,
    SenderHistory,
    SenderHistoryIn,
    Thread,
    ThreadIn,
)
from herald_core.schema import Alert, Route, WorkspaceConfig
from herald_server.api.deps import ServicesDep
from herald_server.bus import BusEvent
from herald_server.events import ALERT_SENT, EMAIL_NOTED, add_event, to_bus
from herald_server.internal import history
from herald_server.internal.client import PREFIX
from herald_server.internal.history import Scope
from herald_server.internal.schemas import TriageInput, TriageResult
from herald_server.internal.token import TOKEN_HEADER
from herald_server.models import STATUS_FOR_ROUTE, Email, Workspace
from herald_server.services import Services

log = logging.getLogger(__name__)


def check_token(
    request: Request, token: Annotated[str | None, Header(alias=TOKEN_HEADER)] = None
) -> None:
    expected: str = request.app.state.internal_token
    # Constant time, so the answer's timing does not give the token away a byte at a time.
    if token is None or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad internal token")


router = APIRouter(
    prefix=f"{PREFIX}/emails/{{email_id}}",
    include_in_schema=False,
    dependencies=[Depends(check_token)],
)

EmailId = Annotated[str, Path()]


def _email(session: Session, email_id: str) -> Email:
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


def _load(services: Services, email_id: str) -> TriageInput:
    with Session(services.engine) as session:
        email = _email(session, email_id)
        workspace = session.get(Workspace, email.workspace_id)
        assert workspace is not None
        return TriageInput(
            email=email.to_core(),
            business_name=workspace.name,
            config=WorkspaceConfig.model_validate(workspace.config),
        )


def _save(services: Services, email_id: str, result: TriageResult) -> list[BusEvent]:
    notes, decision = result.notes, result.decision
    with Session(services.engine) as session:
        email = _email(session, email_id)
        email.notes = notes.model_dump(mode="json") if notes else None
        email.decision = decision.model_dump(mode="json")
        email.context = result.context.model_dump(mode="json")
        # The AI never sets status: it follows the route decide chose.
        email.status = STATUS_FOR_ROUTE[decision.route]
        events = [
            add_event(
                session,
                email.workspace_id,
                EMAIL_NOTED,
                {
                    "email_id": email.id,
                    "status": email.status,
                    "notes": email.notes,
                    "decision": email.decision,
                    "context": email.context,
                },
            )
        ]
        if decision.route is Route.ALERT:
            alert = Alert(
                workspace_id=email.workspace_id,
                email_id=email.id,
                title=f"Herald: {email.subject}"[:120],
                summary=notes.summary if notes else email.subject,
                reason=decision.reason,
                quote=notes.quotes[0].text if notes and notes.quotes else None,
                link=f"{services.settings.web_url}/emails/{email.id}",
            )
            events.append(
                add_event(session, email.workspace_id, ALERT_SENT, alert.model_dump(mode="json"))
            )
        # One commit for the result and its events, staged in order, so email.noted always
        # has the lower id and SSE replay sends the note before its alert.
        session.commit()
        for event in events:
            session.refresh(event)
        return [to_bus(event) for event in events]


def _lookup[In: BaseModel, Out: BaseModel](
    services: Services,
    email_id: str,
    query: Callable[[Session, Scope, In], Out],
    args: In,
) -> Out:
    with Session(services.engine) as session:
        return query(session, Scope.of(_email(session, email_id)), args)


@router.get("/triage-input")
async def triage_input(email_id: EmailId, services: ServicesDep) -> TriageInput:
    return await asyncify(_load)(services, email_id)


@router.post("/triage-result", status_code=status.HTTP_204_NO_CONTENT)
async def save_triage_result(
    email_id: EmailId, result: TriageResult, services: ServicesDep
) -> None:
    # Publish only after the commit: a tab must never hear about a change the database lacks.
    for event in await asyncify(_save)(services, email_id, result):
        await services.bus.publish(event)
    if result.decision.route is Route.ALERT:
        log.info("email %s alert recorded", email_id)


@router.get("/history/sender")
async def sender_history(
    email_id: EmailId, args: Annotated[SenderHistoryIn, Query()], services: ServicesDep
) -> SenderHistory:
    return await asyncify(_lookup)(services, email_id, history.sender_history, args)


@router.get("/history/thread")
async def thread(
    email_id: EmailId, args: Annotated[ThreadIn, Query()], services: ServicesDep
) -> Thread:
    return await asyncify(_lookup)(services, email_id, history.thread, args)


@router.get("/history/corrections")
async def corrections(
    email_id: EmailId, args: Annotated[CorrectionsIn, Query()], services: ServicesDep
) -> Corrections:
    return await asyncify(_lookup)(services, email_id, history.corrections, args)
