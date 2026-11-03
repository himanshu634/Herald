"""Plug-in points that each deployment implements: where alerts go.

The AI provider plug-in point is `herald_core.model.TriageModel`.
"""

from typing import Protocol

from pydantic import BaseModel


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
