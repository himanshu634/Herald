"""Database tables. Every tenant-owned row carries `workspace_id`; every query filters on it."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel, col

from herald_core.schema import Email as CoreEmail
from herald_core.schema import Route


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class MailboxStatus(StrEnum):
    """Health of a connected mailbox."""

    ACTIVE = "active"
    PAUSED = "paused"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"


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
    # A serialized herald_core.schema.WorkspaceConfig. Always valid, even in a draft workspace.
    config: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # False until the owner saves the setup. A draft workspace accepts no email.
    setup_done: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class Mailbox(SQLModel, table=True):
    """A connected mail account. A reconnect updates the existing row."""

    # One row per address per provider per workspace, so a reconnect cannot add a duplicate.
    # Across workspaces, uq_mailbox_live_address (below the class) allows one live row.
    __table_args__ = (UniqueConstraint("workspace_id", "provider", "email_address"),)

    id: str = Field(default_factory=_id, primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    provider: str  # Connector registry key, e.g. "gmail".
    email_address: str = Field(index=True)  # Stored lower-case.
    status: MailboxStatus = Field(default=MailboxStatus.ACTIVE, index=True)
    credentials_enc: str | None = None  # SecretBox token; None once disconnected.
    cursor: str | None = None  # Opaque to everything but the connector.
    provider_state: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    subscription_expires_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


# One business per mailbox: an address is live in at most one workspace, so its mail is triaged
# under one business's rules. Partial, because a disconnected row keeps its emails and is
# reused if that workspace connects again; counting it would block the address forever. Built
# from the column, not a SQL string: the status column stores the enum name ('DISCONNECTED').
Index(
    "uq_mailbox_live_address",
    col(Mailbox.provider),
    col(Mailbox.email_address),
    unique=True,
    postgresql_where=col(Mailbox.status) != MailboxStatus.DISCONNECTED,
    sqlite_where=col(Mailbox.status) != MailboxStatus.DISCONNECTED,
)


class Email(SQLModel, table=True):
    # One tuple: a second __table_args__ assignment would silently drop the first.
    __table_args__ = (
        # Dedupe for synced mail. Test-box emails leave both columns NULL, and NULLs never collide.
        UniqueConstraint("mailbox_id", "provider_message_id"),
        # History looks up a sender's earlier mail in one workspace, newest first.
        Index("ix_email_ws_sender_received", "workspace_id", "sender", "received_at"),
    )

    id: str = Field(default_factory=_id, primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    mailbox_id: str | None = Field(default=None, foreign_key="mailbox.id", index=True)
    provider_message_id: str | None = None
    sender: str
    subject: str
    body: str
    thread_id: str | None = Field(default=None, index=True)
    status: EmailStatus = Field(default=EmailStatus.NEW, index=True)
    notes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    decision: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # A serialized herald_core.history.EmailContext: what the history tools gathered.
    context: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    received_at: datetime = Field(default_factory=_now)

    def to_core(self) -> CoreEmail:
        return CoreEmail(
            id=self.id,
            workspace_id=self.workspace_id,
            sender=self.sender,
            subject=self.subject,
            body=self.body,
            thread_id=self.thread_id,
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
