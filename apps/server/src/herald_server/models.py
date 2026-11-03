"""Database tables. Every tenant-owned row carries `workspace_id`; every query filters on it."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from herald_core.schema import Email as CoreEmail
from herald_core.schema import Route


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class EmailStatus(StrEnum):
    """Where an email stands. Moved only by the decide step and the owner's actions."""

    NEW = "new"
    ALERTED = "alerted"
    NEEDS_A_LOOK = "needs_a_look"
    INBOX = "inbox"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CLOSED = "closed"


STATUS_FOR_ROUTE = {
    Route.ALERT: EmailStatus.ALERTED,
    Route.NEEDS_A_LOOK: EmailStatus.NEEDS_A_LOOK,
    Route.INBOX: EmailStatus.INBOX,
    Route.CLOSED: EmailStatus.CLOSED,
}


class Workspace(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    name: str
    # A serialized herald_core.schema.WorkspaceConfig.
    config: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_now)


class Email(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    sender: str
    subject: str
    body: str
    status: EmailStatus = Field(default=EmailStatus.NEW, index=True)
    notes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    decision: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    received_at: datetime = Field(default_factory=_now)

    def to_core(self) -> CoreEmail:
        return CoreEmail(
            id=self.id,
            workspace_id=self.workspace_id,
            sender=self.sender,
            subject=self.subject,
            body=self.body,
        )


class Correction(SQLModel, table=True):
    """An owner override, kept as an example for that business."""

    id: str = Field(default_factory=_id, primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    email_id: str = Field(foreign_key="email.id")
    field: str
    from_value: str | None
    to_value: str
    created_at: datetime = Field(default_factory=_now)


class Event(SQLModel, table=True):
    """Every SSE event, stored so a reconnecting tab can replay what it missed."""

    id: int | None = Field(default=None, primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    type: str
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_now)
