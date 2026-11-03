"""Live workspace events over SSE.

One-way only: owner actions are plain POSTs. FastAPI sends a keep-alive comment every 15 s.
On reconnect the browser sends Last-Event-ID; missed events are replayed from the database.
"""

from collections.abc import AsyncIterable
from typing import Annotated

from asyncer import asyncify
from fastapi import APIRouter, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session

from herald_server.api.deps import ServicesDep, WorkspaceDep
from herald_server.bus import BusEvent
from herald_server.events import events_after

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["events"])


def _sse(event: BusEvent) -> ServerSentEvent:
    return ServerSentEvent(data=event.data, event=event.type, id=str(event.id))


@router.get("/events", response_class=EventSourceResponse)
async def stream_events(
    workspace: WorkspaceDep,
    services: ServicesDep,
    last_event_id: Annotated[int | None, Header()] = None,
) -> AsyncIterable[ServerSentEvent]:
    def missed() -> list[BusEvent]:
        with Session(services.engine) as session:
            return events_after(session, workspace.id, last_event_id or 0)

    # Subscribe before replaying so nothing published in between is lost.
    async with services.bus.subscribe(workspace.id) as live:
        seen = 0
        if last_event_id is not None:
            for event in await asyncify(missed)():
                seen = event.id
                yield _sse(event)
        async for event in live:
            if event.id > seen:
                yield _sse(event)
