"""Test emails with known answers, read from TOML files.

One file holds one business: its name, its config and its cases. A config is either a
`module:NAME` reference (Tripfold points at the seed, so the eval always measures the config
the product ships) or an inline `[config]` table for an eval-only business.

A label lists only what the case is about. Anything left out is not scored, so a case about
a rule does not also fail on a debatable anger score.
"""

import hashlib
import importlib
import tomllib
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from herald_core.history import (
    CorrectionExample,
    Corrections,
    History,
    PastEmail,
    SenderHistory,
    Thread,
    ThreadMessage,
)
from herald_core.schema import (
    FLOOR_FLAGS,
    SPAM_TOPIC,
    Email,
    RiskFlag,
    Route,
    Urgency,
    WorkspaceConfig,
)

DATASETS = files("herald_evals").joinpath("datasets")


def _as_list(value):
    # A label can be one value ("alert") or any of several (["inbox", "needs_a_look"]).
    return value if isinstance(value, list) else [value]


Routes = Annotated[list[Route], BeforeValidator(_as_list), Field(min_length=1)]
Topics = Annotated[list[str], BeforeValidator(_as_list), Field(min_length=1)]
Urgencies = Annotated[list[Urgency], BeforeValidator(_as_list), Field(min_length=1)]


def _anger_range(value):
    return [value, value] if isinstance(value, int) else value


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Routes
    topic: Topics | None = None
    urgency: Urgencies | None = None
    anger: Annotated[tuple[int, int], BeforeValidator(_anger_range)] | None = None
    # Flags the AI must add, and flags neither the AI nor the word check may raise.
    flags: list[RiskFlag] = Field(default_factory=list)
    no_flags: list[RiskFlag] = Field(default_factory=list)
    # Only the rules listed here are scored; a missing verdict counts as "no".
    rules: dict[str, bool] = Field(default_factory=dict)

    @property
    def should_alert(self) -> bool | None:
        """True or False when the label is clear, None when more than one route is fine."""
        if self.route == [Route.ALERT]:
            return True
        if Route.ALERT not in self.route:
            return False
        return None

    @property
    def floor(self) -> set[RiskFlag]:
        return set(self.flags) & FLOOR_FLAGS


class PastEmailSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days_ago: float
    subject: str
    topic: str | None = None
    urgency: Urgency | None = None
    status: str = "inbox"
    summary: str | None = None


class SenderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_seen_days_ago: float
    count_7d: int
    count_30d: int
    top_topics: list[str] = Field(default_factory=list)
    recent: list[PastEmailSpec] = Field(default_factory=list)


class ThreadMessageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str
    days_ago: float
    body: str


class CorrectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    summary: str | None = None
    field: str = "status"
    from_value: str | None = None
    to_value: str


class HistorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: SenderSpec | None = None
    thread: list[ThreadMessageSpec] = Field(default_factory=list)
    corrections: list[CorrectionSpec] = Field(default_factory=list)

    def build(self, case_id: str, now: datetime) -> History:
        def ago(days: float) -> datetime:
            return now - timedelta(days=days)

        sender = None
        if self.sender:
            s = self.sender
            sender = SenderHistory(
                first_seen=ago(s.first_seen_days_ago),
                as_of=now,
                count_7d=s.count_7d,
                count_30d=s.count_30d,
                top_topics=s.top_topics,
                recent=[
                    PastEmail(
                        id=f"{case_id}-past-{i}",
                        received_at=ago(p.days_ago),
                        subject=p.subject,
                        topic=p.topic,
                        urgency=p.urgency,
                        status=p.status,
                        summary=p.summary,
                    )
                    for i, p in enumerate(s.recent)
                ],
            )
        thread = None
        if self.thread:
            thread = Thread(
                messages=[
                    ThreadMessage(
                        id=f"{case_id}-msg-{i}",
                        sender=m.sender,
                        received_at=ago(m.days_ago),
                        body=m.body,
                    )
                    for i, m in enumerate(self.thread)
                ]
            )
        corrections = None
        if self.corrections:
            corrections = Corrections(
                items=[
                    CorrectionExample(
                        id=f"{case_id}-fix-{i}",
                        subject=c.subject,
                        summary=c.summary,
                        field=c.field,
                        from_value=c.from_value,
                        to_value=c.to_value,
                    )
                    for i, c in enumerate(self.corrections)
                ]
            )
        return History(sender=sender, thread=thread, corrections=corrections)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    # False until a person has read the email and agreed with its label. Cases drafted with
    # an AI's help start False, so the AI is not marking its own homework.
    reviewed: bool = False
    tags: list[str] = Field(default_factory=list)
    note: str = ""
    sender: str
    subject: str
    body: str
    expect: Expect
    history: HistorySpec | None = None

    def email(self, workspace_id: str) -> Email:
        # The graph asks for the thread only when the email has a thread id.
        thread_id = f"{self.id}-thread" if self.history and self.history.thread else None
        return Email(
            id=self.id,
            workspace_id=workspace_id,
            sender=self.sender,
            subject=self.subject,
            body=self.body,
            thread_id=thread_id,
        )


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    business: str
    config_ref: str | None = None
    config: WorkspaceConfig
    cases: list[Case]

    @model_validator(mode="after")
    def _labels_match_config(self) -> "Dataset":
        # A label that names a rule or topic the config does not have can never pass, and
        # would quietly score as a model failure.
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.name}: case ids must be unique")
        rule_ids = {r.id for r in self.config.rules}
        topics = {t.name for t in self.config.topics} | {SPAM_TOPIC}
        for case in self.cases:
            if unknown := set(case.expect.rules) - rule_ids:
                raise ValueError(f"{self.name}/{case.id}: unknown rules {sorted(unknown)}")
            if unknown := set(case.expect.topic or []) - topics:
                raise ValueError(f"{self.name}/{case.id}: unknown topics {sorted(unknown)}")
        return self

    def config_hash(self) -> str:
        return hashlib.sha256(self.config.model_dump_json().encode()).hexdigest()[:12]


def _load_config(raw: dict) -> tuple[WorkspaceConfig, str | None]:
    ref = raw.pop("config_ref", None)
    if ref:
        module, _, attr = ref.partition(":")
        config = getattr(importlib.import_module(module), attr)
        if not isinstance(config, WorkspaceConfig):
            raise TypeError(f"{ref} is not a WorkspaceConfig")
        return config, ref
    return WorkspaceConfig.model_validate(raw.pop("config")), None


def load(path: Path, name: str | None = None) -> Dataset:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    config, ref = _load_config(raw)
    return Dataset(
        name=name or path.stem,
        business=raw.pop("business"),
        config_ref=ref,
        config=config,
        cases=raw.pop("cases", []),
        **raw,
    )


def builtin_names() -> list[str]:
    return sorted(
        p.name.removesuffix(".toml") for p in DATASETS.iterdir() if p.name.endswith(".toml")
    )


def load_named(name_or_path: str) -> Dataset:
    """A built-in dataset by name ("tripfold"), or any TOML file by path."""
    path = Path(name_or_path)
    if path.suffix == ".toml" and path.exists():
        return load(path)
    builtin = DATASETS.joinpath(f"{name_or_path}.toml")
    if not builtin.is_file():
        raise SystemExit(f"No dataset {name_or_path!r}. Built in: {', '.join(builtin_names())}")
    return load(Path(str(builtin)), name_or_path)
