"""What the pipeline loads before triage and saves after it. The history tools use core types."""

from pydantic import BaseModel

from herald_core.history import EmailContext
from herald_core.schema import Decision, Email, Notes, WorkspaceConfig


class TriageInput(BaseModel):
    email: Email
    business_name: str
    config: WorkspaceConfig


class TriageResult(BaseModel):
    notes: Notes | None
    decision: Decision
    context: EmailContext
