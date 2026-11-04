"""Types for the history tools the agent can call, and the record of what it looked up.

Tool inputs forbid extra fields and carry no workspace or email id: the server binds both
when it builds the toolbox, so the model cannot ask about another tenant.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from herald_core.schema import AiFailure, Urgency

SENDER_HISTORY = "sender_history"
THREAD = "thread"
RECENT_CORRECTIONS = "recent_corrections"


class SenderHistoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str
    days: int = Field(30, ge=1, le=90)
    limit: int = Field(5, ge=1, le=5)


class PastEmail(BaseModel):
    id: str
    received_at: datetime
    subject: str
    topic: str | None
    urgency: Urgency | None
    status: str
    summary: str | None


class SenderHistory(BaseModel):
    first_seen: datetime | None
    count_7d: int
    count_30d: int
    top_topics: list[str]
    recent: list[PastEmail]
    # When the current email arrived: the counts and `recent` are relative to it. decide needs
    # it to tell which recent emails fall in the last 7 days. None in data saved before it.
    as_of: datetime | None = None


class ThreadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    limit: int = Field(5, ge=1, le=5)


class ThreadMessage(BaseModel):
    id: str
    sender: str
    received_at: datetime
    body: str
    from_owner: bool = False  # True for a reply the owner sent; `sender` is then their mailbox.


class Thread(BaseModel):
    messages: list[ThreadMessage]


class CorrectionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(5, ge=1, le=5)


class CorrectionExample(BaseModel):
    id: str
    subject: str
    summary: str | None
    field: str
    from_value: str | None
    to_value: str


class Corrections(BaseModel):
    items: list[CorrectionExample]


class History(BaseModel):
    sender: SenderHistory | None = None
    thread: Thread | None = None
    corrections: Corrections | None = None

    def is_empty(self) -> bool:
        return (
            (self.sender is None or self.sender.first_seen is None)
            and not (self.thread and self.thread.messages)
            and not (self.corrections and self.corrections.items)
        )


class EmailContext(BaseModel):
    """What triage looked up for one email: counts, the ids it fetched, the tools the model
    chose to call, failures and timings. The sender's ids reached the model only when `asked`
    holds a sender_history call."""

    repeat_7d: int = 0
    repeat_30d: int = 0
    recent_ids: list[str] = Field(default_factory=list)
    thread_ids: list[str] = Field(default_factory=list)
    correction_ids: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    ms: dict[str, int] = Field(default_factory=dict)
    # "node:tool" for each model tool call, e.g. "write_notes:sender_history".
    asked: list[str] = Field(default_factory=list)
    # Model calls that gave no answer, and why. Empty when the AI answered both.
    ai_failures: list[AiFailure] = Field(default_factory=list)

    @classmethod
    def from_run(
        cls,
        history: History,
        failed: list[str],
        ms: dict[str, int],
        asked: list[str] | None = None,
        ai_failures: list[AiFailure] | None = None,
    ) -> "EmailContext":
        sender, thread, corrections = history.sender, history.thread, history.corrections
        return cls(
            repeat_7d=sender.count_7d if sender else 0,
            repeat_30d=sender.count_30d if sender else 0,
            recent_ids=[e.id for e in sender.recent] if sender else [],
            thread_ids=[m.id for m in thread.messages] if thread else [],
            correction_ids=[c.id for c in corrections.items] if corrections else [],
            failed=failed,
            ms=ms,
            asked=asked or [],
            ai_failures=ai_failures or [],
        )
