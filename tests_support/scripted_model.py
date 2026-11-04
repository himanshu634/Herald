"""A test double for `TriageModel`: it returns what a test scripts and guesses nothing.

Each argument may be a value, a callable, or an exception instance to raise. Notes and verdicts
callables get `(email, config)`; the setup callable gets `(name, description)`.
"""

from collections.abc import Callable, Sequence
from typing import Any

from herald_core.history import History
from herald_core.model_tools import ModelTool
from herald_core.schema import (
    Email,
    Notes,
    RuleAction,
    RuleDraft,
    RuleVerdict,
    SetupDraft,
    TopicDraft,
    Urgency,
    WorkspaceConfig,
)

DEFAULT_SETUP = SetupDraft(
    topics=[TopicDraft(name="Questions", meaning="Anything that fits no other topic")],
    facts=[],
    guidance=["Customers who mention a deadline in the next two days are urgent."],
    rules=[
        RuleDraft(
            name="About to cancel",
            when="The customer says they will cancel or leave",
            action=RuleAction.ALERT,
        )
    ],
)


def plain_notes(email: Email, config: WorkspaceConfig, **overrides: Any) -> Notes:
    """Calm, sure notes on the config's first topic. Tests override what they care about."""
    fields: dict[str, Any] = {
        "topic": config.topics[0].name,
        "urgency": Urgency.NORMAL,
        "anger": 1,
        "summary": email.subject[:120],
        "sure": True,
    }
    return Notes(**(fields | overrides))


class ScriptedModel:
    def __init__(
        self,
        notes: Notes | Callable[[Email, WorkspaceConfig], Notes] | Exception | None = None,
        verdicts: list[RuleVerdict]
        | Callable[[Email, WorkspaceConfig], list[RuleVerdict]]
        | Exception
        | None = None,
        setup: SetupDraft | Callable[[str, str], SetupDraft] | Exception | None = None,
    ) -> None:
        self.notes = notes if notes is not None else plain_notes
        self.verdicts = verdicts if verdicts is not None else []
        self.setup = setup if setup is not None else DEFAULT_SETUP
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def _answer(scripted: Any, *args: Any) -> Any:
        if isinstance(scripted, Exception):
            raise scripted
        return scripted(*args) if callable(scripted) else scripted

    async def write_notes(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> Notes:
        self.calls.append(
            (
                "write_notes",
                {
                    "email": email,
                    "business_name": business_name,
                    "config": config,
                    "history": history,
                    "tools": tools,
                },
            )
        )
        return self._answer(self.notes, email, config)

    async def judge_rules(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> list[RuleVerdict]:
        self.calls.append(
            (
                "judge_rules",
                {
                    "email": email,
                    "business_name": business_name,
                    "config": config,
                    "history": history,
                    "tools": tools,
                },
            )
        )
        return self._answer(self.verdicts, email, config)

    async def suggest_setup(self, name: str, description: str) -> SetupDraft:
        self.calls.append(("suggest_setup", {"name": name, "description": description}))
        return self._answer(self.setup, name, description)
