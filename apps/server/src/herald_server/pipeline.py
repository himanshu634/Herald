"""Run one email through the triage graph and act on the decision."""

import logging

from asyncer import asyncify
from sqlmodel import Session

from herald_core.adapters import Alert
from herald_core.graph import triage
from herald_core.schema import Decision, Notes, Route, WorkspaceConfig
from herald_server.bus import BusEvent
from herald_server.events import ALERT_SENT, EMAIL_NOTED, add_event, to_bus
from herald_server.models import STATUS_FOR_ROUTE, Email, Workspace
from herald_server.services import Services

log = logging.getLogger(__name__)


def _load(services: Services, email_id: str) -> tuple[Email, str, WorkspaceConfig]:
    with Session(services.engine) as session:
        email = session.get(Email, email_id)
        if email is None:
            raise LookupError(f"email {email_id} not found")
        workspace = session.get(Workspace, email.workspace_id)
        assert workspace is not None
        return email, workspace.name, WorkspaceConfig.model_validate(workspace.config)


def _save(
    services: Services, email_id: str, notes: Notes | None, decision: Decision
) -> tuple[Email, list[BusEvent]]:
    with Session(services.engine) as session:
        email = session.get(Email, email_id)
        assert email is not None
        email.notes = notes.model_dump(mode="json") if notes else None
        email.decision = decision.model_dump(mode="json")
        email.status = STATUS_FOR_ROUTE[decision.route]
        event = add_event(
            session,
            email.workspace_id,
            EMAIL_NOTED,
            {
                "email_id": email.id,
                "status": email.status,
                "notes": email.notes,
                "decision": email.decision,
            },
        )
        session.commit()
        session.refresh(email)
        session.refresh(event)
        return email, [to_bus(event)]


def _record_alert(services: Services, email: Email, alert: Alert) -> list[BusEvent]:
    with Session(services.engine) as session:
        event = add_event(session, email.workspace_id, ALERT_SENT, alert.model_dump(mode="json"))
        session.commit()
        session.refresh(event)
        return [to_bus(event)]


async def process_email(services: Services, email_id: str) -> Decision:
    email, name, config = await asyncify(_load)(services, email_id)
    state = await triage(services.graph, email.to_core(), config, business_name=name)
    notes, decision = state.get("notes"), state["decision"]

    email, events = await asyncify(_save)(services, email_id, notes, decision)
    for event in events:
        await services.bus.publish(event)

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
        try:
            await services.notifier.send(alert)
        except Exception:
            # The email is already "alerted" in the inbox; a failed push must not lose it.
            log.exception("notifier failed for email %s", email.id)
        else:
            for event in await asyncify(_record_alert)(services, email, alert):
                await services.bus.publish(event)
    return decision
