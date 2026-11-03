from asyncer import asyncify
from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, col, select

from herald_core.schema import WorkspaceConfig
from herald_server.api.deps import ServicesDep, SessionDep, WorkspaceDep
from herald_server.api.schemas import (
    DraftOut,
    SetupIn,
    SetupOut,
    SuggestIn,
    WorkspaceIn,
    WorkspaceOut,
)
from herald_server.models import Workspace
from herald_server.seed import TRIPFOLD, TRIPFOLD_NAME
from herald_server.services import Services
from herald_server.setup import draft_config

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _out(workspace: Workspace) -> WorkspaceOut:
    return WorkspaceOut.model_validate(workspace, from_attributes=True)


def _create(
    session: Session,
    name: str,
    config: WorkspaceConfig,
    *,
    setup_done: bool = True,
    demo: bool = False,
) -> Workspace:
    workspace = Workspace(
        name=name, config=config.model_dump(mode="json"), setup_done=setup_done, demo=demo
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@router.get("")
def list_workspaces(session: SessionDep) -> list[WorkspaceOut]:
    rows = session.exec(select(Workspace).order_by(col(Workspace.created_at))).all()
    return [_out(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(data: WorkspaceIn, session: SessionDep) -> WorkspaceOut:
    return _out(_create(session, data.name, data.config))


@router.post("/demo", status_code=status.HTTP_201_CREATED)
def create_demo_workspace(session: SessionDep) -> WorkspaceOut:
    return _out(_create(session, TRIPFOLD_NAME, TRIPFOLD, demo=True))


def _create_draft(services: Services, name: str, config: WorkspaceConfig) -> WorkspaceOut:
    with Session(services.engine) as session:
        return _out(_create(session, name, config, setup_done=False))


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def start_setup(data: SetupIn, services: ServicesDep) -> SetupOut:
    """Onboarding step one: a draft workspace holding the AI's first guess at its config."""
    # The AI call runs before the write, so no session stays open while the model thinks.
    config, drafted = await draft_config(services.model, data.name, data.description)
    workspace = await asyncify(_create_draft)(services, data.name, config)
    return SetupOut(workspace=workspace, drafted=drafted)


# workspace_id is read by WorkspaceDep.
@router.get("/{workspace_id}")  # noqa: FAST003
def get_workspace(workspace: WorkspaceDep) -> WorkspaceOut:
    return _out(workspace)


@router.post("/{workspace_id}/setup/suggest")  # noqa: FAST003
async def suggest_setup(
    data: SuggestIn, workspace: WorkspaceDep, services: ServicesDep
) -> DraftOut:
    """Draft again from a new description. Saves nothing: only PUT /config writes."""
    config, drafted = await draft_config(services.model, workspace.name, data.description)
    return DraftOut(config=config, drafted=drafted)


def _save_config(services: Services, workspace_id: str, data: WorkspaceIn) -> WorkspaceOut:
    with Session(services.engine) as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        workspace.name = data.name
        workspace.config = data.config.model_dump(mode="json")
        workspace.setup_done = True
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        return _out(workspace)


@router.put("/{workspace_id}/config")  # noqa: FAST003
async def save_config(
    data: WorkspaceIn, workspace: WorkspaceDep, services: ServicesDep
) -> WorkspaceOut:
    """Save the owner's reviewed setup. Ends onboarding; also the save for later edits."""
    return await asyncify(_save_config)(services, workspace.id, data)
