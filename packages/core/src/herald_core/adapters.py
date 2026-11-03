"""Plug-in points that each deployment implements: where emails come from, where alerts go.

The AI provider plug-in point is `herald_core.model.TriageModel`.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from herald_core.schema import Email


class Alert(BaseModel):
    workspace_id: str
    email_id: str
    title: str
    summary: str
    reason: str
    quote: str | None = None
    link: str | None = None


class Notifier(Protocol):
    async def send(self, alert: Alert) -> None: ...


class EmailSource(Protocol):
    """A real inbox (Gmail, Outlook) later; the test-email box needs no source."""

    def poll(self, workspace_id: str) -> AsyncIterator[Email]: ...
