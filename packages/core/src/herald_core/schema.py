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
        # Keeps configs saved before topic meanings loading, with no migration. Old data could
        # hold names that differ only by case. Drop the repeats so stored configs still load;
        # object topics skip this and keep the strict unique-name error.
        if isinstance(data, dict) and isinstance(data.get("topics"), list):
            topics, seen = [], set()
            for t in data["topics"]:
                if isinstance(t, str):
                    key = t.strip().lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    t = {"name": t}
                topics.append(t)
            data = data | {"topics": topics}
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
    thread_id: str | None = None
    # The mail provider filed it as spam. Only read when the owner chose to read Spam too.
    in_spam: bool = False


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
    question: str | None = Field(
        default=None,
        description="When unsure: the one question the owner could answer to settle it.",
    )
    fact_draft: str | None = Field(
        default=None,
        description="When unsure: a fact that would settle it, for the owner to check.",
    )

    @model_validator(mode="after")
    def _question_only_when_unsure(self) -> "Notes":
        # A sure note carries no question, so nothing asks the owner about it.
        if self.sure:
            self.question = self.fact_draft = None
        # Trimmed, not rejected: a too-long line from the model must not throw away the notes.
        # The draft is cut to a fact's limit so the owner can save it as it stands.
        if self.question:
            self.question = self.question.strip()[:300] or None
        if self.fact_draft:
            self.fact_draft = self.fact_draft.strip()[:200] or None
        return self


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


class FailureKind(StrEnum):
    """Why a model call gave no answer, sorted by what trying again can fix."""

    # Down, busy, rate limited, slow or unreachable. A later try may work.
    UNAVAILABLE = "unavailable"
    # Herald's own key, model name or billing. Every email fails the same way until fixed.
    SETUP = "setup"
    # This request: refused, malformed, too large or answered badly. A retry fails again.
    UNREADABLE = "unreadable"


class AiFailure(BaseModel):
    """One model call that gave no answer. Saved with the email, so "the AI was down" and
    "the AI could not read it" stay apart in the app, the logs and the evals."""

    call: str
    kind: FailureKind
    # The exception's class name, never its message: a message can quote the request.
    error: str
    # Seconds the API asked us to wait (429, 529), when it said.
    retry_after: float | None = None
    request_id: str | None = None


class Alert(BaseModel):
    """What an email raises when `decide` routes it to "alert". SSE sends it as `alert.sent`."""

    workspace_id: str
    email_id: str
    title: str
    summary: str
    reason: str
    quote: str | None = None
    link: str | None = None
