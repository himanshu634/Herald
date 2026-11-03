"""Run one email through the triage graph and act on the decision."""

import logging
import time
from datetime import datetime

from asyncer import asyncify
from sqlmodel import Session

from herald_core.graph import triage
from herald_core.history import EmailContext, History
from herald_core.schema import Alert, Decision, Notes, Route, WorkspaceConfig
from herald_server.bus import BusEvent
from herald_server.events import ALERT_SENT, EMAIL_NOTED, add_event, to_bus
from herald_server.models import STATUS_FOR_ROUTE, Email, Workspace
from herald_server.services import Services
from herald_server.tools import build_toolbox

log = logging.getLogger(__name__)


def _load(services: Services, email_id: str) -> tuple[Email, str, WorkspaceConfig, datetime]:
    with Session(services.engine) as session:
        email = session.get(Email, email_id)
        if email is None:
            raise LookupError(f"email {email_id} not found")
        workspace = session.get(Workspace, email.workspace_id)
        assert workspace is not None
        # received_at is read back from the row (naive), the same way the history tools compare it.
        return (
            email,
            workspace.name,
            WorkspaceConfig.model_validate(workspace.config),
            email.received_at,
        )


def _save(
    services: Services,
    email_id: str,
    notes: Notes | None,
    decision: Decision,
    context: EmailContext,
) -> tuple[Email, BusEvent]:
    with Session(services.engine) as session:
        email = session.get(Email, email_id)
        assert email is not None
        email.notes = notes.model_dump(mode="json") if notes else None
        email.decision = decision.model_dump(mode="json")
        email.context = context.model_dump(mode="json")
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
                "context": email.context,
            },
        )
        session.commit()
        session.refresh(email)
        session.refresh(event)
        return email, to_bus(event)


def _record_alert(services: Services, email: Email, alert: Alert) -> BusEvent:
    with Session(services.engine) as session:
        event = add_event(session, email.workspace_id, ALERT_SENT, alert.model_dump(mode="json"))
        session.commit()
        session.refresh(event)
        return to_bus(event)


async def _run(
    services: Services, email: Email, name: str, config: WorkspaceConfig, received_at: datetime
) -> tuple[Notes | None, Decision, EmailContext, int]:
    tools = build_toolbox(services.engine, email.workspace_id, email.id, received_at)
    started = time.perf_counter()
    state = await triage(services.graph, email.to_core(), config, business_name=name, tools=tools)
    total_ms = round((time.perf_counter() - started) * 1000)
    # Copy the toolbox's list and dict so nothing that runs later can change what we save.
    context = EmailContext.from_run(
        state.get("history") or History(), list(tools.failed), dict(tools.ms) | {"triage": total_ms}
    )
    return state.get("notes"), state["decision"], context, total_ms


async def trial_read(
    services: Services, email_id: str, config: WorkspaceConfig
) -> tuple[Notes | None, Decision]:
    """What Herald would make of this email with a draft config. Writes and publishes nothing.

    The owner tries a fact or rule change on one email before keeping it, so this must leave
    the email, its events and the saved config exactly as they were.
    """
    email, name, _saved, received_at = await asyncify(_load)(services, email_id)
    notes, decision, _context, total_ms = await _run(services, email, name, config, received_at)
    log.info(
        "email %s trial read in %d ms: route=%s rules=%s",
        email.id,
        total_ms,
        decision.route,
        ",".join(decision.fired_rule_ids) or "none",
    )
    return notes, decision


async def process_email(services: Services, email_id: str) -> Decision:
    email, name, config, received_at = await asyncify(_load)(services, email_id)
    log.info("email %s triage started in workspace %s", email.id, email.workspace_id)
    notes, decision, context, total_ms = await _run(services, email, name, config, received_at)
    log.info(
        "email %s triaged in %d ms: route=%s urgency=%s rules=%s floor=%s notes=%s failed tools=%s",
        email.id,
        total_ms,
        decision.route,
        decision.urgency,
        ",".join(decision.fired_rule_ids) or "none",
        ",".join(decision.floor_flags) or "none",
        "yes" if notes else "no",
        ",".join(context.failed) or "none",
    )

    email, event = await asyncify(_save)(services, email_id, notes, decision, context)
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
        await services.bus.publish(await asyncify(_record_alert)(services, email, alert))
        log.info("email %s alert recorded", email.id)
    return decision
