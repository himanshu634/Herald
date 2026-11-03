"""Types shared by every Herald tenant.

The business itself lives in `WorkspaceConfig` (data), never in code. `Notes` is what the AI
writes about an email; it has no status field on purpose: only the decide step and the
owner's own actions move an email's status.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

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


TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
TopicMeaning = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
FactLine = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
GuidanceLine = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class Topic(BaseModel):
    name: TopicName
    meaning: TopicMeaning | None = None

    @field_validator("meaning")
    @classmethod
    def _blank_meaning_is_none(cls, value: str | None) -> str | None:
        return value or None


class Rule(BaseModel):
    id: str
    name: str
    when: str = Field(description="Plain-language condition the AI judges, yes or no.")
    action: RuleAction
    urgency: Urgency | None = Field(default=None, description="Used by set_urgency only.")

    @model_validator(mode="after")
    def _urgency_for_set_urgency(self) -> "Rule":
        # decide ignores a set_urgency rule with no urgency, so it would match and do nothing.
        if self.action is RuleAction.SET_URGENCY and self.urgency is None:
            raise ValueError("A set_urgency rule needs an urgency")
        return self


class WorkspaceConfig(BaseModel):
    """Everything Herald knows about one business."""

    business_profile: str = Field(min_length=1, max_length=2000)
    # At least one: the fake model and the notes prompt both fall back to the first topic.
    topics: list[Topic] = Field(min_length=1, max_length=12)
    facts: list[FactLine] = Field(
        default_factory=list, max_length=10, description="Short facts about the brand."
    )
    important_contacts: list[str] = Field(
        default_factory=list, description="Email addresses or domains such as bigclient.com."
    )
    guidance: list[GuidanceLine] = Field(
        default_factory=list,
        max_length=8,
        description="The owner's own lines on how to read topic, urgency and anger.",
    )
    rules: list[Rule] = Field(default_factory=list, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def _plain_string_topics(cls, data):
        # Keeps configs saved before topic meanings loading, with no migration.
        if isinstance(data, dict) and isinstance(data.get("topics"), list):
            data = data | {
                "topics": [{"name": t} if isinstance(t, str) else t for t in data["topics"]]
            }
        return data

    @model_validator(mode="after")
    def _unique_topic_names(self) -> "WorkspaceConfig":
        names = [t.name.lower() for t in self.topics]
        if len(names) != len(set(names)):
            raise ValueError("Topic names must be unique")
        return self

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> "WorkspaceConfig":
        # Verdicts are matched to rules by id; two rules with one id would share a verdict.
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule ids must be unique")
        return self

    def topic_names(self) -> list[str]:
        return [t.name for t in self.topics]

    def is_important(self, sender: str) -> bool:
        sender = sender.lower()
        domain = sender.rsplit("@", 1)[-1]
        return any(c.lower() in (sender, domain) for c in self.important_contacts)


class RuleDraft(BaseModel):
    """A rule the AI suggests at setup. It has no id: the server assigns unique ones."""

    name: str
    when: str
    action: RuleAction
    urgency: Urgency | None = None


class TopicDraft(BaseModel):
    """A topic the AI suggests at setup, with a one-line meaning."""

    name: str
    meaning: str


class SetupDraft(BaseModel):
    """The AI's first guess at a business's setup, read from its description."""

    topics: list[TopicDraft]
    facts: list[str]
    guidance: list[str]
    rules: list[RuleDraft]


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
