"""The alert an email raises when `decide` routes it to "alert". SSE sends it as `alert.sent`."""

from pydantic import BaseModel


class Alert(BaseModel):
    workspace_id: str
    email_id: str
    title: str
    summary: str
    reason: str
    quote: str | None = None
    link: str | None = None
