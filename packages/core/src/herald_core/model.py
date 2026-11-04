"""The AI behind the notes and the judgement rules.

`TriageModel` is the plug-in point. Models come from providers (`herald_core.providers`): each
subclasses `ProviderModel` and adds one structured call to its API, which lets the model call
the model tools first. Tests use a scripted double from `tests_support/`, never a model in
shipped code.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from herald_core.history import History
from herald_core.prompt import RULES_ASK, SETUP_INSTRUCTIONS, system_prompt, user_message
from herald_core.schema import (
    AiFailure,
    Email,
    FailureKind,
    Notes,
    RuleVerdict,
    SetupDraft,
    WorkspaceConfig,
)
from herald_core.tools import ModelTool

# Rounds of tool calls before the model must answer. The one tool takes no input, so a second
# round could only repeat the first. Each round is a full model call before decide runs.
MAX_TOOL_ROUNDS = 1

# Seconds per request, and quick retries inside one call. The worker's job timeout is 300 s and
# arq never retries a job it timed out, so the SDK defaults (600 s, 2 retries) could strand an
# email as "new". Triage takes under 10 s in the evals. One retry absorbs a dropped connection;
# a longer outage is retried by the worker minutes later instead of held open here.
REQUEST_TIMEOUT = 30.0
REQUEST_RETRIES = 1
# Seconds for one model node, tool round and retry included. It also cuts short a long
# retry-after the SDK would otherwise sleep through, and keeps the job well inside 300 s.
MODEL_DEADLINE = 90.0
# Seconds per request for the setup draft. It runs in the owner's request, not a worker job,
# and writes a whole setup, so it gets longer than triage before falling back.
SETUP_TIMEOUT = 120.0


class ModelError(Exception):
    """The model could not produce notes; the email goes to "Needs a look"."""

    def __init__(self, message: str, kind: FailureKind = FailureKind.UNREADABLE) -> None:
        super().__init__(message)
        self.kind = kind


class ModelUnavailable(ModelError):
    """The AI was down or busy, and a later try may work. The worker queues the email again."""

    def __init__(self, failure: AiFailure) -> None:
        super().__init__(f"{failure.call}: {failure.error}", FailureKind.UNAVAILABLE)
        self.failure = failure


def status_kind(status: int) -> FailureKind:
    """Sorts an HTTP error status by what trying again can fix. Providers call it for their
    SDK's status errors, so every provider sorts the same way."""
    # 408 timeout, 409 conflict, 429 rate limit, and any 5xx (529 overloaded included).
    if status in (408, 409, 429) or status >= 500:
        return FailureKind.UNAVAILABLE
    # 401 key, 402 billing or credits, 403 permission, 404 model.
    if status in (401, 402, 403, 404):
        return FailureKind.SETUP
    return FailureKind.UNREADABLE


def failure_kind(exc: BaseException) -> FailureKind:
    """Sorts an error by what trying again can fix. Providers sort their SDK errors into a
    ModelError's kind; what is left is a node deadline (TimeoutError) or a bug. Anything
    unknown is not retried: a bug in Herald fails the same way every time, and retrying it
    would only delay the email."""
    if isinstance(exc, ModelError):
        return exc.kind
    if isinstance(exc, TimeoutError):
        return FailureKind.UNAVAILABLE
    return FailureKind.UNREADABLE


def _retry_after(exc: BaseException) -> float | None:
    # Both SDKs put the HTTP response on their status errors.
    response = getattr(exc, "response", None)
    if response is None:
        return None
    # Seconds only; the HTTP-date form is rare here and the worker's backoff covers it.
    try:
        seconds = float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def failure_of(call: str, exc: BaseException) -> AiFailure:
    # A ModelError wraps the SDK error, so look through it for the retry-after and request id.
    cause = exc.__cause__ if isinstance(exc, ModelError) and exc.__cause__ else exc
    return AiFailure(
        call=call,
        kind=failure_kind(exc),
        error=type(cause).__name__,
        retry_after=_retry_after(cause),
        request_id=getattr(cause, "request_id", None),
    )


class TriageModel(Protocol):
    async def write_notes(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> Notes: ...

    async def judge_rules(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> list[RuleVerdict]: ...

    async def suggest_setup(self, name: str, description: str) -> SetupDraft: ...


class Verdicts(BaseModel):
    """The rules call's answer."""

    # Matched rules only. Writing a "no" and a quote for every rule was most of the call's
    # output tokens, and so most of its time; decide reads only the matches, and a missing
    # rule is a "no".
    verdicts: list[RuleVerdict] = Field(description="Only the rules the email meets.")


class ProviderModel(ABC):
    """A `TriageModel` built from one structured API call. The prompts are the same for every
    provider; a provider only says how to make the call."""

    @abstractmethod
    async def _parse[T: BaseModel](
        self,
        system: str,
        content: str,
        output: type[T],
        tools: Sequence[ModelTool] = (),
        request_timeout: float | None = None,
    ) -> T:
        """One answer in the `output` schema, after at most MAX_TOOL_ROUNDS rounds of tool
        calls. Raises ModelError, with its kind sorted, when there is no answer."""

    async def write_notes(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> Notes:
        content = user_message(email, config.is_important(email.sender), history or History())
        return await self._parse(system_prompt(business_name, config), content, Notes, tools)

    async def judge_rules(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> list[RuleVerdict]:
        if not config.rules:
            return []
        block = user_message(email, config.is_important(email.sender), history or History())
        content = f"{block}\n\n{RULES_ASK}"
        system = system_prompt(business_name, config)
        return (await self._parse(system, content, Verdicts, tools)).verdicts

    async def suggest_setup(self, name: str, description: str) -> SetupDraft:
        content = f"<business>\nName: {name}\n\n{description}\n</business>"
        return await self._parse(
            SETUP_INSTRUCTIONS, content, SetupDraft, request_timeout=SETUP_TIMEOUT
        )
