"""Recording events: store first (for replay), publish after the commit."""

from typing import Any

from sqlmodel import Session, col, select

from herald_server.bus import BusEvent
from herald_server.models import Event

EMAIL_RECEIVED = "email.received"
EMAIL_NOTED = "email.noted"
EMAIL_STATUS = "email.status"
ALERT_SENT = "alert.sent"
MAILBOX_STATUS = "mailbox.status"
REPLY_STATUS = "reply.status"  # data: email_id, reply_id, status


def add_event(session: Session, workspace_id: str, type_: str, data: dict[str, Any]) -> Event:
    """Stage an event in the caller's transaction. Publish it with `to_bus` after commit."""
    event = Event(workspace_id=workspace_id, type=type_, data=data)
    session.add(event)
    return event


def to_bus(event: Event) -> BusEvent:
    assert event.id is not None, "publish only committed events"
    return BusEvent.model_validate(event, from_attributes=True)


def events_after(session: Session, workspace_id: str, last_id: int) -> list[BusEvent]:
    rows = session.exec(
        select(Event)
        .where(Event.workspace_id == workspace_id, col(Event.id) > last_id)
        .order_by(col(Event.id))
    ).all()
    return [to_bus(row) for row in rows]
