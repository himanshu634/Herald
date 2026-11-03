"""Types shared by every Herald tenant.

The business itself lives in `WorkspaceConfig` (data), never in code. `Notes` is what the AI
writes about an email; it has no status field on purpose: only the decide step and the
owner's own actions move an email's status.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

SPAM_TOPIC = "Spam or not for me"


class Urgency(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


URGENCY_RANK = {Urgency.LOW: 0, Urgency.NORMAL: 1, Urgency.HIGH: 2, Urgency.URGENT: 3}


class RiskFlag(StrEnum):
    SAFETY = "safety"
    ACCOUNT_OR_DATA = "account_or_data"
    LEGAL_THREAT = "legal_threat"
    ABOUT_TO_CANCEL = "about_to_cancel"


# The safety floor: these always alert, and no owner rule can switch them off.
FLOOR_FLAGS = frozenset({RiskFlag.SAFETY, RiskFlag.ACCOUNT_OR_DATA, RiskFlag.LEGAL_THREAT})


class RuleAction(StrEnum):
    ALERT = "alert"
    SET_URGENCY = "set_urgency"
    CLOSE = "close"


class Rule(BaseModel):
    id: str
    name: str
    when: str = Field(description="Plain-language condition the AI judges, yes or no.")
    action: RuleAction
    urgency: Urgency | None = Field(default=None, description="Used by set_urgency only.")


class WorkspaceConfig(BaseModel):
    """Everything Herald knows about one business."""

    business_profile: str
    topics: list[str]
    important_contacts: list[str] = Field(
        default_factory=list, description="Email addresses or domains such as bigclient.com."
    )
    rules: list[Rule] = Field(default_factory=list)

    def is_important(self, sender: str) -> bool:
        sender = sender.lower()
        domain = sender.rsplit("@", 1)[-1]
        return any(c.lower() in (sender, domain) for c in self.important_contacts)


class Email(BaseModel):
    id: str
    workspace_id: str
    sender: str
    subject: str
    body: str


class Quote(BaseModel):
    note: str = Field(description="Which note this line supports, e.g. urgency or anger.")
    text: str = Field(description="The exact line from the email.")


class Notes(BaseModel):
    topic: str
    urgency: Urgency
    anger: Annotated[int, Field(ge=1, le=5)]
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    summary: str
    quotes: list[Quote] = Field(default_factory=list)
    sure: bool = Field(description="False when the AI is not confident in these notes.")


class RuleVerdict(BaseModel):
    rule_id: str
    matched: bool
    quote: str | None = Field(default=None, description="The line that decided the answer.")


class Route(StrEnum):
    ALERT = "alert"
    NEEDS_A_LOOK = "needs_a_look"
    INBOX = "inbox"
    CLOSED = "closed"


class Decision(BaseModel):
    route: Route
    urgency: Urgency | None
    reason: str
    fired_rule_ids: list[str] = Field(default_factory=list)
    floor_flags: list[RiskFlag] = Field(default_factory=list)
