from fastapi import APIRouter, status
from sqlmodel import col, select

from herald_server.api.deps import SessionDep, WorkspaceDep
from herald_server.api.schemas import WorkspaceIn, WorkspaceOut
from herald_server.models import Workspace
from herald_server.seed import TRIPFOLD, TRIPFOLD_NAME

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _create(session: SessionDep, data: WorkspaceIn) -> Workspace:
    workspace = Workspace(name=data.name, config=data.config.model_dump(mode="json"))
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@router.get("")
def list_workspaces(session: SessionDep) -> list[WorkspaceOut]:
    rows = session.exec(select(Workspace).order_by(col(Workspace.created_at))).all()
    return [WorkspaceOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(data: WorkspaceIn, session: SessionDep) -> WorkspaceOut:
    return WorkspaceOut.model_validate(_create(session, data), from_attributes=True)


@router.post("/demo", status_code=status.HTTP_201_CREATED)
def create_demo_workspace(session: SessionDep) -> WorkspaceOut:
    workspace = _create(session, WorkspaceIn(name=TRIPFOLD_NAME, config=TRIPFOLD))
    return WorkspaceOut.model_validate(workspace, from_attributes=True)


# workspace_id is read by WorkspaceDep.
@router.get("/{workspace_id}")  # noqa: FAST003
def get_workspace(workspace: WorkspaceDep) -> WorkspaceOut:
    return WorkspaceOut.model_validate(workspace, from_attributes=True)
