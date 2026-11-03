from datetime import datetime

from pydantic import BaseModel, Field

from herald_core.schema import Decision, Notes, WorkspaceConfig
from herald_server.models import EmailStatus


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: WorkspaceConfig


class WorkspaceOut(BaseModel):
    id: str
    name: str
    config: WorkspaceConfig
    created_at: datetime


class EmailIn(BaseModel):
    sender: str = Field(min_length=3, max_length=320)
    subject: str = Field(max_length=500)
    body: str = Field(max_length=50_000)


class EmailOut(BaseModel):
    id: str
    workspace_id: str
    sender: str
    subject: str
    body: str
    status: EmailStatus
    notes: Notes | None
    decision: Decision | None
    received_at: datetime
