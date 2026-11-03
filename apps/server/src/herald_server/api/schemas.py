from datetime import datetime

from pydantic import BaseModel, Field

from herald_core.history import EmailContext
from herald_core.schema import Decision, Notes, WorkspaceConfig
from herald_server.models import EmailStatus


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: WorkspaceConfig


class WorkspaceOut(BaseModel):
    id: str
    name: str
    config: WorkspaceConfig
    setup_done: bool
    created_at: datetime


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)


class SetupOut(BaseModel):
    workspace: WorkspaceOut
    drafted: bool = Field(description="False when the AI failed and a plain fallback was used.")


class SuggestIn(BaseModel):
    description: str = Field(min_length=1, max_length=2000)


class DraftOut(BaseModel):
    config: WorkspaceConfig
    drafted: bool = Field(description="False when the AI failed and a plain fallback was used.")


class ConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: WorkspaceConfig


class EmailIn(BaseModel):
    sender: str = Field(min_length=3, max_length=320)
    subject: str = Field(max_length=500)
    body: str = Field(max_length=50_000)
    thread_id: str | None = Field(default=None, max_length=200)


class EmailOut(BaseModel):
    id: str
    workspace_id: str
    sender: str
    subject: str
    body: str
    thread_id: str | None
    status: EmailStatus
    notes: Notes | None
    decision: Decision | None
    context: EmailContext | None
    received_at: datetime
