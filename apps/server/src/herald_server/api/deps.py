from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
from sqlmodel import Session

from herald_server.connectors.base import MailConnector
from herald_server.crypto import SecretBox
from herald_server.models import Workspace
from herald_server.queue import JobQueue
from herald_server.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


ServicesDep = Annotated[Services, Depends(get_services)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


def get_session(services: ServicesDep) -> Iterator[Session]:
    with Session(services.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_secrets(services: ServicesDep) -> SecretBox:
    if services.secrets is None:
        raise HTTPException(status_code=503, detail="Mail connectors need HERALD_TOKEN_KEY")
    return services.secrets


SecretsDep = Annotated[SecretBox, Depends(get_secrets)]


def get_connector(provider: Annotated[str, Path()], services: ServicesDep) -> MailConnector:
    connector = services.connectors.get(provider)
    if connector is None:
        raise HTTPException(status_code=404, detail="Mail provider not available")
    return connector


ConnectorDep = Annotated[MailConnector, Depends(get_connector)]


# No auth in the skeleton. When it lands it must be a cookie: EventSource cannot send headers.
# Uses its own short session so a long SSE stream does not hold a database connection.
def get_workspace(workspace_id: Annotated[str, Path()], services: ServicesDep) -> Workspace:
    with Session(services.engine) as session:
        workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
