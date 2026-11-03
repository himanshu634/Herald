from datetime import datetime

from pydantic import BaseModel, Field

from herald_core.schema import Decision, Notes, WorkspaceConfig
from herald_server.models import EmailStatus, MailboxStatus


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


class MailboxOut(BaseModel):
    """A connected mailbox. Never carries credentials, the cursor or provider state."""

    id: str
    workspace_id: str
    provider: str
    email_address: str
    status: MailboxStatus
    subscription_expires_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime


class ConnectOut(BaseModel):
    authorization_url: str
