from datetime import datetime

from pydantic import BaseModel, Field

from herald_core.history import EmailContext
from herald_core.schema import Decision, Notes, WorkspaceConfig
from herald_server.models import EmailStatus, MailboxStatus, ReplyError, ReplyStatus


class WorkspaceIn(BaseModel):
    """A workspace's name and config: creating one, or saving the owner's reviewed setup."""

    name: str = Field(min_length=1, max_length=100)
    config: WorkspaceConfig


class WorkspaceOut(BaseModel):
    id: str
    name: str
    config: WorkspaceConfig
    setup_done: bool
    demo: bool
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


class EmailIn(BaseModel):
    sender: str = Field(min_length=3, max_length=320)
    subject: str = Field(max_length=500)
    body: str = Field(max_length=50_000)
    thread_id: str | None = Field(default=None, max_length=200)


class EmailOut(BaseModel):
    id: str
    workspace_id: str
    mailbox_id: str | None
    sender: str
    reply_to: str | None
    reply_address: str = Field(
        description="Where a reply goes: Reply-To when it is one plain address, else the "
        "sender. Empty when there is no usable address."
    )
    subject: str
    body: str
    thread_id: str | None
    status: EmailStatus
    notes: Notes | None
    decision: Decision | None
    context: EmailContext | None
    received_at: datetime
    in_spam: bool = Field(description="Read from the mail provider's Spam folder.")


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    client_key: str = Field(
        min_length=8,
        max_length=64,
        description="The draft's id, made by the browser. The same key never sends twice.",
    )
    mark_done: bool = Field(default=False, description="Mark the email done if the reply is sent.")


class ReplyOut(BaseModel):
    id: str
    email_id: str
    to_address: str
    subject: str
    body: str
    status: ReplyStatus
    error: ReplyError | None
    created_at: datetime
    sent_at: datetime | None


class TryIn(BaseModel):
    """A draft config the owner has not saved, to try on one email."""

    config: WorkspaceConfig


class TryOut(BaseModel):
    """What Herald would do with the email under the draft. Nothing was saved."""

    status: EmailStatus
    notes: Notes | None
    decision: Decision


class MailboxOut(BaseModel):
    """A connected mailbox. Never carries credentials, the cursor or provider state."""

    id: str
    workspace_id: str
    provider: str
    email_address: str
    status: MailboxStatus
    can_send: bool
    read_spam: bool
    subscription_expires_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime


class ConnectIn(BaseModel):
    read_spam: bool | None = Field(
        default=None,
        description="Read the Spam folder too. Leave it out on a reconnect to keep the "
        "mailbox's current choice.",
    )


class ConnectOut(BaseModel):
    authorization_url: str


class MailboxPatch(BaseModel):
    read_spam: bool
