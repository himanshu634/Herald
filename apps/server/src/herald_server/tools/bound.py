"""The scope every history tool shares. Each query is read-only and stays in the bound workspace."""

from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import select

from herald_server.models import Email


class Bound:
    """The scope every query shares. The model never supplies any of these values."""

    def __init__(self, engine: Engine, workspace_id: str, email_id: str, before: datetime) -> None:
        self.engine = engine
        self.workspace_id = workspace_id
        self.email_id = email_id
        self.before = before

    def _scope(self) -> tuple:
        # Same workspace, never the email being judged (compared by id, since two emails can
        # share a timestamp), and nothing received after it. `<=` plus the id check means two
        # emails with equal timestamps each see the other but never themselves.
        return (
            Email.workspace_id == self.workspace_id,
            Email.id != self.email_id,
            Email.received_at <= self.before,
        )

    def earlier_emails(self):
        return select(Email).where(*self._scope())
